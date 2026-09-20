#!/usr/bin/python3
"""On-demand relay: Surface Pro 7 rear camera -> v4l2loopback webcam.

The camera runs only while an application is actually streaming from
/dev/video60, and stops a few seconds after the last one stops.

Design follows v4l2-relayd (https://gitlab.com/vicamo/v4l2-relayd):
  * an OUTPUT pipeline (appsrc -> v4l2sink) stays PLAYING permanently so the
    loopback keeps announcing a capture device (exclusive_caps=1); it is fed
    black frames while idle
  * an INPUT pipeline (libcamera -> crop 16:9 -> scale -> appsink) is created
    when v4l2loopback reports a streaming client, and torn down when it
    reports none
  * v4l2loopback raises V4L2_EVENT_PRI_CLIENT_USAGE on STREAMON/STREAMOFF of
    the capture side (not on open, so device probes do not start the camera)

Additions over v4l2-relayd:
  * the camera is chosen by setting libcamerasrc's camera-name property, not via
    a gst-launch string: the ACPI name contains a backslash, and if quoting
    fails libcamerasrc would silently open the FRONT camera, whose failed
    D-PHY lock can wedge the IPU4 isys power island
  * a stop grace period, so format renegotiation does not bounce the camera
  * v4l2loopback's close() path does not raise the usage event, so while the
    camera is on we re-subscribe periodically; subscribing always delivers the
    current state
  * camera buffers have their timestamps cleared before hand-off; libcamera's
    capture timestamps otherwise throttle delivery to a few fps
  * if PipeWire has no node for the loopback (it was probed before this relay
    started feeding it), WirePlumber is restarted once
"""
import fcntl, json, os, signal, struct, subprocess, sys, time
import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst, GLib
try:                                    # PyGObject >= 3.52 moved these
    gi.require_version('GLibUnix', '2.0')
    from gi.repository import GLibUnix
    _signal_add = getattr(GLibUnix, 'signal_add', None) or getattr(GLibUnix, 'signal_add_full')
    _fd_add = getattr(GLibUnix, 'fd_add_full', None) or GLib.unix_fd_add_full
except (ValueError, ImportError, AttributeError):
    _signal_add = GLib.unix_signal_add
    _fd_add = GLib.unix_fd_add_full

CAMERA = r'\_SB_.PCI0.I2C3.CAMR'                       # REAR camera only
DEV = os.environ.get('SP7_LOOPBACK', '/dev/video60')
SW = int(os.environ.get('SP7_SENSOR_W', 3200)); SH = int(os.environ.get('SP7_SENSOR_H', 2400))
OW = int(os.environ.get('SP7_OUT_W', 1280));    OH = int(os.environ.get('SP7_OUT_H', 720))
STOP_GRACE_S, RESYNC_S, MAX_START_RETRIES = 3, 10, 3
# gamma 1.5 looked best on a bright scene (median 173->131) but crushed a dim
# one (117->63): the AGC meters before the gamma curve, so gamma is a fixed
# offset. 1.8/1.1 is the compromise (bright ->~155, dim ->103).
TONE_GAMMA = float(os.environ.get('SP7_GAMMA', 1.8))
TONE_CONTRAST = float(os.environ.get('SP7_CONTRAST', 1.1))
TONE_SATURATION = float(os.environ.get('SP7_SATURATION', 1.4))
DEBUG = os.environ.get('SP7_RELAY_DEBUG') == '1'
SKIP_PW_CHECK = os.environ.get('SP7_SKIP_PW_CHECK') == '1'

# verified against /usr/include/linux/videodev2.h and v4l2loopback 0.15.4
V4L2_EVENT_PRI_CLIENT_USAGE = 0x10E00001
VIDIOC_SUBSCRIBE_EVENT      = 0x4020565A
VIDIOC_UNSUBSCRIBE_EVENT    = 0x4020565B
VIDIOC_DQEVENT              = 0x80885659
V4L2_EVENT_SUB_FL_SEND_INITIAL = 1
EVENT_SIZE, EVENT_U_OFF, EVENT_PENDING_OFF = 136, 8, 72

def log(msg):
    print(f'relay: {msg}', flush=True)

class Relay:
    def __init__(self):
        target_h = (SW * OH // OW) & ~1
        self.crop_tb = max(0, (SH - target_h) // 2) & ~1
        self.black = b'\x10\x80\x10\x80' * (OW * OH // 2)      # YUY2 black
        self.out = Gst.parse_launch(
            f'appsrc name=out is-live=true format=time do-timestamp=true '
            f'caps=video/x-raw,format=YUY2,width={OW},height={OH},framerate=30/1 '
            f'! videoconvert ! v4l2sink device={DEV} sync=false')
        self.appsrc = self.out.get_by_name('out')
        self.inp = None
        self.clients = 0
        self.stop_timer = self.resync_timer = 0
        self.retries = 0
        self.fd = -1
        self.loop = GLib.MainLoop()
        bus = self.out.get_bus(); bus.add_signal_watch(); bus.connect('message', self.on_out_msg)

    # ---- output side -------------------------------------------------------
    def push_black(self, n=2):
        for _ in range(n):
            self.appsrc.emit('push-buffer', Gst.Buffer.new_wrapped(self.black))

    def on_out_msg(self, bus, msg):
        if msg.type == Gst.MessageType.ERROR:
            err, dbg = msg.parse_error()
            log(f'output pipeline error: {err.message} ({dbg})'); self.loop.quit()

    # ---- input side --------------------------------------------------------
    def start_camera(self):
        if self.inp is not None:
            return
        self.inp = Gst.parse_launch(
            f'libcamerasrc name=src ! video/x-raw,width={SW},height={SH} ! videoconvert '
            f'! videocrop top={self.crop_tb} bottom={self.crop_tb} ! videoscale '
            f'! video/x-raw,format=YUY2,width={OW},height={OH} '
            # the ov8865 delivers a horizontally mirrored image (its subdev reports
            # horizontal_flip=1 and vertical_flip=1); un-mirror at 1280x720 where it's cheap
            f'! videoflip method=horizontal-flip '
            f'! appsink name=sink emit-signals=true max-buffers=2 drop=true sync=false')
        src = self.inp.get_by_name('src')
        src.set_property('camera-name', CAMERA)
        # Tone/colour shaping in the software ISP. Its AGC targets mid-histogram
        # with no EV control, which on a bright scene lands the median at ~173/255
        # and clips highlights; there is no real colour tuning for the ov8865.
        # Swept 2026-09-19: gamma 1.5 / contrast 1.2 / saturation 1.4 puts the
        # median at ~131, clipping at 0.3%, shadows intact (p5=21), saturation x1.8.
        # Saturation only exists when ipa/simple/ov8865.yaml (identity CCM) loads.
        for knob, val in (('gamma', TONE_GAMMA), ('contrast', TONE_CONTRAST), ('saturation', TONE_SATURATION)):
            try:
                src.set_property(knob, val)
            except TypeError as e:
                log(f'{knob} not settable: {e}')
        self.inp.get_by_name('sink').connect('new-sample', self.on_sample)
        bus = self.inp.get_bus(); bus.add_signal_watch(); bus.connect('message', self.on_in_msg)
        log(f'app streaming -> camera ON ({SW}x{SH} -> {OW}x{OH})')
        self.inp.set_state(Gst.State.PLAYING)
        if not self.resync_timer:
            self.resync_timer = GLib.timeout_add_seconds(RESYNC_S, self.resync)

    def stop_camera(self, reason):
        if self.inp is None:
            return
        self.inp.get_bus().remove_signal_watch()
        self.inp.set_state(Gst.State.NULL)
        self.inp = None
        if self.resync_timer:
            GLib.source_remove(self.resync_timer); self.resync_timer = 0
        self.push_black()
        log(f'{reason} -> camera OFF')

    def on_sample(self, sink):
        sample = sink.emit('pull-sample')
        if sample:
            self.retries = 0
            # libcamera's capture timestamps are on a different time base than the
            # output pipeline; left in place they throttle delivery through the
            # loopback to a few frames per second. A metadata-only copy (pixels
            # are shared) with timestamps cleared lets appsrc do-timestamp apply
            # the output pipeline's running time instead.
            buf = sample.get_buffer().copy()
            buf.pts = buf.dts = buf.duration = Gst.CLOCK_TIME_NONE
            ret = self.appsrc.emit('push-buffer', buf)
            if DEBUG:
                self.pushed = getattr(self, 'pushed', 0) + 1
                if self.pushed % 15 == 1 or ret != Gst.FlowReturn.OK:
                    log(f'debug: pushed {self.pushed} frames, push-buffer={ret.value_nick}, '
                        f'appsrc queued={self.appsrc.get_property("current-level-bytes")} bytes')
        return Gst.FlowReturn.OK

    def on_in_msg(self, bus, msg):
        if msg.type != Gst.MessageType.ERROR:
            return
        err, dbg = msg.parse_error()
        log(f'camera error: {err.message}')
        self.stop_camera('camera error')
        if self.clients > 0 and self.retries < MAX_START_RETRIES:
            self.retries += 1
            log(f'retrying camera start ({self.retries}/{MAX_START_RETRIES}) in 3s')
            GLib.timeout_add_seconds(3, lambda: (self.clients > 0 and self.start_camera(), False)[1])

    # ---- v4l2loopback client-usage events ----------------------------------
    def subscribe(self):
        sub = struct.pack('=III20x', V4L2_EVENT_PRI_CLIENT_USAGE, 0, V4L2_EVENT_SUB_FL_SEND_INITIAL)
        fcntl.ioctl(self.fd, VIDIOC_SUBSCRIBE_EVENT, sub)

    def resync(self):
        try:
            sub = struct.pack('=III20x', V4L2_EVENT_PRI_CLIENT_USAGE, 0, 0)
            fcntl.ioctl(self.fd, VIDIOC_UNSUBSCRIBE_EVENT, sub)
            self.subscribe()                    # queues the current usage state
        except OSError as e:
            log(f'resync failed: {e}')
        return True

    def on_event(self, fd, cond):
        while True:
            buf = bytearray(EVENT_SIZE)
            try:
                fcntl.ioctl(fd, VIDIOC_DQEVENT, buf)
            except OSError:
                break
            etype, = struct.unpack_from('=I', buf, 0)
            if etype == V4L2_EVENT_PRI_CLIENT_USAGE:
                self.on_usage(struct.unpack_from('=I', buf, EVENT_U_OFF)[0])
            if struct.unpack_from('=I', buf, EVENT_PENDING_OFF)[0] == 0:
                break
        return True

    def on_usage(self, count):
        if count == self.clients:
            return
        self.clients = count
        if count > 0:
            if self.stop_timer:
                GLib.source_remove(self.stop_timer); self.stop_timer = 0
            self.retries = 0
            self.start_camera()
        elif self.inp is not None and not self.stop_timer:
            self.stop_timer = GLib.timeout_add_seconds(STOP_GRACE_S, self.grace_expired)

    def grace_expired(self):
        self.stop_timer = 0
        if self.clients == 0:
            self.stop_camera('no app streaming')
        return False

    # ---- PipeWire visibility -----------------------------------------------
    def ensure_pipewire_node(self):
        try:
            objs = json.loads(subprocess.run(['pw-dump'], capture_output=True, text=True, timeout=10).stdout or '[]')
            # A Video/Device object alone is not enough: wireplumber creates the
            # Video/Source node only if the loopback reported capture caps when the
            # device was probed. Require the node.
            present = any((o.get('info') or {}).get('props', {}).get('api.v4l2.path') == DEV and
                          str((o.get('info') or {}).get('props', {}).get('media.class', '')).startswith('Video/Source')
                          for o in objs)
        except Exception as e:
            log(f'pw-dump failed: {e}'); return False
        if present:
            log(f'PipeWire has a node for {DEV}')
        else:
            log(f'PipeWire has no node for {DEV}; restarting WirePlumber once so it re-probes')
            subprocess.run(['systemctl', '--user', 'try-restart', 'wireplumber'])
        return False

    # ---- lifecycle ----------------------------------------------------------
    def run(self):
        waited = False
        while not os.path.exists(DEV):
            if not waited:
                log(f'waiting for {DEV} (created by sudo ~/loadcam)'); waited = True
            time.sleep(2)
        if self.out.set_state(Gst.State.PLAYING) == Gst.StateChangeReturn.FAILURE:
            log('output pipeline failed to start'); return 1
        self.push_black()
        self.fd = os.open(DEV, os.O_RDWR | os.O_NONBLOCK)
        self.subscribe()
        _fd_add(GLib.PRIORITY_DEFAULT, self.fd, GLib.IOCondition.PRI, self.on_event)
        for s in (signal.SIGINT, signal.SIGTERM):
            _signal_add(GLib.PRIORITY_DEFAULT, s, self.quit)
        if not SKIP_PW_CHECK:
            GLib.timeout_add_seconds(4, self.ensure_pipewire_node)
        log(f'idle, feeding {DEV}; camera starts when an app streams from it')
        self.loop.run()
        self.stop_camera('shutting down')
        self.out.set_state(Gst.State.NULL)
        os.close(self.fd)
        return 0

    def quit(self):
        self.loop.quit(); return False

if __name__ == '__main__':
    Gst.init(None)
    sys.exit(Relay().run())
