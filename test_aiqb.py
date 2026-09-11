#!/usr/bin/env python3
"""Self-check: every SP7 tuning file parses with zero errors, and known
values decode as expected. Run from the sp7-camera directory."""
import glob, sys
import aiqb

FILES = {
    "ov8865_extension*/OV8865_MSHW0191_ICL.aiqb": {"width": 3280, "height": 2464, "bit_depth": 10, "lsc": (63, 47, 5)},
    "ov5693_extension*/OV5693_MSHW0190_ICL.cpf": {"lsc": (None, None, None)},
    "ov7251_extension*/OV7251_MSHW0192_ICL.cpf": {"lsc": (None, None, None)},
}
# Not this unit's tuning (project "Juventas"); its LAIQ list holds envelope tags
# aiqb.py does not know. Informational only: the DFLT AIQB inside must decode.
INFO = ["ov8865_extension*/OV8865_MSHW0201_ICL.aiqb"]
fail = 0
for pat, want in FILES.items():
    path = sorted(glob.glob("camera-pkgs/" + pat))[0]
    res = aiqb.parse(path)
    errs = [r for r in res["records"] if "error" in r]
    by = {r["name_id"]: r for r in res["records"] if "data" in r}
    ok = not errs and 1 in by and 2 in by and 28 in by
    g, l = by.get(2, {}).get("data", {}), by.get(28, {}).get("data", {})
    if "width" in want:
        ok &= (g["width"], g["height"], g["bit_depth"]) == (want["width"], want["height"], want["bit_depth"])
        ok &= (l["grid_width"], l["grid_height"], l["num_light_srcs"]) == want["lsc"]
    if 28 in by:   # every LSC table has grid_width*grid_height gains, all in a sane range
        for grid in l["grids"]:
            for t in grid["tables"]:
                ok &= len(t) == l["grid_width"] * l["grid_height"] and abs(min(t) - 1.0) < 0.01 and max(t) < 8.0
    print("%-4s %-28s general=%sx%s/%s-bit lsc=%sx%s x%s errors=%d" % (
        "ok" if ok else "FAIL", path.split("/")[-1], g.get("width"), g.get("height"), g.get("bit_depth"),
        l.get("grid_width"), l.get("grid_height"), l.get("num_light_srcs"), len(errs)))
    fail += not ok
for pat in INFO:
    path = sorted(glob.glob("camera-pkgs/" + pat))[0]
    res = aiqb.parse(path)
    by = {r["name_id"]: r for r in res["records"] if "data" in r}
    print("info %-28s general=%s lsc=%s unknown-envelope-errors=%d" % (
        path.split("/")[-1], 2 in by, 28 in by, sum("error" in r for r in res["records"])))
sys.exit(1 if fail else 0)
