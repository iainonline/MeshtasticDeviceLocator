# Fabled Mesh — Meshtastic Node Locator (Web App)

A modern, browser-based rewrite of the Python mesh tracker. Plug a
**Heltec V3** (or any Meshtastic serial device) into your phone or laptop via
**USB-C**, pick a node from the mesh, then walk or drive around while the app
fuses your GPS track with the node's signal strength to plot its **probable
location as a circle on a live map** — the circle's size is the uncertainty.

## How it works

1. **USB-C connection** — the app talks to the radio with the
   [Web Serial API](https://developer.mozilla.org/docs/Web/API/Web_Serial_API)
   using the official `@meshtastic/core` + `@meshtastic/transport-web-serial`
   libraries (115200 baud).
2. **Your position** — the browser Geolocation API streams your phone's GPS;
   you appear as a pulsing blue dot with an accuracy ring.
3. **Sampling** — every packet received *directly* from the target node
   (0 hops, not via MQTT) yields an `(your lat/lon, RSSI, SNR)` sample.
   Relayed packets are skipped because their RSSI describes the relay, not
   the target. An optional **active ping** (traceroute every 30 s) solicits
   replies from quiet nodes.
4. **Estimation** — RSSI is converted to range with a log-distance path-loss
   model, samples are outlier-filtered (2σ), weighted by signal strength,
   SNR, and age, and fed to a Levenberg–Marquardt weighted least-squares
   trilateration. The red circle's **radius is the estimated uncertainty**
   (residual error inflated by poor bearing diversity — circle the node to
   shrink it).

Green→red dots along your track show sample RSSI. A green square marks the
node's *self-reported* GPS position when it broadcasts one, for comparison.

## Requirements

- **Browser with Web Serial**: Chrome or Edge on desktop, or **Chrome on
  Android** (connect the Heltec V3 with a USB-C OTG cable). iOS Safari does
  not support Web Serial.
- **Secure context**: `localhost` or HTTPS (the dev server below serves
  self-signed HTTPS so a phone on your LAN can connect).
- A Heltec V3 running Meshtastic firmware with the serial console left at
  defaults.

## Run it

```bash
cd web
npm install
npm run dev
```

- On the same machine: open `https://localhost:5173`.
- From a phone: open `https://<your-computer-ip>:5173`, accept the
  self-signed-certificate warning, then plug the radio into the **phone**.
  (For a phone-only setup, `npm run build` and host `dist/` on any HTTPS
  static host — the app is fully client-side; nothing leaves the browser
  except map-tile requests.)

Then:

1. Tap **Connect USB** and pick the Heltec V3's serial port
   (`USB Single Serial` / `CP210x` / `USB JTAG`).
2. Wait for the node list to populate; tap the node you want to locate.
3. Walk or drive. Try to arc around the suspected area — bearing diversity
   is what turns a big circle into a small one.

## Settings

| Setting | Meaning |
| --- | --- |
| Region / frequency | LoRa band (915 US, 868 EU, 433, 920) — used in the path-loss model |
| TX power of target | The *target's* transmit power (Meshtastic default 20 dBm on Heltec V3) |
| Environment | Path-loss exponent: open 2.2 → dense urban 3.8 |

**Export JSONL** downloads the session (params, estimate, every sample) in a
format compatible in spirit with the old Python tracker's logs.

## Accuracy expectations

RSSI ranging is inherently noisy (multipath, antenna orientation, terrain).
Expect the circle to be tens–hundreds of meters across in good conditions.
The app never claims better than ~15 % of the estimated range; treat the
circle as a search area, not a pin.
