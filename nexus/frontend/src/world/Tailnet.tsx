import { useMemo, useRef } from "react";
import { Line } from "@react-three/drei";
import { useFrame } from "@react-three/fiber";
import { QuadraticBezierCurve3, Vector3 } from "three";
import type { Line2 } from "three/examples/jsm/lines/Line2.js";
import type { Vec3 } from "./layout";

function Link({ from, to }: { from: Vec3; to: Vec3 }) {
  const line = useRef<Line2>(null);
  const points = useMemo(() => {
    const start = new Vector3(...from);
    const end = new Vector3(...to);
    const span = start.distanceTo(end);
    const crest = start.clone().lerp(end, 0.5);
    crest.y = Math.max(start.y, end.y) + 1.2 + span * 0.16;
    return new QuadraticBezierCurve3(start, crest, end).getPoints(48);
  }, [from, to]);

  // The dashes travel along the link, towards the hub.
  useFrame((_, delta) => {
    if (line.current) line.current.material.dashOffset -= delta * 0.55;
  });

  return (
    <Line
      ref={line}
      points={points}
      color="#6fb4ff"
      lineWidth={1.6}
      dashed
      dashSize={0.24}
      gapSize={0.16}
      transparent
      opacity={0.6}
      toneMapped={false}
    />
  );
}

// The mesh VPN as light: one link from every device that is online right now to the Tailscale
// plinth. A device that drops off the tailnet loses its link, the same rule the old graph had.
export function Tailnet({ anchors, hub }: { anchors: { id: string; at: Vec3 }[]; hub: Vec3 }) {
  return (
    <group>
      {anchors.map((anchor) => (
        <Link key={anchor.id} from={anchor.at} to={hub} />
      ))}
    </group>
  );
}
