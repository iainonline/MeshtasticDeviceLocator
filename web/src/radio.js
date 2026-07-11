/**
 * Meshtastic device connection, built on the official @meshtastic/core
 * packages. Two transports are supported:
 *
 *  - USB-C (Web Serial): fast and simple, but Android Chrome can only
 *    offer a device in the picker if it recognizes the USB-serial chip
 *    (see KNOWN_VENDOR_IDS below) — some boards/cables/Android versions
 *    never surface a device at all, regardless of filters.
 *  - Bluetooth LE (Web Bluetooth): the reliable fallback on Android,
 *    since it filters by the Meshtastic GATT service UUID rather than
 *    depending on Android's built-in USB-serial driver recognition.
 *
 * Tested target: Heltec V3 (ESP32-S3 + SX1262).
 */
import { MeshDevice } from "@meshtastic/core";
import { TransportWebSerial } from "@meshtastic/transport-web-serial";
import { TransportWebBluetooth } from "@meshtastic/transport-web-bluetooth";

const STATUS_NAMES = {
  1: "Restarting",
  2: "Disconnected",
  3: "Connecting",
  4: "Reconnecting",
  5: "Connected",
  6: "Configuring",
  7: "Configured",
};

export function webSerialSupported() {
  return "serial" in navigator;
}

export function webBluetoothSupported() {
  return "bluetooth" in navigator;
}

// USB vendor IDs for the serial chips found on common Meshtastic boards.
// Passing these as filters is required for Web Serial to work on Android:
// unlike desktop, Chrome for Android can only surface a device in the
// port picker when the request includes a vendor/product filter it can use
// to ask the OS for USB permission — an unfiltered requestPort() always
// reports "No compatible devices found" there, even though the exact same
// hardware is visible to the native Meshtastic app (which uses Android's
// USB host API directly, not Web Serial).
const KNOWN_VENDOR_IDS = [
  0x10c4, // Silicon Labs CP210x / CP2102N (Heltec V3, many others)
  0x1a86, // WCH CH340 / CH341 / CH9102
  0x0403, // FTDI FT230X / FT232
  0x067b, // Prolific PL2303
  0x303a, // Espressif (native USB-JTAG/CDC on some ESP32-S3 boards)
];

async function requestSerialPort() {
  return navigator.serial.requestPort({
    filters: KNOWN_VENDOR_IDS.map((usbVendorId) => ({ usbVendorId })),
  });
}

export class Radio {
  constructor(handlers = {}) {
    this.handlers = handlers;
    this.device = null;
    this.transport = null;
    this.myNodeNum = null;
    /** @type {Map<number, object>} nodeNum -> node record */
    this.nodes = new Map();
  }

  /** Prompt for a device over the given transport ("usb" | "bluetooth") and bring it up. */
  async connect(transport = "usb") {
    const dbg = (msg) => {
      try {
        this.handlers.onDebug?.(msg);
      } catch {
        /* a bad debug handler must never break the connection */
      }
    };

    dbg(`Starting ${transport} connection. UA: ${navigator.userAgent}`);
    try {
      if (transport === "bluetooth") {
        dbg(
          `Requesting Bluetooth device (filtering by Meshtastic GATT service ${TransportWebBluetooth.ServiceUuid})… Tip: if the browser crashes when you tap Connect in the chooser, the crash is in the OS pairing step — pair the radio in Android's Bluetooth settings first (PIN is on the radio's screen), then retry here; an existing bond skips that step.`,
        );
        const device = await navigator.bluetooth.requestDevice({
          filters: [{ services: [TransportWebBluetooth.ServiceUuid] }],
        });
        dbg(`Bluetooth device selected: "${device.name || "(unnamed)"}" id=${device.id}`);
        device.addEventListener("gattserverdisconnected", () =>
          dbg("BLE: gattserverdisconnected event fired"),
        );
        dbg(
          `Connecting GATT server and resolving read/write/notify characteristics… (visibilityState=${document.visibilityState}) — Android may now show a native pairing/bonding prompt outside this page; if so, the next log line only appears after you handle it.`,
        );
        const gattStall = setTimeout(() => {
          dbg(
            `Still waiting for GATT connect after 10s (visibilityState=${document.visibilityState}). If a system Bluetooth pairing dialog appeared, this page is paused until it's resolved.`,
          );
        }, 10000);
        try {
          // On Android, the first gatt.connect() to an unbonded device kicks
          // off the OS pairing flow, and the GATT link routinely drops the
          // moment bonding completes — the immediate retry then succeeds
          // because the bond now exists. Native apps retry internally;
          // a single-shot connect misreads this normal sequence as failure.
          const MAX_ATTEMPTS = 4;
          let lastErr = null;
          for (let attempt = 1; attempt <= MAX_ATTEMPTS; attempt++) {
            try {
              if (attempt > 1) dbg(`GATT connect attempt ${attempt}/${MAX_ATTEMPTS}…`);
              this.transport = await TransportWebBluetooth.createFromDevice(device);
              lastErr = null;
              break;
            } catch (err) {
              lastErr = err;
              dbg(
                `GATT attempt ${attempt}/${MAX_ATTEMPTS} failed: ${err?.name || "Error"}: ${err?.message || err}${
                  attempt < MAX_ATTEMPTS
                    ? " — retrying (a drop right after Android finishes pairing is normal; the bond persists)."
                    : ""
                }`,
              );
              try {
                device.gatt?.disconnect();
              } catch {
                /* already down */
              }
              if (attempt < MAX_ATTEMPTS) {
                await new Promise((r) => setTimeout(r, 1500 * attempt));
              }
            }
          }
          if (lastErr) throw lastErr;
        } finally {
          clearTimeout(gattStall);
        }
        dbg(`Bluetooth transport ready (GATT connected, characteristics resolved). visibilityState=${document.visibilityState}`);
      } else {
        dbg(
          `Requesting serial port (vendor filters: ${KNOWN_VENDOR_IDS.map((v) => "0x" + v.toString(16)).join(", ")})…`,
        );
        const port = await requestSerialPort();
        const info = port.getInfo?.() || {};
        dbg(
          `Port selected. usbVendorId=${info.usbVendorId ?? "?"} usbProductId=${info.usbProductId ?? "?"}. Opening at 115200 baud…`,
        );
        this.transport = await TransportWebSerial.createFromPort(port, 115200);
        dbg("Serial transport ready (port open).");
      }
    } catch (err) {
      dbg(`Transport creation FAILED: ${err?.name || "Error"}: ${err?.message || err}`);
      throw err;
    }

    dbg("Creating MeshDevice and subscribing to protocol events…");
    this.device = new MeshDevice(this.transport);
    // Quiet the bundled console logger; we mirror everything through onDebug instead.
    this.device.log.settings.minLevel = 5;

    const ev = this.device.events;

    let fromRadioCount = 0;
    ev.onFromRadio.subscribe(() => {
      fromRadioCount += 1;
      if (fromRadioCount === 1 || fromRadioCount % 20 === 0) {
        dbg(`Received ${fromRadioCount} FromRadio message(s) so far.`);
      }
    });

    ev.onLogEvent.subscribe((log) => {
      dbg(`device log [level ${log.level}]: ${log.message}`);
    });

    ev.onDeviceStatus.subscribe((status) => {
      dbg(`Device status -> ${STATUS_NAMES[status] || status}`);
    });

    ev.onMyNodeInfo.subscribe((info) => {
      dbg(`onMyNodeInfo: myNodeNum=${info.myNodeNum}`);
      this.myNodeNum = info.myNodeNum;
      this.handlers.onMyNode?.(info.myNodeNum);
    });

    let nodeInfoCount = 0;
    ev.onNodeInfoPacket.subscribe((ni) => {
      nodeInfoCount += 1;
      dbg(`onNodeInfoPacket #${nodeInfoCount}: num=${ni.num} shortName=${ni.user?.shortName ?? "?"}`);
      const rec = this.nodes.get(ni.num) ?? { num: ni.num };
      rec.longName = ni.user?.longName || rec.longName;
      rec.shortName = ni.user?.shortName || rec.shortName;
      rec.hwModel = ni.user?.hwModel ?? rec.hwModel;
      rec.snr = ni.snr ?? rec.snr;
      rec.hopsAway = ni.hopsAway ?? rec.hopsAway;
      rec.lastHeard = ni.lastHeard ? ni.lastHeard * 1000 : rec.lastHeard;
      if (ni.position && ni.position.latitudeI) {
        rec.reportedLat = ni.position.latitudeI / 1e7;
        rec.reportedLon = ni.position.longitudeI / 1e7;
        this.handlers.onReported?.({
          num: ni.num,
          lat: rec.reportedLat,
          lon: rec.reportedLon,
          t: Date.now(),
        });
      }
      this.nodes.set(ni.num, rec);
      this.handlers.onNodes?.(this.nodes);
    });

    // Position packets: a node broadcasting its own GPS. Most accurate source
    // of truth for where that node is, and the primary signal for mobility.
    ev.onPositionPacket?.subscribe((pkt) => {
      const pos = pkt.data || {};
      if (!pos.latitudeI) return;
      const num = pkt.from;
      const lat = pos.latitudeI / 1e7;
      const lon = pos.longitudeI / 1e7;
      const rec = this.nodes.get(num) ?? { num };
      rec.reportedLat = lat;
      rec.reportedLon = lon;
      rec.lastHeard = Date.now();
      this.nodes.set(num, rec);
      this.handlers.onReported?.({ num, lat, lon, t: Date.now() });
      this.handlers.onNodes?.(this.nodes);
    });

    ev.onMeshPacket.subscribe((pkt) => {
      if (pkt.from === this.myNodeNum) return;
      const rec = this.nodes.get(pkt.from) ?? { num: pkt.from };
      rec.lastHeard = Date.now();
      if (typeof pkt.rxRssi === "number" && pkt.rxRssi !== 0) {
        rec.lastRssi = pkt.rxRssi;
      }
      if (typeof pkt.rxSnr === "number" && pkt.rxSnr !== 0) {
        rec.lastSnr = pkt.rxSnr;
      }

      // A usable ranging sample needs an RSSI reading and must have been
      // received directly (not relayed): over multiple hops the RSSI
      // describes the last relay, not the target node.
      const hopsUsed =
        pkt.hopStart && pkt.hopStart > 0 ? pkt.hopStart - pkt.hopLimit : null;
      const direct = hopsUsed === null ? !pkt.viaMqtt : hopsUsed === 0 && !pkt.viaMqtt;

      // Record per-packet reception detail so the UI can show/filter which
      // nodes we're actually hearing firsthand (the ones we can locate).
      rec.lastHopsUsed = hopsUsed;
      rec.viaMqtt = !!pkt.viaMqtt;
      if (direct) {
        rec.directHeard = true;
        rec.lastDirectHeard = Date.now();
      }
      this.nodes.set(pkt.from, rec);
      this.handlers.onNodes?.(this.nodes);

      if (typeof pkt.rxRssi === "number" && pkt.rxRssi !== 0) {
        this.handlers.onSignal?.({
          from: pkt.from,
          rssi: pkt.rxRssi,
          snr: typeof pkt.rxSnr === "number" ? pkt.rxSnr : null,
          direct,
          hopsUsed,
          t: Date.now(),
        });
      }
    });

    ev.onDeviceStatus.subscribe((status) => {
      this.handlers.onStatus?.(status);
    });

    // Traceroute replies carry the full path (and per-hop SNR) between us and
    // the responding node — this is the "who connects to who" data. The
    // responder is, by definition, currently reachable/active.
    ev.onTraceRoutePacket?.subscribe((pkt) => {
      const responder = pkt.from;
      const rd = pkt.data || {};
      const route = (rd.route || []).map(Number);
      const routeBack = (rd.routeBack || []).map(Number);
      const me = this.myNodeNum;

      // Forward path we sent along: me -> intermediate route -> responder.
      const fwd = [me, ...route, responder].filter((n) => n != null);
      // Return path the reply took: responder -> routeBack -> me.
      const back = [responder, ...routeBack, me].filter((n) => n != null);

      const edges = [];
      const addPath = (path, snrs) => {
        for (let i = 0; i < path.length - 1; i++) {
          edges.push({
            a: path[i],
            b: path[i + 1],
            snr: snrs && snrs[i] != null ? snrs[i] / 4 : null, // proto stores SNR*4
          });
        }
      };
      addPath(fwd, rd.snrTowards);
      addPath(back, rd.snrBack);

      const rec = this.nodes.get(responder);
      if (rec) {
        rec.respondedAt = Date.now();
        this.nodes.set(responder, rec);
      }
      this.handlers.onTopology?.({ responder, edges });
      this.handlers.onNodes?.(this.nodes);
    });

    dbg("Calling device.configure() (requesting node/channel config from radio)…");
    const stall = setTimeout(() => {
      dbg(
        "Still waiting for configure() after 8s — the device hasn't replied yet. It may be busy, asleep, or the transport isn't actually delivering data.",
      );
    }, 8000);
    try {
      await this.device.configure();
      dbg("configure() resolved — device is fully configured.");
    } catch (err) {
      dbg(`configure() FAILED: ${err?.name || "Error"}: ${err?.message || err}`);
      throw err;
    } finally {
      clearTimeout(stall);
    }
  }

  /**
   * Actively solicit a reply from a node so we get fresh RSSI samples even
   * when it isn't chatty. Traceroute is ideal: firmware replies automatically.
   */
  async ping(nodeNum) {
    if (!this.device) return;
    try {
      await this.device.traceRoute(nodeNum);
    } catch {
      // Rate-limited or busy; the next scheduled ping will retry.
    }
  }

  /**
   * Probe the mesh: traceroute a set of nodes one at a time to discover which
   * are reachable (they reply) and how they're connected. LoRa airtime is
   * scarce and the firmware rate-limits traceroute, so this is deliberately
   * slow and bounded. Returns when all probes have been sent (replies arrive
   * asynchronously via onTopology).
   */
  async scanNetwork(nodeNums, { spacingMs = 4000, max = 20, onProgress } = {}) {
    if (!this.device || this._scanning) return;
    this._scanning = true;
    const targets = nodeNums.slice(0, max);
    try {
      for (let i = 0; i < targets.length; i++) {
        if (!this.device) break;
        onProgress?.(i + 1, targets.length, targets[i]);
        try {
          await this.device.traceRoute(targets[i]);
        } catch {
          // rate-limited/busy — skip this one, keep going
        }
        if (i < targets.length - 1) {
          await new Promise((r) => setTimeout(r, spacingMs));
        }
      }
    } finally {
      this._scanning = false;
    }
  }

  get scanning() {
    return !!this._scanning;
  }

  async disconnect() {
    try {
      await this.device?.disconnect?.();
    } catch {
      /* ignore */
    }
    try {
      await this.transport?.disconnect();
    } catch {
      /* ignore */
    }
    this.device = null;
    this.transport = null;
  }
}
