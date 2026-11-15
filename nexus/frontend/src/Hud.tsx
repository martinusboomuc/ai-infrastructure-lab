import type { AlertsResponse, Service, TopologyNode } from "./api";

// The few flat controls laid over the room: the lab's vital signs on the left, the ways out of
// the 3D view on the right, and the name of whatever the pointer is on at the bottom.
export function Hud({
  nodes,
  services,
  alerts,
  stale,
  caption,
  alertsOpen,
  onToggleAlerts,
  onOverview,
  onListView,
}: {
  nodes: TopologyNode[];
  services: Service[];
  alerts: AlertsResponse | null;
  stale: string | null;
  caption: string | null;
  alertsOpen: boolean;
  onToggleAlerts: () => void;
  onOverview: () => void;
  onListView: () => void;
}) {
  const online = nodes.filter((node) => node.online).length;
  const up = services.filter((service) => service.status === "up").length;
  const down = services.filter((service) => service.status === "down").length;
  const firing = alerts?.alerts.filter((alert) => !alert.silenced).length ?? 0;

  return (
    <>
      <header className="hud hud-left">
        <h1 className="hud-title">Nexus</h1>
        <div className="hud-stats">
          <span className="hud-stat">
            <strong>
              {online}/{nodes.length}
            </strong>{" "}
            machines online
          </span>
          <span className={`hud-stat ${down > 0 ? "bad" : ""}`}>
            <strong>{up}</strong> tools up{down > 0 && `, ${down} down`}
          </span>
          <span className={`hud-stat ${firing > 0 ? "bad" : ""}`}>
            <strong>{firing}</strong> {firing === 1 ? "alert" : "alerts"} firing
          </span>
        </div>
        {stale && <div className="hud-stale">Backend not answering ({stale}). Showing last data.</div>}
      </header>

      <nav className="hud hud-right">
        <button className="hud-button" onClick={onOverview}>
          Overview
        </button>
        <button
          className={`hud-button ${alertsOpen ? "active" : ""} ${firing > 0 ? "bad" : ""}`}
          onClick={onToggleAlerts}
          aria-pressed={alertsOpen}
        >
          Alerts{firing > 0 && ` (${firing})`}
        </button>
        <button className="hud-button" onClick={onListView}>
          List view
        </button>
      </nav>

      <div className="hud-caption" aria-live="polite">
        {caption ?? "Click a machine or a tool for a closer look. Scroll there to move in. Overview steps back."}
      </div>
    </>
  );
}
