import { TopologyGraph } from "./TopologyGraph";
import "./App.css";

function App() {
  return (
    <div className="app">
      <header className="app-header">
        <h1>Nexus</h1>
        <span className="app-subtitle">Homelab topology — live</span>
      </header>
      <TopologyGraph />
    </div>
  );
}

export default App;
