#!/bin/bash
# First light — capture raw frames via the CSI2 BE SOC path.
#   sudo ~/cap rear    (ov8865, 3264x2448, CSI-2 port 0)
#   sudo ~/cap front   (ov5693, 2592x1944, CSI-2 port 2)
set -e
CAM="${1:-rear}"
if [ "$CAM" = front ]; then SENSOR='ov5693 1-0036'; PORT=2; RES=2592x1944
else                        SENSOR='ov8865 2-0010'; PORT=0; RES=3264x2448; fi
FMT=SBGGR10_1X10
OUT=/home/bobmob/Projects/sp7-camera/caps/$CAM.raw
TCK=/home/bobmob/Projects/sp7-camera/build/tck

echo "=== configuring pipeline: $CAM ($SENSOR -> CSI-2 $PORT -> BE SOC) ==="
# No global `media-ctl -r`: after a failed stream the driver can leave an
# entity flagged as streaming, and then resetting ANY link returns EBUSY even
# with nothing open. Touch only what this capture needs instead.
if [ "$CAM" = front ]; then OTHER=0; else OTHER=2; fi
# the other port's route into BE SOC:0 must be off (two sources on one pad is invalid);
# BE SOC links are DYNAMIC so this is allowed even in the stuck state
python3 "$TCK/enable-link.py" "Intel IPU4 CSI-2 $OTHER:1" "Intel IPU4 CSI2 BE SOC:0" 0x4 >/dev/null 2>&1 || true
media-ctl -d /dev/media0 -V "\"$SENSOR\":0 [fmt:$FMT/$RES]"
media-ctl -d /dev/media0 -V "\"Intel IPU4 CSI-2 $PORT\":0 [fmt:$FMT/$RES]"
media-ctl -d /dev/media0 -V "\"Intel IPU4 CSI-2 $PORT\":1 [fmt:$FMT/$RES]"
# sensor -> CSI-2 is a normal link: only set it if it is not already enabled
if ! media-ctl -d /dev/media0 -p 2>/dev/null | grep -A40 "entity.*\"\?$SENSOR" | grep -qE "CSI-2 $PORT\":0 \[ENABLED"; then
  media-ctl -d /dev/media0 -l "\"$SENSOR\":0 -> \"Intel IPU4 CSI-2 $PORT\":0 [1]"
fi
python3 "$TCK/enable-link.py" "Intel IPU4 CSI-2 $PORT:1" "Intel IPU4 CSI2 BE SOC:0"
python3 "$TCK/enable-link.py" "Intel IPU4 CSI2 BE SOC:8" "Intel IPU4 BE SOC capture 0:0"
media-ctl -d /dev/media0 -V "\"Intel IPU4 CSI2 BE SOC\":0 [fmt:$FMT/$RES]"
media-ctl -d /dev/media0 -V "\"Intel IPU4 CSI2 BE SOC\":8 [fmt:$FMT/$RES]"

DEV=$(media-ctl -d /dev/media0 -e "Intel IPU4 BE SOC capture 0")
W=${RES%x*}; H=${RES#*x}

# Raise exposure/gain or the frame is near-black.
SD=$(media-ctl -d /dev/media0 -e "$SENSOR")
v4l2-ctl -d "$SD" --set-ctrl exposure=1900 2>/dev/null || true
v4l2-ctl -d "$SD" --set-ctrl analogue_gain=127 2>/dev/null || true

echo "=== capturing 3 frames from $DEV ($RES) ==="
rm -f "$OUT"
timeout 45 v4l2-ctl -d "$DEV" \
  --set-fmt-video=width=$W,height=$H,pixelformat=BG10 \
  --stream-mmap=4 --stream-count=3 --stream-to="$OUT" && echo "  capture returned 0" || echo "  *** capture FAILED rc=$?"

echo "=== result ==="
ls -l "$OUT" 2>/dev/null | sed 's/^/  /' || echo "  no file produced"
echo "  expected: $((W*H*2*3)) bytes for 3 frames"
echo
echo "=== bounce count / stream health ==="
dmesg | grep -iE 'bounce|verify_stream|frames_done|STR2MMIO|sync error|dphy|no clean frame' | tail -8 | sed 's/^/  /'
