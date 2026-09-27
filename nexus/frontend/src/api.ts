export interface HostHealth {
  cpu_pct: number | null;
  memory_pct: number | null;
  disk_pct: number | null;
  up: boolean | null;
}

export interface TopologyNode {
  id: string;
  label: string;
  type: "host" | "vm" | "laptop" | "phone";
  parent: string | null;
  online: boolean;
  tailscale_ip: string | null;
  health: HostHealth | null;
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
