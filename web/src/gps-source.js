/**
 * Phone-side GPS forwarder. Watches this device's location and streams
 * fixes to the relay server (server.js) for a session, so a tracker running
 * elsewhere (e.g. a Pi5 with no GPS of its own) can consume them — see
 * remote-gps.js on the consumer side.
 */
import { wsUrlFor } from "./remote-gps.js";

const $ = (id) => document.getElementById(id);

function setDot(state) {
  $("dot").className = `dot ${state}`;
}

function getSessionIdFromUrl() {
  const params = new URLSearchParams(location.search);
  const s = (params.get("s") || "").trim().toUpperCase();
  return /^[A-Z0-9]{4,12}$/.test(s) ? s : null;
}

let ws = null;
let wakeLock = null;
let fixCount = 0;
let watchId = null;

async function acquireWakeLock() {
  try {
    wakeLock = await navigator.wakeLock?.request("screen");
    wakeLock?.addEventListener("release", () => {
      wakeLock = null;
    });
  } catch {
    // Wake Lock unsupported/denied — forwarding still works, screen may just sleep.
  }
}

document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible" && !wakeLock) acquireWakeLock();
});

function connect(sessionId) {
  $("session").innerHTML = `Session <b>${sessionId}</b>`;
  const url = wsUrlFor(`/ws/gps?s=${encodeURIComponent(sessionId)}&role=source`);
  ws = new WebSocket(url);

  ws.addEventListener("open", () => {
    setDot("waiting");
    $("status").textContent = "Connected. Waiting for a GPS fix…";
    startWatchingPosition();
  });

  ws.addEventListener("close", () => {
    setDot("error");
    $("status").textContent = "Disconnected from tracker — reconnecting…";
    setTimeout(() => connect(sessionId), 3000);
  });

  ws.addEventListener("error", () => {
    setDot("error");
    $("status").textContent = "Connection error — retrying…";
  });
}

function startWatchingPosition() {
  if (!("geolocation" in navigator)) {
    setDot("error");
    $("status").textContent = "Geolocation isn't available in this browser.";
    return;
  }
  if (watchId != null) return;
  watchId = navigator.geolocation.watchPosition(
    (pos) => {
      const fix = {
        lat: pos.coords.latitude,
        lon: pos.coords.longitude,
        accuracyM: pos.coords.accuracy,
        heading: pos.coords.heading,
        speed: pos.coords.speed,
        t: pos.timestamp,
      };
      fixCount += 1;
      if (ws?.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: "fix", fix }));
        setDot("live");
        $("status").textContent = "Broadcasting your location to the tracker.";
      }
      $("stats").textContent = `Fix #${fixCount} · ±${Math.round(fix.accuracyM)}m · ${new Date().toLocaleTimeString()}`;
    },
    (err) => {
      setDot("error");
      $("status").textContent = `GPS error: ${err.message}`;
    },
    { enableHighAccuracy: true, maximumAge: 2000, timeout: 15000 },
  );
}

const urlSession = getSessionIdFromUrl();
if (urlSession) {
  acquireWakeLock();
  connect(urlSession);
} else {
  $("dot").textContent = "?";
  $("status").textContent = "No session code in the link.";
  $("entry").style.display = "flex";
  $("code-go").addEventListener("click", () => {
    const v = $("code-input").value.trim().toUpperCase();
    if (!/^[A-Z0-9]{4,12}$/.test(v)) {
      $("status").textContent = "That doesn't look like a valid code.";
      return;
    }
    $("entry").style.display = "none";
    acquireWakeLock();
    connect(v);
  });
}

if (!window.isSecureContext) {
  $("status").textContent = "This page needs HTTPS (or localhost) to access GPS.";
  setDot("error");
}
