import { defineConfig } from "vite";
import basicSsl from "@vitejs/plugin-basic-ssl";
import { fileURLToPath } from "node:url";

// @meshtastic/core bundles tslog, which imports Node built-ins at module
// scope but only uses them behind runtime guards — shim them for the browser.
const shim = fileURLToPath(new URL("./src/shims/node-shims.js", import.meta.url));

export default defineConfig({
  base: "./",
  plugins: [
    // Web Serial and Geolocation require a secure context; self-signed HTTPS
    // lets a phone on the same LAN reach the dev server.
    basicSsl(),
  ],
  resolve: {
    alias: {
      os: shim,
      path: shim,
      util: shim,
    },
  },
});
