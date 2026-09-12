#!/bin/bash
# Install the patched isys module into updates/ (takes precedence over kernel/)
set -e
SRC=/home/bobmob/Projects/sp7-camera/intel-ipu4p-isys.ko.zst
DST=/usr/lib/modules/6.19.8-arch1-1-ipu4p/updates/intel-ipu4p-isys.ko.zst
install -Dm644 "$SRC" "$DST"
echo "installed: $(ls -l "$DST" | awk '{print $5}') bytes"
depmod -a 6.19.8-arch1-1-ipu4p
echo "depmod done; modprobe will now resolve to:"
modinfo -F filename -k 6.19.8-arch1-1-ipu4p intel-ipu4p-isys
echo
echo "Reboot next:  sudo systemctl reboot"
