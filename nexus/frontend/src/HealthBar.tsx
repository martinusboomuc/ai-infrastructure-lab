import { healthColor } from "./health";

// The health bar of the node detail panel. Its colour thresholds live in health.ts, shared with
// the displays drawn on the servers in the 3D room.
export function HealthBar({ label, pct }: { label: string; pct: number | null }) {
  if (pct === null) return null;
  const color = healthColor(pct);
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
