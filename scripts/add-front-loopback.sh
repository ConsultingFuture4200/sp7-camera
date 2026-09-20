#!/bin/bash
# Add the FRONT camera loopback (/dev/video61). RUN AS ROOT: sudo ~/camfront
set -u
U=bobmob; RT="sudo -u $U XDG_RUNTIME_DIR=/run/user/$(id -u $U) DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/$(id -u $U)/bus"
DIR=/home/$U/Projects/sp7-camera
echo "== 1. config (written first, so a failed reload can be retried)"
cat > /etc/modprobe.d/v4l2loopback-sp7.conf <<'CONF'
# Surface Pro 7 camera loopbacks, fed on demand by sp7-camera-relay (rear) and
# sp7-camera-relay-front. exclusive_caps=1: announce a capture device only while fed.
# card_label is an array of strings: ONE quoted string, comma separated
# (separate quoted strings leak the quote characters into the names).
options v4l2loopback devices=2 video_nr=60,61 card_label="Surface Pro 7 Rear Camera,Surface Pro 7 Front Camera" exclusive_caps=1,1 max_buffers=2
CONF
grep options /etc/modprobe.d/v4l2loopback-sp7.conf | sed 's/^/   /'
install -m644 $DIR/70-sp7-loopback.rules /etc/udev/rules.d/70-sp7-loopback.rules
udevadm control --reload
echo "== 2. stop the relays and wait for the loopbacks to be released"
$RT systemctl --user stop sp7-camera-relay.service sp7-camera-relay-front.service
for i in 1 2 3 4 5 6 7 8 9 10; do
  holders=$(for p in /proc/[0-9]*; do ls -l $p/fd 2>/dev/null | grep -qE '/dev/video6[01]' && echo "$(cat $p/comm)($(basename $p))"; done | paste -sd' ')
  [ -z "$holders" ] && break; sleep 1
done
[ -n "$holders" ] && echo "   still open by: $holders"
echo "== 3. reload v4l2loopback"
if ! modprobe -r v4l2loopback; then
  echo "   cannot unload v4l2loopback (busy: ${holders:-?}) - close the app using the camera and rerun"
  $RT systemctl --user start sp7-camera-relay.service sp7-camera-relay-front.service; exit 1
fi
modprobe v4l2loopback || { journalctl -k -n 3 --no-pager | sed 's/^/   /'; exit 1; }
sleep 1; udevadm settle
for d in 60 61; do echo "   /dev/video$d: [$(v4l2-ctl -d /dev/video$d --info 2>/dev/null | awk -F': *' '/Card type/{print $2}')]  $(udevadm info -q property /dev/video$d | grep -oE 'ID_V4L_CAPABILITIES=.*')"; done
echo "== 4. start both relays"
$RT systemctl --user start sp7-camera-relay.service sp7-camera-relay-front.service
sleep 8
$RT systemctl --user is-active sp7-camera-relay.service sp7-camera-relay-front.service | paste -sd' ' | sed 's/^/   relays: /'
echo "== 5. PipeWire"
$RT wpctl status 2>/dev/null | sed -n '/^Video/,/Streams/p' | grep -E '[0-9]+\. ' | sed 's/^/   /'
echo "done. Chrome: quit fully and relaunch to see both cameras."
