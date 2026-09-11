# sp7-camera

Tools and notes for Surface Pro 7 camera support on Linux (Omarchy).

- `aiqb.py` decodes Intel CPF/AIQB camera tuning files to JSON.
- `camera-pkgs/` holds the Windows driver packages extracted from this SP7
  (Intel-proprietary; gitignored). `test_aiqb.py` needs it present.
- `docs/` has the install runbook, versioned per file name.

Build: none. Test: `python3 test_aiqb.py` (exit 0 = all SP7 sensor files decode).

Rule: never commit or publish the blobs in `camera-pkgs/`. Share hashes and
versions (`hashes.csv`, `devices.txt`) instead.
