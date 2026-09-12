# sp7-camera

Getting the **Surface Pro 7** (model 1866) built-in cameras working on Linux.

**Status 2026-09-12: both cameras work.** Front (ov5693) and rear (ov8865)
capture raw frames through the Ice Lake IPU4P, and libcamera enumerates and
streams them at ~20 fps.

    Available cameras:
    1: Internal back camera  (\_SB_.PCI0.I2C3.CAMR)
    2: Internal front camera (\_SB_.PCI0.I2C2.CAMF)

The Surface Pro 7's ISP (Intel IPU4P, PCI `8086:8a19`) has no upstream Linux
driver and Intel has no plans to add one. The working stack is
[ruslanbay/ipu4-drivers](https://github.com/ruslanbay/ipu4-drivers) plus
[thisiscamk/sp7-ipu4-camera](https://github.com/thisiscamk/sp7-ipu4-camera);
this repo adds what was needed to make that combination actually run on a second
unit.

**→ [docs/both-cameras-working.md](docs/both-cameras-working.md)** — the full
recipe, the bugs, and the settle-count finding.

## What is here

### `patches/`

- `0057-*` — the thisiscamk delta rebased onto ruslanbay's v6.19 series as one
  reviewable patch (SP7 D-PHY building block 10, buttress power timeout, ov5693
  binned-mode quirk, BE SOC routing, and more).
- `0058-*` — two fixes found here:
  - a **general protection fault during isys probe** —
    `list_first_entry()` on an empty entity link list returns
    `container_of(head)`, not NULL, so `csi2_try_fmt()` dereferences a wild
    pointer for every unlinked debug tap;
  - **`VIDIOC_ENUM_FRAMESIZES` returning ENOTTY** on the CSI2 BE SOC capture
    node, because the single-planar ioctl ops struct lacked it — that node is
    the only clean-raster route, so libcamera could never configure a stream.

### The settle counts

The front camera's remaining problem was not the PHY fix but the CSI-2 lane
settle counts: the driver uses the calculated **minimum**, which fails D-PHY
sync 100% of the time on this unit. `csi2_dsettle=880 csi2_csettle=1400` fixes
it. Both are runtime-writable; `scripts/front-sweep.sh` finds a working pair.

### `scripts/`

Load the stack in the required order, capture from either camera via the BE SOC
path, sweep settle counts, install the module and config. `ipu4p.conf` is the
modprobe.d file (blacklists + `fw_version_check=0` + the settle values).

### Tools

- `aiqb.py` (repo root) — decodes Intel `.cpf` / `.aiqb` tuning files
  (CPFF/AIQB containers of `ia_mkn_record_header` records) into JSON: sensor
  geometry, black level, per-illuminant lens-shading grids, colour matrices,
  gain curves, optics. Run from the repo root:

      python3 aiqb.py FILE.cpf --summary
      python3 test_aiqb.py

- `tools/cpd-dump.py` — parses the IPU firmware CPD container, mirroring the
  structures and validation in the driver's `ipu6-cpd.{c,h}`. See
  [docs/cpd-report.txt](docs/cpd-report.txt) for the SP7 blob's layout.

      python3 tools/cpd-dump.py cpd_component_signed.bin

## What is and is not in git

`camera-pkgs/` (Windows driver packages, IPU4P firmware, tuning files), decoded
JSON, raw captures and built modules are Intel/Microsoft material or large
binaries, and are gitignored. `devices.txt` and `hashes.csv` identify them
without redistributing them. The firmware blob is obtainable from any Windows
install of Intel camera package `42.18362.3.16827`; its sha256 is in
`docs/both-cameras-working.md`.

## Docs

- `docs/both-cameras-working.md` — build + run recipe, the bugs, known limits.
- `docs/cpd-report.txt` — firmware container breakdown.
- `docs/omarchy-surface-pro-7.v0.6.0.md` — install runbook and hardware IDs.
- `docs/1353-comment.md` — the original thread post.

Discussion and credit:
[linux-surface#1353](https://github.com/linux-surface/linux-surface/discussions/1353).
The reverse engineering is ruslanbay's and thisiscamk's; this repo contributes
two bug fixes, the settle-count finding, and an independent second-unit
confirmation.
