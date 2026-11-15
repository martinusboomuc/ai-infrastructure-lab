import { useRef } from "react";
import { RoundedBox } from "@react-three/drei";
import { useFrame } from "@react-three/fiber";
import type { Group, MeshStandardMaterial } from "three";
import type { Service } from "../api";
import { Emblem } from "./Emblems";
import { type Interaction, phaseOf, pointerHandlers, STATUS_COLOR } from "./interaction";
import { LOGO_LIFT, type Placement } from "./layout";
import { Logo3D } from "./Logo3D";
import { BRANDS, EMBLEMS } from "./logos";
import { fitText, SANS, useCanvasTexture } from "./useCanvasTexture";

const SIDE = 0.86;

// One tool, shown the way a museum shows an object: its mark as a solid on a plinth, a
// nameplate on the front, and a band of light around the top that carries its live status.
export function ServicePlinth({
  service,
  placement,
  active,
  alerting,
  interaction,
}: {
  service: Service;
  placement: Placement;
  active: boolean;
  alerting: boolean;
  interaction: Interaction;
}) {
  const emblem = useRef<Group>(null);
  const band = useRef<MeshStandardMaterial>(null);
  const phase = phaseOf(service.id) * Math.PI * 2;
  const { height } = placement;
  const statusColor = alerting ? STATUS_COLOR.alert : STATUS_COLOR[service.status];
  const dimmed = service.status === "down";

  useFrame(({ clock }) => {
    const t = clock.elapsedTime;
    if (emblem.current) {
      // A slight sway, never enough to turn the mark edge-on, where it stops being recognisable.
      emblem.current.rotation.y = Math.sin(t * 0.35 + phase) * 0.16;
      const lift = active ? 0.1 : 0;
      emblem.current.position.y = height + LOGO_LIFT + lift + Math.sin(t * 0.8 + phase) * 0.025;
    }
    if (band.current) {
      band.current.emissiveIntensity = alerting ? 3 + Math.sin(t * 6) * 2.2 : active ? 4.5 : 2.4;
    }
  });

  const plate = useCanvasTexture(
    512,
    112,
    (ctx) => {
      ctx.fillStyle = "#0c1017";
      ctx.fillRect(0, 0, 512, 112);
      ctx.strokeStyle = "#3a4558";
      ctx.lineWidth = 3;
      ctx.strokeRect(5, 5, 502, 102);
      ctx.fillStyle = "#d7dee9";
      fitText(ctx, service.name.toUpperCase(), 256, 58, 452, 46, (size) => `600 ${size}px ${SANS}`);
    },
    [service.name],
  );

  const brand = BRANDS[service.id];
  const fallback = EMBLEMS[service.id] ?? { kind: "generic" as const, color: "#8b9bb4" };

  return (
    <group
      position={placement.position}
      {...pointerHandlers({ kind: "service", id: service.id }, interaction)}
    >
      <RoundedBox
        args={[SIDE, height, SIDE]}
        radius={0.03}
        smoothness={3}
        position={[0, height / 2, 0]}
        castShadow
        receiveShadow
      >
        <meshStandardMaterial color="#2a3140" metalness={0.7} roughness={0.36} />
      </RoundedBox>

      <mesh position={[0, height + 0.012, 0]}>
        <boxGeometry args={[SIDE - 0.04, 0.024, SIDE - 0.04]} />
        <meshStandardMaterial
          ref={band}
          color="#0a0d12"
          emissive={statusColor}
          emissiveIntensity={2.4}
        />
      </mesh>
      <mesh position={[0, height + 0.03, 0]} receiveShadow>
        <boxGeometry args={[SIDE - 0.14, 0.03, SIDE - 0.14]} />
        <meshStandardMaterial color="#0d1118" metalness={0.9} roughness={0.25} />
      </mesh>

      <mesh position={[0, height - 0.17, SIDE / 2 + 0.002]}>
        <planeGeometry args={[0.7, 0.153]} />
        <meshBasicMaterial map={plate} />
      </mesh>

      <group ref={emblem} position={[0, height + LOGO_LIFT, 0]}>
        {brand ? (
          <Logo3D brand={brand} size={0.78} dimmed={dimmed} />
        ) : (
          <Emblem kind={fallback.kind} color={fallback.color} dimmed={dimmed} />
        )}
      </group>
    </group>
  );
}
