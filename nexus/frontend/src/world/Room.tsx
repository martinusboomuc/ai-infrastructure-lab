import { useRef } from "react";
import { MeshReflectorMaterial } from "@react-three/drei";
import { useFrame } from "@react-three/fiber";
import type { PointLight } from "three";
import type { Bay } from "./layout";
import { fitText, SANS, useCanvasTexture } from "./useCanvasTexture";

const WALL_Z = -6.6;
const CEILING = 6.4;
const SLATS = Array.from({ length: 27 }, (_, index) => -13 + index);

// One aisle sign per layer, hung from the ceiling over its bay the way a datacenter marks its
// rows. Signs over the rows nearer the camera hang lower, so no sign crosses the logos of the row
// behind it; lettering on the floor was tried first and was hidden by the plinths in front of it.
function BaySign({ bay, row }: { bay: Bay; row: number }) {
  const texture = useCanvasTexture(
    1024,
    128,
    (ctx) => {
      ctx.fillStyle = "#0a0e15";
      ctx.fillRect(0, 0, 1024, 128);
      ctx.fillStyle = "#dbe6f5";
      fitText(ctx, bay.layer.toUpperCase(), 512, 68, 940, 70, (size) => `600 ${size}px ${SANS}`);
    },
    [bay.layer],
  );
  const y = 5.2 - row * 0.6;
  const drop = CEILING - y - 0.15;
  return (
    <group>
      <group position={[bay.x, y, bay.z]}>
        <mesh>
          <boxGeometry args={[2.5, 0.34, 0.05]} />
          <meshStandardMaterial color="#1b212c" metalness={0.8} roughness={0.4} />
        </mesh>
        <mesh position={[0, 0, 0.027]}>
          <planeGeometry args={[2.4, 0.3]} />
          <meshBasicMaterial map={texture} toneMapped={false} />
        </mesh>
        {[-1.05, 1.05].map((x) => (
          <mesh key={x} position={[x, 0.15 + drop / 2, 0]}>
            <cylinderGeometry args={[0.008, 0.008, drop, 6]} />
            <meshStandardMaterial color="#39414f" metalness={0.9} roughness={0.3} />
          </mesh>
        ))}
      </group>
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[bay.x, 0.012, bay.z + 0.62]}>
        <planeGeometry args={[Math.max(bay.width - 0.3, 1.1), 0.03]} />
        <meshBasicMaterial color="#5f7fa8" transparent opacity={0.8} depthWrite={false} />
      </mesh>
    </group>
  );
}

// The room itself: a polished floor that mirrors what stands on it, a slatted back wall with
// light strips, ceiling panels, and a beacon that only lights while an alert is firing.
export function Room({ bays, alarm }: { bays: Bay[]; alarm: boolean }) {
  const beacon = useRef<PointLight>(null);
  const accent = alarm ? "#ff3b3b" : "#3aa0ff";
  // Rows ordered from the back wall towards the camera: 0 is the furthest.
  const rowDepths = [...new Set(bays.map((bay) => bay.z))].sort((a, b) => a - b);

  useFrame(({ clock }) => {
    if (beacon.current) {
      beacon.current.intensity = alarm ? 60 + Math.sin(clock.elapsedTime * 5) * 55 : 0;
    }
  });

  return (
    <group>
      <mesh rotation={[-Math.PI / 2, 0, 0]} receiveShadow>
        <planeGeometry args={[60, 60]} />
        <MeshReflectorMaterial
          resolution={1024}
          blur={[320, 90]}
          mixBlur={1}
          mixStrength={9}
          mixContrast={1}
          mirror={0.55}
          depthScale={0.9}
          minDepthThreshold={0.4}
          maxDepthThreshold={1.4}
          color="#141923"
          metalness={0.55}
          roughness={0.7}
        />
      </mesh>

      {bays.map((bay) => (
        <BaySign key={bay.layer} bay={bay} row={rowDepths.indexOf(bay.z)} />
      ))}

      <mesh position={[0, CEILING / 2, WALL_Z - 0.2]} receiveShadow>
        <boxGeometry args={[30, CEILING, 0.2]} />
        <meshStandardMaterial color="#141a26" metalness={0.3} roughness={0.85} />
      </mesh>
      {SLATS.map((x) => (
        <mesh key={x} position={[x, CEILING / 2, WALL_Z]} receiveShadow>
          <boxGeometry args={[0.62, CEILING, 0.22]} />
          <meshStandardMaterial color="#232c3d" metalness={0.5} roughness={0.55} />
        </mesh>
      ))}
      {[-9.5, -4.5, 4.5, 9.5].map((x) => (
        <mesh key={x} position={[x, CEILING / 2, WALL_Z + 0.02]}>
          <boxGeometry args={[0.07, CEILING - 1.2, 0.04]} />
          <meshStandardMaterial color="#05070a" emissive={accent} emissiveIntensity={2.6} />
        </mesh>
      ))}

      {[-1, 1].map((side) => (
        <mesh key={side} position={[side * 14, CEILING / 2, 2]} receiveShadow>
          <boxGeometry args={[0.2, CEILING, 20]} />
          <meshStandardMaterial color="#141a26" metalness={0.3} roughness={0.85} />
        </mesh>
      ))}

      <mesh position={[0, CEILING, 2]} rotation={[Math.PI / 2, 0, 0]}>
        <planeGeometry args={[30, 20]} />
        <meshStandardMaterial color="#07090e" roughness={0.95} />
      </mesh>
      {[-6.5, 0, 6.5].map((x) => (
        <mesh key={x} position={[x, CEILING - 0.03, -1.2]}>
          <boxGeometry args={[3.4, 0.04, 0.5]} />
          <meshStandardMaterial color="#0a0c10" emissive="#dfe9ff" emissiveIntensity={1.6} />
        </mesh>
      ))}

      <pointLight
        ref={beacon}
        position={[0, CEILING - 0.6, -2]}
        color="#ff2a2a"
        intensity={0}
        distance={22}
        decay={2}
      />
    </group>
  );
}
