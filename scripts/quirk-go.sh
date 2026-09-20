#!/bin/bash
# One shot: install the BTF-stripped quirk module, load isys, run the front A/B.
# RUN AS ROOT:  sudo ~/quirkgo
set -u
if [[ $(uname -r) != 6.19.8-arch1-1-ipu4p ]]; then echo "ABORT: need the linux-ipu4p kernel"; exit 2; fi
DIR=/home/bobmob/Projects/sp7-camera
LOG=$DIR/quirk-go-$(date +%H%M%S).log
exec > >(tee "$LOG") 2>&1
echo "### quirk-go $(date -Is)  log: $LOG"

echo "== 1. install module (BTF stripped)"
/home/bobmob/instmod | grep -v -e Reboot -e '^$' | sed 's/^/   /'

if lsmod | grep -q '^intel_ipu4p_isys'; then
  echo "== 2. isys already loaded -> unloading to pick up the new module"
  modprobe -r intel_ipu4p_isys || { echo "   could not unload isys (busy?) -> reboot then rerun"; exit 3; }
fi
echo "== 2. modprobe intel_ipu4p_isys"
since=$(date '+%Y-%m-%d %H:%M:%S')
if ! modprobe intel_ipu4p_isys; then
  echo "   FAILED"; journalctl -k --since "$since" --no-pager | tail -20; exit 3
fi
sleep 3
P=/sys/module/intel_ipu4p_isys/parameters
echo "   quirk param: $(cat $P/sp7_front_timing_quirk 2>&1)  dsettle=$(cat $P/csi2_dsettle) csettle=$(cat $P/csi2_csettle)"
echo "   taint: $(cat /proc/sys/kernel/tainted)  media: $(ls /dev/media* 2>&1 | tr '\n' ' ')"
journalctl -k --since "$since" --no-pager | grep -iE 'ipu|isys|csi2|ov5693|ov8865' | tail -12 | sed 's/^/   /'
[ -e /dev/video42 ] || { echo "   no /dev/video42 -> isys probe did not finish; see log"; exit 3; }

echo "== 3. front A/B (quirk on, then off with 1000/1800)"
bash $DIR/front-ab.sh
echo "### done $(date -Is)  log: $LOG"
