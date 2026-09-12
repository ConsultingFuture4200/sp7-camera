# Colour tuning: Intel .cpf → libcamera

libcamera's software ISP ("simple" IPA) falls back to
`ipa/simple/uncalibrated.yaml` for these sensors, which means no colour
correction at all. The Windows camera package ships real tuning data, and
`tools/cpf2libcamera.py` converts the useful part of it.

## What transfers, and what does not

The simple IPA supports `BlackLevel`, `Awb`, `Ccm`, `Adjust` (gamma/contrast)
and `Agc`. Of Intel's data:

| Intel CMC record | transfers? | why |
|---|---|---|
| `advanced_color_matrices` | **yes** | `traditional_matrix` is a 3x3 with unity row sums per illuminant — exactly libcamera's CCM convention. Each illuminant carries CIE xy, so the colour temperature libcamera keys on is derived with McCamy's approximation. |
| `black_level` / `black_level_global` | **no** | Describes the pedestal under *Windows'* sensor configuration (~64.8 in 10-bit). Measured on this driver the floor is ~15 (rear) and ~0 (front), so copying it would crush shadows. libcamera's BlackLevel algorithm measures it instead. |
| `lens_shading_correction_4x4` | not yet | The simple IPA has no LSC algorithm. The data is there (63x47 grids, 4 channels, per illuminant) if one is added. |
| `analog_gain_conversion`, `noise`, `optics_and_mechanics` | no | No corresponding algorithm in the simple IPA. |

## Result

`ipa/simple/ov5693.yaml` carries six CCMs spanning 2664K-7053K, converted from
`OV5693_MSHW0190_ICL.cpf`. Each was checked to preserve neutrals (row sums
within 1e-7 of unity, so grey stays grey) with saturation gains of 1.55-2.25.

Install to `/usr/share/libcamera/ipa/simple/ov5693.yaml`, or point
`LIBCAMERA_IPA_CONFIG_PATH` at the `ipa/` directory here to test without
touching the system:

    LIBCAMERA_IPA_CONFIG_PATH=$PWD/ipa cam -c 2 --capture=10

libcamera logs `Using tuning file .../ov5693.yaml` when it picks it up, instead
of the `falling back to uncalibrated.yaml` warning.

## The rear camera has no tuning to convert

`OV8865_MSHW0191_ICL.cpf` — the file matching this unit's rear module — is a
240-byte `CPFF/HALB/DFLT/HDRA` stub with no AIQB payload. The only substantial
ov8865 file in the package, `OV8865_XXX_CNL.cpf`, is **byte-identical to
`TPG1_INTEL.cpf` and `TPG2_INTEL.cpf`** (md5 `30b34c90c0c84e8baffba788303cf095`)
— it is the test-pattern-generator tuning, not sensor data. So there is nothing
to convert for the rear; a CCM for it would have to be measured against a colour
target.

## Evaluating a CCM

`tools/render-raw.py` debayers a RAW10 capture to PNG with optional CCM, for
comparing matrices offline:

    python3 tools/render-raw.py front.raw 2592 1944 out.png \
        --ccm 1.7649,-0.6068,-0.1581,-0.4043,1.7496,-0.3452,-0.1520,-0.5956,1.7475

Its AWB is a crude grey-world (or `--whitepatch`) estimator and is **not** a
substitute for libcamera's: in mixed lighting it picks a poor white point, and a
CCM faithfully amplifies whatever white point it is given. Judge a CCM on a live
libcamera stream in even lighting, not on this.
