/**
 * Consumer side of the phone-GPS relay: subscribes to a session on the
 * server (see server.js) and re-emits fixes pushed by the paired phone
 * (running gps.html) in the same shape GeoWatcher produces, so the rest of
 * the app doesn't need to know which source is active.
 */
export function makeSessionCode() {
  const alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"; // no 0/O/1/I
  let code = "";
  for (let i = 0; i < 6; i++) {
    code += alphabet[Math.floor(Math.random() * alphabet.length)];
  }
  return code;
}

export function wsUrlFor(pathAndQuery) {
  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${location.host}${pathAndQuery}`;
}

export class RemoteGpsClient {
  constructor(sessionId, handlers = {}) {
    this.sessionId = sessionId;
    this.handlers = handlers;
    this.ws = null;
    this.reconnectTimer = null;
    this.closedByUser = false;
  }

  start() {
    this.closedByUser = false;
    this._connect();
  }

  _connect() {
    const url = wsUrlFor(`/ws/gps?s=${encodeURIComponent(this.sessionId)}&role=consumer`);
    let ws;
    try {
      ws = new WebSocket(url);
    } catch (err) {
      this.handlers.onError?.(`Couldn't open relay connection: ${err.message || err}`);
      this._scheduleReconnect();
      return;
    }
    this.ws = ws;

    ws.addEventListener("open", () => this.handlers.onConnect?.());
    ws.addEventListener("close", () => {
      this.handlers.onDisconnect?.();
      if (!this.closedByUser) this._scheduleReconnect();
    });
    ws.addEventListener("error", () => {
      this.handlers.onError?.("Relay connection error.");
    });
    ws.addEventListener("message", (ev) => {
      let msg;
      try {
        msg = JSON.parse(ev.data);
      } catch {
        return;
      }
      if (msg.type === "fix" && msg.fix) {
        this.handlers.onFix?.(msg.fix);
      } else if (msg.type === "status") {
        this.handlers.onStatus?.({ sourcesConnected: msg.sources });
      }
    });
  }

  _scheduleReconnect() {
    clearTimeout(this.reconnectTimer);
    this.reconnectTimer = setTimeout(() => {
      if (!this.closedByUser) this._connect();
    }, 3000);
  }

  stop() {
    this.closedByUser = true;
    clearTimeout(this.reconnectTimer);
    this.ws?.close();
    this.ws = null;
  }
}
