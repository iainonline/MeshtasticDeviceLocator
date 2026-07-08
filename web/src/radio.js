/**
 * Meshtastic device connection over USB-C (Web Serial), built on the
 * official @meshtastic/core + @meshtastic/transport-web-serial packages.
 * Tested target: Heltec V3 (ESP32-S3 + SX1262), 115200 baud.
 */
import { MeshDevice } from "@meshtastic/core";
import { TransportWebSerial } from "@meshtastic/transport-web-serial";

export function webSerialSupported() {
  return "serial" in navigator;
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

  /** Prompt for a serial port and bring the device up. */
  async connect() {
    const port = await requestSerialPort();
    this.transport = await TransportWebSerial.createFromPort(port, 115200);
    this.device = new MeshDevice(this.transport);
    // Quiet the bundled logger; the app surfaces its own status.
    this.device.log.settings.minLevel = 5;

    const ev = this.device.events;

    ev.onMyNodeInfo.subscribe((info) => {
      this.myNodeNum = info.myNodeNum;
      this.handlers.onMyNode?.(info.myNodeNum);
    });

    ev.onNodeInfoPacket.subscribe((ni) => {
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
      }
      this.nodes.set(ni.num, rec);
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
      this.nodes.set(pkt.from, rec);
      this.handlers.onNodes?.(this.nodes);

      // A usable ranging sample needs an RSSI reading and must have been
      // received directly (not relayed): over multiple hops the RSSI
      // describes the last relay, not the target node.
      const hopsUsed =
        pkt.hopStart && pkt.hopStart > 0 ? pkt.hopStart - pkt.hopLimit : null;
      const direct = hopsUsed === null ? !pkt.viaMqtt : hopsUsed === 0 && !pkt.viaMqtt;
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

    await this.device.configure();
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
