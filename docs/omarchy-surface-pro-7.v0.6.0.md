# Omarchy on Surface Pro 7 — install runbook

**TL;DR** — Install stock Omarchy from its own ISO first, then bolt on the
linux-surface kernel + iptsd, then layer `javon27/omarchy-surface-touch` on top
for tablet ergonomics. Three things bite: Secure Boot must be off (or a MOK
enrolled), Omarchy 4 boots **Limine**, not GRUB, so linux-surface's
`grub-mkconfig` step does not apply, and the touchscreen is dead until iptsd is
running — so keep a USB keyboard within reach for the whole process.

Target: Surface Pro 7 (1866, Ice Lake). Omarchy 4.0.3. Reference:
<https://github.com/javon27/omarchy-surface-touch>

---

## Device

| | |
|---|---|
| Model | Surface Pro 7 (1866) — not the 7+ |
| CPU / GPU | Intel Core i5-1035G4 (Ice Lake) / Iris Plus |
| RAM | 8 GB |
| Storage | 128 GB (119 GB usable) — **113 GB used under Windows** |
| Windows | 11 Pro 25H2, build 26200.9168 |
| **Serial number** | **034116602053** |

**Full wipe, not dual-boot.** Shrinking Windows would leave ~6 GB, which is not
enough for Omarchy. Back up anything you want off the 113 GB before step 3.

**Windows recovery:** there is no recovery drive for this Surface. If you ever
want Windows back, download the image from
<https://support.microsoft.com/surface-recovery-image> using the serial above,
onto a 16 GB+ USB stick.

---

## Camera artifacts exported from Windows (2026-09-10)

Pulled from the working Windows install before the wipe. Location: USB stick
`SIMMAX` (`D:\sp7-camera`) — **copy to durable storage before section 3.**

| Item | Value |
|---|---|
| IPU4P firmware | `camera-pkgs/iacamera64.inf_amd64_88452739904c935a/cpd_component_signed.bin` (3.9 MB) |
| SHA-256 | `FF2C36CC81A5C726508B22970C2E2538FF06107DC5A72C93401403C227E5157F` |
| Intel camera driver version | 42.18362.3.16827 |
| UEFI | 24.109.140 (2025-07-20) |
| IPU | `PCI 8086:8A19 rev 03`, subsys `8086:7270` |
| Rear camera | OV8865, `ACPI\INT347A`, `MSHW0191` — has `.aiqb` tuning |
| IR camera | OV7251, `ACPI\INT347E`, `MSHW0192` |
| Front camera | OV5693, `ACPI\INT33BE\0` (Windows name "Surface Camera Front"; matches the Linux `ov5693` driver's ACPI ID) |
| Control logic | 3x `ACPI\INT3472` |
| AVStream front-end | `INT3480` (Windows-only aggregation device, not a sensor) |
| Sensor tuning | `*.cpf`, `*_pipeCfg.bin`, `*.aiqb` per sensor under `camera-pkgs/ov*_extension.*` |
| Full driver store | `driverstore/` — 132 packages via `pnputil /export-driver` |
| Hashes | `hashes.csv` |

Use: after touch is working (section 4), the experiment for linux-surface
discussion #1353 is to place the blob as `/lib/firmware/intel/ipu/ipu4p_cpd.bin`
on ruslanbay's IPU4 kernel branch and see whether the CSE firmware-auth failure
changes. Post versions and hashes publicly; share the blob itself only privately
(Intel-proprietary).

---

## 0. What will and will not work

Per the linux-surface feature matrix for Surface Pro 7:

| Component | Status |
|---|---|
| Touchscreen | Works — **requires linux-surface kernel + iptsd** |
| Pen | Works — requires linux-surface kernel |
| Type Cover keyboard + trackpad | Works on mainline 5.4+ (so it works in the installer) |
| Wi-Fi / Bluetooth (Intel AX201) | Works out of the box |
| Suspend (S0ix), hibernate | Works |
| Battery status, sensors/accelerometer | Works |
| **Cameras** | **Not supported.** No fix. |

`linux-firmware-marvell` is for Marvell-radio Surfaces (Pro 4/5/6, Book).
SP7 is Intel AX201 — **skip that package**.

---

## 1. Pre-flight (on the Surface, before you touch anything)

1. **Back up.** This wipes the device. On this unit (113 of 119 GB used) dual-booting
   is not viable — treat it as a full wipe.
2. **If Windows stays on the box:** suspend or disable BitLocker first, and shrink
   the Windows partition from inside Windows Disk Management. Do not resize an
   encrypted volume from the Linux side.
3. **Disable "Device Encryption"** in Windows settings even if BitLocker proper
   is off — SP7 ships with it on by default.
4. **Enter UEFI:** power off fully, then hold **Volume Up** and press **Power**;
   release Volume Up when the Surface logo appears.
5. In UEFI:
   - **Security → Secure Boot → Disabled.** (Alternative in §5 if you want it on.)
   - **Boot configuration →** enable USB storage, move it above internal storage.
6. Have a **USB-A keyboard + hub** ready. If the Type Cover misbehaves in the
   installer you have no touchscreen to fall back on.

---

## 2. Write the ISO

On this workstation:

```bash
cd ~/tmp
curl -LO https://iso.omarchy.org/omarchy-4.0.3.iso
curl -LO https://iso.omarchy.org/omarchy-4.0.3.iso.sha256
sha256sum -c omarchy-4.0.3.iso.sha256

lsblk -o NAME,SIZE,MODEL,TRAN        # identify the stick — get this right
sudo dd if=omarchy-4.0.3.iso of=/dev/sdX bs=4M status=progress oflag=direct conv=fsync
sync
```

**Write the ISO directly with `dd`. Do not use Ventoy.** Under Ventoy, archinstall
treats the environment as removable media and writes Limine to the USB stick's
ESP instead of the internal ESP — the install "succeeds" and then boots straight
back into Windows.

---

## 3. Install Omarchy

Boot from the stick (Volume Down + Power, or the UEFI boot menu).

- Network: the installer should bring up Wi-Fi. If you land at a shell, `iwctl`:
  `station wlan0 scan` → `station wlan0 get-networks` → `station wlan0 connect <SSID>`.
- Answer the installer's questions. Disk encryption (LUKS) is fine and recommended
  on a tablet — note that you will be typing the passphrase at boot with the Type
  Cover attached, since there is no on-screen keyboard at the LUKS prompt.
- Let it finish, reboot, remove the stick.

At this point you have Omarchy + Hyprland with a **non-functional touchscreen**.
That is expected.

---

## 4. linux-surface kernel + iptsd

The `omarchy-surface-touch` repo deliberately does not script this — "switching
kernels is too consequential to script blindly." Do it by hand.

```bash
# Signing key
curl -s https://raw.githubusercontent.com/linux-surface/linux-surface/master/pkg/keys/surface.asc \
  | sudo pacman-key --add -
sudo pacman-key --finger 56C464BAAC421453        # verify this fingerprint
sudo pacman-key --lsign-key 56C464BAAC421453
```

Add to `/etc/pacman.conf`:

```ini
[linux-surface]
Server = https://pkg.surfacelinux.com/arch/
```

Then:

```bash
sudo pacman -Syu
sudo pacman -S linux-surface linux-surface-headers iptsd
sudo systemctl enable --now iptsd
```

Skip `linux-firmware-marvell` (§0). Skip `linux-firmware-intel` too — the SP7
cameras do not work regardless.

### 4a. Bootloader — the Omarchy-specific step

linux-surface's docs say run `grub-mkconfig`. **Omarchy 4 uses Limine with
snapper**, so that command is wrong here. Before rebooting, confirm the new
kernel actually has a boot entry:

```bash
ls /boot/vmlinuz-*                 # expect vmlinuz-linux AND vmlinuz-linux-surface
sudo grep -n "linux-surface" /boot/limine.conf   # or /boot/limine/limine.conf
```

If the surface kernel is present in `/boot` but absent from `limine.conf`, the
Limine pacman hook did not regenerate. Force it:

```bash
sudo limine-update      # or: sudo limine-entry-tool
```

If neither exists on your install, add the entry by hand in `limine.conf`,
copying the existing `linux` entry and swapping `vmlinuz-linux` →
`vmlinuz-linux-surface` and `initramfs-linux.img` → `initramfs-linux-surface.img`,
keeping the same `cmdline` (critically the LUKS/root UUID). **Do not remove the
stock `linux` entry** — it is your recovery path if the surface kernel fails to
boot.

Reboot, select the surface kernel, then verify:

```bash
uname -r | grep surface          # must contain "surface"
systemctl status iptsd
sudo libinput debug-events       # tap the screen — events should appear
```

Do not continue until the touchscreen actually registers events.

---

## 5. Secure Boot (optional — only if you want it back on)

linux-surface ships a signed kernel plus a shim:

```bash
sudo pacman -S linux-surface-secureboot-mok
```

Re-enable Secure Boot in UEFI, reboot, and MokManager appears. Choose to enroll
the key; the password is **`surface`**. MokManager reads **QWERTY regardless of
your layout**. Note this path is built around shim + GRUB; with Limine expect to
do extra work. Given SP7 is a personal device, leaving Secure Boot off is the
low-friction choice.

---

## 6. Tablet ergonomics — omarchy-surface-touch

Only now, with touch confirmed working:

```bash
git clone https://github.com/javon27/omarchy-surface-touch.git
cd omarchy-surface-touch
```

First collect the three device-specific values the modules need:

```bash
libinput list-devices | grep -i touch   # TOUCH_DEVICE_NAME (the IPTS digitizer)
hyprctl monitors                        # MONITOR / MODE / SCALE for auto-rotate
monitor-sensor --accel                  # confirm the accelerometer reports
```

Edit those into the relevant module configs, then install **in this order**,
verifying each before moving on (check the process is actually running — do not
trust exit codes):

1. `./install.sh kernel` — iptsd restart-forever override. SP7-class devices hit
   "Interrupted system call" hidraw crashes; this restarts iptsd within a second
   instead of giving up. Safest first step.
2. `./install.sh osk` — wvkbd on-screen keyboard (patched for upstream flicker /
   no-repeat) plus the toggle and autostart wrapper. Pulls build deps.
3. `./install.sh trackpad` — virtual trackpad panel. Prerequisite for the screensaver.
4. `./install.sh two-finger-right-click auto-rotate touchpad-mt-fix` — any order.
   `touchpad-mt-fix` addresses the Type Cover trackpad losing two-finger scroll
   after suspend, which you will hit on SP7.
5. `./install.sh screensaver` — after trackpad.
6. `./install.sh lock-pin` — **last**. PIN unlock screen with an on-screen keypad.
   Confirm you understand it before enabling: it replaces your unlock path, and
   getting it wrong on a device with no working touchscreen-at-lock is how you
   lock yourself out. Keep the Type Cover attached the first time you test it.

`./install.sh` with no arguments gives an interactive menu; `--all` does everything.
Given the ordering and per-device config, **run them selectively, not `--all`**.

### Security note, stated plainly
`trackpad` and `two-finger-right-click` run as **systemd system services with
root**, because they read a raw input device and create `/dev/uinput`. The author
acknowledges this is a tradeoff made for cross-distro install simplicity; a udev
rule would be the tighter approach. On a personal tablet this is acceptable —
just know it is there.

---

## 7. Verification checklist

- [ ] `uname -r` contains `surface`
- [ ] Stock `linux` entry still bootable in Limine (recovery path intact)
- [ ] Touchscreen produces events in `libinput debug-events`
- [ ] Pen works (hover + tip + barrel button)
- [ ] Type Cover detaches/reattaches cleanly
- [ ] On-screen keyboard toggles with the Type Cover detached
- [ ] Auto-rotate follows physical orientation, and **touch rotates with it**
- [ ] Suspend → resume: Wi-Fi returns, trackpad two-finger scroll still works
- [ ] Lock → unlock works with keyboard detached
- [ ] Battery percentage reports correctly

---

## Known rough edges

- **Cameras never work.** Both front and rear. If you need video calls, plan on a
  USB webcam.
- **iptsd crashes** are a known unresolved upstream issue; the restart override is
  mitigation, not a fix.
- **Omarchy updates** may touch Hyprland config and Limine entries. After an
  `omarchy-update`, re-check that the surface kernel entry survived and that the
  touch services are still enabled.
- **Kernel updates** pull a new `linux-surface`; regenerate/verify the Limine
  entry each time until you have confirmed the hook fires automatically.
- The reference repo was developed on a Surface Pro **7+**, not a 7. They are
  close (same generation of IPTS) but not identical — expect the device-name and
  monitor values in §6 to differ.

---

## Sources

- <https://github.com/javon27/omarchy-surface-touch> (README, `kernel/README.md`)
- <https://github.com/linux-surface/linux-surface/wiki/Installation-and-Setup>
- <https://github.com/linux-surface/linux-surface/wiki/Supported-Devices-and-Features>
- <https://omarchy.org/>
- <https://github.com/omacom/omarchy/discussions/1604> (Limine / dual-boot, Ventoy ESP trap)

---

## Appendix A — Camera experiment plan (post-install, optional)

Do not start until section 4 is done and touch works on the linux-surface
kernel. This adds a third, lab-only kernel.

Reality check (linux-surface discussion #1353, Jan 2026): the Windows blob
`cpd_component_signed.bin` already resolved "FW authentication failed" for
ruslanbay. The effort is blocked on streaming, not firmware.

| Stage | Goal | Blocker | Effort |
|---|---|---|---|
| 1 Reproduce | driver loads, FW auths, 3 sensors probe | none known | a weekend |
| 2 Raw frame | one Bayer frame via ISYS | "wrong media bus code 0x200a (0x3007 expected)" — unsolved | unknown |
| 3 Webcam | frames in apps | no libcamera pipeline handler | days-weeks with libcamera soft-ISP, once 2 is done |

Strategic point: Intel's closed ISP (PSYS) is not required. Raw frames +
libcamera simple pipeline + software ISP = working (mediocre) webcam.

### Stage 1

```bash
sudo install -D -m644 sp7-camera/camera-pkgs/iacamera64.inf_*/cpd_component_signed.bin \
     /lib/firmware/ipu4p_cpd.bin
sha256sum /lib/firmware/ipu4p_cpd.bin   # FF2C36CC81A5C726508B22970C2E2538FF06107DC5A72C93401403C227E5157F

sudo pacman -S --needed base-devel bc cpio pahole python v4l-utils
git clone --depth 1 -b ipu4-6.1 https://github.com/ruslanbay/linux.git ipu4-linux
cd ipu4-linux
zcat /proc/config.gz > .config
scripts/config -m INTEL_IPU4 -m VIDEO_OV8865 -m VIDEO_OV5693 -m VIDEO_OV7251 \
               -e MEDIA_CONTROLLER -e VIDEO_V4L2_SUBDEV_API -m INTEL_SKL_INT3472
make olddefconfig
make -j$(nproc) LOCALVERSION=-ipu4
sudo make modules_install
sudo install -m644 arch/x86/boot/bzImage /boot/vmlinuz-linux-ipu4
sudo mkinitcpio -k $(make -s kernelrelease) -g /boot/initramfs-linux-ipu4.img
# Limine: duplicate the linux-surface entry, swap both filenames, keep cmdline
```

Verify: `dmesg | grep -iE 'ipu|ov8865|ov5693|ov7251|int3472'` has no
"FW authentication failed"; `media-ctl -p` shows 3 sensors on CSI-2 ports
3 (OV8865), 6 (OV7251), 7 (OV5693). If ports 6/7 are missing, the
`ipu4_csi_offsets` table needs 8 entries (known issue in the thread).

Config symbol names are from memory of Intel's out-of-tree tree; confirm in
`make menuconfig` if any is rejected.

### Stage 2 — first hypothesis, no code

The thread's media-ctl sequence only sets the format on the sensor pad.
Propagate it through the CSI-2 receiver before assuming a driver bug:

```bash
media-ctl -r
media-ctl -V '"ov8865 1-0010":0 [fmt:SBGGR10_1X10/800x600]'
media-ctl -V '"Intel IPU4 CSI-2 3":0 [fmt:SBGGR10_1X10/800x600]'
media-ctl -V '"Intel IPU4 CSI-2 3":1 [fmt:SBGGR10_1X10/800x600]'
media-ctl -l '"ov8865 1-0010":0 -> "Intel IPU4 CSI-2 3":0 [1]'
media-ctl -p | grep -A3 'CSI-2 3'
yavta -c1 -I -s800x600 -Fframe.bin -fSBGGR10 /dev/video<N>
```

A frame here unblocks the project. Otherwise the check lives in
`ipu-isys-queue.c` — printk from there. Either way post `media-ctl -p` and
`dmesg` to #1353.

### Stage 3

Raw frames -> libcamera simple pipeline handler + software ISP. The Windows
`.aiqb`/`.cpf` tuning files are proprietary AIQ format; park them until an
IPU4 IPA exists that could use lens-shading/colour-matrix tables.

Refs: https://github.com/ruslanbay/linux/tree/ipu4-6.1 ·
https://github.com/ruslanbay/ipu4-next · https://github.com/Kleist/ipu4-driver
(IPU4 only, not IPU4P) · linux-surface discussion #1353

### Tuning file format (verified 2026-09-10 on this workstation)

`.cpf` = `CPFF` container wrapping `AIQB` (tuning) + `HALB` (HAL config);
`.aiqb` = bare `AIQB`. Container header 24 bytes: tag[4], u32 size, 12 zero,
u32 crc. Records follow, each `ia_mkn_record_header` (public, Intel
`ia_mkn_types.h`): `{u32 size; u8 data_format_id; u8 key_id; u16 data_name_id}`.
`key_id=0` everywhere: no packing, no encryption. Payloads are raw LE
integers/float32.

`data_name_id` for records < 256 follows `enum cmc_name_id` in Intel's public
`ia_cmc_types.h` (IPU6 copy: github.com/intel/ipu6-camera-bins,
`include/ipu6/ia_imaging/`), with the struct for every record. OV8865
MSHW0191 contains: 1 comment, 2 general_data (3280x2464, 10-bit, color_order 2),
3 black_level, 7 module_sensitivity, 9 noise, 13 optics_and_mechanics,
15 chromaticity_response, 17 nvm_info, 19 analog_gain_conversion,
20 digital_gain, 21 sensor_metadata, 22 gdc2, 25 advanced_color_matrices,
28 lens_shading_correction_4x4 (5 light sources), 31 black_level_global,
33 lsc_4x4_ratio, 34 multi_gain_conversions. Records >= 257 and 60000+ are
AIQ algorithm tuning; no public definitions; not needed for libcamera.

Local copy: `~/tmp/sp7-camera/camera-pkgs/`. Headers fetched to the job tmp
dir; re-fetch from the repos above.

### aiqb.py (built 2026-09-10)

`~/tmp/sp7-camera/aiqb.py` decodes CPF/AIQB to JSON; `test_aiqb.py` is the
self-check (`cd ~/tmp/sp7-camera && python3 test_aiqb.py`). Decoded output for
the three SP7 sensors is in `~/tmp/sp7-camera/decoded/*.json`.

Layout notes learned against the data (deviations from the IPU6 header):
- LSC 4x4 header is idx[16] + u16 num_light_srcs, num_tables, grid_width,
  grid_height (24 bytes); `_ratio` (id 33) is byte-identical in layout.
- LSC gains are u16 with unit gain at `1 << (16 - fraction_bits)`; the header's
  Q-notation reads inverted against the data. Table minimum is exactly 1.0.
- ACM light-source info is the 20-byte V100 form (no cct).
- black_level_global carries the 8-byte pointer placeholder on disk plus an
  8-byte reserved tail. Black levels are 16-bit normalised (≈64 at 10-bit).
- optics has a 16-byte per-aperture tail beyond the documented 64 bytes.
- Newer CPFF files nest LCMC -> DFLT -> AIQB and LAIQ; those use a 16-byte
  container header. HALB records are a separate namespace, not CMC.

Values decoded for OV8865 MSHW0191 (rear): 3280x2464 10-bit, color_order 2,
f=3.57 mm, 1.40 um pixels, base ISO 86, LSC 63x47 x 4 tables x 5 illuminants
(corner gain up to ~4.4), ACM 7 illuminants x 24 hue sectors, noise model
c1..c5 = [0.00055, 0.084, 0, 3.91, 4.34]. OV5693 (front) 2592x1944, LSC 6
illuminants. OV7251 (IR) 648x488, LSC 1 illuminant (flat, max 2.0).
