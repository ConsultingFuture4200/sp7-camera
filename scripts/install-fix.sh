#!/bin/bash
# Install the enum_framesizes module fix + make the CSI-2 settle values persist.
set -e
SRC=/home/bobmob/Projects/sp7-camera
install -Dm644 "$SRC/intel-ipu4p-isys.ko.zst" \
  /usr/lib/modules/6.19.8-arch1-1-ipu4p/updates/intel-ipu4p-isys.ko.zst
echo "module installed: $(stat -c%s /usr/lib/modules/6.19.8-arch1-1-ipu4p/updates/intel-ipu4p-isys.ko.zst) bytes"
install -Dm644 "$SRC/ipu4p.conf" /etc/modprobe.d/ipu4p.conf
echo "modprobe.d updated:"
grep -E '^options' /etc/modprobe.d/ipu4p.conf | sed 's/^/    /'
depmod -a 6.19.8-arch1-1-ipu4p
echo "depmod done -> $(modinfo -F filename -k 6.19.8-arch1-1-ipu4p intel-ipu4p-isys)"
echo
echo "Reboot, then:  sudo ~/loadcam   (settle values now applied automatically)"
