import {
  siCloudflare,
  siDiscord,
  siDocker,
  siGithub,
  siGithubactions,
  siGrafana,
  siK3s,
  siMlflow,
  siPrometheus,
  siProxmox,
  siTailscale,
} from "simple-icons";

// The mark each tool is known by, as an SVG path on a 24-unit grid, extruded into a solid in
// Logo3D. Paths and brand colours come from the simple-icons package; the marks themselves
// remain their owners' trademarks and are used here only to identify the tool.
export interface Brand {
  path: string;
  color: string;
}

function brand(icon: { path: string; hex: string }, color?: string): Brand {
  return { path: icon.path, color: color ?? `#${icon.hex}` };
}

// Tailscale's and GitHub's own colours are near-black, which disappears in a dark room; both
// brands also publish a light variant for dark backgrounds, which is what is used here.
const LIGHT = "#e6e9ee";

export const BRANDS: Record<string, Brand> = {
  proxmox: brand(siProxmox),
  k3s: brand(siK3s),
  docker: brand(siDocker),
  tailscale: brand(siTailscale, LIGHT),
  cloudflare: brand(siCloudflare),
  prometheus: brand(siPrometheus),
  // The Pushgateway is a Prometheus project and has no mark of its own.
  pushgateway: brand(siPrometheus),
  grafana: brand(siGrafana),
  mlflow: brand(siMlflow),
  "github-actions": brand(siGithubactions),
  ghcr: brand(siGithub, LIGHT),
  discord: brand(siDiscord),
};

// Tools with no published mark in simple-icons get a small modelled object instead of a
// logo: see Emblems.tsx. A service id in neither table gets the generic emblem.
export type EmblemKind = "container" | "storage" | "bank" | "generic";

export const EMBLEMS: Record<string, { kind: EmblemKind; color: string }> = {
  cadvisor: { kind: "container", color: "#1aa6a6" },
  "azure-blob": { kind: "storage", color: "#0a84ff" },
  "bankml-api": { kind: "bank", color: "#e9dcc0" },
};
