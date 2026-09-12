#!/bin/bash
# Sweep CSI-2 settle counts for the front ov5693. Runtime params — no reload needed.
# Window per the port author: dsettle 661..1103, csettle 684..2247 (@419.2MHz).
# Baseline calc minimum (661/684) is ~40% reliable; mid-window should be better.
P=/sys/module/intel_ipu4p_isys/parameters
CAP=/home/bobmob/Projects/sp7-camera/capture.sh
OUT=/home/bobmob/Projects/sp7-camera/caps/front.raw
EXPECT=30233088

cycle_island() {
  echo auto > /sys/bus/intel-ipu4-bus/devices/intel-ipu4-mmu1/power/control 2>/dev/null
  echo on   > /sys/bus/intel-ipu4-bus/devices/intel-ipu4-mmu0/power/control 2>/dev/null
  sleep 1
  echo auto > /sys/bus/intel-ipu4-bus/devices/intel-ipu4-mmu0/power/control 2>/dev/null
  sleep 5
  echo on   > /sys/bus/intel-ipu4-bus/devices/intel-ipu4-mmu1/power/control 2>/dev/null
  sleep 1
}

try() {  # $1=dsettle $2=csettle
  echo "$1" > $P/csi2_dsettle; echo "$2" > $P/csi2_csettle
  printf '### dsettle=%-5s csettle=%-5s ' "$1" "$2"
  dmesg -C >/dev/null 2>&1
  rm -f "$OUT"
  timeout 60 "$CAP" front >/tmp/fs.out 2>&1
  sz=$(stat -c%s "$OUT" 2>/dev/null || echo 0)
  err=$(dmesg | grep -c 'non-recoverable synchronization')
  if [ "$sz" = "$EXPECT" ]; then echo "-> *** SUCCESS $sz bytes (dphy errs during: $err)"; return 0
  else echo "-> fail (got $sz bytes, $err dphy sync errors)"; fi
  cycle_island
  return 1
}

echo "=== front ov5693 settle sweep — current: dsettle=$(cat $P/csi2_dsettle) csettle=$(cat $P/csi2_csettle) ==="
for pair in "880 1400" "880 684" "661 1400" "1000 2000" "750 1000" "1103 2247"; do
  set -- $pair
  if try "$1" "$2"; then
    echo
    echo "WINNER: csi2_dsettle=$1 csi2_csettle=$2"
    echo "  (880 is inside the rear ov8865 window too, so a shared value may serve both)"
    exit 0
  fi
done
echo
echo "No settle value worked. Restoring auto-calc (-1) — next step is the PHY bb sweep."
echo -1 > $P/csi2_dsettle; echo -1 > $P/csi2_csettle
exit 1
