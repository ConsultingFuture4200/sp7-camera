"""Capture one rear frame with given libcamera knobs, report tone/colour stats,
write a mirror-corrected preview.  usage: tone-test.py LABEL [gamma G] [contrast C] [saturation S]"""
import sys, gi, struct, zlib, statistics
gi.require_version('Gst', '1.0')
from gi.repository import Gst, GLib
Gst.init(None)
label = sys.argv[1]; kv = dict(zip(sys.argv[2::2], map(float, sys.argv[3::2])))
pipe = Gst.parse_launch('libcamerasrc name=src ! videoconvert ! video/x-raw,format=RGB '
                        '! appsink name=sink emit-signals=true max-buffers=2 drop=true sync=false')
src = pipe.get_by_name('src'); src.set_property('camera-name', r'\_SB_.PCI0.I2C3.CAMR')
for k, v in kv.items(): src.set_property(k, v)
st = {'n': 0, 'done': False}; loop = GLib.MainLoop()
def on_sample(sink):
    s = sink.emit('pull-sample')
    if not s or st['done']: return Gst.FlowReturn.OK
    st['n'] += 1
    if st['n'] < 90: return Gst.FlowReturn.OK          # ~6 s for AGC to settle
    c = s.get_caps().get_structure(0); w, h = c.get_value('width'), c.get_value('height')
    ok, mi = s.get_buffer().map(Gst.MapFlags.READ)
    d = bytes(mi.data); s.get_buffer().unmap(mi); st['done'] = True
    stride = len(d)//h
    lum, sat = [], []
    for y in range(0, h, 9):
        b = y*stride
        for x in range(0, w, 9):
            r, g, bl = d[b+x*3], d[b+x*3+1], d[b+x*3+2]
            lum.append((r*299+g*587+bl*114)//1000)
            mx, mn = max(r, g, bl), min(r, g, bl); sat.append((mx-mn)/mx if mx else 0)
    lum.sort()
    p = lambda q: lum[int(len(lum)*q)]
    print(f"  {label:<28} luma p5={p(.05):3d} p50={p(.5):3d} p95={p(.95):3d}  clipped={sum(1 for v in lum if v>=250)/len(lum)*100:4.1f}%  "
          f"mean sat={statistics.mean(sat):.3f}", flush=True)
    W2, H2 = w//4, h//4; rows = bytearray()
    for oy in range(H2):
        rb = (oy*4)*stride; rows += b'\x00' + b''.join(d[rb+x*12: rb+x*12+3] for x in range(W2-1, -1, -1))
    ch = lambda t, b: struct.pack('>I', len(b))+t+b+struct.pack('>I', zlib.crc32(t+b) & 0xffffffff)
    open(f'caps/tone-{label}.png', 'wb').write(b'\x89PNG\r\n\x1a\n'+ch(b'IHDR', struct.pack('>IIBBBBB', W2, H2, 8, 2, 0, 0, 0))
                                             + ch(b'IDAT', zlib.compress(bytes(rows), 6))+ch(b'IEND', b''))
    loop.quit(); return Gst.FlowReturn.OK
pipe.get_by_name('sink').connect('new-sample', on_sample)
pipe.get_bus().add_signal_watch(); pipe.get_bus().connect('message', lambda b, m: loop.quit() if m.type == Gst.MessageType.ERROR else None)
pipe.set_state(Gst.State.PLAYING); GLib.timeout_add_seconds(40, loop.quit); loop.run(); pipe.set_state(Gst.State.NULL)
if not st['done']: print(f"  {label:<28} NO FRAME", flush=True)
