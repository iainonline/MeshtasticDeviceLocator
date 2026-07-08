import { defineConfig } from "vite";
import basicSsl from "@vitejs/plugin-basic-ssl";
import { fileURLToPath } from "node:url";

// @meshtastic/core bundles tslog, which imports Node built-ins at module
// scope but only uses them behind runtime guards — shim them for the browser.
const shim = fileURLToPath(new URL("./src/shims/node-shims.js", import.meta.url));

export default defineConfig(({ mode }) => ({
  base: "./",
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
  preview: {
    host: true,
    port: Number(process.env.PORT) || 4173,
    allowedHosts: true,
  },
}));
