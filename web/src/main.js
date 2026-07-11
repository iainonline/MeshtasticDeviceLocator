import "./style.css";
import { Radio, webSerialSupported, webBluetoothSupported } from "./radio.js";
import { GeoWatcher } from "./geo.js";
import { RemoteGpsClient, makeSessionCode } from "./remote-gps.js";
import qrcode from "qrcode-generator";
import { LocatorMap } from "./map.js";
import {
  DEFAULT_PARAMS,
  estimatePosition,
  rssiToDistance,
} from "./estimator.js";

const $ = (id) => document.getElementById(id);

const state = {
  radio: null,
  connected: false,
  myNodeNum: null,
  gpsFix: null,
  targetNum: null,
  samples: [], // {lat, lon, rssi, snr, t}
  estimate: null,
  params: { ...DEFAULT_PARAMS },
  pingTimer: null,
  estimateTimer: null,
  nodeFilter: "",
  nodeDirectOnly: false,
  nodeAgeFilter: 0, // seconds; 0 = any
  nodeSort: "recent", // "recent" | "signal" | "hops"
  gpsMode: "local", // "local" | "remote"
  remoteSessionId: null,
  netShow: false,
  topology: new Map(), // "a-b" -> {a, b, snr}
};

const map = new LocatorMap($("map"));

/* ---------------- logging ---------------- */

// Full history (for "Copy debug log"), independent of the trimmed DOM list.
const debugLines = [];
// Lines recovered from the previous session at boot (e.g. one that crashed);
// kept separately so "Copy debug log" can include them — they'd otherwise be
// visible in the panel but impossible to copy out.
const recoveredLines = [];

// Mirrored to localStorage on every line so that if the page is killed
// outright (Android backgrounding a Custom Tab during a native Bluetooth
// pairing dialog, an OOM kill, a crash) — not just navigated away from —
// the log up to the last line written survives for the *next* load to
// show, since in-memory state and a normal "beforeunload" handler are both
// unreliable for that case (a hard kill fires neither).
const LOG_STORAGE_KEY = "fabledMeshLog";
function persistLog() {
  try {
    localStorage.setItem(LOG_STORAGE_KEY, JSON.stringify(debugLines.slice(-500)));
  } catch {
    /* storage full/unavailable — logging must never throw */
  }
}

function log(msg, isErr = false) {
  const line = `${new Date().toLocaleTimeString()} ${isErr ? "[ERROR] " : ""}${msg}`;
  debugLines.push(line);
  if (debugLines.length > 1000) debugLines.shift();
  persistLog();

  const el = document.createElement("div");
  if (isErr) el.className = "err";
  el.textContent = line;
  $("log").prepend(el);
  while ($("log").childElementCount > 150) $("log").lastChild.remove();
}

window.addEventListener("error", (e) => {
  log(`Uncaught error: ${e.message} (${e.filename?.split("/").pop()}:${e.lineno})`, true);
});
window.addEventListener("unhandledrejection", (e) => {
  const r = e.reason;
  log(`Unhandled promise rejection: ${r?.name || ""} ${r?.message || r}`, true);
});

// Page lifecycle: log every transition so a recovered log shows whether the
// page was still alive and just backgrounded, vs. never got a chance to log
// anything further (i.e. was killed, not just hidden).
for (const evt of ["visibilitychange", "pagehide", "pageshow", "freeze", "resume"]) {
  document.addEventListener(evt, () => log(`Page lifecycle: ${evt} (visibilityState=${document.visibilityState})`));
}
window.addEventListener("beforeunload", () => log("Page lifecycle: beforeunload"));

/* ---------------- formatting ---------------- */

function fmtDist(m) {
  if (m == null || !Number.isFinite(m)) return "—";
  return m >= 1000 ? `${(m / 1000).toFixed(2)} km` : `${Math.round(m)} m`;
}

function nodeLabel(rec) {
  return (
    rec.longName ||
    rec.shortName ||
    `!${(rec.num >>> 0).toString(16).padStart(8, "0")}`
  );
}

function ago(t) {
  if (!t) return "never";
  const s = Math.max(0, (Date.now() - t) / 1000);
  if (s < 60) return `${Math.round(s)}s ago`;
  if (s < 3600) return `${Math.round(s / 60)}m ago`;
  return `${Math.round(s / 3600)}h ago`;
}

/* ---------------- node list ---------------- */

// Best-known hop distance for a node: prefer the hop count from an actual
// received packet (lastHopsUsed); fall back to the routing-table hopsAway.
// null = unknown.
function nodeHops(n) {
  if (typeof n.lastHopsUsed === "number") return n.lastHopsUsed;
  if (typeof n.hopsAway === "number") return n.hopsAway;
  return null;
}

function isDirect(n) {
  return nodeHops(n) === 0 && !n.viaMqtt;
}

function hopBadge(n) {
  const h = nodeHops(n);
  if (n.viaMqtt) return `<span class="hop hop-mqtt">MQTT</span>`;
  if (h === 0) return `<span class="hop hop-direct">direct · 0 hop</span>`;
  if (h > 0) return `<span class="hop hop-relay">${h} hop${h > 1 ? "s" : ""}</span>`;
  return `<span class="hop hop-unknown">? hops</span>`;
}

function renderNodes() {
  const nodes = state.radio ? [...state.radio.nodes.values()] : [];
  const now = Date.now();
  const maxAgeMs = state.nodeAgeFilter * 1000;
  const visible = nodes
    .filter((n) => n.num !== state.myNodeNum)
    .filter((n) =>
      state.nodeFilter
        ? nodeLabel(n).toLowerCase().includes(state.nodeFilter) ||
          (n.shortName || "").toLowerCase().includes(state.nodeFilter)
        : true,
    )
    .filter((n) => (state.nodeDirectOnly ? isDirect(n) : true))
    .filter((n) =>
      maxAgeMs > 0 ? n.lastHeard && now - n.lastHeard <= maxAgeMs : true,
    )
    .sort((a, b) => {
      if (state.nodeSort === "signal") {
        return (b.lastRssi ?? -999) - (a.lastRssi ?? -999);
      }
      if (state.nodeSort === "hops") {
        return (nodeHops(a) ?? 99) - (nodeHops(b) ?? 99);
      }
      return (b.lastHeard || 0) - (a.lastHeard || 0);
    });

  $("node-count").textContent = String(visible.length);
  const ul = $("node-list");
  ul.innerHTML = "";
  if (visible.length === 0 && nodes.length > 1) {
    const li = document.createElement("li");
    li.className = "node-empty";
    li.textContent = state.nodeDirectOnly
      ? "No 0-hop nodes yet — move closer to hear a node directly."
      : "No nodes match the current filters.";
    ul.appendChild(li);
    return;
  }
  for (const n of visible) {
    const li = document.createElement("li");
    if (n.num === state.targetNum) li.classList.add("selected");
    const sig = n.lastRssi != null ? `${n.lastRssi} dBm` : "";
    li.innerHTML = `
      <span class="nn-short">${escapeHtml(n.shortName || "??")}</span>
      <span class="nn-main">
        <div class="nn-name">${escapeHtml(nodeLabel(n))}</div>
        <div class="nn-sub">${hopBadge(n)} · ${ago(n.lastHeard)}</div>
      </span>
      <span class="nn-sig">${sig}</span>`;
    li.addEventListener("click", () => selectTarget(n.num));
    ul.appendChild(li);
  }
}

/* ---------------- network overlay ---------------- */

function renderNetwork() {
  if (!state.radio) return;
  const RECENT_MS = 10 * 60 * 1000;
  const now = Date.now();
  const positioned = [];
  for (const n of state.radio.nodes.values()) {
    if (n.num === state.myNodeNum) continue;
    if (n.reportedLat == null || n.reportedLon == null) continue;
    positioned.push({
      num: n.num,
      lat: n.reportedLat,
      lon: n.reportedLon,
      short: n.shortName || "•",
      label: nodeLabel(n),
      active: n.respondedAt && now - n.respondedAt < RECENT_MS,
    });
  }
  const edges = [...state.topology.values()];
  map.renderNetwork(positioned, edges);

  const located = positioned.length;
  const links = edges.filter(
    (e) =>
      positioned.some((p) => p.num === e.a) &&
      positioned.some((p) => p.num === e.b),
  ).length;
  $("net-status").textContent =
    `${located} node(s) with a broadcast position on the map, ${links} link(s) drawn.` +
    (located === 0 ? " No nodes are broadcasting position yet." : "");

  renderNetworkLinks(edges);
}

// Text list of every discovered link, including nodes that don't report a
// position (so can't be drawn on the map). "·" = located, "○" = unlocated.
function renderNetworkLinks(edges) {
  const ul = $("net-links");
  ul.innerHTML = "";
  const endpointLabel = (num) => {
    const rec = state.radio?.nodes.get(num);
    const located = rec && rec.reportedLat != null;
    return {
      text: rec ? nodeLabel(rec) : `!${(num >>> 0).toString(16).padStart(8, "0")}`,
      located,
    };
  };
  const rows = edges
    .map((e) => ({ ...e, a: endpointLabel(e.a), b: endpointLabel(e.b) }))
    .sort((x, y) => (y.snr ?? -999) - (x.snr ?? -999));
  for (const r of rows) {
    const li = document.createElement("li");
    li.className = "net-link";
    const dot = (ep) =>
      `<span class="ep-dot ${ep.located ? "ep-located" : "ep-unlocated"}" title="${ep.located ? "on map" : "no position"}"></span>`;
    li.innerHTML =
      `${dot(r.a)}${escapeHtml(r.a.text)} ↔ ${dot(r.b)}${escapeHtml(r.b.text)}` +
      `<span class="net-link-snr">${r.snr != null ? `${r.snr.toFixed(1)} dB` : ""}</span>`;
    ul.appendChild(li);
  }
}

async function scanNetwork() {
  if (!state.radio || !state.connected) {
    log("Connect a radio before scanning the network.", true);
    return;
  }
  if (state.radio.scanning) return;
  const targets = [...state.radio.nodes.values()]
    .filter((n) => n.num !== state.myNodeNum)
    .sort((a, b) => (b.lastHeard || 0) - (a.lastHeard || 0))
    .map((n) => n.num);
  if (targets.length === 0) {
    log("No known nodes to scan yet — wait for the node list to populate.", true);
    return;
  }
  // Auto-enable the overlay so results are visible as they arrive.
  if (!state.netShow) {
    $("net-show").checked = true;
    state.netShow = true;
    renderNetwork();
  }
  $("btn-net-scan").disabled = true;
  log(`Scanning network: tracerouting ${Math.min(targets.length, 20)} node(s), ~4s apart. LoRa airtime is limited, so this takes a while.`);
  await state.radio.scanNetwork(targets, {
    spacingMs: 4000,
    max: 20,
    onProgress: (i, total, num) => {
      const rec = state.radio?.nodes.get(num);
      $("net-status").textContent = `Scanning ${i}/${total}: ${rec ? nodeLabel(rec) : num}…`;
    },
  });
  log("Network scan complete. Nodes that replied are marked active; links show how packets relayed.");
  $("btn-net-scan").disabled = false;
  renderNetwork();
}

function escapeHtml(s) {
  return String(s).replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
}

/* ---------------- target tracking ---------------- */

function selectTarget(num) {
  if (state.targetNum === num) return;
  state.targetNum = num;
  state.samples = [];
  state.estimate = null;
  map.clearSamples();
  const rec = state.radio?.nodes.get(num);
  $("target-name").textContent = rec ? nodeLabel(rec) : `#${num}`;
  $("card-target").classList.remove("hidden");
  renderNodes();
  updateTargetStats(null);
  if (rec?.reportedLat != null) {
    map.updateReported(rec.reportedLat, rec.reportedLon, nodeLabel(rec));
  }
  restartPingTimer();
  log(`Tracking ${rec ? nodeLabel(rec) : num}. Walk or drive around it — samples from different bearings sharpen the fix.`);
}

function stopTracking() {
  state.targetNum = null;
  state.samples = [];
  state.estimate = null;
  map.clearSamples();
  $("card-target").classList.add("hidden");
  restartPingTimer();
  renderNodes();
  log("Stopped tracking.");
}

function onSignal(sig) {
  if (sig.from !== state.targetNum) return;
  const rec = state.radio.nodes.get(sig.from);
  if (!state.gpsFix) {
    updateTargetStats(sig);
    $("hint").textContent = "Signal heard, but no phone GPS fix yet — samples are being discarded.";
    return;
  }
  if (!sig.direct) {
    updateTargetStats(sig);
    $("hint").textContent = `Packet relayed over ${sig.hopsUsed} hop(s) — RSSI reflects the relay, sample skipped.`;
    return;
  }
  const sample = {
    lat: state.gpsFix.lat,
    lon: state.gpsFix.lon,
    rssi: sig.rssi,
    snr: sig.snr,
    t: sig.t,
  };
  state.samples.push(sample);
  map.addSample(sample);
  recomputeEstimate();
  updateTargetStats(sig);
  if (rec?.reportedLat != null) {
    map.updateReported(rec.reportedLat, rec.reportedLon, nodeLabel(rec));
  }
}

function recomputeEstimate() {
  if (!state.targetNum || state.samples.length === 0) return;
  const est = estimatePosition(state.samples, state.params);
  if (!est) return;
  state.estimate = est;
  const rec = state.radio?.nodes.get(state.targetNum);
  const name = rec ? nodeLabel(rec) : `#${state.targetNum}`;
  map.updateEstimate(
    est,
    `${name} — probable location ±${fmtDist(est.radiusM)} (${est.quality.n} samples)`,
  );
  updateTargetStats(null);
}

function updateTargetStats(sig) {
  $("stat-samples").textContent = String(state.samples.length);
  const lastRssi = sig?.rssi ?? state.samples.at(-1)?.rssi;
  const lastSnr = sig?.snr ?? state.samples.at(-1)?.snr;
  $("stat-rssi").textContent = lastRssi != null ? `${lastRssi} dBm` : "—";
  $("stat-snr").textContent = lastSnr != null ? `${Number(lastSnr).toFixed(1)} dB` : "—";
  $("stat-range").textContent =
    lastRssi != null ? `~${fmtDist(rssiToDistance(lastRssi, state.params))}` : "—";

  const est = state.estimate;
  $("stat-radius").textContent = est ? `±${fmtDist(est.radiusM)}` : "—";
  $("stat-spread").textContent = est?.quality.bearingSpreadDeg != null
    ? `${Math.round(est.quality.bearingSpreadDeg)}°`
    : "—";

  const hint = $("hint");
  if (!est) {
    hint.textContent = state.samples.length === 0
      ? "Waiting for a direct packet from the target…"
      : "";
  } else if (est.quality.mode === "coarse") {
    hint.textContent = "Coarse estimate — need 3+ samples for trilateration.";
  } else if (est.quality.mode === "low-diversity") {
    hint.textContent = "Low bearing diversity — move around the node (circle it) to tighten the fix.";
  } else {
    hint.textContent = "";
  }
}

function restartPingTimer() {
  clearInterval(state.pingTimer);
  state.pingTimer = null;
  if (state.targetNum != null && $("chk-ping").checked && state.connected) {
    const fire = () => state.radio?.ping(state.targetNum);
    fire();
    state.pingTimer = setInterval(fire, 30000);
  }
}

/* ---------------- export ---------------- */

function exportJsonl() {
  const rec = state.radio?.nodes.get(state.targetNum);
  const lines = [
    JSON.stringify({
      type: "session",
      target: state.targetNum,
      targetName: rec ? nodeLabel(rec) : null,
      params: state.params,
      exportedAt: new Date().toISOString(),
      estimate: state.estimate,
    }),
    ...state.samples.map((s) => JSON.stringify({ type: "sample", ...s })),
  ];
  const blob = new Blob([lines.join("\n") + "\n"], {
    type: "application/x-ndjson",
  });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `fabled-mesh-${state.targetNum}-${Date.now()}.jsonl`;
  a.click();
  URL.revokeObjectURL(a.href);
}

/* ---------------- radio connection ---------------- */

function setConnecting(isConnecting) {
  $("btn-connect-usb").disabled = isConnecting;
  $("btn-connect-ble").disabled = isConnecting;
  if (isConnecting) {
    $("btn-connect-usb").textContent = "Connecting…";
    $("btn-connect-ble").textContent = "Connecting…";
  } else {
    $("btn-connect-usb").textContent = "Connect USB";
    $("btn-connect-ble").textContent = "Connect Bluetooth";
  }
}

async function connect(transport) {
  if (transport === "usb" && !webSerialSupported()) {
    log("Web Serial is not supported here. Try Connect Bluetooth instead, or use Chrome/Edge on desktop.", true);
    return;
  }
  if (transport === "bluetooth" && !webBluetoothSupported()) {
    log("Web Bluetooth is not supported here. Try Connect USB instead, or use Chrome/Edge on desktop.", true);
    return;
  }
  setConnecting(true);
  try {
    state.radio = new Radio({
      onMyNode: (num) => {
        state.myNodeNum = num;
        $("device-info").innerHTML = `Connected to Heltec V3 (${transport}) · my node <b>!${(num >>> 0).toString(16)}</b>`;
        renderNodes();
      },
      onNodes: () => {
        renderNodes();
        if (state.netShow) renderNetwork();
      },
      onSignal: onSignal,
      onStatus: (status) => {
        // DeviceStatusEnum: 7 = configured, <=2 = disconnected
        if (status <= 2 && state.connected) handleDisconnect();
      },
      onTopology: ({ responder, edges }) => {
        for (const e of edges) {
          const key = e.a < e.b ? `${e.a}-${e.b}` : `${e.b}-${e.a}`;
          state.topology.set(key, { a: e.a, b: e.b, snr: e.snr });
        }
        const rec = state.radio?.nodes.get(responder);
        log(`Traceroute reply from ${rec ? nodeLabel(rec) : responder} — ${edges.length} link(s) mapped.`);
        renderNetworkLinks([...state.topology.values()]);
        if (state.netShow) renderNetwork();
      },
      onDebug: (msg) => log(msg),
    });
    await state.radio.connect(transport);
    state.connected = true;
    $("radio-badge").classList.replace("off", "on");
    $("connect-buttons").classList.add("hidden");
    $("btn-disconnect").classList.remove("hidden");
    setConnecting(false);
    log(`Radio connected over ${transport === "bluetooth" ? "Bluetooth" : "USB"} and configured.`);
    restartPingTimer();
  } catch (e) {
    const msg = e?.message || String(e);
    log(`Connect failed: ${e?.name || "Error"}: ${msg}${e?.stack ? `\n${e.stack}` : ""}`, true);
    if (transport === "usb" && /no port selected|no compatible device|not found/i.test(msg)) {
      log(
        "No USB device shown in the picker. This Android/Chrome combo doesn't recognize the Heltec V3's USB-serial chip over Web Serial — try Connect Bluetooth instead (pair the radio first in Android Bluetooth settings if it doesn't appear).",
        true,
      );
    } else if (transport === "bluetooth" && /no devices found|cancelled|user cancel/i.test(msg)) {
      log(
        "No Bluetooth device selected. Make sure the radio's Bluetooth is enabled (Meshtastic app → Radio Config → Bluetooth) and it's powered on and in range.",
        true,
      );
    } else if (transport === "bluetooth") {
      log(
        "Bluetooth connect failed after pairing. Two common causes: (1) the official Meshtastic app is holding the radio — Meshtastic firmware allows only ONE Bluetooth connection, so force-stop the Meshtastic app (Android Settings → Apps → Meshtastic → Force stop) and retry; (2) a stale pairing — forget the Heltec in Android Bluetooth settings, power-cycle the radio, and pair again (watch the radio's screen for the PIN).",
        true,
      );
    }
    setConnecting(false);
    try {
      await state.radio?.disconnect();
    } catch {
      /* ignore */
    }
    state.radio = null;
  }
}

function handleDisconnect() {
  state.connected = false;
  clearInterval(state.pingTimer);
  $("radio-badge").classList.replace("on", "off");
  $("connect-buttons").classList.remove("hidden");
  $("btn-disconnect").classList.add("hidden");
  setConnecting(false);
  $("device-info").textContent = "Disconnected.";
  log("Radio disconnected.", true);
}

async function disconnect() {
  await state.radio?.disconnect();
  state.radio = null;
  handleDisconnect();
}

/* ---------------- GPS: local device or relayed from a phone ---------------- */

function handleGpsFix(fix, sourceLabel) {
  const first = !state.gpsFix;
  state.gpsFix = fix;
  $("gps-badge").classList.remove("off", "warn");
  $("gps-badge").classList.add(fix.accuracyM <= 30 ? "on" : "warn");
  $("gps-badge").textContent = `GPS ±${Math.round(fix.accuracyM)}m`;
  map.updateUser(fix);
  if (first) log(`${sourceLabel} GPS fix acquired (±${Math.round(fix.accuracyM)} m).`);
}

function handleGpsError(msg) {
  $("gps-badge").classList.remove("on", "warn");
  $("gps-badge").classList.add("off");
  log(`GPS: ${msg}`, true);
}

const geo = new GeoWatcher(
  (fix) => handleGpsFix(fix, "Phone"),
  (msg) => handleGpsError(msg),
);

let remoteGps = null;

function gpsRelayLink() {
  return `${location.origin}/gps.html?s=${encodeURIComponent(state.remoteSessionId)}`;
}

function renderGpsQr() {
  const link = gpsRelayLink();
  // 'L' error correction keeps the code sparse (easier to scan on a small
  // panel); the payload is a short URL so capacity isn't a concern.
  const qr = qrcode(0, "L");
  qr.addData(link);
  qr.make();
  $("gps-qr").innerHTML = qr.createSvgTag({ cellSize: 5, margin: 2 });
}

function startRemoteGps(sessionId) {
  state.gpsFix = null;
  $("gps-remote-code").textContent = sessionId;
  renderGpsQr();
  $("gps-remote-status").textContent = "Waiting for a phone to connect…";
  remoteGps = new RemoteGpsClient(sessionId, {
    onFix: (fix) => {
      $("gps-remote-status").textContent = "Receiving live position from phone.";
      handleGpsFix(fix, "Remote phone");
    },
    onStatus: ({ sourcesConnected }) => {
      $("gps-remote-status").textContent =
        sourcesConnected > 0
          ? "Phone connected — waiting for its first GPS fix…"
          : "Waiting for a phone to connect…";
    },
    onConnect: () => log(`Remote GPS relay connected (session ${sessionId}).`),
    onDisconnect: () => handleGpsError("relay disconnected, reconnecting…"),
    onError: (msg) => log(`Remote GPS: ${msg}`, true),
  });
  remoteGps.start();
}

function stopRemoteGps() {
  remoteGps?.stop();
  remoteGps = null;
}

function setGpsMode(mode) {
  if (state.gpsMode === mode) return;
  state.gpsMode = mode;
  if (mode === "remote") {
    geo.stop();
    $("gps-remote-panel").classList.remove("hidden");
    state.remoteSessionId = state.remoteSessionId || makeSessionCode();
    startRemoteGps(state.remoteSessionId);
    log("Switched to remote (phone) GPS source.");
  } else {
    stopRemoteGps();
    $("gps-remote-panel").classList.add("hidden");
    state.gpsFix = null;
    geo.start();
    log("Switched to this device's own GPS.");
  }
}

/* ---------------- periodic re-estimate (time decay) ---------------- */

state.estimateTimer = setInterval(() => {
  if (state.samples.length >= 3) recomputeEstimate();
  renderNodes(); // refresh "last heard" ages
}, 5000);

/* ---------------- UI wiring ---------------- */

$("btn-connect-usb").addEventListener("click", () => connect("usb"));
$("btn-connect-ble").addEventListener("click", () => connect("bluetooth"));
$("btn-disconnect").addEventListener("click", () => disconnect());
$("btn-clear").addEventListener("click", () => {
  state.samples = [];
  state.estimate = null;
  map.clearSamples();
  updateTargetStats(null);
  log("Samples reset.");
});
$("btn-stop").addEventListener("click", stopTracking);
$("btn-export").addEventListener("click", exportJsonl);
$("chk-ping").addEventListener("change", restartPingTimer);

$("node-filter").addEventListener("input", (e) => {
  state.nodeFilter = e.target.value.trim().toLowerCase();
  renderNodes();
});
$("filter-direct").addEventListener("change", (e) => {
  state.nodeDirectOnly = e.target.checked;
  renderNodes();
});
$("filter-age").addEventListener("change", (e) => {
  state.nodeAgeFilter = Number(e.target.value);
  renderNodes();
});
$("filter-sort").addEventListener("change", (e) => {
  state.nodeSort = e.target.value;
  renderNodes();
});

$("net-show").addEventListener("change", (e) => {
  state.netShow = e.target.checked;
  if (state.netShow) renderNetwork();
  else map.clearNetwork();
});
$("btn-net-scan").addEventListener("click", scanNetwork);

$("set-freq").addEventListener("change", (e) => {
  state.params.freqMhz = Number(e.target.value);
  recomputeEstimate();
});
$("set-tx").addEventListener("change", (e) => {
  state.params.txPowerDbm = Number(e.target.value);
  recomputeEstimate();
});
$("set-env").addEventListener("change", (e) => {
  state.params.pathLossExp = Number(e.target.value);
  recomputeEstimate();
});

$("btn-follow").addEventListener("click", () => {
  map.setFollow(!map.follow);
  $("btn-follow").classList.toggle("active", map.follow);
});
map.onFollowChange = (v) => $("btn-follow").classList.toggle("active", v);
$("btn-fit").addEventListener("click", () => map.fitAll());

$("btn-panel").addEventListener("click", () =>
  $("panel").classList.toggle("open"),
);

$("gps-source-select").addEventListener("change", (e) => setGpsMode(e.target.value));

$("btn-gps-new-code").addEventListener("click", () => {
  state.remoteSessionId = makeSessionCode();
  stopRemoteGps();
  startRemoteGps(state.remoteSessionId);
  log(`New GPS relay session: ${state.remoteSessionId}`);
});

$("btn-gps-copy-link").addEventListener("click", async () => {
  const link = gpsRelayLink();
  try {
    await navigator.clipboard.writeText(link);
    $("btn-gps-copy-link").textContent = "Copied!";
  } catch {
    log(`Phone GPS link: ${link}`);
    $("btn-gps-copy-link").textContent = "See log";
  }
  setTimeout(() => ($("btn-gps-copy-link").textContent = "Copy phone link"), 1500);
});

$("btn-copy-log").addEventListener("click", async () => {
  let text = debugLines.slice().reverse().join("\n");
  if (recoveredLines.length) {
    text += `\n\n— Recovered log from previous session (last ${recoveredLines.length} lines, oldest first) —\n${recoveredLines.join("\n")}`;
  }
  try {
    await navigator.clipboard.writeText(text);
    $("btn-copy-log").textContent = "Copied!";
  } catch {
    // Clipboard API unavailable/blocked — fall back to a download.
    const blob = new Blob([text], { type: "text/plain" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `fabled-mesh-debug-${Date.now()}.txt`;
    a.click();
    URL.revokeObjectURL(a.href);
    $("btn-copy-log").textContent = "Downloaded";
  }
  setTimeout(() => ($("btn-copy-log").textContent = "Copy debug log"), 1500);
});

/* ---------------- boot ---------------- */

// Recover the previous session's log (if any) before this session starts
// overwriting the same storage key — this is what survives a hard page
// kill (e.g. Android backgrounding/destroying the tab mid-Bluetooth-pairing)
// that never gets to run beforeunload/pagehide.
(() => {
  try {
    const prev = JSON.parse(localStorage.getItem(LOG_STORAGE_KEY) || "null");
    if (Array.isArray(prev) && prev.length) {
      recoveredLines.push(...prev);
      const box = document.createElement("div");
      box.style.cssText = "color:#d4a72c;border-top:1px dashed #d4a72c;margin-top:6px;padding-top:6px;";
      box.textContent = `— Recovered log from previous session (last ${prev.length} lines, oldest first) —`;
      $("log").appendChild(box);
      for (const line of prev) {
        const el = document.createElement("div");
        el.textContent = line;
        el.className = "muted";
        $("log").appendChild(el);
      }
    }
  } catch {
    /* corrupt/unavailable storage — nothing to recover */
  }
})();

$("build-id").textContent = `(build ${__BUILD_ID__})`;
log(`Build: ${__BUILD_ID__} — if this doesn't match the latest change, this tab/browser is showing a cached page. Close the tab fully and reopen, or hard-refresh.`);

// Never silently hide a connect option — say exactly why it's unavailable,
// since "the button just isn't there" is unbdebuggable from the user's side.
function browserCompatNote(ua) {
  if (/SamsungBrowser/i.test(ua)) {
    return "Samsung Internet doesn't implement this API — open this page in Chrome instead.";
  }
  if (/FBAN|FBAV|Instagram|Line\/|MicroMessenger|Twitter/i.test(ua)) {
    return "This looks like an in-app browser (social/messaging app) — these block this API even when Chromium-based. Open this page in Chrome directly.";
  }
  if (/iPhone|iPad|iPod/i.test(ua) && !/CriOS|EdgiOS/i.test(ua)) {
    return "iOS Safari (and all iOS browsers, since Apple forces them to use Safari's engine) does not support this API at all — Web Serial/Bluetooth are Android/desktop-only.";
  }
  if (/Firefox/i.test(ua)) {
    return "Firefox doesn't implement this API — use Chrome or Edge.";
  }
  if (!/Chrome|Chromium|CriOS|Edg\//i.test(ua)) {
    return "This browser doesn't appear to be Chrome/Edge — those are required for this API.";
  }
  return "This specific browser build doesn't expose this API (older version, or disabled by an enterprise/device policy).";
}

log(
  `Environment: secureContext=${window.isSecureContext} webSerial=${webSerialSupported()} webBluetooth=${webBluetoothSupported()} UA="${navigator.userAgent}"`,
);
if (!window.isSecureContext) {
  log("Not a secure context — Web Serial, Web Bluetooth and GPS will be unavailable. Serve over HTTPS or localhost.", true);
}
if (!webSerialSupported()) {
  const note = browserCompatNote(navigator.userAgent);
  $("btn-connect-usb").disabled = true;
  $("btn-connect-usb").title = `USB unavailable: ${note}`;
  log(`Connect USB is disabled: Web Serial isn't available here. ${note}`, true);
}
if (!webBluetoothSupported()) {
  const note = browserCompatNote(navigator.userAgent);
  $("btn-connect-ble").disabled = true;
  $("btn-connect-ble").title = `Bluetooth unavailable: ${note}`;
  log(`Connect Bluetooth is disabled: Web Bluetooth isn't available here. ${note}`, true);
}
if (!webSerialSupported() && !webBluetoothSupported()) {
  log("Neither connection method works in this browser. Open this page in Chrome or Edge on Android or desktop.", true);
}
geo.start();
log("Ready. Connect your Heltec V3 via USB-C or Bluetooth, then pick a node to hunt.");
