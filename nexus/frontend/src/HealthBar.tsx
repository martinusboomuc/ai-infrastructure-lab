// Shared by the compact node card (HomelabNode) and the full detail panel (NodeDetailPanel) —
// one definition of what a health bar looks like, so the two views never drift apart.
export function HealthBar({ label, pct }: { label: string; pct: number | null }) {
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
