Small follow-up: **both cameras now show up in Chrome** on this SP7, through
stock Arch PipeWire 1.6.8 / WirePlumber 0.5.17, no patched libcamera or
PipeWire. Two findings on the way there that may save others time.

## WirePlumber 0.5.17 bug: one disabled V4L2 device hides every later one

The IPU4 driver exposes ~55 raw V4L2 capture nodes, and the natural thing is
to hide them from apps with a `monitor.v4l2.rules` rule setting
`device.disabled = true`. With that rule in place my loopback camera only
appeared in PipeWire sometimes, and `IsCameraPresent` on the camera portal
was false.

Cause: `monitors/v4l2/create-device.lua` handles the disabled case by
returning from an `AsyncEventHook` **without `transition:advance ()`**, so the
event dispatcher stalls and no V4L2 device enumerated after the first disabled
one is ever created. Whether your camera shows up depends on udev enumeration
order. The libcamera device hook and the V4L2 node hook both advance; only
this one does not. A one-line fix (the script with the missing advance) goes
in `~/.local/share/wireplumber/scripts/monitors/v4l2/create-device.lua` —
WirePlumber does not look in `~/.config/wireplumber/scripts/`. With that,
all 55 raw nodes are disabled and the cameras are created every time.
@Elefantenjongleur this may be why you had to disable the V4L2 monitor
entirely rather than filter it.

## The app-facing setup

Since PipeWire's own libcamera plugin never hands these cameras to WirePlumber
here, apps get them through `v4l2loopback` (two devices, `exclusive_caps=1`)
fed by a small on-demand relay per camera: it subscribes to
`V4L2_EVENT_PRI_CLIENT_USAGE` on the loopback and only opens the real camera
while an app is streaming, so the isys power island suspends between uses and
a bad start cannot wedge it. libcamera → crop 16:9 → 1280x720 YUY2 →
un-mirror → loopback. Numbers through PipeWire on the i5-1035G4:

| | rear ov8865 | front ov5693 |
|---|---|---|
| source mode | 3200x2400 | 2560x1600 |
| delivered | 15 fps | 28.7 fps |
| first frame after the app opens it | 0.7 s | 0.4 s |
| camera off after the app stops | 3 s | 3 s |

The front rate is only possible because of the receiver timing from the
previous comment (0 sensor bounces on every start). Two small gotchas in the
loopback config: `max_buffers` is a single value, not per device, and
`card_label` for two devices has to be **one** quoted comma-separated string —
separate quoted strings leak the quote characters into the device names, and a
udev rule matching on the name then silently misses. Also, libcamera's pipeline
handler locks the whole IPU media device while streaming, so two processes
cannot use the two cameras at the same time; an app switching between them is
fine.

Everything (relay, units, WirePlumber script, loopback config, udev rule,
setup script) is under `relay/` and `scripts/` in
https://github.com/ConsultingFuture4200/sp7-camera. A native PipeWire path
would still be nicer than the loopback, so @Elefantenjongleur's SPA setup is
the next thing to try when it lands.
