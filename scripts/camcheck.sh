#!/bin/bash
# Verify the on-demand route: IPU4P stack -> sp7-camera-relay -> v4l2loopback
# (/dev/video60) -> PipeWire -> camera portal -> Chrome. No sudo.
# The camera itself is only ON while an app is streaming; idle is normal.
ok() { printf '  %-36s %s\n' "$1" "$2"; }
echo "=== kernel + stack ==="
[[ $(uname -r) == 6.19.8-arch1-1-ipu4p ]] && ok "linux-ipu4p" "yes" || { ok "linux-ipu4p" "NO - pick it in the Limine menu"; exit 1; }
[ -e /dev/media0 ] && ok "IPU4P stack loaded" "yes" || { ok "IPU4P stack loaded" "NO - sudo ~/loadcam"; exit 1; }
python3 -c "import os; os.close(os.open('/dev/video42', os.O_RDWR))" 2>/dev/null \
  && ok "camera island healthy" "yes" || { ok "camera island healthy" "NO (EIO) - reboot"; exit 1; }

echo "=== loopback + relay ==="
for d in 60 61; do
  if [ -e /dev/video$d ]; then
    ok "/dev/video$d" "$(v4l2-ctl -d /dev/video$d --info 2>/dev/null | awk -F': *' '/Card type/{print $2}')"
  else
    ok "/dev/video$d" "MISSING - sudo ~/loadcam (video61: sudo ~/camfront once)"
  fi
done
ok "relay services (rear front)" "$(systemctl --user is-active sp7-camera-relay sp7-camera-relay-front | paste -sd' ')"
last=$(journalctl --user -u sp7-camera-relay -n 50 --no-pager -o cat 2>/dev/null | grep -E 'camera ON|camera OFF|idle, feeding|waiting for' | tail -1)
case "$last" in
  *"camera ON"*)  ok "camera right now" "ON (an app is streaming)";;
  *"camera OFF"*|*"idle, feeding"*) ok "camera right now" "off - starts when an app streams";;
  *"waiting for"*) ok "camera right now" "relay waiting for /dev/video60";;
  *) ok "camera right now" "unknown";;
esac
journalctl --user -u sp7-camera-relay -n 4 --no-pager -o cat 2>/dev/null | sed 's/^/    /'

echo "=== PipeWire + portal ==="
node=$(pw-dump 2>/dev/null | python3 -c "
import json,sys
for o in json.load(sys.stdin):
    p=(o.get('info') or {}).get('props') or {}
    if str(p.get('api.v4l2.path','')).startswith('/dev/video6') and str(p.get('media.class','')).startswith('Video/Source'):
        print(p.get('node.description') or p.get('node.name'))" 2>/dev/null | paste -sd'|')
ok "PipeWire camera nodes" "${node:-NONE}"
p=$(busctl --user get-property org.freedesktop.portal.Desktop /org/freedesktop/portal/desktop org.freedesktop.portal.Camera IsCameraPresent 2>/dev/null)
ok "portal IsCameraPresent" "${p:-unknown}"

echo "=== Chrome ==="
grep -q WebRtcPipeWireCamera ~/.config/chrome-flags.conf 2>/dev/null && ok "PipeWire camera flag" "set" || ok "PipeWire camera flag" "NOT set"
pgrep -f /opt/google/chrome/chrome >/dev/null && ok "Chrome" "running - quit fully and relaunch once the node shows" || ok "Chrome" "not running"
