### Surface Pro 7 (1866) data points from a working Windows install, plus a tuning-file decoder

Before wiping Windows on my SP7 I exported the camera stack. Sharing the identifiers and a couple of findings; not the blobs.

**Hardware / driver identifiers (Windows 11 25H2, UEFI 24.109.140 of 2025-07-20)**

| Device | ID | Notes |
|---|---|---|
| IPU4P | `PCI 8086:8A19 rev 03`, subsys `8086:7270` | "Intel(R) Imaging Signal Processor", `iaisp64.inf` |
| Front RGB | `ACPI\INT33BE\0` | OV5693; Windows uses `INT33BE`, not `INT3479`, on this unit |
| Rear RGB | `ACPI\INT347A\0`, subsys `MSHW0191` | OV8865 |
| IR | `ACPI\INT347E\0`, subsys `MSHW0192` | OV7251 |
| Control logic | 3x `ACPI\INT3472` | |

Intel camera driver package version across all of the above: **42.18362.3.16827**.

**Firmware**

The Windows package `iacamera64.inf` carries `cpd_component_signed.bin`, 3,960,832 bytes, SHA-256
`ff2c36cc81a5c726508b22970c2e2538ff06107dc5a72c93401403c227e5157f`.
@ruslanbay if that matches the file you used as `ipu4p_cpd.bin`, we have two independent copies agreeing; if not, the difference may be worth a look.

**Sensor facts relevant to the media-bus-code issue**

The tuning data for the rear OV8865 declares `general_data` = 3280x2464, 10-bit, `color_order` 2, `bit_depth_packed` 10 — i.e. 10-bit Bayer end to end on the Windows side, consistent with expecting `SBGGR10_1X10` (0x3007) rather than a YUV code at the ISYS node.

**Tuning file format**

The `.cpf` / `.aiqb` files shipped with the sensor drivers are not obfuscated. They are `CPFF` / `AIQB` containers of `ia_mkn_record_header` records (`u32 size; u8 data_format_id; u8 key_id; u16 data_name_id`), and the camera-module-characterisation records (`data_name_id` < 256) follow the structs Intel publishes in `ia_cmc_types.h` (e.g. in `intel/ipu6-camera-bins`). I wrote a small decoder that pulls out geometry, black levels, per-illuminant lens-shading grids (63x47, 4 channels), colour matrices (7 illuminants x 24 hue sectors), noise model, gain conversion curves and optics for all three SP7 sensors, with size checks per record. A few deviations from the published header worth knowing if anyone else goes this way:

- LSC-4x4 header is `grid_indices[16]` + `u16 num_light_srcs, num_tables, grid_width, grid_height`; the `_ratio` record (id 33) has the same on-disk layout.
- LSC gains are `u16` with unit gain at `1 << (16 - fraction_bits)`; the header's Q-notation reads inverted against the data.
- Advanced-colour-matrix light-source info is the 20-byte V100 form.
- Newer files nest `CPFF -> LCMC -> DFLT -> AIQB` (+ `LAIQ`), with a 16-byte header on the list containers.

This doesn't help with streaming, but once ISYS frames exist it gives a libcamera software-ISP path real lens-shading and CCM tables instead of guesses. Decoder: https://github.com/ConsultingFuture4200/sp7-camera

Happy to run `media-ctl -p` / dmesg on the 6.1 branch once the machine is on Linux; the format-propagation idea (setting `SBGGR10_1X10` on both CSI-2 pads, not just the sensor pad, before streaming) is the first thing I plan to try.
