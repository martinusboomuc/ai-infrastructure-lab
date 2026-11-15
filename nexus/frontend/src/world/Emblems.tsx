import { useMemo } from "react";
import { ExtrudeGeometry, Shape } from "three";
import type { EmblemKind } from "./logos";

// Small modelled objects for the tools that have no published logo: a shipping container for
// cAdvisor, a stack of storage platters for Blob Storage, a bank front for the BankML API.
// Each fits the same half-metre cube a logo does.

function Surface({ color, dimmed }: { color: string; dimmed: boolean }) {
  return (
    <meshPhysicalMaterial
      color={dimmed ? "#4a5261" : color}
      metalness={0.5}
      roughness={0.3}
      clearcoat={0.8}
      clearcoatRoughness={0.25}
      emissive={color}
      emissiveIntensity={dimmed ? 0 : 0.18}
    />
  );
}

function Container({ color, dimmed }: { color: string; dimmed: boolean }) {
  const ribs = [-0.36, -0.27, -0.18, -0.09, 0, 0.09, 0.18, 0.27, 0.36];
  return (
    <group>
      <mesh castShadow>
        <boxGeometry args={[0.9, 0.4, 0.38]} />
        <Surface color={color} dimmed={dimmed} />
      </mesh>
      {ribs.map((x) => (
        <mesh key={x} position={[x, 0, 0]} castShadow>
          <boxGeometry args={[0.035, 0.34, 0.41]} />
          <Surface color={color} dimmed={dimmed} />
        </mesh>
      ))}
      <mesh position={[0, 0.205, 0]}>
        <boxGeometry args={[0.92, 0.02, 0.4]} />
        <meshStandardMaterial color="#10141b" metalness={0.8} roughness={0.4} />
      </mesh>
      <mesh position={[0, -0.205, 0]}>
        <boxGeometry args={[0.92, 0.02, 0.4]} />
        <meshStandardMaterial color="#10141b" metalness={0.8} roughness={0.4} />
      </mesh>
    </group>
  );
}

function Storage({ color, dimmed }: { color: string; dimmed: boolean }) {
  return (
    <group>
      {[-0.2, 0, 0.2].map((y) => (
        <group key={y} position={[0, y, 0]}>
          <mesh castShadow>
            <cylinderGeometry args={[0.36, 0.36, 0.15, 48]} />
            <Surface color={color} dimmed={dimmed} />
          </mesh>
          <mesh position={[0, -0.09, 0]}>
            <cylinderGeometry args={[0.33, 0.33, 0.04, 48]} />
            <meshStandardMaterial color="#0c1118" metalness={0.9} roughness={0.3} />
          </mesh>
        </group>
      ))}
    </group>
  );
}

function Bank({ color, dimmed }: { color: string; dimmed: boolean }) {
  const pediment = useMemo(() => {
    const outline = new Shape();
    outline.moveTo(-0.46, 0);
    outline.lineTo(0.46, 0);
    outline.lineTo(0, 0.2);
    outline.closePath();
    const geometry = new ExtrudeGeometry(outline, { depth: 0.4, bevelEnabled: false });
    geometry.translate(0, 0, -0.2);
    return geometry;
  }, []);
  return (
    <group position={[0, -0.04, 0]}>
      <mesh position={[0, -0.3, 0]} castShadow>
        <boxGeometry args={[0.92, 0.07, 0.46]} />
        <Surface color={color} dimmed={dimmed} />
      </mesh>
      {[-0.31, -0.105, 0.105, 0.31].map((x) => (
        <mesh key={x} position={[x, -0.07, 0.12]} castShadow>
          <cylinderGeometry args={[0.048, 0.055, 0.4, 20]} />
          <Surface color={color} dimmed={dimmed} />
        </mesh>
      ))}
      <mesh position={[0, -0.07, -0.08]} castShadow>
        <boxGeometry args={[0.78, 0.4, 0.2]} />
        <Surface color={color} dimmed={dimmed} />
      </mesh>
      <mesh position={[0, 0.16, 0]} castShadow>
        <boxGeometry args={[0.9, 0.06, 0.42]} />
        <Surface color={color} dimmed={dimmed} />
      </mesh>
      <mesh geometry={pediment} position={[0, 0.19, 0]} castShadow>
        <Surface color={color} dimmed={dimmed} />
      </mesh>
    </group>
  );
}

function Generic({ color, dimmed }: { color: string; dimmed: boolean }) {
  return (
    <mesh castShadow>
      <icosahedronGeometry args={[0.36, 0]} />
      <Surface color={color} dimmed={dimmed} />
    </mesh>
  );
}

export function Emblem({
  kind,
  color,
  dimmed,
}: {
  kind: EmblemKind;
  color: string;
  dimmed: boolean;
}) {
  if (kind === "container") return <Container color={color} dimmed={dimmed} />;
  if (kind === "storage") return <Storage color={color} dimmed={dimmed} />;
  if (kind === "bank") return <Bank color={color} dimmed={dimmed} />;
  return <Generic color={color} dimmed={dimmed} />;
}
