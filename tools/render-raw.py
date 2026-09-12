#!/usr/bin/env python3
"""Debayer a RAW10 IPU4 capture to PNG, optionally applying a libcamera-style CCM.

Lets the CCMs converted from Intel's .cpf be evaluated on a real frame without
depending on a live stream. Grey-world AWB, then optional CCM, then gamma.

Usage: render-raw.py IN.raw WIDTH HEIGHT OUT.png [--ccm a,b,c,d,e,f,g,h,i] [--black N]
"""
import array, struct, sys, zlib

def main():
    src, W, H, dst = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), sys.argv[4]
    ccm = None; black = 0
    if '--ccm' in sys.argv:
        ccm = [float(v) for v in sys.argv[sys.argv.index('--ccm')+1].split(',')]
    if '--black' in sys.argv:
        black = float(sys.argv[sys.argv.index('--black')+1])

    a = array.array('H'); a.frombytes(open(src,'rb').read(W*H*2))
    S = 4                                   # 4x4 box -> manageable preview
    OW, OH = W//S, H//S

    # pass 1: demosaic to linear float RGB, collect channel means for grey-world AWB
    pix = []
    sr = sg = sb = 0.0
    for oy in range(OH):
        row = []
        for ox in range(OW):
            R=G=B=0.0
            for dy in (0,2):
                for dx in (0,2):
                    y, x = oy*S+dy, ox*S+dx
                    i = y*W+x
                    B += a[i]; G += (a[i+1]+a[(y+1)*W+x])/2; R += a[(y+1)*W+x+1]
            R=max(R/4-black,0); G=max(G/4-black,0); B=max(B/4-black,0)
            row.append((R,G,B)); sr+=R; sg+=G; sb+=B
        pix.append(row)
    n = OW*OH
    if '--whitepatch' in sys.argv:
        # white-patch: average the brightest 5% by luma and make that neutral.
        flat = [(0.299*r+0.587*g+0.114*b, r, g, b) for row in pix for r,g,b in row]
        flat.sort(key=lambda t: t[0], reverse=True)
        top = flat[:max(1, len(flat)//20)]
        mr = sum(t[1] for t in top)/len(top)
        mg = sum(t[2] for t in top)/len(top)
        mb = sum(t[3] for t in top)/len(top)
    else:
        mr, mg, mb = sr/n, sg/n, sb/n
    gr = mg/mr if mr > 1e-6 else 1.0
    gb = mg/mb if mb > 1e-6 else 1.0
    print(f"  channel means R={mr:.1f} G={mg:.1f} B={mb:.1f} -> awb gains R={gr:.3f} B={gb:.3f}", file=sys.stderr)

    # normalise on the 99.5th percentile of luma so exposure is comparable
    lum = sorted(0.299*r*gr + 0.587*g + 0.114*b*gb for row in pix for r,g,b in row)
    hi = max(lum[int(len(lum)*0.995)], 1.0)

    out = bytearray()
    def enc(v):
        v = max(0.0, min(1.0, v/hi)) ** (1/2.2)
        return max(0, min(255, int(v*255+0.5)))
    for row in pix:
        line = bytearray()
        for r,g,b in row:
            r, b = r*gr, b*gb
            if ccm:
                r, g, b = (ccm[0]*r+ccm[1]*g+ccm[2]*b,
                           ccm[3]*r+ccm[4]*g+ccm[5]*b,
                           ccm[6]*r+ccm[7]*g+ccm[8]*b)
            line += bytes((enc(r), enc(g), enc(b)))
        out += b'\x00' + line

    def chunk(t,d):
        return struct.pack('>I',len(d))+t+d+struct.pack('>I', zlib.crc32(t+d)&0xffffffff)
    open(dst,'wb').write(b'\x89PNG\r\n\x1a\n'
        + chunk(b'IHDR', struct.pack('>IIBBBBB', OW,OH,8,2,0,0,0))
        + chunk(b'IDAT', zlib.compress(bytes(out),6)) + chunk(b'IEND', b''))
    print(f"  wrote {dst} {OW}x{OH}{' with CCM' if ccm else ' (no CCM)'}", file=sys.stderr)

main()
