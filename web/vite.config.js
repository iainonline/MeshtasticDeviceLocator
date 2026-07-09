import { defineConfig } from "vite";
import basicSsl from "@vitejs/plugin-basic-ssl";
import { fileURLToPath } from "node:url";

// @meshtastic/core bundles tslog, which imports Node built-ins at module
// scope but only uses them behind runtime guards — shim them for the browser.
const shim = fileURLToPath(new URL("./src/shims/node-shims.js", import.meta.url));

// Stamped into the UI so a screenshot/log line proves which build is
// actually loaded — Railway rebuilding doesn't mean a given browser tab or
// cache is serving the new output, and that gap has been hard to diagnose
// from outside. Prefer Railway's own commit SHA env var; fall back to a
// build timestamp for local builds.
const BUILD_ID =
  process.env.RAILWAY_GIT_COMMIT_SHA?.slice(0, 7) ||
  new Date().toISOString().replace(/[:.]/g, "-");

export default defineConfig(({ mode }) => ({
  base: "./",
  define: {
    __BUILD_ID__: JSON.stringify(BUILD_ID),
  },
  plugins: [
    // Web Serial and Geolocation require a secure context; self-signed HTTPS
    // lets a phone on the same LAN reach the local dev server. Only enable
    // this for `vite dev` — a production host (e.g. Railway) terminates real
    // HTTPS at its edge and speaks plain HTTP to the app, so shipping a
    // self-signed cert there would break every request.
    ...(mode === "development" ? [basicSsl()] : []),
  ],
  resolve: {
    alias: {
      os: shim,
      path: shim,
      util: shim,
    },
  },
  build: {
    rollupOptions: {
      // Two independent entry points: the full tracker, and the minimal
      // phone-side GPS forwarder (kept separate so the phone never has to
      // download Leaflet/Meshtastic — see gps.html / src/gps-source.js).
      input: {
        main: fileURLToPath(new URL("./index.html", import.meta.url)),
        gps: fileURLToPath(new URL("./gps.html", import.meta.url)),
      },
    },
  },
  preview: {
    host: true,
    port: Number(process.env.PORT) || 4173,
    allowedHosts: true,
  },
}));
