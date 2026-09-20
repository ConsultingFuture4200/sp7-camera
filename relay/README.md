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

## WirePlumber 0.5.17 bug: one disabled V4L2 device hides every later one

`50-sp7-ipu4.conf` disables the ~55 raw IPU4 V4L2 nodes with a
`monitor.v4l2.rules` rule (`device.disabled = true`). In WirePlumber 0.5.17
`monitors/v4l2/create-device.lua` handles that case by returning from an
**AsyncEventHook without `transition:advance()`**, so the dispatcher stalls and
no V4L2 device enumerated after the first disabled one is ever created. The
libcamera device hook and the V4L2 node hook both advance; only this one does
not. Symptom: the loopback appears in PipeWire only when udev happens to
enumerate it before an IPU node, and `IsCameraPresent` is false.

`wireplumber-scripts/monitors/v4l2/create-device.lua` is the upstream script
with the missing `transition:advance()` added. Install it as
`~/.local/share/wireplumber/scripts/monitors/v4l2/create-device.lua`
(WirePlumber does **not** look in `~/.config/wireplumber/scripts/`), restart
`wireplumber`, and all 55 raw nodes are disabled while the loopback becomes
`Surface Pro 7 Rear Camera (V4L2)` with the camera portal reporting a camera.
