import type { Alert, Service, TopologyNode } from "./api";

// One thing in the room: a machine from /api/topology or a tool from /api/services.
export interface Selection {
  kind: "node" | "service";
  id: string;
}

export function selectionKey(selection: Selection): string {
  return `${selection.kind}:${selection.id}`;
}

// Which objects a firing alert belongs to. Grafana gives an alert a free-text target and name,
// not a reference to a Nexus object, so this is a substring match on the node's or service's id
// and display name. An alert that matches nothing still lights the room beacon and is listed in
// the alerts drawer; it is never dropped.
export function alertingKeys(
  alerts: Alert[],
  nodes: TopologyNode[],
  services: Service[],
): Set<string> {
  const keys = new Set<string>();
  const firing = alerts
    .filter((alert) => !alert.silenced)
    .map((alert) => `${alert.target} ${alert.name}`.toLowerCase());
  if (firing.length === 0) return keys;

  const matches = (...names: string[]) =>
    names.some((name) => firing.some((text) => text.includes(name.toLowerCase())));

  for (const node of nodes) {
    if (matches(node.id, node.label)) keys.add(selectionKey({ kind: "node", id: node.id }));
  }
  for (const service of services) {
    if (matches(service.id, service.name)) {
      keys.add(selectionKey({ kind: "service", id: service.id }));
    }
  }
  return keys;
}
