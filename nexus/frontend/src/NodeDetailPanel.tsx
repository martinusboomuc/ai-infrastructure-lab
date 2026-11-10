import type { TopologyNode } from "./api";
import { HealthBar } from "./HealthBar";

const TYPE_LABELS: Record<TopologyNode["type"], string> = {
  host: "Hypervisor",
  vm: "Virtual machine",
  laptop: "Laptop",
  phone: "Phone",
};

// Slide-in detail for whichever node was last clicked — live status plus direct links out to
// the real tool it represents, rather than making the graph itself carry that much detail at
// all times.
export function NodeDetailPanel({
  node,
  onClose,
}: {
  node: TopologyNode;
  onClose: () => void;
}) {
  return (
    <aside className="detail-panel">
      <div className="detail-header">
        <div>
          <div className="detail-label">{node.label}</div>
          <div className="detail-type">{TYPE_LABELS[node.type]}</div>
        </div>
        <button className="detail-close" onClick={onClose} aria-label="Close detail panel">
          &times;
        </button>
      </div>

      <div className={`detail-status ${node.online ? "up" : "down"}`}>
        <span className={`status-dot ${node.online ? "up" : "down"}`} />
        {node.online ? "Online" : "Offline"}
      </div>

      {node.tailscale_ip && (
        <div className="detail-row">
          <span className="detail-row-label">Tailscale IP</span>
          <span className="detail-row-value">{node.tailscale_ip}</span>
        </div>
      )}

      {node.health && (
        <div className="detail-health">
          <HealthBar label="CPU" pct={node.health.cpu_pct} />
          <HealthBar label="MEM" pct={node.health.memory_pct} />
          <HealthBar label="DSK" pct={node.health.disk_pct} />
        </div>
      )}

      <div className="detail-links">
        <div className="detail-links-heading">Open</div>
        {node.links.length > 0 ? (
          node.links.map((link) => (
            <a
              key={link.url}
              href={link.url}
              target="_blank"
              rel="noreferrer"
              className="detail-link"
            >
              {link.label} &rarr;
            </a>
          ))
        ) : (
          <div className="detail-links-empty">No linked tools for this node.</div>
        )}
      </div>
    </aside>
  );
}
