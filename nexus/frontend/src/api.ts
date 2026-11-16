export interface HostHealth {
  cpu_pct: number | null;
  memory_pct: number | null;
  disk_pct: number | null;
  up: boolean | null;
}

export interface QuickLink {
  label: string;
  url: string;
}

export interface TopologyNode {
  id: string;
  label: string;
  type: "host" | "vm" | "laptop" | "phone";
  parent: string | null;
  online: boolean;
  tailscale_ip: string | null;
  health: HostHealth | null;
  links: QuickLink[];
}

// Always relative: in production nginx reverse-proxies /api/ to the backend container by its
// Compose service name (see nginx.conf); in dev, Vite's own server.proxy does the equivalent
// (see vite.config.ts). The frontend's own code never needs to know the backend's real address.
export async function fetchTopology(): Promise<TopologyNode[]> {
  const response = await fetch("/api/topology");
  if (!response.ok) {
    throw new Error(`topology fetch failed: ${response.status}`);
  }
  const data = await response.json();
  return data.nodes;
}

export interface Decision {
  alternative: string;
  reason: string;
  adr: QuickLink;
}

// A live value the backend reads for a service, such as the BankML model's ROC-AUC.
export interface Fact {
  label: string;
  value: string;
}

export interface Service {
  id: string;
  name: string;
  layer: string;
  description: string;
  links: QuickLink[];
  decision: Decision | null;
  status: "up" | "down" | "unknown";
  facts: Fact[];
}

export async function fetchServices(): Promise<Service[]> {
  const response = await fetch("/api/services");
  if (!response.ok) {
    throw new Error(`services fetch failed: ${response.status}`);
  }
  const data = await response.json();
  return data.services;
}

export interface Alert {
  name: string;
  folder: string;
  severity: string;
  target: string;
  summary: string;
  starts_at: string;
  silenced: boolean;
}

export interface AlertsResponse {
  configured: boolean;
  alerts: Alert[];
  channels: QuickLink[];
  grafana_url: string;
  error: string | null;
}

export async function fetchAlerts(): Promise<AlertsResponse> {
  const response = await fetch("/api/alerts");
  if (!response.ok) {
    throw new Error(`alerts fetch failed: ${response.status}`);
  }
  return response.json();
}
