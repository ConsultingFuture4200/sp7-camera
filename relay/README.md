# On-demand camera relay for ordinary applications

`sp7-camera-relay.py` bridges libcamera to a `v4l2loopback` node so apps that
only speak V4L2 / PipeWire-v4l2 (Chrome, OBS, etc.) see a normal webcam.

* Loopback: `modprobe v4l2loopback video_nr=60 card_label="Surface Camera" exclusive_caps=1`
  (done by `scripts/load-ipu4p.sh`).
* The relay keeps the loopback's output side open permanently but only starts
  the real camera when a consumer opens `/dev/video60`, using the
  `V4L2_EVENT_PRI_CLIENT_USAGE` event, and stops it 3 s after the last consumer
  leaves, so the IPU power island suspends between uses.
* Pipeline: `libcamerasrc` (rear, `\_SB_.PCI0.I2C3.CAMR`) → 3200x2400 → crop →
  scale → YUY2 1280x720 → `videoflip method=horizontal-flip` (the sensor
  delivers a mirrored image) → loopback. libcamera's timestamps are cleared
  before pushing; leaving them in gave 0.6–2.6 fps out of the loopback.
* Install: copy `sp7-camera-relay.service` and the `tuning.conf` drop-in to
  `~/.config/systemd/user/`, the two WirePlumber snippets to
  `~/.config/wireplumber/wireplumber.conf.d/`, `chrome-flags.conf` to
  `~/.config/`, then `systemctl --user enable --now sp7-camera-relay`.
