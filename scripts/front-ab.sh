#!/bin/bash
# A/B the Surface Pro 7 front-camera receiver timing. RUN AS ROOT (param writes).
# quirk=1: Windows' fixed receiver timing (1155/1269 ticks, georgemihaila's trace)
# quirk=0: the driver's calculated timing + our best settle override (1000/1800)
# Captures go through libcamera (tools/front-test.py); each try is a cold start.
if [[ $(uname -r) != 6.19.8-arch1-1-ipu4p ]]; then echo "ABORT: need the linux-ipu4p kernel"; exit 2; fi
P=/sys/module/intel_ipu4p_isys/parameters
ISL=/sys/bus/intel-ipu4-bus/devices/intel-ipu60/power/runtime_status
DIR=/home/bobmob/Projects/sp7-camera
N=${N:-6}
export LIBCAMERA_IPA_CONFIG_PATH=$DIR/ipa HOME=/home/bobmob
[ -e $P/sp7_front_timing_quirk ] || { echo "ABORT: module has no sp7_front_timing_quirk param - the new module is not installed/loaded"; exit 2; }
python3 -c "import os; os.close(os.open('/dev/video42', os.O_RDWR))" 2>/dev/null || { echo "ABORT: /dev/video42 EIO - reboot"; exit 2; }
wait_idle() { for i in $(seq 1 40); do [ "$(cat $ISL)" = suspended ] && return; sleep 1; done; }
run() {   # $1 label
  local ok=0 b bl="" since res r
  echo "  == $1 =="
  for i in $(seq 1 $N); do
    wait_idle; since=$(date '+%Y-%m-%d %H:%M:%S')
    res=$(cd $DIR && timeout 60 /usr/bin/python3 tools/front-test.py "$1-$i" 2>&1 | grep -E "^\s+$1-$i")
    b=$(journalctl -k --since "$since" --no-pager | grep -c 'bouncing sensor')
    if printf '%s' "$res" | grep -qE 'p50=[1-9]'; then r=OK; ok=$((ok+1)); bl="$bl $b"; else r=fail; fi
    printf '    try %-2s %-4s bounces=%-3s %s\n' "$i" "$r" "$b" "$(printf '%s' "$res" | grep -oE 'first frame after [0-9.]+s')"
    sleep 2
  done
  echo "  -> $1: $ok/$N locked; bounces when locked:$bl"
  journalctl -k --since "-20 min" --no-pager | grep -c 'SP7 front timing quirk applied' | sed 's/^/     (quirk-applied log lines so far: /; s/$/)/'
}
echo "### front ov5693 A/B, $N cold starts each, $(date -Is)"
echo 1 > $P/sp7_front_timing_quirk; run "quirk-on"
echo 0 > $P/sp7_front_timing_quirk; echo 1000 > $P/csi2_dsettle; echo 1800 > $P/csi2_csettle; run "quirk-off-1000-1800"
echo 1 > $P/sp7_front_timing_quirk
echo "### restored: quirk=$(cat $P/sp7_front_timing_quirk)"
