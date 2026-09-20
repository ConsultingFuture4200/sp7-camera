"""One front-camera (ov5693) capture through libcamera. Reports whether frames
arrived, how long the first took, tone stats, and writes a preview.
usage: front-test.py LABEL"""
import sys, gi, struct, zlib, time
gi.require_version('Gst', '1.0')
from gi.repository import Gst, GLib
Gst.init(None)
label = sys.argv[1]
pipe = Gst.parse_launch('libcamerasrc name=src ! videoconvert ! video/x-raw,format=RGB '
                        '! appsink name=sink emit-signals=true max-buffers=2 drop=true sync=false')
src = pipe.get_by_name('src'); src.set_property('camera-name', r'\_SB_.PCI0.I2C2.CAMF')
st = {'n': 0, 'done': False, 't0': time.monotonic(), 'first': None}; loop = GLib.MainLoop()
def on_sample(sink):
    s = sink.emit('pull-sample')
    if not s or st['done']: return Gst.FlowReturn.OK
    st['n'] += 1
    if st['first'] is None: st['first'] = time.monotonic() - st['t0']
    if st['n'] < 60: return Gst.FlowReturn.OK
    c = s.get_caps().get_structure(0); w, h = c.get_value('width'), c.get_value('height')
    ok, mi = s.get_buffer().map(Gst.MapFlags.READ); d = bytes(mi.data); s.get_buffer().unmap(mi); st['done'] = True
    stride = len(d)//h; lum = sorted((d[y*stride+x*3]*299+d[y*stride+x*3+1]*587+d[y*stride+x*3+2]*114)//1000
                                     for y in range(0, h, 9) for x in range(0, w, 9))
    p = lambda q: lum[int(len(lum)*q)]
    print(f"  {label}: {w}x{h}, first frame after {st['first']:.1f}s, 60 frames in {time.monotonic()-st['t0']:.1f}s, "
          f"luma p5={p(.05)} p50={p(.5)} p95={p(.95)}", flush=True)
    W2, H2 = w//4, h//4; rows = bytearray()
    for oy in range(H2):
        rb = (oy*4)*stride; rows += b'\x00' + b''.join(d[rb+x*12: rb+x*12+3] for x in range(W2))
    ch = lambda t, b: struct.pack('>I', len(b))+t+b+struct.pack('>I', zlib.crc32(t+b) & 0xffffffff)
    open(f'caps/front-{label}.png', 'wb').write(b'\x89PNG\r\n\x1a\n'+ch(b'IHDR', struct.pack('>IIBBBBB', W2, H2, 8, 2, 0, 0, 0))
                                              + ch(b'IDAT', zlib.compress(bytes(rows), 6))+ch(b'IEND', b''))
    loop.quit(); return Gst.FlowReturn.OK
pipe.get_by_name('sink').connect('new-sample', on_sample)
pipe.get_bus().add_signal_watch()
pipe.get_bus().connect('message', lambda b, m: (print(f"  {label}: ERROR {m.parse_error()[0].message}", flush=True), loop.quit()) if m.type == Gst.MessageType.ERROR else None)
pipe.set_state(Gst.State.PLAYING); GLib.timeout_add_seconds(50, loop.quit); loop.run(); pipe.set_state(Gst.State.NULL)
if not st['done']: print(f"  {label}: NO FRAMES in 50s (got {st['n']})", flush=True)
