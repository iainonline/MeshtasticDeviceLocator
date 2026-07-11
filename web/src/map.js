/** Real-time Leaflet map: user position, sample trail, node estimate circle. */
import L from "leaflet";
import "leaflet/dist/leaflet.css";

function rssiColor(rssi) {
  // -60 (strong, green) .. -120 (weak, red)
  const t = Math.min(Math.max((-60 - rssi) / 60, 0), 1);
  const hue = 120 * (1 - t);
  return `hsl(${hue}, 85%, 45%)`;
}

export class LocatorMap {
  constructor(el) {
    this.map = L.map(el, { zoomControl: true }).setView([0, 0], 3);
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      attribution: "&copy; OpenStreetMap contributors",
    }).addTo(this.map);

    this.samplesLayer = L.layerGroup().addTo(this.map);
    // Network overlay: self-reported node positions + topology edges.
    this.networkLayer = L.layerGroup().addTo(this.map);
    this.follow = true;
    this.hasCenteredOnce = false;

    this.userMarker = null;
    this.userAccuracy = null;
    this.estimateCircle = null;
    this.estimateMarker = null;
    this.reportedMarker = null;

    this.map.on("dragstart", () => {
      this.follow = false;
      this.onFollowChange?.(false);
    });

    // Leaflet measures its container once at init; if the viewport changes
    // afterwards (rotation, URL bar collapsing, Custom Tab chrome settling
    // after first paint) the map keeps painting at the stale size and the
    // page looks clipped. Re-measure on every viewport change, and once
    // shortly after load to catch a first paint that happened mid-layout.
    let relayoutTimer = null;
    const relayout = () => {
      clearTimeout(relayoutTimer);
      relayoutTimer = setTimeout(() => this.map.invalidateSize(), 150);
    };
    window.addEventListener("resize", relayout);
    window.addEventListener("orientationchange", relayout);
    window.visualViewport?.addEventListener("resize", relayout);
    setTimeout(() => this.map.invalidateSize(), 500);
  }

  setFollow(v) {
    this.follow = v;
    if (v && this.lastUser) {
      this.map.panTo([this.lastUser.lat, this.lastUser.lon]);
    }
  }

  /** Update the user's (phone GPS) position. */
  updateUser(fix) {
    this.lastUser = fix;
    const ll = [fix.lat, fix.lon];
    if (!this.userMarker) {
      this.userMarker = L.marker(ll, {
        icon: L.divIcon({
          className: "user-dot-wrap",
          html: '<div class="user-dot"></div>',
          iconSize: [18, 18],
          iconAnchor: [9, 9],
        }),
        title: "You",
        zIndexOffset: 1000,
      }).addTo(this.map);
      this.userAccuracy = L.circle(ll, {
        radius: fix.accuracyM || 0,
        color: "#2f81f7",
        weight: 1,
        fillOpacity: 0.08,
        interactive: false,
      }).addTo(this.map);
    } else {
      this.userMarker.setLatLng(ll);
      this.userAccuracy.setLatLng(ll).setRadius(fix.accuracyM || 0);
    }
    if (!this.hasCenteredOnce) {
      this.map.setView(ll, 16);
      this.hasCenteredOnce = true;
    } else if (this.follow) {
      this.map.panTo(ll, { animate: true });
    }
  }

  /** Add a signal sample dot at the observer position, coloured by RSSI. */
  addSample(sample) {
    L.circleMarker([sample.lat, sample.lon], {
      radius: 5,
      color: rssiColor(sample.rssi),
      weight: 2,
      fillColor: rssiColor(sample.rssi),
      fillOpacity: 0.7,
    })
      .bindTooltip(
        `${sample.rssi} dBm${sample.snr != null ? ` / SNR ${sample.snr.toFixed(1)}` : ""}`,
      )
      .addTo(this.samplesLayer);
  }

  clearSamples() {
    this.samplesLayer.clearLayers();
    this.clearEstimate();
  }

  /** Draw / move the probable-location circle. Radius = uncertainty. */
  updateEstimate(est, label) {
    const ll = [est.lat, est.lon];
    const color = est.quality.mode === "trilateration" ? "#e5534b" : "#d4a72c";
    if (!this.estimateCircle) {
      this.estimateCircle = L.circle(ll, {
        radius: est.radiusM,
        color,
        weight: 2,
        dashArray: est.quality.mode === "trilateration" ? null : "6 6",
        fillColor: color,
        fillOpacity: 0.12,
      }).addTo(this.map);
      this.estimateMarker = L.marker(ll, {
        icon: L.divIcon({
          className: "node-est-wrap",
          html: '<div class="node-est">?</div>',
          iconSize: [26, 26],
          iconAnchor: [13, 13],
        }),
      }).addTo(this.map);
    } else {
      this.estimateCircle.setLatLng(ll).setRadius(est.radiusM);
      this.estimateCircle.setStyle({
        color,
        fillColor: color,
        dashArray: est.quality.mode === "trilateration" ? null : "6 6",
      });
      this.estimateMarker.setLatLng(ll);
    }
    this.estimateMarker.bindTooltip(label, { direction: "top" });
  }

  clearEstimate() {
    this.estimateCircle?.remove();
    this.estimateMarker?.remove();
    this.reportedMarker?.remove();
    this.estimateCircle = null;
    this.estimateMarker = null;
    this.reportedMarker = null;
  }

  /** Show the position the node itself reported (if any), for comparison. */
  updateReported(lat, lon, label) {
    const ll = [lat, lon];
    if (!this.reportedMarker) {
      this.reportedMarker = L.marker(ll, {
        icon: L.divIcon({
          className: "node-rep-wrap",
          html: '<div class="node-rep"></div>',
          iconSize: [14, 14],
          iconAnchor: [7, 7],
        }),
      }).addTo(this.map);
    } else {
      this.reportedMarker.setLatLng(ll);
    }
    this.reportedMarker.bindTooltip(`${label} (self-reported)`, {
      direction: "top",
    });
  }

  /**
   * Draw the network overlay: a marker for every node that self-reports a
   * position, plus topology edges between positioned nodes.
   * @param {Array<{num,lat,lon,label,active}>} positionedNodes
   * @param {Array<{a,b,snr}>} edges  node-num pairs
   */
  renderNetwork(positionedNodes, edges) {
    this.networkLayer.clearLayers();
    const byNum = new Map(positionedNodes.map((n) => [n.num, n]));

    // Edges first, so node dots sit on top.
    const drawn = new Set();
    for (const e of edges) {
      const a = byNum.get(e.a);
      const b = byNum.get(e.b);
      if (!a || !b) continue; // can only draw edges between located nodes
      const key = e.a < e.b ? `${e.a}-${e.b}` : `${e.b}-${e.a}`;
      if (drawn.has(key)) continue;
      drawn.add(key);
      const line = L.polyline(
        [
          [a.lat, a.lon],
          [b.lat, b.lon],
        ],
        { color: "#7d56f3", weight: 2, opacity: 0.7 },
      ).addTo(this.networkLayer);
      if (e.snr != null) {
        line.bindTooltip(`SNR ${e.snr.toFixed(1)} dB`, { sticky: true });
      }
    }

    for (const n of positionedNodes) {
      L.marker([n.lat, n.lon], {
        icon: L.divIcon({
          className: "net-node-wrap",
          html: `<div class="net-node${n.active ? " active" : ""}">${escapeHtmlAttr(n.short || "•")}</div>`,
          iconSize: [30, 18],
          iconAnchor: [15, 9],
        }),
      })
        .bindTooltip(n.label + (n.active ? " · responded" : ""), {
          direction: "top",
        })
        .addTo(this.networkLayer);
    }
  }

  clearNetwork() {
    this.networkLayer.clearLayers();
  }

  /**
   * Draw an estimate circle + marker for EVERY node we can place.
   * @param {Array<{num,label,short,lat,lon,radiusM,source,mobility,selected}>} list
   */
  renderEstimates(list) {
    if (!this.estimatesLayer) {
      this.estimatesLayer = L.layerGroup().addTo(this.map);
    }
    this.estimatesLayer.clearLayers();
    const SRC_COLOR = {
      reported: "#3fb950", // node's own GPS
      trilateration: "#e5534b", // solved from RSSI
      coarse: "#d4a72c", // single/low-info guess
    };
    for (const n of list) {
      const color = SRC_COLOR[n.source] || "#8b949e";
      L.circle([n.lat, n.lon], {
        radius: n.radiusM,
        color,
        weight: n.selected ? 3 : 1.5,
        opacity: n.selected ? 1 : 0.6,
        dashArray: n.source === "coarse" ? "6 6" : null,
        fillColor: color,
        fillOpacity: n.selected ? 0.15 : 0.06,
      }).addTo(this.estimatesLayer);

      const mob =
        n.mobility === "mobile" ? "▶" : n.mobility === "static" ? "■" : "";
      L.marker([n.lat, n.lon], {
        zIndexOffset: n.selected ? 500 : 0,
        icon: L.divIcon({
          className: "est-node-wrap",
          html: `<div class="est-node est-${n.source}${n.selected ? " selected" : ""}">${escapeHtmlAttr(n.short || "•")}${mob ? `<span class="est-mob">${mob}</span>` : ""}</div>`,
          iconSize: [34, 18],
          iconAnchor: [17, 9],
        }),
      })
        .bindTooltip(
          `${n.label} · ${n.source}${n.mobility !== "unknown" ? ` · ${n.mobility}` : ""} · ±${n.radiusM >= 1000 ? (n.radiusM / 1000).toFixed(1) + "km" : Math.round(n.radiusM) + "m"}`,
          { direction: "top" },
        )
        .on("click", () => this.onEstimateClick?.(n.num))
        .addTo(this.estimatesLayer);
    }
  }

  clearEstimates() {
    this.estimatesLayer?.clearLayers();
  }

  /** Fit the view to all drawn estimate markers (used when there's no GPS fix). */
  fitEstimates() {
    if (!this.estimatesLayer) return false;
    const pts = [];
    this.estimatesLayer.eachLayer((l) => {
      if (l.getLatLng) pts.push(l.getLatLng());
    });
    if (!pts.length) return false;
    this.map.fitBounds(L.latLngBounds(pts).pad(0.3), { maxZoom: 16 });
    return true;
  }

  fitAll() {
    const items = [];
    if (this.lastUser) items.push([this.lastUser.lat, this.lastUser.lon]);
    if (this.estimateCircle) {
      const b = this.estimateCircle.getBounds();
      items.push(b.getSouthWest(), b.getNorthEast());
    }
    this.networkLayer.eachLayer((l) => {
      if (l.getLatLng) items.push(l.getLatLng());
    });
    if (items.length) {
      this.map.fitBounds(L.latLngBounds(items).pad(0.2));
      this.follow = false;
      this.onFollowChange?.(false);
    }
  }
}

function escapeHtmlAttr(s) {
  return String(s).replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c],
  );
}
