/**
 * Position estimation from RSSI samples.
 *
 * Ported and modernised from the Python mesh_tracker implementation:
 *  - log-distance path loss model (RSSI -> distance)
 *  - outlier rejection (2 sigma on RSSI)
 *  - weights from RSSI, SNR and sample age (exponential time decay)
 *  - bearing-diversity check
 *  - Levenberg-Marquardt weighted least squares in a local ENU frame
 *  - uncertainty radius from weighted residuals + geometry
 */

const EARTH_M_PER_DEG_LAT = 110540;
const EARTH_M_PER_DEG_LON = 111320; // scaled by cos(lat)

export const DEFAULT_PARAMS = {
  txPowerDbm: 20, // Heltec V3 (SX1262) default max TX power
  freqMhz: 915, // 915 US / 868 EU / 433
  pathLossExp: 2.7, // 2 = free space, 2.5-3 outdoor, 3-4 urban
  timeDecaySec: 600, // sample weight halves roughly every ~7 min
  maxSamples: 200,
};

/** Log-distance path loss: estimated distance in meters for a given RSSI. */
export function rssiToDistance(rssi, params = DEFAULT_PARAMS) {
  const { txPowerDbm, freqMhz, pathLossExp } = params;
  // Free-space path loss at the 1 m reference distance
  const fspl1m = 20 * Math.log10(freqMhz) - 27.55;
  const pathLoss = txPowerDbm - rssi - fspl1m;
  const d = 10 ** (pathLoss / (10 * pathLossExp));
  return Math.max(d, 1);
}

function toLocal(lat, lon, lat0, lon0) {
  const kx = EARTH_M_PER_DEG_LON * Math.cos((lat0 * Math.PI) / 180);
  return {
    x: (lon - lon0) * kx,
    y: (lat - lat0) * EARTH_M_PER_DEG_LAT,
  };
}

function toGeo(x, y, lat0, lon0) {
  const kx = EARTH_M_PER_DEG_LON * Math.cos((lat0 * Math.PI) / 180);
  return {
    lat: lat0 + y / EARTH_M_PER_DEG_LAT,
    lon: lon0 + x / kx,
  };
}

export function haversineMeters(lat1, lon1, lat2, lon2) {
  const R = 6371000;
  const p1 = (lat1 * Math.PI) / 180;
  const p2 = (lat2 * Math.PI) / 180;
  const dp = ((lat2 - lat1) * Math.PI) / 180;
  const dl = ((lon2 - lon1) * Math.PI) / 180;
  const a =
    Math.sin(dp / 2) ** 2 + Math.cos(p1) * Math.cos(p2) * Math.sin(dl / 2) ** 2;
  return 2 * R * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

/**
 * How two-dimensional the observer track is: ratio of the minor to major
 * principal axis of the observer positions (0 = perfectly collinear).
 * Range-only fixes from a (near-)straight track have a mirror ambiguity, so
 * the uncertainty must be inflated.
 */
function trackPlanarity(points) {
  if (points.length < 3) return 0;
  const mx = mean(points.map((p) => p.x));
  const my = mean(points.map((p) => p.y));
  let sxx = 0;
  let sxy = 0;
  let syy = 0;
  for (const p of points) {
    const dx = p.x - mx;
    const dy = p.y - my;
    sxx += dx * dx;
    sxy += dx * dy;
    syy += dy * dy;
  }
  const tr = sxx + syy;
  const det = sxx * syy - sxy * sxy;
  const disc = Math.sqrt(Math.max(0, tr * tr - 4 * det));
  const l1 = (tr + disc) / 2;
  const l2 = (tr - disc) / 2;
  if (l1 <= 0) return 0;
  return Math.sqrt(Math.max(l2, 0) / l1);
}

/** Circular standard deviation of bearings, in degrees. */
function bearingSpread(points, cx, cy) {
  if (points.length < 2) return 0;
  let sumSin = 0;
  let sumCos = 0;
  for (const p of points) {
    const b = Math.atan2(p.x - cx, p.y - cy);
    sumSin += Math.sin(b);
    sumCos += Math.cos(b);
  }
  const r = Math.hypot(sumSin, sumCos) / points.length;
  // Circular std dev; r ~ 1 means all bearings identical
  const std = Math.sqrt(Math.max(0, -2 * Math.log(Math.max(r, 1e-9))));
  return (std * 180) / Math.PI;
}

/**
 * Estimate node position from samples.
 *
 * @param {Array<{lat:number, lon:number, rssi:number, snr:number|null, t:number}>} samples
 *   Observer GPS position + signal readings, t in ms epoch.
 * @param {object} params estimation parameters (see DEFAULT_PARAMS)
 * @returns {null | {lat:number, lon:number, radiusM:number, quality:object}}
 */
export function estimatePosition(samples, params = DEFAULT_PARAMS) {
  const now = Date.now();
  let s = samples.slice(-params.maxSamples);
  if (s.length === 0) return null;

  // --- Low-sample fallback: circle centred on strongest recent sample ---
  if (s.length < 3) {
    const best = s.reduce((a, b) => (b.rssi > a.rssi ? b : a));
    const d = rssiToDistance(best.rssi, params);
    return {
      lat: best.lat,
      lon: best.lon,
      radiusM: clampRadius(d * 1.5 + 50),
      quality: {
        n: s.length,
        mode: "coarse",
        avgRssi: mean(s.map((x) => x.rssi)),
        bearingSpreadDeg: 0,
        rmseM: null,
      },
    };
  }

  // --- Outlier rejection: drop samples > 2 sigma from mean RSSI ---
  if (s.length >= 5) {
    const m = mean(s.map((x) => x.rssi));
    const sd = std(s.map((x) => x.rssi));
    if (sd > 0) {
      const kept = s.filter((x) => Math.abs(x.rssi - m) <= 2 * sd);
      if (kept.length >= 3) s = kept;
    }
  }

  // --- Weights: signal strength x SNR bonus x time decay ---
  const meas = s.map((x) => {
    let w = 10 ** (x.rssi / 20);
    if (x.snr != null && x.snr > 0) w *= x.snr + 10;
    const ageSec = Math.max(0, (now - x.t) / 1000);
    w *= Math.exp(-ageSec / params.timeDecaySec);
    return { ...x, w, d: rssiToDistance(x.rssi, params) };
  });

  const totW = meas.reduce((acc, m) => acc + m.w, 0);
  if (!(totW > 0)) return null;

  // Local ENU frame around the weighted centroid of observer positions
  const lat0 = meas.reduce((a, m) => a + m.lat * m.w, 0) / totW;
  const lon0 = meas.reduce((a, m) => a + m.lon * m.w, 0) / totW;
  const pts = meas.map((m) => ({ ...m, ...toLocal(m.lat, m.lon, lat0, lon0) }));

  // --- Levenberg-Marquardt on f_i = sqrt(w_i) * (||p - p_i|| - d_i) ---
  let px = 0;
  let py = 0;
  let lambda = 1e-3;
  let cost = costAt(px, py, pts);
  for (let iter = 0; iter < 60; iter++) {
    // Build normal equations J^T J and J^T r
    let jtj00 = 0;
    let jtj01 = 0;
    let jtj11 = 0;
    let jtr0 = 0;
    let jtr1 = 0;
    for (const p of pts) {
      const dx = px - p.x;
      const dy = py - p.y;
      const dist = Math.max(Math.hypot(dx, dy), 1e-6);
      const r = dist - p.d;
      const sw = Math.sqrt(p.w);
      const jx = (sw * dx) / dist;
      const jy = (sw * dy) / dist;
      jtj00 += jx * jx;
      jtj01 += jx * jy;
      jtj11 += jy * jy;
      jtr0 += jx * sw * r;
      jtr1 += jy * sw * r;
    }
    const a00 = jtj00 * (1 + lambda);
    const a11 = jtj11 * (1 + lambda);
    const det = a00 * a11 - jtj01 * jtj01;
    if (Math.abs(det) < 1e-12) break;
    const sx = (-jtr0 * a11 + jtr1 * jtj01) / det;
    const sy = (-jtr1 * a00 + jtr0 * jtj01) / det;
    const nx = px + sx;
    const ny = py + sy;
    const nCost = costAt(nx, ny, pts);
    if (nCost < cost) {
      px = nx;
      py = ny;
      cost = nCost;
      lambda = Math.max(lambda / 3, 1e-9);
      if (Math.hypot(sx, sy) < 0.5) break; // converged to < 0.5 m
    } else {
      lambda *= 4;
      if (lambda > 1e6) break;
    }
  }

  // --- Uncertainty: weighted RMS residual + geometry penalties ---
  let wr2 = 0;
  for (const p of pts) {
    const r = Math.hypot(px - p.x, py - p.y) - p.d;
    wr2 += p.w * r * r;
  }
  const rmse = Math.sqrt(wr2 / totW);

  const spread = bearingSpread(pts, px, py);
  // Poor angular diversity => position is poorly constrained along one axis
  const geomFactor = spread >= 60 ? 1 : 1 + (60 - spread) / 20;
  const avgDist = mean(pts.map((p) => p.d));
  // RSSI ranging is noisy: never claim better than ~15% of range
  const floor = Math.max(30, avgDist * 0.15);
  let radiusM = rmse * geomFactor;

  // Near-collinear observer track => mirror ambiguity across the track line;
  // the true position may be at ~range on either side, so widen accordingly.
  const planarity = trackPlanarity(pts);
  if (planarity < 0.25) {
    radiusM = Math.max(radiusM, avgDist * (1 - planarity));
  }

  radiusM = clampRadius(Math.max(radiusM, floor));

  const { lat, lon } = toGeo(px, py, lat0, lon0);
  return {
    lat,
    lon,
    radiusM,
    quality: {
      n: pts.length,
      mode:
        spread >= 30 && planarity >= 0.25 ? "trilateration" : "low-diversity",
      planarity,
      avgRssi: mean(pts.map((p) => p.rssi)),
      bearingSpreadDeg: spread,
      rmseM: rmse,
      avgDistM: avgDist,
    },
  };
}

function costAt(x, y, pts) {
  let c = 0;
  for (const p of pts) {
    const r = Math.hypot(x - p.x, y - p.y) - p.d;
    c += p.w * r * r;
  }
  return c;
}

function clampRadius(r) {
  return Math.min(Math.max(r, 25), 10000);
}

function mean(a) {
  return a.reduce((x, y) => x + y, 0) / a.length;
}

function std(a) {
  const m = mean(a);
  return Math.sqrt(mean(a.map((x) => (x - m) ** 2)));
}
