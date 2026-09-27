import { useEffect, useMemo, useState } from "react";
import { ReactFlow, Background, type Edge, type Node } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { fetchTopology, type TopologyNode } from "./api";
import { HomelabNode } from "./HomelabNode";

const POLL_INTERVAL_MS = 10_000;

const nodeTypes = { homelab: HomelabNode };

// Fixed layout, not a force-directed one: with a handful of known nodes, a hand-placed layout
// reads more clearly than an auto-layout algorithm re-jittering positions on every poll.
const POSITIONS: Record<string, { x: number; y: number }> = {
  tailscale: { x: 400, y: 0 },
  pve01: { x: 400, y: 160 },
  "k8s-01": { x: 100, y: 340 },
  "docker-01": { x: 400, y: 340 },
  "monitoring-01": { x: 700, y: 340 },
  macbook: { x: 750, y: 0 },
  iphone: { x: 900, y: 0 },
};

function buildGraph(topologyNodes: TopologyNode[]): { nodes: Node[]; edges: Edge[] } {
  const tailscaleHub: Node = {
    id: "tailscale",
    position: POSITIONS.tailscale,
    data: { label: "Tailscale" },
    style: {
      background: "#1e293b",
      color: "#94a3b8",
      border: "1px dashed #475569",
      borderRadius: 999,
      padding: "6px 16px",
      fontSize: 12,
    },
  };

  const nodes: Node[] = [tailscaleHub];
  const edges: Edge[] = [];

  for (const n of topologyNodes) {
    const pos = POSITIONS[n.id] ?? { x: 400, y: 500 };
    nodes.push({
      id: n.id,
      type: "homelab",
      position: pos,
      data: n as unknown as Record<string, unknown>,
    });

    // "Runs on" — the physical/virtual hosting relationship.
    if (n.parent) {
      edges.push({
        id: `${n.parent}-${n.id}`,
        source: n.parent,
        target: n.id,
        style: { stroke: "#475569" },
      });
    }

    // "On the VPN" — only drawn while the device is actually online, so a personal device
    // genuinely disappears from the mesh when it's not connected, not just greys out.
    if (n.online) {
      edges.push({
        id: `tailscale-${n.id}`,
        source: "tailscale",
        target: n.id,
        animated: true,
        style: { stroke: "#3b82f6", strokeDasharray: "4 4" },
      });
    }
  }

  return { nodes, edges };
}

export function TopologyGraph() {
  const [topologyNodes, setTopologyNodes] = useState<TopologyNode[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function poll() {
      try {
        const data = await fetchTopology();
        if (!cancelled) {
          setTopologyNodes(data);
          setError(null);
        }
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      }
    }
    poll();
    const interval = setInterval(poll, POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, []);

  const { nodes, edges } = useMemo(
    () => buildGraph(topologyNodes ?? []),
    [topologyNodes],
  );

  if (error && !topologyNodes) {
    return <div className="graph-error">Can't reach the Nexus backend: {error}</div>;
  }

  // Deliberately don't render ReactFlow until real data has arrived: `fitView` only runs once,
  // on ReactFlow's own first mount — rendering it early (with just the Tailscale hub node, before
  // the backend response lands) means it fits the camera to that one node, and never re-fits once
  // the rest of the graph shows up a moment later. Mounting ReactFlow for the first time only
  // once the full node list already exists is what makes fitView actually fit everything.
  if (!topologyNodes) {
    return <div className="graph-loading">Loading homelab topology…</div>;
  }

  return (
    <div className="graph-container">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        fitView
        fitViewOptions={{ padding: 0.3 }}
        nodesDraggable
        nodesConnectable={false}
        elementsSelectable={false}
        proOptions={{ hideAttribution: true }}
      >
        <Background color="#1e293b" gap={24} />
      </ReactFlow>
    </div>
  );
}
