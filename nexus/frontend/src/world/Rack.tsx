import { useRef } from "react";
import { useFrame } from "@react-three/fiber";
import type { MeshStandardMaterial } from "three";
import type { TopologyNode } from "../api";
import { healthColor } from "../health";
import { type Selection, selectionKey } from "../selection";
import { type Interaction, phaseOf, pointerHandlers, STATUS_COLOR } from "./interaction";
import { RACK, rackUnits, UNIT, unitY } from "./layout";
import { MONO, useCanvasTexture } from "./useCanvasTexture";

const METRICS = [
  ["CPU", "cpu_pct"],
  ["MEM", "memory_pct"],
  ["DSK", "disk_pct"],
] as const;

function drawUnitDisplay(ctx: CanvasRenderingContext2D, node: TopologyNode) {
  ctx.fillStyle = "#020b12";
  ctx.fillRect(0, 0, 512, 288);
  ctx.textBaseline = "alphabetic";
  ctx.textAlign = "left";

  ctx.fillStyle = node.online ? "#8fdcff" : "#51606e";
  ctx.font = `600 50px ${MONO}`;
  ctx.fillText(node.label, 26, 66);

  if (!node.online) {
    ctx.fillStyle = "#b03a3a";
    ctx.font = `600 40px ${MONO}`;
    ctx.fillText("OFFLINE", 26, 170);
    return;
  }

  ctx.fillStyle = "#3f8fb5";
  ctx.font = `28px ${MONO}`;
  ctx.fillText(node.tailscale_ip ?? "no tailnet address", 26, 106);

  METRICS.forEach(([label, key], row) => {
    const pct = node.health?.[key] ?? null;
    const y = 150 + row * 46;
    ctx.fillStyle = "#58788f";
    ctx.font = `26px ${MONO}`;
    ctx.textAlign = "left";
    ctx.fillText(label, 26, y + 20);
    ctx.fillStyle = "#0a2636";
    ctx.fillRect(100, y, 300, 22);
    if (pct !== null) {
      ctx.fillStyle = healthColor(pct);
      ctx.fillRect(100, y, 3 * Math.min(pct, 100), 22);
      ctx.fillStyle = "#b9d6e6";
      ctx.textAlign = "right";
      ctx.fillText(`${pct.toFixed(0)}%`, 490, y + 20);
    }
  });
}

const BAYS = [0, 1, 2, 3, 4, 5];

function ServerUnit({
  node,
  y,
  active,
  alerting,
  interaction,
}: {
  node: TopologyNode;
  y: number;
  active: boolean;
  alerting: boolean;
  interaction: Interaction;
}) {
  const width = RACK.width - 0.2;
  const depth = RACK.depth - 0.16;
  const front = depth / 2;
  const activity = useRef<(MeshStandardMaterial | null)[]>([]);
  const edge = useRef<MeshStandardMaterial>(null);
  const phase = phaseOf(node.id) * 40;
  const cpu = node.health?.cpu_pct ?? 0;

  const display = useCanvasTexture(512, 288, (ctx) => drawUnitDisplay(ctx, node), [
    node.label,
    node.online,
    node.tailscale_ip,
    node.health?.cpu_pct?.toFixed(0),
    node.health?.memory_pct?.toFixed(0),
    node.health?.disk_pct?.toFixed(0),
  ]);

  useFrame(({ clock }) => {
    const t = clock.elapsedTime;
    // Drive lights flicker faster and more often the busier the CPU is: load is visible from
    // across the room, before any number is read.
    const rate = 3 + cpu * 0.25;
    const duty = 0.15 + Math.min(cpu, 100) / 140;
    activity.current.forEach((material, bay) => {
      if (!material) return;
      const wave = Math.sin(t * rate * (1 + bay * 0.37) + phase + bay * 1.9);
      material.emissiveIntensity = node.online && wave > 1 - 2 * duty ? 3.2 : 0.15;
    });
    if (edge.current) {
      edge.current.emissiveIntensity = alerting ? 2.6 + Math.sin(t * 6) * 2.2 : active ? 3.2 : 0.9;
    }
  });

  const edgeColor = alerting
    ? STATUS_COLOR.alert
    : node.online
      ? active
        ? "#7cc4ff"
        : "#2f6fb0"
      : "#3a4350";

  return (
    <group position={[0, y, 0]} {...pointerHandlers({ kind: "node", id: node.id }, interaction)}>
      <mesh castShadow receiveShadow>
        <boxGeometry args={[width, UNIT.height, depth]} />
        <meshStandardMaterial
          color={node.online ? "#2b313c" : "#1c2028"}
          metalness={0.85}
          roughness={0.36}
        />
      </mesh>
      <mesh position={[0, 0, front + 0.006]}>
        <boxGeometry args={[width, UNIT.height - 0.03, 0.012]} />
        <meshStandardMaterial color="#12161d" metalness={0.7} roughness={0.5} />
      </mesh>
      {[-1, 1].map((side) => (
        <mesh key={side} position={[side * (width / 2 + 0.035), 0, front + 0.01]}>
          <boxGeometry args={[0.07, UNIT.height - 0.04, 0.03]} />
          <meshStandardMaterial color="#3a4250" metalness={0.9} roughness={0.3} />
        </mesh>
      ))}

      <mesh position={[-0.34, 0.02, front + 0.014]}>
        <planeGeometry args={[0.66, 0.371]} />
        <meshBasicMaterial map={display} toneMapped={false} />
      </mesh>

      {BAYS.map((bay) => {
        const x = 0.14 + (bay % 3) * 0.17;
        const row = bay < 3 ? 0.1 : -0.09;
        return (
          <group key={bay} position={[x, row, front + 0.013]}>
            <mesh>
              <boxGeometry args={[0.15, 0.16, 0.012]} />
              <meshStandardMaterial color="#232934" metalness={0.8} roughness={0.45} />
            </mesh>
            <mesh position={[0.05, -0.055, 0.008]}>
              <boxGeometry args={[0.022, 0.022, 0.006]} />
              <meshStandardMaterial
                ref={(material) => {
                  activity.current[bay] = material;
                }}
                color="#0a0d12"
                emissive="#59f0a6"
                emissiveIntensity={0.15}
              />
            </mesh>
          </group>
        );
      })}

      <mesh position={[0.66, 0, front + 0.016]}>
        <circleGeometry args={[0.03, 24]} />
        <meshStandardMaterial
          color="#0a0d12"
          emissive={node.online ? STATUS_COLOR.up : STATUS_COLOR.down}
          emissiveIntensity={node.online ? 3.5 : 1.2}
        />
      </mesh>

      <mesh position={[0, -UNIT.height / 2 + 0.012, front + 0.016]}>
        <boxGeometry args={[width - 0.06, 0.014, 0.008]} />
        <meshStandardMaterial
          ref={edge}
          color="#0a0d12"
          emissive={edgeColor}
          emissiveIntensity={0.9}
        />
      </mesh>
    </group>
  );
}

function drawHostDisplay(ctx: CanvasRenderingContext2D, host: TopologyNode | undefined) {
  ctx.fillStyle = "#020b12";
  ctx.fillRect(0, 0, 1024, 150);
  ctx.textBaseline = "middle";
  ctx.textAlign = "left";
  ctx.font = `600 54px ${MONO}`;
  if (!host) {
    ctx.fillStyle = "#51606e";
    ctx.fillText("HOST NOT ON THE TAILNET", 30, 78);
    return;
  }
  ctx.fillStyle = host.online ? "#8fdcff" : "#51606e";
  ctx.fillText(host.id.toUpperCase(), 30, 78);
  ctx.font = `34px ${MONO}`;
  if (!host.online) {
    ctx.fillStyle = "#b03a3a";
    ctx.fillText("OFFLINE", 300, 80);
    return;
  }
  let x = 300;
  for (const [label, key] of METRICS) {
    const pct = host.health?.[key] ?? null;
    ctx.fillStyle = "#58788f";
    ctx.fillText(label, x, 80);
    ctx.fillStyle = pct === null ? "#51606e" : healthColor(pct);
    ctx.fillText(pct === null ? "--" : `${pct.toFixed(0)}%`, x + 82, 80);
    x += 236;
  }
}

// The hypervisor as the rack itself, and each VM as a chassis mounted in it: the "runs on"
// relationship the old graph drew as an edge is simply where the machine sits.
export function Rack({
  nodes,
  selection,
  hovered,
  alerting,
  interaction,
}: {
  nodes: TopologyNode[];
  selection: Selection | null;
  hovered: Selection | null;
  alerting: Set<string>;
  interaction: Interaction;
}) {
  const host = nodes.find((node) => node.type === "host");
  const units = rackUnits(nodes);
  const { width, height, depth } = RACK;
  const frame = useRef<(MeshStandardMaterial | null)[]>([]);

  const isActive = (id: string) =>
    (selection?.kind === "node" && selection.id === id) ||
    (hovered?.kind === "node" && hovered.id === id);
  const hostActive = host ? isActive(host.id) : false;
  const hostAlerting = host ? alerting.has(selectionKey({ kind: "node", id: host.id })) : false;

  const display = useCanvasTexture(1024, 150, (ctx) => drawHostDisplay(ctx, host), [
    host?.id,
    host?.online,
    host?.health?.cpu_pct?.toFixed(0),
    host?.health?.memory_pct?.toFixed(0),
    host?.health?.disk_pct?.toFixed(0),
  ]);

  useFrame(({ clock }) => {
    const intensity = hostAlerting
      ? 2.6 + Math.sin(clock.elapsedTime * 6) * 2.2
      : hostActive
        ? 3.4
        : 1.3;
    for (const material of frame.current) {
      if (material) material.emissiveIntensity = intensity;
    }
  });

  const blanks = Array.from(
    { length: Math.max(0, UNIT.slots - units.length) },
    (_, index) => units.length + index,
  );
  const hostHandlers = host ? pointerHandlers({ kind: "node", id: host.id }, interaction) : {};

  return (
    <group position={[RACK.x, 0, RACK.z]} scale={RACK.scale}>
      <group {...hostHandlers}>
        {[-1, 1].map((side) => (
          <mesh key={side} position={[side * (width / 2 - 0.02), height / 2, 0]} castShadow>
            <boxGeometry args={[0.04, height, depth]} />
            <meshStandardMaterial color="#161a22" metalness={0.8} roughness={0.42} />
          </mesh>
        ))}
        <mesh position={[0, height / 2, -depth / 2 + 0.02]} castShadow>
          <boxGeometry args={[width, height, 0.04]} />
          <meshStandardMaterial color="#12151c" metalness={0.7} roughness={0.5} />
        </mesh>
        <mesh position={[0, height - 0.02, 0]} castShadow>
          <boxGeometry args={[width + 0.04, 0.05, depth + 0.04]} />
          <meshStandardMaterial color="#1b202a" metalness={0.85} roughness={0.35} />
        </mesh>
        <mesh position={[0, 0.07, 0]} castShadow receiveShadow>
          <boxGeometry args={[width + 0.04, 0.14, depth + 0.04]} />
          <meshStandardMaterial color="#1b202a" metalness={0.85} roughness={0.35} />
        </mesh>

        <mesh position={[0, height - 0.24, depth / 2 - 0.05]}>
          <boxGeometry args={[width - 0.08, 0.34, 0.06]} />
          <meshStandardMaterial color="#12161d" metalness={0.8} roughness={0.4} />
        </mesh>
        <mesh position={[0, height - 0.24, depth / 2 - 0.018]}>
          <planeGeometry args={[1.5, 0.22]} />
          <meshBasicMaterial map={display} toneMapped={false} />
        </mesh>

        {[-1, 1].map((side) => (
          <mesh key={side} position={[side * (width / 2 + 0.004), height / 2, depth / 2 - 0.01]}>
            <boxGeometry args={[0.014, height - 0.3, 0.014]} />
            <meshStandardMaterial
              ref={(material) => {
                frame.current[side === -1 ? 0 : 1] = material;
              }}
              color="#0a0d12"
              emissive={
                hostAlerting ? STATUS_COLOR.alert : host?.online ? "#e57000" : STATUS_COLOR.unknown
              }
              emissiveIntensity={1.3}
            />
          </mesh>
        ))}
      </group>

      {units.map((node, slot) => (
        <ServerUnit
          key={node.id}
          node={node}
          y={unitY(slot)}
          active={isActive(node.id)}
          alerting={alerting.has(selectionKey({ kind: "node", id: node.id }))}
          interaction={interaction}
        />
      ))}
      {blanks.map((slot) => (
        <mesh key={slot} position={[0, unitY(slot), depth / 2 - 0.09]}>
          <boxGeometry args={[width - 0.2, UNIT.height - 0.03, 0.02]} />
          <meshStandardMaterial color="#141820" metalness={0.75} roughness={0.5} />
        </mesh>
      ))}
    </group>
  );
}
