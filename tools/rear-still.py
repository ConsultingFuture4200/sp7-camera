"""Capture one full-resolution still straight from libcamera (no loopback).
Skips frames so auto-exposure settles, then writes RGB + a downscaled preview."""
import sys, gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst, GLib
Gst.init(None)
SKIP = int(sys.argv[1]) if len(sys.argv) > 1 else 150
pipe = Gst.parse_launch(
    'libcamerasrc name=src ! videoconvert ! video/x-raw,format=RGB '
    '! appsink name=sink emit-signals=true max-buffers=2 drop=true sync=false')
pipe.get_by_name('src').set_property('camera-name', r'\_SB_.PCI0.I2C3.CAMR')
state = {'n': 0, 'saved': False}
loop = GLib.MainLoop()
def on_sample(sink):
    s = sink.emit('pull-sample')
    if not s or state['saved']:
        return Gst.FlowReturn.OK
    state['n'] += 1
    if state['n'] < SKIP:
        return Gst.FlowReturn.OK
    caps = s.get_caps().get_structure(0)
    w, h = caps.get_value('width'), caps.get_value('height')
    ok, mi = s.get_buffer().map(Gst.MapFlags.READ)
    if ok:
        open('caps/still.rgb', 'wb').write(mi.data)
        open('caps/still.dim', 'w').write(f'{w} {h}')
        s.get_buffer().unmap(mi)
        state['saved'] = True
        print(f'  captured {w}x{h} after {state["n"]} frames', flush=True)
    loop.quit()
    return Gst.FlowReturn.OK
pipe.get_by_name('sink').connect('new-sample', on_sample)
bus = pipe.get_bus(); bus.add_signal_watch()
bus.connect('message', lambda b, m: loop.quit() if m.type == Gst.MessageType.ERROR else None)
pipe.set_state(Gst.State.PLAYING)
GLib.timeout_add_seconds(45, loop.quit)
loop.run()
pipe.set_state(Gst.State.NULL)
