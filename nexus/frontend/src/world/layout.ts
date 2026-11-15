import type { Service, TopologyNode } from "../api";

// Where everything stands in the room, in metres, y up, the camera looking down -z. A fixed,
// hand-placed room for the same reason the old graph had fixed positions: a handful of known
// objects reads better standing still than re-arranged by an algorithm on every poll.

export type Vec3 = [number, number, number];

// `scale` enlarges the rack and the desk as built: at true size a 19-inch rack is a small
// object in a room wide enough to hold every tool, and its displays would be unreadable.
export const RACK = { x: -7.4, z: -2.4, width: 1.7, height: 3.1, depth: 1.3, scale: 1.4 } as const;
export const UNIT = { height: 0.54, pitch: 0.62, first: 0.45, slots: 4 } as const;
export const DESK = { x: 7.6, z: -0.6, top: 1.0, scale: 1.35 } as const;

// Bottom to top. A VM the table does not know is stacked above these, in id order.
const VM_ORDER = ["monitoring-01", "docker-01", "k8s-01"];

export function rackUnits(nodes: TopologyNode[]): TopologyNode[] {
  const rank = (id: string) => {
    const index = VM_ORDER.indexOf(id);
    return index === -1 ? VM_ORDER.length : index;
  };
  return nodes
    .filter((node) => node.type === "vm")
    .sort((a, b) => rank(a.id) - rank(b.id) || a.id.localeCompare(b.id));
}

export function unitY(slot: number): number {
  return UNIT.first + slot * UNIT.pitch;
}

// The point on a machine where its tailnet link attaches, and where the camera aims.
export function nodeAnchor(node: TopologyNode, nodes: TopologyNode[]): Vec3 {
  if (node.type === "vm") {
    const slot = rackUnits(nodes).findIndex((unit) => unit.id === node.id);
    const s = RACK.scale;
    return [RACK.x + s * (RACK.width / 2 + 0.03), s * unitY(slot), RACK.z + s * 0.3];
  }
  const d = DESK.scale;
  if (node.type === "laptop") return [DESK.x - d * 0.5, d * (DESK.top + 0.72), DESK.z - d * 0.1];
  if (node.type === "phone") return [DESK.x + d * 0.8, d * (DESK.top + 0.52), DESK.z + d * 0.12];
  return [RACK.x, RACK.scale * RACK.height + 0.04, RACK.z];
}

export interface Placement {
  position: Vec3;
  // Plinth height. Rows further back stand taller, so a logo is never hidden by the row in
  // front of it.
  height: number;
}

export interface Bay {
  layer: string;
  x: number;
  z: number;
  width: number;
}

const SPACING = 1.5;
const BAY_GAP = 0.9;
const ROW_LIMIT = 11;
const ROW_Z = [-4.2, -1.4, 1.4];
const ROW_HEIGHT = [2.0, 1.3, 0.6];

// Services stand in bays, one per layer, in the order the backend lists them (hardware up).
// Bays fill a row until it is full, then wrap to the next row towards the camera.
export function layoutServices(services: Service[]): {
  placements: Map<string, Placement>;
  bays: Bay[];
} {
  const layers = [...new Set(services.map((service) => service.layer))];
  const rows: { layer: string; members: Service[]; width: number }[][] = [[]];
  let used = 0;
  for (const layer of layers) {
    const members = services.filter((service) => service.layer === layer);
    const width = members.length * SPACING;
    const row = rows[rows.length - 1];
    const needed = row.length === 0 ? width : used + BAY_GAP + width;
    if (row.length > 0 && needed > ROW_LIMIT) {
      rows.push([{ layer, members, width }]);
      used = width;
    } else {
      row.push({ layer, members, width });
      used = needed;
    }
  }

  const placements = new Map<string, Placement>();
  const bays: Bay[] = [];
  rows.forEach((row, rowIndex) => {
    const last = ROW_Z.length - 1;
    const z = rowIndex <= last ? ROW_Z[rowIndex] : ROW_Z[last] + (rowIndex - last) * 2.4;
    const height = ROW_HEIGHT[Math.min(rowIndex, last)];
    const total = row.reduce((sum, bay) => sum + bay.width, 0) + BAY_GAP * (row.length - 1);
    let cursor = -total / 2;
    for (const bay of row) {
      bays.push({ layer: bay.layer, x: cursor + bay.width / 2, z, width: bay.width });
      bay.members.forEach((service, index) => {
        placements.set(service.id, {
          position: [cursor + SPACING / 2 + index * SPACING, 0, z],
          height,
        });
      });
      cursor += bay.width + BAY_GAP;
    }
  });
  return { placements, bays };
}

// How high above its plinth a logo floats.
export const LOGO_LIFT = 0.66;

// Camera pose for a close look: [camera x, y, z, target x, y, z].
export type Pose = [number, number, number, number, number, number];

export function poseFor(target: Vec3, kind: "service" | "rack" | "desk"): Pose {
  const [x, y, z] = target;
  if (kind === "rack") return [x + 3.8, y + 0.7, z + 7.6, x, y, z];
  if (kind === "desk") return [x - 2.0, y + 1.3, z + 4.4, x, y, z];
  // From above and in front: high enough that the row standing between the camera and this
  // plinth stays below the frame.
  return [x, y + 1.5, z + 4.2, x, y - 0.2, z];
}
