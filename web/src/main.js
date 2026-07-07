import "./style.css";
import { Radio, webSerialSupported } from "./radio.js";
import { GeoWatcher } from "./geo.js";
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
};

const map = new LocatorMap($("map"));

/* ---------------- logging ---------------- */

function log(msg, isErr = false) {
  const el = document.createElement("div");
  if (isErr) el.className = "err";
  el.textContent = `${new Date().toLocaleTimeString()} ${msg}`;
  $("log").prepend(el);
  while ($("log").childElementCount > 80) $("log").lastChild.remove();
}

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

function renderNodes() {
  const nodes = state.radio ? [...state.radio.nodes.values()] : [];
  const visible = nodes
    .filter((n) => n.num !== state.myNodeNum)
    .filter((n) =>
      state.nodeFilter
        ? nodeLabel(n).toLowerCase().includes(state.nodeFilter) ||
          (n.shortName || "").toLowerCase().includes(state.nodeFilter)
        : true,
    )
    .sort((a, b) => (b.lastHeard || 0) - (a.lastHeard || 0));

  $("node-count").textContent = String(visible.length);
  const ul = $("node-list");
  ul.innerHTML = "";
  for (const n of visible) {
    const li = document.createElement("li");
    if (n.num === state.targetNum) li.classList.add("selected");
    const sig =
      n.lastRssi != null
        ? `${n.lastRssi} dBm`
        : n.hopsAway > 0
          ? `${n.hopsAway} hop${n.hopsAway > 1 ? "s" : ""}`
          : "";
    li.innerHTML = `
      <span class="nn-short">${escapeHtml(n.shortName || "??")}</span>
      <span class="nn-main">
        <div class="nn-name">${escapeHtml(nodeLabel(n))}</div>
        <div class="nn-sub">${ago(n.lastHeard)}</div>
      </span>
      <span class="nn-sig">${sig}</span>`;
    li.addEventListener("click", () => selectTarget(n.num));
    ul.appendChild(li);
  }
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

async function connect() {
  if (!webSerialSupported()) {
    log("Web Serial is not supported here. Use Chrome/Edge on desktop, or Chrome on Android with a USB-C OTG connection.", true);
    return;
  }
  $("btn-connect").disabled = true;
  $("btn-connect").textContent = "Connecting…";
  try {
    state.radio = new Radio({
      onMyNode: (num) => {
        state.myNodeNum = num;
        $("device-info").innerHTML = `Connected to Heltec V3 · my node <b>!${(num >>> 0).toString(16)}</b>`;
        renderNodes();
      },
      onNodes: () => renderNodes(),
      onSignal: onSignal,
      onStatus: (status) => {
        // DeviceStatusEnum: 7 = configured, <=2 = disconnected
        if (status <= 2 && state.connected) handleDisconnect();
      },
    });
    await state.radio.connect();
    state.connected = true;
    $("radio-badge").classList.replace("off", "on");
    $("btn-connect").textContent = "Disconnect";
    $("btn-connect").disabled = false;
    log("Radio connected and configured.");
    restartPingTimer();
  } catch (e) {
    log(`Connect failed: ${e?.message || e}`, true);
    $("btn-connect").textContent = "Connect USB";
    $("btn-connect").disabled = false;
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
  $("btn-connect").textContent = "Connect USB";
  $("btn-connect").disabled = false;
  $("device-info").textContent = "Disconnected.";
  log("Radio disconnected.", true);
}

async function disconnect() {
  await state.radio?.disconnect();
  state.radio = null;
  handleDisconnect();
}

/* ---------------- phone GPS ---------------- */

const geo = new GeoWatcher(
  (fix) => {
    const first = !state.gpsFix;
    state.gpsFix = fix;
    $("gps-badge").classList.remove("off", "warn");
    $("gps-badge").classList.add(fix.accuracyM <= 30 ? "on" : "warn");
    $("gps-badge").textContent = `GPS ±${Math.round(fix.accuracyM)}m`;
    map.updateUser(fix);
    if (first) log(`Phone GPS fix acquired (±${Math.round(fix.accuracyM)} m).`);
  },
  (msg) => {
    $("gps-badge").classList.remove("on", "warn");
    $("gps-badge").classList.add("off");
    log(`GPS: ${msg}`, true);
  },
);

/* ---------------- periodic re-estimate (time decay) ---------------- */

state.estimateTimer = setInterval(() => {
  if (state.samples.length >= 3) recomputeEstimate();
  renderNodes(); // refresh "last heard" ages
}, 5000);

/* ---------------- UI wiring ---------------- */

$("btn-connect").addEventListener("click", () =>
  state.connected ? disconnect() : connect(),
);
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

/* ---------------- boot ---------------- */

if (!window.isSecureContext) {
  log("Not a secure context — Web Serial and GPS will be unavailable. Serve over HTTPS or localhost.", true);
}
if (!webSerialSupported()) {
  log("This browser lacks Web Serial. Use Chrome or Edge (Android Chrome works via USB-C OTG).", true);
}
geo.start();
log("Ready. Connect your Heltec V3 via USB-C, then pick a node to hunt.");
