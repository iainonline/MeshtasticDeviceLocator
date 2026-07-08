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

  fitAll() {
    const items = [];
    if (this.lastUser) items.push([this.lastUser.lat, this.lastUser.lon]);
    if (this.estimateCircle) {
      const b = this.estimateCircle.getBounds();
      items.push(b.getSouthWest(), b.getNorthEast());
    }
    if (items.length) {
      this.map.fitBounds(L.latLngBounds(items).pad(0.2));
      this.follow = false;
      this.onFollowChange?.(false);
    }
  }
}
