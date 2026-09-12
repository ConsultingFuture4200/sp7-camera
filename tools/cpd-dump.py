#!/usr/bin/env python3
"""Dump an Intel IPU CPD firmware container.

Structure definitions and validation logic mirror
Kleist/ipu4-driver kernel/ipu4/ipu6-cpd.{c,h}:

  outer CPD ($CPD) -> [0]=manifest  [1]=metadata  [2]=moduledata
  moduledata       -> module_data_hdr + inner CPD (marker not checked
                      by the kernel; entry offsets are relative to the
                      start of the moduledata entry)
  metadata         -> cpd_metadata_extn + N * cpd_metadata_cmpnt,
                      one component per inner-CPD entry
"""
import struct, sys, hashlib

CPD_HDR_MARK = 0x44504324           # "$CPD"
MANIFEST_IDX, METADATA_IDX, MODULEDATA_IDX = 0, 1, 2
EXTN_TYPE_IUNIT = 0x10
IMG_TYPE = {0: "RESERVED", 1: "BOOTLOADER", 2: "MAIN_FIRMWARE"}
MAX_MANIFEST_SIZE, MAX_METADATA_SIZE = 2048 * 4, 64 * 1024
EXTN_SIZE = 28                      # sizeof(struct ipu6_cpd_metadata_extn)
CMPNT = {84: "IPU6 (48-byte hash)", 68: "IPU6SE / IPU4 (32-byte hash)"}
# The driver resolves servers by POSITION, not by the metadata id:
#   ipu6_configure_spc(): server_fw_addr = *(pkg_dir + (pkg_dir_idx + 1) * 2)
#   PKG_DIR_ENT_LEN == 2, so component index i sits at pkg_dir[2 * (1 + i)]
#   => IPU6_CPD_PKG_DIR_PSYS_SERVER_IDX (0) is component index 0
#      IPU6_CPD_PKG_DIR_ISYS_SERVER_IDX (1) is component index 1
# The metadata 'id' is a separate type tag, FIELD_PREP'd into PKG_DIR_TYPE_MASK.
CMPNT_ROLE = {0: "PSYS_SERVER", 1: "ISYS_SERVER"}

def rdhdr(buf, off):
    mark, ent_cnt, hv, ev, hl = struct.unpack_from("<IIBBB", buf, off)
    return mark, ent_cnt, hv, ev, hl

def rdents(buf, base, ent_cnt, hdr_len):
    out = []
    for i in range(ent_cnt):
        name, off, ln = struct.unpack_from("<12sII", buf, base + hdr_len + i * 24)
        out.append((name.rstrip(b"\0").decode("ascii", "replace"), off, ln))
    return out

def main(path):
    buf = open(path, "rb").read()
    fails = []
    def chk(label, cond, detail=""):
        print(f"  [{'PASS' if cond else 'FAIL'}] {label}{('  ' + detail) if detail else ''}")
        if not cond: fails.append(label)

    print(f"file   : {path}")
    print(f"size   : {len(buf)} bytes")
    print(f"sha256 : {hashlib.sha256(buf).hexdigest()}")

    mark, ent_cnt, hv, ev, hl = rdhdr(buf, 0)
    layout = {0x14: "CSE 1.7 (IPU6)", 0x10: "CSE 1.6 (IPU6SE/IPU4)"}.get(hl, "unknown")
    print(f"\n== outer CPD header ==")
    print(f"  hdr_mark : 0x{mark:08x} ({'$CPD' if mark == CPD_HDR_MARK else 'BAD'})")
    print(f"  ent_cnt  : {ent_cnt}    hdr_ver: {hv}  ent_ver: {ev}  hdr_len: 0x{hl:x}  [{layout}]")

    ents = rdents(buf, 0, ent_cnt, hl)
    print(f"\n== outer CPD entries ==")
    print(f"  {'idx':>3}  {'name':<12} {'offset':>10} {'length':>10}  role")
    roles = {MANIFEST_IDX: "MANIFEST", METADATA_IDX: "METADATA", MODULEDATA_IDX: "MODULEDATA"}
    for i, (n, o, l) in enumerate(ents):
        print(f"  {i:>3}  {n:<12} {o:>10} {l:>10}  {roles.get(i,'')}")

    # ---- metadata ----
    _, moff, mlen = ents[METADATA_IDX]
    extn_type, extn_len, img_type = struct.unpack_from("<III", buf, moff)
    payload = mlen - EXTN_SIZE
    cmpnt_size = next((s for s in (68, 84) if payload % s == 0), None)
    ncmp = payload // cmpnt_size if cmpnt_size else 0
    print(f"\n== metadata ==")
    print(f"  extn_type : 0x{extn_type:x} ({'IUNIT' if extn_type == EXTN_TYPE_IUNIT else 'unexpected'})")
    print(f"  img_type  : {img_type} ({IMG_TYPE.get(img_type,'unknown')})")
    print(f"  payload   : {payload} bytes -> {ncmp} x {cmpnt_size}-byte components"
          f"  [{CMPNT.get(cmpnt_size,'?')}]")

    # ---- moduledata ----
    _, doff, dlen = ents[MODULEDATA_IDX]
    mh = struct.unpack_from("<IIIIII", buf, doff)
    sys_ver = buf[doff+24:doff+35].rstrip(b"\0").decode("ascii", "replace")
    fw_arch = buf[doff+35:doff+42].rstrip(b"\0").decode("ascii", "replace")
    print(f"\n== moduledata header ==")
    print(f"  hdr_len         : 0x{mh[0]:x}")
    print(f"  endian          : 0x{mh[1]:x}")
    print(f"  fw_pkg_date     : 0x{mh[2]:08x}")
    print(f"  hive_sdk_date   : 0x{mh[3]:08x}")
    print(f"  compiler_date   : 0x{mh[4]:08x}")
    print(f"  target_platform : 0x{mh[5]:x}")
    print(f"  sys_ver         : {sys_ver!r}")
    print(f"  fw_arch_ver     : {fw_arch!r}")

    ibase = doff + mh[0]
    imark, ient, ihv, iev, ihl = rdhdr(buf, ibase)
    print(f"\n== inner CPD (moduledata @ {ibase}) ==")
    print(f"  hdr_mark : 0x{imark:08x} (kernel does not check the inner marker)")
    print(f"  ent_cnt  : {ient}    hdr_len: 0x{ihl:x}")

    ients = rdents(buf, ibase, ient, ihl)
    print(f"\n== firmware components ==")
    print(f"  {'idx':>3}  {'type':>5} {'role (by index)':<15} {'rel.off':>10} {'length':>10} "
          f"{'entry_pt':>10} {'icache':>10}  sha256[:16]")
    for i, (n, o, l) in enumerate(ients):
        if cmpnt_size and i < ncmp:
            c = moff + EXTN_SIZE + i * cmpnt_size
            cid, csize, cver = struct.unpack_from("<III", buf, c)
            hlen = cmpnt_size - 36
            h = buf[c+12:c+12+hlen].hex()[:16]
            ep, ic = struct.unpack_from("<II", buf, c + 12 + hlen)
        else:
            cid = csize = ep = ic = 0; h = "-"
        role = CMPNT_ROLE.get(i, "client PG")
        print(f"  {i:>3}  {cid:>5} {role:<15} {o:>10} {l:>10} "
              f"0x{ep:08x} 0x{ic:08x}  {h}")

    # sanity: metadata component sizes should match inner entry lengths
    if cmpnt_size and ncmp == ient:
        mism = []
        for i, (_, o, l) in enumerate(ients):
            c = moff + EXTN_SIZE + i * cmpnt_size
            _, csize, _ = struct.unpack_from("<III", buf, c)
            if csize != l: mism.append((i, l, csize))
        print()
        chk("metadata component count == inner CPD entry count", True, f"{ncmp}")
        chk("component sizes agree between metadata and inner CPD",
            not mism, "" if not mism else f"mismatches: {mism}")

    print(f"\n== ipu6_cpd_validate_cpd_file ==")
    chk("hdr_mark == $CPD", mark == CPD_HDR_MARK)
    chk("all outer entries within file",
        all(o <= len(buf) and o + l <= len(buf) for _, o, l in ents))
    chk("manifest <= MAX_MANIFEST_SIZE", ents[MANIFEST_IDX][2] <= MAX_MANIFEST_SIZE,
        f"{ents[MANIFEST_IDX][2]} <= {MAX_MANIFEST_SIZE}")
    chk("metadata size within bounds", EXTN_SIZE <= mlen <= MAX_METADATA_SIZE, f"{mlen}")
    chk("extn_type == IUNIT", extn_type == EXTN_TYPE_IUNIT)
    chk("img_type == MAIN_FIRMWARE", img_type == 2)
    chk("metadata size multiple of cpd_metadata_cmpnt_size", cmpnt_size is not None,
        f"cmpnt_size={cmpnt_size}")
    chk("all inner entries within moduledata",
        all(o <= dlen and o + l <= dlen for _, o, l in ients))

    print(f"\n== RESULT: {'VALIDATES' if not fails else 'FAILS (' + ', '.join(fails) + ')'} ==")
    return 1 if fails else 0

if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
