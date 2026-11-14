import { useState } from "react";
import { AlertsView } from "./AlertsView";
import { ServicesView } from "./ServicesView";
import { TopologyGraph } from "./TopologyGraph";
import "./App.css";

const VIEWS = {
  topology: "Topology",
  services: "Services",
  alerts: "Alerts",
} as const;

type View = keyof typeof VIEWS;

function App() {
  const [view, setView] = useState<View>("topology");

  return (
    <div className="app">
      <header className="app-header">
        <h1>Nexus</h1>
        <nav className="app-nav">
          {(Object.keys(VIEWS) as View[]).map((v) => (
            <button
              key={v}
              className={`app-tab ${v === view ? "active" : ""}`}
              onClick={() => setView(v)}
            >
              {VIEWS[v]}
            </button>
          ))}
        </nav>
      </header>
      {view === "topology" && <TopologyGraph />}
      {view === "services" && <ServicesView />}
      {view === "alerts" && <AlertsView />}
    </div>
  );
}

export default App;
