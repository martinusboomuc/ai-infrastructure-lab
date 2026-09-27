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

const API_BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";

export async function fetchTopology(): Promise<TopologyNode[]> {
  const response = await fetch(`${API_BASE}/api/topology`);
  if (!response.ok) {
    throw new Error(`topology fetch failed: ${response.status}`);
  }
  const data = await response.json();
  return data.nodes;
}
