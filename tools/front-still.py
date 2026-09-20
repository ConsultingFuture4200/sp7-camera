"""Full-resolution front (ov5693) still via libcamera with the ov5693.yaml CCMs and
tone knobs. Writes caps/front-still.{rgb,dim} and a mirror-corrected PNG.
usage: [SIZE=WxH] front-still.py [skip_frames] [gamma] [contrast] [saturation] [prop=value ...]"""
import sys, gi, struct, zlib, time, os
gi.require_version('Gst', '1.0')
from gi.repository import Gst, GLib
os.environ.setdefault('LIBCAMERA_IPA_CONFIG_PATH', '/home/bobmob/Projects/sp7-camera/ipa')
Gst.init(None)
SKIP = int(sys.argv[1]) if len(sys.argv) > 1 else 120
knobs = dict(zip(('gamma', 'contrast', 'saturation'), map(float, sys.argv[2:5]))) if len(sys.argv) >= 5 else {}
for a in sys.argv[5:]:               # extra libcamerasrc properties, e.g. exposure-value=-1.5
    k, v = a.split('=', 1); knobs[k] = float(v) if v.replace('.', '', 1).replace('-', '', 1).isdigit() else v
SIZE = os.environ.get('SIZE', '')    # e.g. SIZE=2592x1944 to request the full sensor mode

pipe = Gst.parse_launch('libcamerasrc name=src ! videoconvert ! video/x-raw,format=RGB' 
                        + (',width=%s,height=%s' % tuple(SIZE.split('x')) if SIZE else '') + ' ! appsink name=sink emit-signals=true max-buffers=2 drop=true sync=false')
src = pipe.get_by_name('src'); src.set_property('camera-name', r'\_SB_.PCI0.I2C2.CAMF')
for k, v in knobs.items(): src.set_property(k, v)
st = {'n': 0, 'done': False, 't0': time.monotonic()}; loop = GLib.MainLoop()
def on_sample(sink):
    s = sink.emit('pull-sample')
    if not s or st['done']: return Gst.FlowReturn.OK
    st['n'] += 1
    if st['n'] < SKIP: return Gst.FlowReturn.OK
    c = s.get_caps().get_structure(0); w, h = c.get_value('width'), c.get_value('height')
    ok, mi = s.get_buffer().map(Gst.MapFlags.READ); d = bytes(mi.data); s.get_buffer().unmap(mi); st['done'] = True
    open('caps/front-still.rgb', 'wb').write(d); open('caps/front-still.dim', 'w').write(f'{w} {h}')
    stride = len(d)//h
    lum = sorted((d[y*stride+x*3]*299+d[y*stride+x*3+1]*587+d[y*stride+x*3+2]*114)//1000 for y in range(0, h, 9) for x in range(0, w, 9))
    p = lambda q: lum[int(len(lum)*q)]
    black = p(.5) == 0
    print(f"  {w}x{h} after {st['n']} frames in {time.monotonic()-st['t0']:.1f}s  luma p5={p(.05)} p50={p(.5)} p95={p(.95)}  "
          f"clipped={sum(1 for v in lum if v>=250)/len(lum)*100:.1f}%  {'** BLACK (lock failed) **' if black else 'real image'}", flush=True)
    if not black:
        W2, H2 = w//2, h//2; rows = bytearray()
        for oy in range(H2):
            rb = (oy*2)*stride; rows += b'\x00' + b''.join(d[rb+x*6: rb+x*6+3] for x in range(W2-1, -1, -1))   # un-mirror
        ch = lambda t, b: struct.pack('>I', len(b))+t+b+struct.pack('>I', zlib.crc32(t+b) & 0xffffffff)
        open('caps/front-still.png', 'wb').write(b'\x89PNG\r\n\x1a\n'+ch(b'IHDR', struct.pack('>IIBBBBB', W2, H2, 8, 2, 0, 0, 0))
                                                + ch(b'IDAT', zlib.compress(bytes(rows), 6))+ch(b'IEND', b''))
        print("  wrote caps/front-still.png (half size, mirror corrected)", flush=True)
    loop.quit(); return Gst.FlowReturn.OK
pipe.get_by_name('sink').connect('new-sample', on_sample)
pipe.get_bus().add_signal_watch(); pipe.get_bus().connect('message', lambda b, m: loop.quit() if m.type == Gst.MessageType.ERROR else None)
pipe.set_state(Gst.State.PLAYING); GLib.timeout_add_seconds(60, loop.quit); loop.run(); pipe.set_state(Gst.State.NULL)
if not st['done']: print(f"  NO FRAME in 60s (got {st['n']})", flush=True)
