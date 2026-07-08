// Browser shims for Node built-ins imported by tslog (bundled inside
// @meshtastic/core). All call sites are behind runtime guards, so inert
// implementations are sufficient.

export const hostname = undefined;

export function normalize(p) {
  return p;
}

export function formatWithOptions(_opts, ...args) {
  return args
    .map((a) => (typeof a === "string" ? a : JSON.stringify(a)))
    .join(" ");
}

export const types = {
  isError: (v) => v instanceof Error,
};

export default { hostname, normalize, formatWithOptions, types };
