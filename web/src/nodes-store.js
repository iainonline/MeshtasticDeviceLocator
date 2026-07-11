/**
 * Multi-node tracking store.
 *
 * Accumulates, per node, everything we learn about where it is:
 *  - RSSI samples (our GPS position + signal, when heard directly), and
 *  - self-reported positions (when the node broadcasts its own GPS).
 *
 * From that it produces a best-available location estimate for EVERY node
 * (not just one target), classifies each node as static / mobile / unknown
 * from how much its position moves over time, and serialises the whole thing
 * to/from localStorage so data survives across sessions.
 */
import { estimatePosition, haversineMeters, DEFAULT_PARAMS } from "./estimator.js";

const MAX_SAMPLES_PER_NODE = 200;
const MAX_REPORTED_PER_NODE = 60;
const MAX_ESTIMATE_HISTORY = 40;

// Mobility thresholds (metres / time).
const MOBILE_SPREAD_M = 60; // positions differing by more than this => mobile
const STATIC_SPREAD_M = 35; // positions all within this (over time) => static
const STATIC_MIN_SPAN_MS = 3 * 60 * 1000; // need this much time to call it static
const REPORTED_STALE_MS = 6 * 60 * 60 * 1000; // ignore self-reports older than this for "current" position
const CONTEXT_STALE_MS = 30 * 60 * 1000; // ignore "where we heard it" context older than this
const HOP_RANGE_M = 2500; // rough single-hop LoRa range for inferred-radius scaling

export class NodeStore {
  constructor() {
    /** @type {Map<number, object>} num -> track */
    this.tracks = new Map();
    this.myNodeNum = null;
  }

  _track(num) {
    let t = this.tracks.get(num);
    if (!t) {
      t = {
        num,
        shortName: null,
        longName: null,
        samples: [], // {lat, lon, rssi, snr, t}
        reported: [], // {lat, lon, t}
        estimateHistory: [], // {lat, lon, t}
        lastContext: null, // {obsLat, obsLon, hops, t} — where WE were when last heard
        estimate: null,
        mobility: "unknown",
        firstSeen: null,
        lastHeard: null,
      };
      this.tracks.set(num, t);
    }
    return t;
  }

  setMeta(num, { shortName, longName, lastHeard } = {}) {
    const t = this._track(num);
    if (shortName) t.shortName = shortName;
    if (longName) t.longName = longName;
    if (lastHeard) t.lastHeard = Math.max(t.lastHeard || 0, lastHeard);
  }

  addSample(num, sample, nowMs) {
    const t = this._track(num);
    if (t.firstSeen == null) t.firstSeen = nowMs;
    t.lastHeard = Math.max(t.lastHeard || 0, sample.t || nowMs);
    t.samples.push(sample);
    if (t.samples.length > MAX_SAMPLES_PER_NODE) {
      t.samples.splice(0, t.samples.length - MAX_SAMPLES_PER_NODE);
    }
  }

  /**
   * Record where WE were (and the hop distance) when we last heard a node —
   * even via relay. Lets us give a coarse "somewhere out there" prediction
   * for nodes that neither broadcast a position nor were heard directly.
   */
  setContext(num, ctx, nowMs) {
    const t = this._track(num);
    if (t.firstSeen == null) t.firstSeen = nowMs;
    t.lastContext = ctx;
    t.lastHeard = Math.max(t.lastHeard || 0, ctx.t || nowMs);
  }

  addReported(num, pos, nowMs) {
    const t = this._track(num);
    if (t.firstSeen == null) t.firstSeen = nowMs;
    t.lastHeard = Math.max(t.lastHeard || 0, pos.t || nowMs);
    const last = t.reported[t.reported.length - 1];
    // De-dupe near-identical consecutive reports (a stationary node beacons
    // the same fix repeatedly); keep it if it moved or enough time passed.
    if (
      last &&
      haversineMeters(last.lat, last.lon, pos.lat, pos.lon) < 5 &&
      (pos.t || nowMs) - last.t < 60000
    ) {
      return;
    }
    t.reported.push(pos);
    if (t.reported.length > MAX_REPORTED_PER_NODE) {
      t.reported.splice(0, t.reported.length - MAX_REPORTED_PER_NODE);
    }
  }

  /** Max pairwise distance across a set of {lat,lon} points, in metres. */
  static spread(points) {
    let max = 0;
    for (let i = 0; i < points.length; i++) {
      for (let j = i + 1; j < points.length; j++) {
        const d = haversineMeters(
          points[i].lat,
          points[i].lon,
          points[j].lat,
          points[j].lon,
        );
        if (d > max) max = d;
      }
    }
    return max;
  }

  /**
   * Classify mobility. Prefers self-reported GPS (accurate); falls back to
   * the history of our own estimates (noisy, so a larger threshold) when the
   * node never reports position.
   */
  classifyMobility(t) {
    const reported = t.reported;
    if (reported.length >= 2) {
      const spread = NodeStore.spread(reported);
      const span = reported[reported.length - 1].t - reported[0].t;
      if (spread > MOBILE_SPREAD_M) return "mobile";
      if (spread <= STATIC_SPREAD_M && span >= STATIC_MIN_SPAN_MS) return "static";
      return "unknown";
    }
    // No/one self-report: infer cautiously from estimate drift.
    const est = t.estimateHistory;
    if (est.length >= 3) {
      const spread = NodeStore.spread(est);
      const span = est[est.length - 1].t - est[0].t;
      // Estimates are uncertain to tens of metres, so require a big, sustained
      // move before calling a node mobile from estimates alone.
      if (spread > 200) return "mobile";
      if (spread <= 80 && span >= STATIC_MIN_SPAN_MS) return "static";
    }
    return "unknown";
  }

  /**
   * Produce the best-available estimate for one node.
   * Priority: fresh self-reported position > RSSI trilateration > coarse.
   */
  estimateNode(t, params, nowMs) {
    // 1) Self-reported position (their own GPS) — most trustworthy.
    const lastRep = t.reported[t.reported.length - 1];
    if (lastRep && nowMs - lastRep.t < REPORTED_STALE_MS) {
      const ageSec = (nowMs - lastRep.t) / 1000;
      const mobile = t.mobility === "mobile";
      // Static: their GPS accuracy dominates (~25 m). Mobile: uncertainty
      // grows with staleness (assume it could have walked off at ~1.5 m/s).
      const radiusM = mobile
        ? Math.min(25 + ageSec * 1.5, 3000)
        : 25;
      return {
        lat: lastRep.lat,
        lon: lastRep.lon,
        radiusM,
        source: "reported",
        quality: { n: t.reported.length, ageSec },
      };
    }

    // 2) RSSI trilateration from our direct samples.
    if (t.samples.length >= 1) {
      const est = estimatePosition(t.samples, params);
      if (est) {
        return { ...est, source: est.quality.mode === "coarse" ? "coarse" : "trilateration" };
      }
    }

    // 3) Inferred: no position broadcast and never heard directly (only via
    // relay). We can't pin it, but we know it was reachable from where we
    // stood, within roughly (hops+1) single-hop ranges — a big honest circle
    // centred on our last observation point.
    if (t.lastContext && nowMs - t.lastContext.t < CONTEXT_STALE_MS) {
      const hops = t.lastContext.hops == null ? 1 : t.lastContext.hops;
      const radiusM = Math.min(HOP_RANGE_M * (hops + 1), 15000);
      return {
        lat: t.lastContext.obsLat,
        lon: t.lastContext.obsLon,
        radiusM,
        source: "inferred",
        quality: { hops },
      };
    }
    return null;
  }

  /** Recompute mobility + estimate for every node. Returns array of tracks. */
  recomputeAll(params = DEFAULT_PARAMS, nowMs = null) {
    const now = nowMs ?? Date.now();
    const out = [];
    for (const t of this.tracks.values()) {
      t.mobility = this.classifyMobility(t);
      const est = this.estimateNode(t, params, now);
      if (est) {
        // Track estimate history (for mobility inference) only when it moved.
        const lastE = t.estimateHistory[t.estimateHistory.length - 1];
        if (
          !lastE ||
          haversineMeters(lastE.lat, lastE.lon, est.lat, est.lon) > 15 ||
          now - lastE.t > 60000
        ) {
          t.estimateHistory.push({ lat: est.lat, lon: est.lon, t: now });
          if (t.estimateHistory.length > MAX_ESTIMATE_HISTORY) {
            t.estimateHistory.shift();
          }
        }
      }
      t.estimate = est;
      out.push(t);
    }
    return out;
  }

  /* ---------------- persistence ---------------- */

  toJSON() {
    return {
      version: 1,
      savedAt: null, // stamped by caller (Date.now unavailable in some contexts)
      myNodeNum: this.myNodeNum,
      tracks: [...this.tracks.values()].map((t) => ({
        num: t.num,
        shortName: t.shortName,
        longName: t.longName,
        samples: t.samples,
        reported: t.reported,
        estimateHistory: t.estimateHistory,
        lastContext: t.lastContext,
        mobility: t.mobility,
        firstSeen: t.firstSeen,
        lastHeard: t.lastHeard,
      })),
    };
  }

  loadJSON(data) {
    if (!data || !Array.isArray(data.tracks)) return;
    this.myNodeNum = data.myNodeNum ?? this.myNodeNum;
    for (const s of data.tracks) {
      if (typeof s.num !== "number") continue;
      const t = this._track(s.num);
      t.shortName = s.shortName ?? t.shortName;
      t.longName = s.longName ?? t.longName;
      t.samples = Array.isArray(s.samples) ? s.samples.slice(-MAX_SAMPLES_PER_NODE) : [];
      t.reported = Array.isArray(s.reported) ? s.reported.slice(-MAX_REPORTED_PER_NODE) : [];
      t.estimateHistory = Array.isArray(s.estimateHistory)
        ? s.estimateHistory.slice(-MAX_ESTIMATE_HISTORY)
        : [];
      t.lastContext = s.lastContext ?? null;
      t.mobility = s.mobility || "unknown";
      t.firstSeen = s.firstSeen ?? null;
      t.lastHeard = s.lastHeard ?? null;
    }
  }
}
