/** Thin wrapper around the browser Geolocation API (the phone's GPS). */

export class GeoWatcher {
  constructor(onFix, onError) {
    this.onFix = onFix;
    this.onError = onError;
    this.watchId = null;
    this.last = null;
  }

  start() {
    if (!("geolocation" in navigator)) {
      this.onError?.("Geolocation is not available in this browser.");
      return;
    }
    this.watchId = navigator.geolocation.watchPosition(
      (pos) => {
        this.last = {
          lat: pos.coords.latitude,
          lon: pos.coords.longitude,
          accuracyM: pos.coords.accuracy,
          heading: pos.coords.heading,
          speed: pos.coords.speed,
          t: pos.timestamp,
        };
        this.onFix?.(this.last);
      },
      (err) => this.onError?.(err.message),
      { enableHighAccuracy: true, maximumAge: 2000, timeout: 15000 },
    );
  }

  stop() {
    if (this.watchId != null) {
      navigator.geolocation.clearWatch(this.watchId);
      this.watchId = null;
    }
  }
}
