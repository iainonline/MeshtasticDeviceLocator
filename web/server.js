// Production server for Fabled Mesh: serves the static build and relays
// phone GPS fixes to a paired browser tab over WebSocket.
//
// Why this exists: navigator.geolocation only reports the GPS of whatever
// device the browser is running on. If you run the tracker on a Pi5
// connected to the radio over USB, the Pi5 has no GPS — you need position
// from your phone instead. A phone opens gps.html (the "source" role) and
// streams fixes here; the main tracker (the "consumer" role) subscribes to
// the same session and receives them in real time. This is the web
// equivalent of the old Python app's GPSd-Forwarder-over-WiFi setup.
import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { WebSocketServer } from "ws";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const DIST_DIR = path.join(__dirname, "dist");
const PORT = Number(process.env.PORT) || 4173;

const MIME_TYPES = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".mjs": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".svg": "image/svg+xml",
  ".json": "application/json; charset=utf-8",
  ".png": "image/png",
  ".ico": "image/x-icon",
};

async function serveStatic(req, res) {
  let urlPath = decodeURIComponent(req.url.split("?")[0]);
  if (urlPath === "/") urlPath = "/index.html";

  // Prevent path traversal outside dist/.
  const filePath = path.normalize(path.join(DIST_DIR, urlPath));
  if (!filePath.startsWith(DIST_DIR)) {
    res.writeHead(400).end("Bad request");
    return;
  }

  let data;
  try {
    data = await readFile(filePath);
  } catch {
    // Both pages are static (no client-side router), so a miss just falls
    // back to whichever entry point matches the path prefix.
    const fallback = urlPath.startsWith("/gps") ? "gps.html" : "index.html";
    try {
      data = await readFile(path.join(DIST_DIR, fallback));
      res.writeHead(200, { "Content-Type": MIME_TYPES[".html"] });
      res.end(data);
    } catch {
      res.writeHead(404).end("Not found");
    }
    return;
  }

  const ext = path.extname(filePath);
  const isHtml = ext === ".html";
  res.writeHead(200, {
    "Content-Type": MIME_TYPES[ext] || "application/octet-stream",
    // index.html/gps.html must always revalidate (see the meta tags in the
    // HTML itself for the matching client-side reasoning); hashed asset
    // filenames change per build, so those can be cached indefinitely.
    "Cache-Control": isHtml
      ? "no-cache, no-store, must-revalidate"
      : "public, max-age=31536000, immutable",
  });
  res.end(data);
}

const server = createServer((req, res) => {
  serveStatic(req, res).catch(() => res.writeHead(500).end("Server error"));
});

/** @type {Map<string, {sources: Set<WebSocket>, consumers: Set<WebSocket>, lastFix: object|null, updatedAt: number}>} */
const sessions = new Map();

function getSession(id) {
  let s = sessions.get(id);
  if (!s) {
    s = { sources: new Set(), consumers: new Set(), lastFix: null, updatedAt: Date.now() };
    sessions.set(id, s);
  }
  return s;
}

function broadcastStatus(session) {
  const payload = JSON.stringify({
    type: "status",
    sources: session.sources.size,
    consumers: session.consumers.size,
  });
  for (const ws of [...session.sources, ...session.consumers]) {
    if (ws.readyState === ws.OPEN) ws.send(payload);
  }
}

const wss = new WebSocketServer({ server, path: "/ws/gps" });

wss.on("connection", (ws, req) => {
  const url = new URL(req.url, "http://internal");
  const sessionId = (url.searchParams.get("s") || "").trim().toUpperCase();
  const role = url.searchParams.get("role") === "source" ? "source" : "consumer";

  if (!sessionId || !/^[A-Z0-9]{4,12}$/.test(sessionId)) {
    ws.close(1008, "invalid session code");
    return;
  }

  const session = getSession(sessionId);
  const bucket = role === "source" ? session.sources : session.consumers;
  bucket.add(ws);
  session.updatedAt = Date.now();

  if (role === "consumer" && session.lastFix) {
    ws.send(JSON.stringify({ type: "fix", fix: session.lastFix }));
  }
  broadcastStatus(session);

  ws.on("message", (raw) => {
    session.updatedAt = Date.now();
    let msg;
    try {
      msg = JSON.parse(raw.toString());
    } catch {
      return;
    }
    if (role === "source" && msg.type === "fix" && msg.fix) {
      session.lastFix = msg.fix;
      const payload = JSON.stringify({ type: "fix", fix: msg.fix });
      for (const c of session.consumers) {
        if (c.readyState === c.OPEN) c.send(payload);
      }
    }
  });

  ws.on("close", () => {
    bucket.delete(ws);
    if (session.sources.size === 0 && session.consumers.size === 0) {
      sessions.delete(sessionId);
    } else {
      broadcastStatus(session);
    }
  });

  ws.on("error", () => ws.close());
});

// Sweep sessions that were abandoned without a clean WebSocket close
// (e.g. the phone lost signal outright rather than closing the tab).
const SESSION_TTL_MS = 30 * 60 * 1000;
setInterval(
  () => {
    const cutoff = Date.now() - SESSION_TTL_MS;
    for (const [id, s] of sessions) {
      if (s.updatedAt < cutoff) {
        for (const ws of [...s.sources, ...s.consumers]) ws.close(1000, "session expired");
        sessions.delete(id);
      }
    }
  },
  5 * 60 * 1000,
).unref();

server.listen(PORT, "0.0.0.0", () => {
  console.log(`Fabled Mesh server listening on :${PORT}`);
});
