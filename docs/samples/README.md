# Sample frames

## Front camera (ov5693), 2026-09-20

With `patches/0059-*` (Windows receiver timing), libcamera simple pipeline +
software ISP, colour matrices from `OV5693_MSHW0190_ICL.cpf`
(`ipa/simple/ov5693.yaml`), gamma 1.8 / contrast 1.1 / saturation 1.4.
Indoor daylight, mirroring corrected, otherwise untouched.

| file | what it is |
|---|---|
| `front-2560x1600.jpg` | as delivered by the ISP (2560x1600 crop of the 2592x1944 mode), 0.3% clipped. Row 1051 is a single corrupted (magenta) line, a transient CSI-2 line error; two frames captured right after were clean. Left in deliberately. |
| `front-1280x800.jpg` | half size |
| `front-backlit-awb-green.jpg` | same setup, windows behind the subject: 22% of the frame clipped and the grey-world AWB goes green |

Exposure controls sent through `libcamerasrc` (`exposure-value`,
`ae-enable=false` + `exposure-time`/`analogue-gain`) are accepted but change
nothing with the simple IPA here; the fix for the backlit case was turning
around.

## Rear camera (ov8865) sample frames

Surface Pro 7 (1866), linux-ipu4p 6.19.8, `ruslanbay/ipu4-drivers` v6.19 series
+ the `thisiscamk` delta + the two fixes in `patches/0058-*`. Captured through
libcamera's simple pipeline with the **software ISP**, indoor daylight.

| file | what it is |
|---|---|
| `rear-3200x2400.jpg` | full sensor mode (3264x2448 -> 3200x2400 out), mirroring corrected |
| `rear-1280x720.jpg` | the size apps receive through the v4l2loopback relay |
| `rear-as-delivered-mirrored.jpg` | exactly as the camera delivers it: horizontally mirrored |

Known quality limitations, all userspace rather than driver:

* **No colour tuning.** The simple IPA falls back to `ipa/simple/uncalibrated.yaml`:
  no lens shading, no colour matrix. Hence the wash-out toward white and the
  faint green-grey cast on neutrals. The Windows package has no usable `.cpf`
  for this sensor - `OV8865_MSHW0191_ICL.cpf` is a 240-byte stub and
  `OV8865_XXX_CNL.cpf` is byte-identical to the TPG tuning files.
* **AGC overshoots** and needs ~10 s to settle; a frame grabbed early is blown out.
  This frame has 0.6% clipped pixels after settling.
* **Mirrored output.** The ov8865 subdev reports `horizontal_flip=1` and
  `vertical_flip=1` although both default to 0.
* ~15 fps at 1280x720; GPU debayer ~14 ms/frame on the i5-1035G4.
