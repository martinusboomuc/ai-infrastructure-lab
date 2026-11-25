import { lazy, Suspense, useCallback, useEffect, useMemo, useState } from "react";
import { AlertsList, AlertsView } from "./AlertsView";
import { BankmlView } from "./BankmlView";
import { fetchAlerts, fetchServices, fetchTopology } from "./api";
import { Hud } from "./Hud";
import { NodeDetailPanel } from "./NodeDetailPanel";
import { alertingKeys, type Selection } from "./selection";
import { ServiceDetailPanel } from "./ServiceDetailPanel";
import { ServicesView } from "./ServicesView";
import { usePolling } from "./usePolling";
import "./App.css";

// three.js is most of the bundle. Loading the room lazily keeps it out of the way of the list
// view, which is what a browser without WebGL gets.
const World = lazy(() => import("./world/World"));

const TOPOLOGY_POLL_MS = 10_000;
const CATALOG_POLL_MS = 30_000;

function webglAvailable(): boolean {
  try {
    const canvas = document.createElement("canvas");
    return canvas.getContext("webgl2") !== null;
  } catch {
    return false;
  }
}

const LIST_VIEWS = { services: "Services", bankml: "BankML", alerts: "Alerts" } as const;
type ListView = keyof typeof LIST_VIEWS;

function ListMode({ onWorld }: { onWorld: (() => void) | null }) {
  const [view, setView] = useState<ListView>("services");
  return (
    <div className="app">
      <header className="app-header">
        <h1>Nexus</h1>
        <nav className="app-nav">
          {(Object.keys(LIST_VIEWS) as ListView[]).map((v) => (
            <button
              key={v}
              className={`app-tab ${v === view ? "active" : ""}`}
              onClick={() => setView(v)}
            >
              {LIST_VIEWS[v]}
            </button>
          ))}
        </nav>
        {onWorld ? (
          <button className="app-tab app-tab-end" onClick={onWorld}>
            3D room
          </button>
        ) : (
          <span className="app-subtitle app-tab-end">
            This browser has no WebGL 2, so the 3D room is unavailable.
          </span>
        )}
      </header>
      {view === "services" && <ServicesView />}
      {view === "bankml" && <BankmlView />}
      {view === "alerts" && <AlertsView />}
    </div>
  );
}

function WorldMode({ onListView }: { onListView: () => void }) {
  const topology = usePolling(fetchTopology, TOPOLOGY_POLL_MS);
  const catalog = usePolling(fetchServices, CATALOG_POLL_MS);
  const alerts = usePolling(fetchAlerts, CATALOG_POLL_MS);

  const [selection, setSelection] = useState<Selection | null>(null);
  const [hovered, setHovered] = useState<Selection | null>(null);
  const [alertsOpen, setAlertsOpen] = useState(false);
  const [homeNonce, setHomeNonce] = useState(0);

  const nodes = topology.data;
  const services = catalog.data;

  const alerting = useMemo(
    () => alertingKeys(alerts.data?.alerts ?? [], nodes ?? [], services ?? []),
    [alerts.data, nodes, services],
  );
  const alarm = (alerts.data?.alerts ?? []).some((alert) => !alert.silenced);

  useEffect(() => {
    document.body.style.cursor = hovered ? "pointer" : "";
    return () => {
      document.body.style.cursor = "";
    };
  }, [hovered]);

  const handleSelect = useCallback((next: Selection | null) => setSelection(next), []);
  const handleHover = useCallback((next: Selection | null) => setHovered(next), []);

  if (!nodes || !services) {
    const error = topology.error ?? catalog.error;
    return (
      <div className="world-shell">
        <div className={error ? "graph-error" : "graph-loading"}>
          {error ? `Can't reach the Nexus backend: ${error}` : "Loading the lab…"}
        </div>
      </div>
    );
  }

  // Looked up by id on every render, not captured at click time: a panel left open shows each
  // poll's fresh state, not the snapshot from when it was opened.
  const selectedNode =
    selection?.kind === "node" ? nodes.find((node) => node.id === selection.id) : undefined;
  const selectedService =
    selection?.kind === "service"
      ? services.find((service) => service.id === selection.id)
      : undefined;

  let caption: string | null = null;
  if (hovered?.kind === "node") {
    const node = nodes.find((candidate) => candidate.id === hovered.id);
    if (node) caption = `${node.label} · ${node.online ? "online" : "offline"}`;
  } else if (hovered?.kind === "service") {
    const service = services.find((candidate) => candidate.id === hovered.id);
    if (service) caption = `${service.name} · ${service.layer}`;
  }

  return (
    <div className="world-shell">
      <Suspense fallback={<div className="graph-loading">Building the room…</div>}>
        <World
          nodes={nodes}
          services={services}
          alerting={alerting}
          alarm={alarm}
          selection={selection}
          hovered={hovered}
          homeNonce={homeNonce}
          onSelect={handleSelect}
          onHover={handleHover}
        />
      </Suspense>

      <Hud
        nodes={nodes}
        services={services}
        alerts={alerts.data}
        stale={topology.error ?? catalog.error}
        caption={caption}
        alertsOpen={alertsOpen}
        onToggleAlerts={() => setAlertsOpen((open) => !open)}
        onOverview={() => {
          setSelection(null);
          setHomeNonce((nonce) => nonce + 1);
        }}
        onListView={onListView}
      />

      {alertsOpen && (
        <aside className="alerts-drawer">
          <div className="detail-header">
            <div className="detail-label">Alerts</div>
            <button
              className="detail-close"
              onClick={() => setAlertsOpen(false)}
              aria-label="Close alerts"
            >
              &times;
            </button>
          </div>
          {alerts.data ? (
            <AlertsList data={alerts.data} />
          ) : (
            <p className="alerts-empty">
              {alerts.error ? `Alerts did not load: ${alerts.error}` : "Loading alerts…"}
            </p>
          )}
        </aside>
      )}

      {selectedNode && <NodeDetailPanel node={selectedNode} onClose={() => setSelection(null)} />}
      {selectedService && (
        <ServiceDetailPanel service={selectedService} onClose={() => setSelection(null)} />
      )}
    </div>
  );
}

function App() {
  const [canRender3d] = useState(webglAvailable);
  const [mode, setMode] = useState<"world" | "list">(canRender3d ? "world" : "list");

  if (mode === "list") {
    return <ListMode onWorld={canRender3d ? () => setMode("world") : null} />;
  }
  return <WorldMode onListView={() => setMode("list")} />;
}

export default App;
