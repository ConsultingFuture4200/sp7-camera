#!/bin/bash
# Step 9 — load the IPU4P stack in the required order. RUN AS ROOT, ONCE PER BOOT.
# Reload does not work (the CSE/firmware handshake wedges), so a failure here
# means reboot before retrying. Adapted from thisiscamk/sp7-ipu4-camera load-ipu4.sh.
LOG=/home/bobmob/Projects/sp7-camera/load-$(date +%H%M%S).log
exec > >(tee "$LOG") 2>&1
echo "=== $(date -Is)  kernel $(uname -r) ==="

step() { echo "--- modprobe $1"; modprobe "$1" || { echo "*** FAILED: $1 (rc=$?)"; FAILED=1; }; }

step ipu_bridge
step intel_ipu4p_isys_csslib
step intel_ipu4p_psys_csslib
step intel_ipu4p
step intel_ipu4p_psys

# Pin the psys IOMMU ON before isys registers ~55 video nodes, so udev's v4l_id
# probe storm cannot bounce the power island into a latched runtime-PM error.
MMU1=/sys/bus/intel-ipu4-bus/devices/intel-ipu4-mmu1/power/control
for i in $(seq 1 50); do [ -e "$MMU1" ] && break; sleep 0.1; done
if [ -e "$MMU1" ]; then echo on > "$MMU1" && echo "--- pinned mmu1 ON"; else echo "*** WARN: $MMU1 absent"; fi

step intel_ipu4p_isys
sleep 3

echo; echo "=== dmesg (camera-relevant) ==="
dmesg | grep -iE 'ipu|cpd|CSE|buttress|mmu|Connected|sensor|ov5693|ov8865|ov7251|int3472|csi' | tail -60

echo; echo "=== nodes ==="
ls -1 /dev/media* /dev/video* 2>/dev/null | head -20
echo "  media devices: $(ls /dev/media* 2>/dev/null | wc -l)   video nodes: $(ls /dev/video* 2>/dev/null | wc -l)"

echo; echo "=== VERDICT ==="
if [ -e /dev/media0 ]; then
  echo "  /dev/media0 PRESENT"
  dmesg | grep -E 'Connected [0-9]+ cameras|Found supported sensor' | tail -5
else
  echo "  *** /dev/media0 MISSING — see dmesg above"
fi

# Unpin after the probe storm so runtime PM can self-heal for app-driven use.
( sleep 30; echo auto > "$MMU1" 2>/dev/null; echo "--- unpinned mmu1 (auto)" >> "$LOG" ) &
disown
echo; echo "log: $LOG"
