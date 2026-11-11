import { Handle, Position } from "@xyflow/react";
import type { TopologyNode } from "./api";
import { HealthBar } from "./HealthBar";
import { NodeIcon } from "./NodeIcon";

export function HomelabNode({ data }: { data: TopologyNode }) {
  return (
    <div className={`homelab-node ${data.online ? "online" : "offline"}`}>
      <Handle type="target" position={Position.Top} style={{ opacity: 0 }} />
      <div className="node-header">
        <NodeIcon type={data.type} />
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
