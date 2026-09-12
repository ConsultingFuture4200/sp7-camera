#!/bin/bash
# Step 8 verification — run AFTER booting the linux-ipu4p entry.
# Read-only. Loads nothing. Safe to run repeatedly.
echo "=== kernel ==="
printf '  running: %s\n' "$(uname -r)"
if [[ $(uname -r) == 6.19.8-arch1-1-ipu4p ]]; then echo "  ✓ on the new kernel"
else echo "  ✗ NOT on the new kernel — you booted $(uname -r); pick 'linux-ipu4p' in the Limine menu"; exit 1; fi

echo "=== ISP visible? ==="
lspci -nnks 00:05.0 | sed 's/^/  /'

echo "=== sensors (expect: deferred, waiting for fwnode graph endpoint) ==="
sudo dmesg 2>/dev/null | grep -iE 'deferred probe pending|ov5693|ov8865|ov7251' | grep -v 'supply d' | tail -6 | sed 's/^/  /'

echo "=== camera modules must NOT be loaded (they are blacklisted) ==="
for m in intel_ipu4p intel_ipu4p_isys intel_ipu4p_psys ipu_bridge; do
  printf '  %-22s ' "$m"; lsmod | grep -qw "$m" && echo "LOADED (unexpected!)" || echo "not loaded ✓"
done

echo "=== no /dev/video* yet (expected at this stage) ==="
ls /dev/video* /dev/media* 2>/dev/null | sed 's/^/  /' || echo "  none ✓"

echo "=== firmware present ==="
ls -l /usr/lib/firmware/ipu4p_cpd.bin 2>&1 | sed 's/^/  /'

echo "=== modprobe config active ==="
grep -E '^(options|blacklist)' /etc/modprobe.d/ipu4p.conf | sed 's/^/  /'

echo "=== the old kernel is still there ==="
ls -d /usr/lib/modules/*/ | sed 's/^/  /'

echo
echo "If all of the above looks right, resume the session and we do step 9"
echo "(loading the module stack in order). Reload does NOT work — one load"
echo "per boot, so a failed attempt means another reboot."
