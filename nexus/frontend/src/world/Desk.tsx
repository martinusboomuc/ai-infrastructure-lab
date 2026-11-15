import { RoundedBox } from "@react-three/drei";
import type { TopologyNode } from "../api";
import type { Selection } from "../selection";
import { type Interaction, pointerHandlers } from "./interaction";
import { DESK } from "./layout";
import { MONO, SANS, useCanvasTexture } from "./useCanvasTexture";

function drawLaptopScreen(ctx: CanvasRenderingContext2D, node: TopologyNode) {
  ctx.fillStyle = "#050a12";
  ctx.fillRect(0, 0, 640, 400);
  ctx.textAlign = "left";
  ctx.textBaseline = "alphabetic";
  ctx.font = `26px ${MONO}`;
  const lines: [string, string][] = [
    ["#5f7a94", "$ tailscale status"],
    ["#9be7b4", `${node.tailscale_ip ?? "-"}  ${node.label.toLowerCase()}  online`],
    ["#5f7a94", "$ open http://k8s-01/"],
    ["#8fdcff", "nexus: connected over the tailnet"],
    ["#5f7a94", "$ _"],
  ];
  lines.forEach(([color, text], row) => {
    ctx.fillStyle = color;
    ctx.fillText(text, 30, 62 + row * 46);
  });
}

function drawPhoneScreen(ctx: CanvasRenderingContext2D, node: TopologyNode) {
  const gradient = ctx.createLinearGradient(0, 0, 0, 512);
  gradient.addColorStop(0, "#0b1f3a");
  gradient.addColorStop(1, "#06101d");
  ctx.fillStyle = gradient;
  ctx.fillRect(0, 0, 256, 512);
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillStyle = "#cfe6ff";
  ctx.font = `600 34px ${SANS}`;
  ctx.fillText(node.label, 128, 150);
  ctx.fillStyle = "#34d399";
  ctx.beginPath();
  ctx.arc(128, 250, 34, 0, Math.PI * 2);
  ctx.fill();
  ctx.fillStyle = "#7fa3c7";
  ctx.font = `22px ${SANS}`;
  ctx.fillText("Tailnet connected", 128, 330);
  ctx.font = `20px ${MONO}`;
  ctx.fillText(node.tailscale_ip ?? "", 128, 368);
}

function Laptop({
  node,
  active,
  interaction,
}: {
  node: TopologyNode;
  active: boolean;
  interaction: Interaction;
}) {
  const screen = useCanvasTexture(640, 400, (ctx) => drawLaptopScreen(ctx, node), [
    node.label,
    node.tailscale_ip,
  ]);
  const body = active ? "#c9ced6" : "#9aa1ab";
  return (
    <group
      position={[-0.5, DESK.top + 0.04, -0.1]}
      rotation={[0, 0.25, 0]}
      {...pointerHandlers({ kind: "node", id: node.id }, interaction)}
    >
      <RoundedBox args={[1.05, 0.04, 0.72]} radius={0.015} smoothness={3} castShadow>
        <meshStandardMaterial color={body} metalness={0.9} roughness={0.32} />
      </RoundedBox>
      <mesh position={[0, 0.022, 0.05]}>
        <boxGeometry args={[0.9, 0.004, 0.38]} />
        <meshStandardMaterial color="#14171c" roughness={0.7} />
      </mesh>
      <group position={[0, 0.02, -0.35]} rotation={[-0.3, 0, 0]}>
        <RoundedBox
          args={[1.05, 0.7, 0.03]}
          radius={0.012}
          smoothness={3}
          position={[0, 0.35, 0]}
          castShadow
        >
          <meshStandardMaterial color={body} metalness={0.9} roughness={0.32} />
        </RoundedBox>
        <mesh position={[0, 0.35, 0.017]}>
          <planeGeometry args={[0.98, 0.6125]} />
          {node.online ? (
            <meshBasicMaterial map={screen} toneMapped={false} />
          ) : (
            <meshStandardMaterial color="#05070a" metalness={0.4} roughness={0.15} />
          )}
        </mesh>
      </group>
    </group>
  );
}

function Phone({
  node,
  active,
  interaction,
}: {
  node: TopologyNode;
  active: boolean;
  interaction: Interaction;
}) {
  const screen = useCanvasTexture(256, 512, (ctx) => drawPhoneScreen(ctx, node), [
    node.label,
    node.tailscale_ip,
  ]);
  return (
    <group
      position={[0.8, DESK.top + 0.035, 0.12]}
      rotation={[0, -0.3, 0]}
      {...pointerHandlers({ kind: "node", id: node.id }, interaction)}
    >
      <mesh position={[0, 0.02, -0.07]} castShadow>
        <boxGeometry args={[0.22, 0.04, 0.26]} />
        <meshStandardMaterial color="#2a2f38" metalness={0.8} roughness={0.4} />
      </mesh>
      <group position={[0, 0.04, -0.02]} rotation={[-0.38, 0, 0]}>
        <RoundedBox
          args={[0.3, 0.6, 0.03]}
          radius={0.014}
          smoothness={4}
          position={[0, 0.3, 0]}
          castShadow
        >
          <meshStandardMaterial
            color={active ? "#3c4350" : "#23272f"}
            metalness={0.9}
            roughness={0.25}
          />
        </RoundedBox>
        <mesh position={[0, 0.3, 0.0165]}>
          <planeGeometry args={[0.27, 0.56]} />
          {node.online ? (
            <meshBasicMaterial map={screen} toneMapped={false} />
          ) : (
            <meshStandardMaterial color="#05070a" metalness={0.4} roughness={0.15} />
          )}
        </mesh>
      </group>
    </group>
  );
}

// The personal devices, on a desk across the room from the rack. A device the tailnet has never
// seen is simply absent from the desk; one that is offline is there with a dark screen.
export function Desk({
  nodes,
  selection,
  hovered,
  interaction,
}: {
  nodes: TopologyNode[];
  selection: Selection | null;
  hovered: Selection | null;
  interaction: Interaction;
}) {
  const laptop = nodes.find((node) => node.type === "laptop");
  const phone = nodes.find((node) => node.type === "phone");
  const isActive = (id: string) =>
    (selection?.kind === "node" && selection.id === id) ||
    (hovered?.kind === "node" && hovered.id === id);

  return (
    <group position={[DESK.x, 0, DESK.z]} rotation={[0, -0.2, 0]} scale={DESK.scale}>
      <RoundedBox
        args={[2.9, 0.07, 1.3]}
        radius={0.02}
        smoothness={3}
        position={[0, DESK.top - 0.015, 0]}
        castShadow
        receiveShadow
      >
        <meshStandardMaterial color="#2b2118" metalness={0.15} roughness={0.55} />
      </RoundedBox>
      {[
        [-1.3, -0.52],
        [1.3, -0.52],
        [-1.3, 0.52],
        [1.3, 0.52],
      ].map(([x, z]) => (
        <mesh key={`${x}:${z}`} position={[x, (DESK.top - 0.05) / 2, z]} castShadow>
          <boxGeometry args={[0.06, DESK.top - 0.05, 0.06]} />
          <meshStandardMaterial color="#14171d" metalness={0.9} roughness={0.35} />
        </mesh>
      ))}
      <mesh position={[0, 0.12, -0.52]}>
        <boxGeometry args={[2.6, 0.04, 0.04]} />
        <meshStandardMaterial color="#14171d" metalness={0.9} roughness={0.35} />
      </mesh>

      {laptop && <Laptop node={laptop} active={isActive(laptop.id)} interaction={interaction} />}
      {phone && <Phone node={phone} active={isActive(phone.id)} interaction={interaction} />}
    </group>
  );
}
