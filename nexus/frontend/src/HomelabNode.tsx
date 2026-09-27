import { Handle, Position } from "@xyflow/react";
import type { TopologyNode } from "./api";

const ICONS: Record<TopologyNode["type"], string> = {
  host: "🖥️",
  vm: "📦",
  laptop: "💻",
  phone: "📱",
};

function HealthBar({ label, pct }: { label: string; pct: number | null }) {
  if (pct === null) return null;
  const color = pct > 90 ? "#f87171" : pct > 75 ? "#fbbf24" : "#4ade80";
  return (
    <div className="health-row">
      <span className="health-label">{label}</span>
      <div className="health-track">
        <div className="health-fill" style={{ width: `${Math.min(pct, 100)}%`, background: color }} />
      </div>
      <span className="health-pct">{pct.toFixed(0)}%</span>
    </div>
  );
}

export function HomelabNode({ data }: { data: TopologyNode }) {
  return (
    <div className={`homelab-node ${data.online ? "online" : "offline"}`}>
      <Handle type="target" position={Position.Top} style={{ opacity: 0 }} />
      <div className="node-header">
        <span className="node-icon">{ICONS[data.type]}</span>
        <span className="node-label">{data.label}</span>
        <span className={`status-dot ${data.online ? "up" : "down"}`} />
      </div>
      {data.tailscale_ip && <div className="node-ip">{data.tailscale_ip}</div>}
      {data.health && (
        <div className="node-health">
          <HealthBar label="CPU" pct={data.health.cpu_pct} />
          <HealthBar label="MEM" pct={data.health.memory_pct} />
          <HealthBar label="DSK" pct={data.health.disk_pct} />
        </div>
      )}
      <Handle type="source" position={Position.Bottom} style={{ opacity: 0 }} />
    </div>
  );
}
