#!/usr/bin/env python3
"""Decode Intel AIQB / CPF camera tuning files into JSON.

Container: CPFF wraps AIQB (+ HALB). Each container is tag[4], u32 size,
12 zero bytes, u32 crc, then records. Record header is ia_mkn_record_header
(Intel ia_mkn_types.h): u32 size, u8 data_format_id, u8 key_id, u16 name_id.
Records with name_id < 256 are CMC (camera module characterisation) records
whose layouts are public in ia_cmc_types.h. Higher IDs are Intel 3A algorithm
tuning with no public layout; they are listed but not decoded.
"""
import json
import struct
import sys

HDR = 24            # container header
REC = 8             # record header
TAGS = (b"AIQB", b"CPFF", b"HALB")
LIST_TAGS = (b"LCMC", b"DFLT", b"LAIQ")   # newer CPFF envelope: tag, u32 size, 8 bytes (count / zero)

CMC_NAMES = {
    1: "comment", 2: "general_data", 3: "black_level", 4: "black_level_spatial",
    5: "saturation_level", 6: "dynamic_range_and_linearity", 7: "module_sensitivity",
    8: "defect_pixels", 9: "noise", 10: "lens_shading_correction",
    11: "lens_shading_correction_ratio", 12: "geometric_distortion_correction",
    13: "optics_and_mechanics", 14: "module_spectral_response",
    15: "chromaticity_response", 16: "flash_chromaticity", 17: "nvm_info",
    18: "color_matrices", 19: "analog_gain_conversion", 20: "digital_gain",
    21: "sensor_metadata", 22: "geometric_distortion_correction2",
    23: "exposure_range", 24: "multi_led_flash_chromaticity",
    25: "advanced_color_matrices", 26: "hdr", 27: "infrared_correction",
    28: "lens_shading_correction_4x4", 29: "lateral_chromatic_aberration_correction",
    30: "phase_difference", 31: "black_level_global", 32: "valid_image_area",
    33: "lens_shading_correction_4x4_ratio", 34: "multi_gain_conversions",
    35: "pipe_comp_decomp", 36: "sensor_decomp", 37: "media_format", 38: "cbd",
}

OPTICS_FIELDS = (
    "actuator camera_module_orientation camera_actuator_features nd_gain "
    "effect_focal_length_x100mm sensor_pix_size_v_x100um sensor_pix_size_h_x100um "
    "sensor_width_pix_total sensor_height_pix_total lens_offset_up_to_horz "
    "lens_offset_horz_to_down range_inf_to_85mm range_inf_to_100mm range_inf_to_300mm "
    "range_inf_to_500mm range_inf_to_950mm range_inf_to_1200mm range_inf_to_hyperfocal "
    "range_inf_to_calibration_distance_far range_inf_to_calibration_distance_near "
    "range_inf_to_min_focusing_distance calibration_distance_far "
    "calibration_distance_near calibration_position_far calibration_position_near "
    "lens_range_limit lens_actuator_offset lens_movement_time min_focus_distance "
    "num_apertures"
).split()
OPTICS_FMT = "<BBHHHHHHHHHHHHHHHHHHHHHhhiiIHH"


def cstr(b):
    return b.split(b"\0", 1)[0].decode("ascii", "replace")


def u16s(p, off, n):
    return list(struct.unpack_from("<%dH" % n, p, off))


def f32s(p, off, n):
    return list(struct.unpack_from("<%df" % n, p, off))


def fixed16(v):
    return v / 65536.0


# Each decoder takes the record payload (after the 8-byte header) and returns
# (dict, bytes_consumed). bytes_consumed is checked against the payload size;
# a mismatch is reported so a wrong layout cannot pass silently.

def d_comment(p):
    return {"project_id": cstr(p[:16]), "comment": cstr(p[16:])}, len(p)


def d_general(p):
    w, h, bd, co, bdp = struct.unpack_from("<5H", p)
    d = {"width": w, "height": h, "bit_depth": bd, "color_order": co,
         "bit_depth_packed": bdp}
    n = 10
    if len(p) >= 26:
        d["sve_pattern"] = list(p[10:26]); n = 26
    if len(p) >= 28:
        d["single_exposure_bit_depth"] = struct.unpack_from("<H", p, 26)[0]; n = 28
    return d, n


def d_black_level(p):
    (num,) = struct.unpack_from("<I", p)
    luts = []
    for i in range(num):
        et, ag, c1, c2, c3, c4 = struct.unpack_from("<IIHHHH", p, 4 + 16 * i)
        luts.append({"exposure_time": et, "analog_gain": ag, "channels": [c1, c2, c3, c4]})
    return {"luts": luts}, 4 + 16 * num


def d_black_level_global(p):
    (num,) = struct.unpack_from("<I", p)
    vals, off = [], 16
    for _ in range(num):
        et, g = struct.unpack_from("<If", p, off)
        bl = f32s(p, off + 8, 16)
        vals.append({"exposure_time_us": et, "total_gain": g,
                     "black_level_4x4": [bl[i:i + 4] for i in range(0, 16, 4)]})
        off += 72
    return {"values": vals}, off + 8


def d_saturation(p):
    return {"channels": u16s(p, 0, 4)}, 8


def d_linearity(p):
    dr, n1, n2, n3, n4 = struct.unpack_from("<IBBBB", p)
    off, luts = 8, []
    for n in (n1, n2, n3, n4):
        luts.append(u16s(p, off, n)); off += 2 * n
    return {"dynamic_range_db": dr, "linearity_luts": luts}, off


def d_sensitivity(p):
    return {"base_iso": struct.unpack_from("<H", p)[0]}, 2


def d_noise(p):
    return {"coefficients_c1_c5": f32s(p, 0, 5)}, 24


def d_optics(p):
    n = struct.calcsize(OPTICS_FMT)
    d = dict(zip(OPTICS_FIELDS, struct.unpack_from(OPTICS_FMT, p)))
    if len(p) > n:
        d["apertures_raw_hex"] = p[n:].hex()
    return d, len(p)


def d_chromaticity_response(p):
    na, nn = struct.unpack_from("<HH", p)
    srcs = []
    for i in range(na + nn):
        x, y, rg, bg = u16s(p, 4 + 8 * i, 4)
        srcs.append({"cie_xy": [x, y], "r_per_g": rg, "b_per_g": bg})
    n = 4 + 8 * (na + nn)
    d = {"num_avg": na, "num_nvm": nn, "lightsources": srcs}
    if len(p) > n:
        d["v101_extension_bytes"] = len(p) - n
    return d, len(p)


def d_nvm_info(p):
    v, co, o = u16s(p, 0, 3)
    return {"nvm_parser_version": v, "nvm_data_color_order": co, "nvm_data_orientation": o}, 6


def d_color_matrices(p):
    (num,) = struct.unpack_from("<H", p)
    ms, off = [], 2
    for _ in range(num):
        st, rg, bg, x, y = struct.unpack_from("<IHHHH", p, off)
        acc = struct.unpack_from("<9i", p, off + 12)
        pref = struct.unpack_from("<9i", p, off + 48)
        ms.append({"light_source": st, "chromaticity_rg_bg": [rg, bg], "cie_xy": [x, y],
                   "matrix_accurate": [fixed16(v) for v in acc],
                   "matrix_preferred": [fixed16(v) for v in pref]})
        off += 84
    return {"matrices": ms}, off


def d_analog_gain(p):
    ct, _, nseg, npair = struct.unpack_from("<4H", p)
    off, segs, pairs = 8, [], []
    for _ in range(nseg):
        gb, ge, cmin, cmax, cstep, m0, c0, m1, c1 = struct.unpack_from("<5I4h", p, off)
        segs.append({"gain_begin": fixed16(gb), "gain_end": fixed16(ge), "code_min": cmin,
                     "code_max": cmax, "code_step": cstep, "M0": m0, "C0": c0, "M1": m1, "C1": c1})
        off += 28
    for _ in range(npair):
        g, c = struct.unpack_from("<II", p, off)
        pairs.append({"gain": fixed16(g), "code": c}); off += 8
    return {"conversion_type": ct, "segments": segs, "pairs": pairs}, off


def d_digital_gain(p):
    gmin, gmax, step, frac = struct.unpack_from("<HHBB", p)
    d = {"gain_min": gmin, "gain_max": gmax, "step_size": step, "fraction_bits": frac}
    off = 6
    if len(p) >= 12:
        ct, npair, _ = struct.unpack_from("<3H", p, 6)
        off = 12
        d["conversion_type"] = ct
        d["pairs"] = [{"gain": fixed16(g), "code": c}
                      for g, c in struct.iter_unpack("<II", p[12:12 + 8 * npair])]
        off += 8 * npair
    return d, off


def d_sensor_metadata(p):
    cfg, data, ne, nc, nf, _ = struct.unpack_from("<HHBBBB", p)
    return {"num_cfg_blocks": cfg, "num_data_blocks": data, "num_exposure_sets": ne,
            "num_color_channels": nc, "max_faces": nf, "raw_blocks_bytes": len(p) - 8}, len(p)


def d_acm(p):
    nls, nsec = struct.unpack_from("<HH", p)
    off = 4
    hues = list(struct.unpack_from("<%dI" % nsec, p, off)); off += 4 * nsec
    ls = []
    for _ in range(nls):
        st, rg, bg, x, y = struct.unpack_from("<Iffff", p, off)
        info = {"light_source": st, "chromaticity_rg_bg": [rg, bg], "cie_xy": [x, y]}
        off += 20
        info["traditional_matrix"] = f32s(p, off, 9); off += 36
        info["sector_matrices"] = [f32s(p, off + 36 * i, 9) for i in range(nsec)]
        off += 36 * nsec
        ls.append(info)
    return {"sector_start_hues": hues, "light_sources": ls}, off


def d_lsc4x4(p):
    idx = list(struct.unpack_from("<16b", p))
    nls, ntab, gw, gh = struct.unpack_from("<4H", p, 16)
    hdr = {"grid_indices_4x4": [idx[i:i + 4] for i in range(0, 16, 4)],
           "num_light_srcs": nls, "num_tables": ntab, "grid_width": gw, "grid_height": gh}
    off, grids = 24, []
    for _ in range(nls):
        st, rg, bg, x, y, frac = struct.unpack_from("<IffffH", p, off)
        off += 22
        tabs = []
        for _ in range(ntab):
            # Intel's "(16-fraction_bits)Qfraction_bits" note reads inverted against
            # the data: unit gain (table minimum) sits at 1 << (16 - frac).
            tabs.append([v / (1 << (16 - frac)) for v in u16s(p, off, gw * gh)])
            off += 2 * gw * gh
        g = {"light_source": st, "chromaticity_rg_bg": [rg, bg], "cie_xy": [x, y],
             "fraction_bits": frac, "tables": tabs}
        grids.append(g)
    hdr["grids"] = grids
    return hdr, off


def d_gdc2(p):
    cs, rs, gw, gh, bw, bh, cnt = struct.unpack_from("<6hH", p)
    return {"col_start": cs, "row_start": rs, "grid_width": gw, "grid_height": gh,
            "block_width": bw, "block_height": bh, "grid_count": cnt,
            "raw_tail_bytes": len(p) - 14}, len(p)


def d_multi_gain(p):
    (num,) = struct.unpack_from("<I", p)
    return {"num_gains": num, "raw_bytes": len(p)}, len(p)


DECODERS = {
    1: d_comment, 2: d_general, 3: d_black_level, 5: d_saturation, 6: d_linearity,
    7: d_sensitivity, 9: d_noise, 13: d_optics, 15: d_chromaticity_response,
    17: d_nvm_info, 18: d_color_matrices, 19: d_analog_gain, 20: d_digital_gain,
    21: d_sensor_metadata, 22: d_gdc2, 25: d_acm, 28: d_lsc4x4,
    31: d_black_level_global, 33: d_lsc4x4, 34: d_multi_gain,
}


def walk(buf, off, end, out, path):
    """Emit records in buf[off:end]; descend into containers and container-bearing records."""
    while off + REC <= end:
        tag = buf[off:off + 4]
        if tag in TAGS or tag in LIST_TAGS:
            size = struct.unpack_from("<I", buf, off + 4)[0]
            hdr = HDR if tag in TAGS else 16
            walk(buf, off + hdr, off + size, out, path + [tag.decode()])
            off += size
            continue
        size, fmt, key, nid = struct.unpack_from("<IBBH", buf, off)
        if size < REC or off + size > end:
            out.append({"path": path, "offset": off, "error": "bad record size %d" % size})
            return
        if buf[off + REC:off + REC + 4] in TAGS + LIST_TAGS:
            walk(buf, off + REC, off + size, out, path + ["rec%d" % nid])
            off += size
            continue
        rec = {"path": "/".join(path), "offset": off, "size": size, "format_id": fmt,
               "key_id": key, "name_id": nid}
        payload = buf[off + REC:off + size]
        if path and path[-1] == "HALB":
            rec["name"] = "halb"
        elif nid in DECODERS:
            rec["name"] = CMC_NAMES.get(nid, "?")
            try:
                data, used = DECODERS[nid](payload)
                rec["data"] = data
                slack = len(payload) - used
                if slack < 0 or slack > 8:      # 64-bit alignment padding only
                    rec["error"] = "decoded %d of %d payload bytes" % (used, len(payload))
            except struct.error as e:
                rec["error"] = "struct: %s" % e
        elif nid < 256:
            rec["name"] = CMC_NAMES.get(nid, "?")
            rec["undecoded"] = True
        else:
            rec["name"] = "aiq_tuning"
        out.append(rec)
        off += size
    return out


def parse(path):
    buf = open(path, "rb").read()
    if buf[:4] not in TAGS + LIST_TAGS:
        raise SystemExit("%s: not an AIQB/CPFF file" % path)
    recs = []
    walk(buf, 0, len(buf), recs, [])
    return {"file": path, "bytes": len(buf), "records": recs}


def main(argv):
    if len(argv) < 2:
        print("usage: aiqb.py FILE.aiqb|FILE.cpf [--summary]", file=sys.stderr)
        return 2
    summary = "--summary" in argv
    for path in [a for a in argv[1:] if not a.startswith("--")]:
        res = parse(path)
        if summary:
            rs = [r for r in res["records"] if "name_id" in r]
            errs = [r for r in res["records"] if "error" in r]
            cmc = [r for r in rs if "data" in r]
            print("%s: %d records, %d CMC decoded, %d undecoded CMC, %d aiq_tuning, %d halb, %d errors" % (
                path, len(rs), len(cmc), sum("undecoded" in r for r in rs),
                sum(r["name"] == "aiq_tuning" for r in rs), sum(r["name"] == "halb" for r in rs), len(errs)))
            for r in rs:
                if r["name"] not in ("aiq_tuning", "halb"):
                    flag = r.get("error") or ("UNDECODED" if "undecoded" in r else "")
                    print("  %-40s id=%-3d size=%-7d %s" % (r["name"], r["name_id"], r["size"], flag))
            for r in errs:
                if "name_id" not in r:
                    print("  ERROR", r)
        else:
            json.dump(res, sys.stdout, indent=1)
            print()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
