#!/usr/bin/env python3
"""Convert an Intel .cpf/.aiqb tuning file into a libcamera 'simple' IPA tuning file.

The simple (software ISP) IPA supports BlackLevel, Awb, Ccm, Adjust (gamma/
contrast) and Agc. Of the data Intel ships, the colour correction matrices are
the part worth transferring: advanced_color_matrices holds one
`traditional_matrix` per illuminant, already normalised to unity row sums, which
is exactly libcamera's CCM convention. Each illuminant carries CIE xy, so the
colour temperature libcamera keys on is derived with McCamy's approximation.

Black level is deliberately NOT emitted: the value in the .cpf describes the
pedestal under Windows' sensor configuration, which need not match what the
Linux driver programs. libcamera's BlackLevel algorithm measures it instead.

Usage: cpf2libcamera.py FILE.cpf SENSOR > /usr/share/libcamera/ipa/simple/SENSOR.yaml
"""
import json, subprocess, sys, os

def cct_mccamy(x, y):
    """CIE xy -> correlated colour temperature (McCamy 1992)."""
    n = (x - 0.3320) / (0.1858 - y)
    return 449 * n**3 + 3525 * n**2 + 6823.3 * n + 5520.33

def main(path, sensor):
    here = os.path.dirname(os.path.abspath(__file__))
    aiqb = os.path.join(os.path.dirname(here), 'aiqb.py')
    recs = json.loads(subprocess.check_output([sys.executable, aiqb, path]))['records']
    acm = next(r for r in recs if r.get('name') == 'advanced_color_matrices')['data']

    entries = []
    for ls in acm['light_sources']:
        x, y = ls['cie_xy']
        if x <= 0 or y <= 0:
            print(f"# skipped light_source {ls['light_source']}: no CIE xy", file=sys.stderr)
            continue
        cct = cct_mccamy(x, y)
        if not (1500 < cct < 15000):
            print(f"# skipped light_source {ls['light_source']}: implausible CCT {cct:.0f}K", file=sys.stderr)
            continue
        m = ls['traditional_matrix']
        sums = [sum(m[i*3:i*3+3]) for i in range(3)]
        if any(abs(s - 1.0) > 0.01 for s in sums):
            print(f"# skipped light_source {ls['light_source']}: row sums {sums} not unity", file=sys.stderr)
            continue
        entries.append((round(cct), m, ls['light_source']))

    entries.sort(key=lambda e: e[0])
    # libcamera interpolates between CCMs by CT; duplicates would be ambiguous
    seen, uniq = set(), []
    for cct, m, src in entries:
        if cct in seen:
            continue
        seen.add(cct); uniq.append((cct, m, src))

    out = []
    out.append('# SPDX-License-Identifier: CC0-1.0')
    out.append('%YAML 1.1')
    out.append('---')
    out.append(f'# libcamera "simple" IPA tuning for {sensor}.')
    out.append(f'# Colour matrices converted from {os.path.basename(path)}')
    out.append('# (Intel CPF advanced_color_matrices -> traditional_matrix per illuminant,')
    out.append('#  colour temperature derived from CIE xy via McCamy\'s approximation).')
    out.append('# Black level is intentionally omitted so the BlackLevel algorithm measures it;')
    out.append('# the pedestal in the CPF reflects Windows\' sensor configuration, not this driver\'s.')
    out.append('version: 1')
    out.append('algorithms:')
    out.append('  - BlackLevel:')
    out.append('  - Awb:')
    out.append('  - Ccm:')
    out.append('      ccms:')
    for cct, m, src in uniq:
        out.append(f'        # Intel light_source {src}')
        out.append(f'        - ct: {cct}')
        out.append(f'          ccm: [ {m[0]: .4f}, {m[1]: .4f}, {m[2]: .4f},')
        out.append(f'                 {m[3]: .4f}, {m[4]: .4f}, {m[5]: .4f},')
        out.append(f'                 {m[6]: .4f}, {m[7]: .4f}, {m[8]: .4f} ]')
    out.append('  - Adjust:')
    out.append('  - Agc:')
    out.append('...')
    print('\n'.join(out))
    print(f"# emitted {len(uniq)} CCMs, {uniq[0][0]}K..{uniq[-1][0]}K", file=sys.stderr)

if __name__ == '__main__':
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
