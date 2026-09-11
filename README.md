# sp7-camera

Surface Pro 7 (model 1866) camera work for Linux: what was extracted from the
working Windows install before wiping it, and a decoder for Intel's camera
tuning file format.

## aiqb.py

Decodes Intel `.cpf` / `.aiqb` tuning files (CPFF/AIQB containers,
`ia_mkn_record_header` records) into JSON. CMC records — sensor geometry, black
level, lens shading, colour matrices, gain curves, optics — are decoded using
the layouts Intel publishes in `ia_cmc_types.h`; algorithm-tuning records are
listed but left opaque.

    python3 aiqb.py FILE.cpf --summary
    python3 aiqb.py FILE.aiqb > out.json
    python3 test_aiqb.py

## What is and is not in git

`camera-pkgs/` (driver packages, IPU4P firmware, tuning files) and the decoded
JSON are Intel/Microsoft material and are gitignored. `devices.txt` and
`hashes.csv` identify them without redistributing them.

## Docs

`docs/omarchy-surface-pro-7.v0.6.0.md` — install runbook, hardware IDs, camera
experiment plan, and the tuning-format notes.
