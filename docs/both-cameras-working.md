# Both Surface Pro 7 cameras working on Linux

Status 2026-09-12: front (ov5693) and rear (ov8865) both capture raw frames,
and libcamera enumerates and streams them.

Unit: Surface Pro 7 (1866), UEFI 24.109.140, Arch, vanilla Linux 6.19.8 built
as a distro kernel package.

| stage | state |
|---|---|
| IPU4P probe + CSE firmware authentication | works |
| rear ov8865 3264x2448 RAW10 | works, 47,941,632 B for 3 frames |
| front ov5693 2592x1944 RAW10 | works, 30,233,088 B, needs settle 880/1400 |
| IR ov7251 | i2c probe -110, ignored (as upstream documents) |
| `cam -l` | lists both cameras |
| libcamera streaming | ~20 fps @ 1632x1224 through the software ISP |

## Ingredients

1. **Kernel 6.19.8** — the version the port was validated against. Patches do
   not apply to 7.x; building 6.19.8 alongside your normal kernel is far less
   work than forward-porting.
2. **[ruslanbay/ipu4-drivers](https://github.com/ruslanbay/ipu4-drivers)**
   `patches/kernel/v6.19/*.patch` — 56 patches, the IPU4/IPU4P driver itself.
3. **`patches/0057-*`** here — the delta from
   [thisiscamk/sp7-ipu4-camera](https://github.com/thisiscamk/sp7-ipu4-camera)
   @ `da7fd41`, rebased onto that series as a single reviewable patch. This is
   what makes the SP7 specifically work, most importantly the D-PHY building
   block 10 configuration without which the front camera is silent.
4. **`patches/0058-*`** here — two bugs that stop the current tree booting or
   being usable by applications. See below.
5. **Firmware** `ipu4p_cpd.bin` — the `ipu4-20191030` blob, sha256
   `ff2c36cc81a5c726508b22970c2e2538ff06107dc5a72c93401403c227e5157f`,
   3,960,832 bytes. Ships in `iacamera64.inf` in Intel camera package
   42.18362.3.16827 on a Windows install, and is byte-identical to the copy in
   ruslanbay's repo. Goes at `/usr/lib/firmware/ipu4p_cpd.bin`. Not
   redistributed here.

## The two fixes in 0058

**GP fault during isys probe.** Fix 12 of the thisiscamk tree leaves the debug
capture nodes unlinked, but `ipu_isys_video_init()` still calls
`try_fmt_vid_mplane()` on them, and `csi2_try_fmt()` opens with
`list_first_entry(&av->vdev.entity.links, ...)`. On an empty list that returns
`container_of(head)` — a wild pointer, not NULL — so `v4l2_ctrl_g_ctrl()` faults
on a non-canonical address and probe dies on CSI-2 port 0.
`ipu_isys_tpg_try_fmt()` has the same pattern.

**`VIDIOC_ENUM_FRAMESIZES` returning ENOTTY.** `ipu_isys_video_init()` selects
`ioctl_ops_mplane` when `line_header_length` is set and `ioctl_ops_splane`
otherwise. The CSI2 BE SOC node — the only route that writes clean
line-addressed raster, therefore the only one applications can use — has no line
header, so it gets the single-planar struct, which was missing
`.vidioc_enum_framesizes`. libcamera's simple pipeline handler probes it, gets
ENOTTY, and reports "No valid configuration found".

## The settle counts (the front camera's real problem)

The driver computes CSI-2 lane settle counts and uses the calculated **minimum**
(dsettle=661, csettle=684 @419.2MHz). On this unit that fails D-PHY sync
**100%** of the time — every stream start ends in

    csi2-2 error: DPHY non-recoverable synchronization error
    csi2-2 error: Frame sync error

Mid-window values fix it:

    options intel_ipu4p_isys csi2_dsettle=880 csi2_csettle=1400

Windows are roughly dsettle 661..1103 and csettle 684..2247; 880 is also inside
the rear ov8865 window (658..1093 @360MHz), which matters because the override
is global. Both are runtime-writable under
`/sys/module/intel_ipu4p_isys/parameters/`, so they can be tested without a
reload — useful, because reloading the stack wedges the CSE handshake and needs
a reboot.

`scripts/front-sweep.sh` sweeps the window automatically.

## Build

Out-of-tree builds need `srcpath=` or they fail before compiling a single IPU4
file:

    make M=drivers/media/pci/intel srcpath=$PWD/drivers/media/pci/intel modules

In-tree (what a distro kernel package does) it resolves on its own. The whole
series compiles clean on gcc 16.2.1 — 0 errors, 24 warnings, 20 of them the
`MIN`/`MAX` collision between Intel's `math_support.h` and
`include/linux/minmax.h`.

## Runtime

Modules must not autoload — udev's ~50 `v4l_id` probes at load re-authenticate
the firmware and bounce the psys power island, and one timed-out buttress
handshake latches mmu1 into an unrecoverable runtime-PM error. `scripts/ipu4p.conf`
blacklists them and sets `fw_version_check=0` (the 20191030 blob genuinely
disagrees with the driver's built-in 20181222 library version — that mismatch is
structural, not a bad download). Load with `scripts/load-ipu4p.sh` after boot,
which also pins mmu1 on across the probe storm and unpins it 30 s later.

Capture with `scripts/capture.sh front|rear`, which routes
sensor -> CSI-2 port -> CSI2 BE SOC and grabs 3 frames.

## Known-imperfect

- libcamera's software ISP runs `ipa/simple/uncalibrated.yaml` — no lens
  shading, no colour matrix, weak AE. `aiqb.py` in this repo decodes the real
  per-illuminant LSC grids and CCMs out of the Windows `.cpf` files; converting
  those into a libcamera tuning file is the obvious next step.
- The software ISP **crops, it does not scale**. Request the sensor's native
  size and downscale downstream, or a 720p request becomes a centre crop.
- Front frames arrive rotated 180 degrees (sensor mounting).
- Rear autofocus: the dw9719 VCM instantiates, but the simple pipeline handler
  has no AF algorithm, so it sits wherever it powers up.
- Suspend/resume untested. Module reload is broken by design here — one load per
  boot.

## Credit

The hard reverse engineering is [ruslanbay](https://github.com/ruslanbay/ipu4-drivers)'s
and [thisiscamk](https://github.com/thisiscamk/sp7-ipu4-camera)'s. This repo adds
two bug fixes, the settle-count finding, and a second unit's confirmation.
Discussion: [linux-surface#1353](https://github.com/linux-surface/linux-surface/discussions/1353).
