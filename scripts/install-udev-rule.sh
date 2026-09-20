#!/bin/bash
# RUN AS ROOT. Makes PipeWire see /dev/video60 as a camera.
set -e
install -Dm644 /home/bobmob/Projects/sp7-camera/70-sp7-loopback.rules /etc/udev/rules.d/70-sp7-loopback.rules
udevadm control --reload
udevadm trigger --action=change --name-match=/dev/video60
udevadm settle
echo "udev now says: $(udevadm info -q property -n /dev/video60 | grep ID_V4L_CAPABILITIES)"
