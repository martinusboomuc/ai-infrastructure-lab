import { useEffect, useMemo, useRef } from "react";
import { CameraControls, Environment, Lightformer } from "@react-three/drei";
import { Canvas, useThree } from "@react-three/fiber";
import { Bloom, EffectComposer, ToneMapping, Vignette } from "@react-three/postprocessing";
import { ToneMappingMode } from "postprocessing";
import type { Service, TopologyNode } from "../api";
import { type Selection, selectionKey } from "../selection";
import { Desk } from "./Desk";
import type { Interaction } from "./interaction";
import {
  DESK,
  LOGO_LIFT,
  layoutServices,
  nodeAnchor,
  type Pose,
  poseFor,
  RACK,
  type Vec3,
} from "./layout";
import { Rack } from "./Rack";
import { Room } from "./Room";
import { ServicePlinth } from "./ServicePlinth";
import { Tailnet } from "./Tailnet";

const FOV = 40;
const LOOK_AT: Vec3 = [0, 1.5, -1.2];

// Far enough back that the rack on the left and the desk on the right are both in frame, which
// on a narrow window means further back than on a wide one.
function homePose(aspect: number): Pose {
  const halfWidth = 10.6;
  const distance = Math.min(
    34,
    Math.max(13.5, halfWidth / (Math.tan((FOV * Math.PI) / 360) * aspect)),
  );
  const [x, y, z] = LOOK_AT;
  return [x, y + distance * 0.44, z + distance * 0.9, x, y, z];
}

// The camera is not the viewer's to steer. It has two kinds of pose, the overview and the close
// look at whatever is selected, and only a click travels between them: it never drags. In the
// overview the wheel and pinch do nothing either. On a selection they move in closer, and back
// out only as far as the pose the click arrived at. The numbers are camera-controls' ACTION
// values: 0 NONE, 16 DOLLY, 1024 TOUCH_DOLLY.
const NO_INPUT = {
  mouse: { left: 0, middle: 0, right: 0, wheel: 0 },
  touch: { one: 0, two: 0, three: 0 },
} as const;
const ZOOM_IN_ONLY = {
  mouse: { left: 0, middle: 0, right: 0, wheel: 16 },
  touch: { one: 0, two: 1024, three: 0 },
} as const;
// How far in the wheel may go, as a share of the arrival distance. Closer than this the object
// overflows the frame and the view stops being a look at it.
const CLOSEST = 0.5;

function CameraRig({ pose, homeNonce }: { pose: Pose | null; homeNonce: number }) {
  const controls = useRef<CameraControls>(null);
  const aspect = useThree((state) => state.size.width / state.size.height);
  const first = useRef(true);
  const key = pose ? pose.join(",") : "home";
  const input = pose ? ZOOM_IN_ONLY : NO_INPUT;
  // The distance the click arrives at is the furthest the wheel can back out to.
  const arrival = pose ? Math.hypot(pose[0] - pose[3], pose[1] - pose[4], pose[2] - pose[5]) : null;

  useEffect(() => {
    const target = pose ?? homePose(aspect);
    // The very first pose is set without a transition, so the room does not open mid-flight.
    void controls.current?.setLookAt(...target, !first.current);
    first.current = false;
    // `key` stands in for `pose`, which is a new array on every poll even when unchanged.
    // oxlint-disable-next-line react-hooks/exhaustive-deps
  }, [key, aspect, homeNonce]);

  return (
    <CameraControls
      ref={controls}
      makeDefault
      mouseButtons={input.mouse}
      touches={input.touch}
      minDistance={arrival === null ? 0 : arrival * CLOSEST}
      maxDistance={arrival ?? Infinity}
      smoothTime={0.5}
    />
  );
}

export interface WorldProps {
  nodes: TopologyNode[];
  services: Service[];
  alerting: Set<string>;
  alarm: boolean;
  selection: Selection | null;
  hovered: Selection | null;
  homeNonce: number;
  onSelect: (selection: Selection | null) => void;
  onHover: (selection: Selection | null) => void;
}

export default function World({
  nodes,
  services,
  alerting,
  alarm,
  selection,
  hovered,
  homeNonce,
  onSelect,
  onHover,
}: WorldProps) {
  const { placements, bays } = useMemo(() => layoutServices(services), [services]);
  const interaction: Interaction = useMemo(() => ({ onSelect, onHover }), [onSelect, onHover]);

  const isActive = (candidate: Selection) =>
    (selection !== null && selectionKey(selection) === selectionKey(candidate)) ||
    (hovered !== null && selectionKey(hovered) === selectionKey(candidate));

  // Tailnet links end at the Tailscale plinth. If the catalog ever stops listing Tailscale, they
  // gather at a point under the ceiling instead of vanishing.
  const tailscale = placements.get("tailscale");
  const hub: Vec3 = tailscale
    ? [tailscale.position[0], tailscale.height + LOGO_LIFT, tailscale.position[2]]
    : [0, 5.2, -2];
  const anchors = nodes
    .filter((node) => node.online)
    .map((node) => ({ id: node.id, at: nodeAnchor(node, nodes) }));

  let pose: Pose | null = null;
  if (selection?.kind === "service") {
    const placement = placements.get(selection.id);
    if (placement) {
      const [x, , z] = placement.position;
      pose = poseFor([x, placement.height + LOGO_LIFT, z], "service");
    }
  } else if (selection?.kind === "node") {
    const node = nodes.find((candidate) => candidate.id === selection.id);
    if (node) {
      const onDesk = node.type === "laptop" || node.type === "phone";
      const anchor = nodeAnchor(node, nodes);
      pose = onDesk
        ? poseFor([DESK.x, anchor[1], DESK.z], "desk")
        : poseFor(
            [RACK.x, node.type === "host" ? RACK.scale * RACK.height * 0.55 : anchor[1], RACK.z],
            "rack",
          );
    }
  }

  return (
    <Canvas
      shadows="percentage"
      dpr={[1, 1.75]}
      camera={{ fov: FOV, near: 0.1, far: 90, position: [0, 5.4, 13.5] }}
      onPointerMissed={() => onSelect(null)}
    >
      <color attach="background" args={["#05070c"]} />
      <fog attach="fog" args={["#05070c", 28, 70]} />

      <ambientLight intensity={0.55} />
      <hemisphereLight args={["#aac4ff", "#0a0d14", 0.6]} />
      <spotLight
        position={[3, 9, 7]}
        angle={0.85}
        penumbra={0.9}
        intensity={3.6}
        decay={0}
        color="#e6edff"
        castShadow
        shadow-mapSize={[2048, 2048]}
        shadow-bias={-0.0002}
      />
      <spotLight
        position={[-9, 6, 4]}
        angle={0.7}
        penumbra={1}
        intensity={2.0}
        decay={0}
        color="#8fb8ff"
      />
      <pointLight position={[RACK.x + 0.6, 2.4, RACK.z + 3]} intensity={26} distance={9} />
      <pointLight position={[DESK.x - 0.4, 3.2, DESK.z + 1.8]} intensity={26} distance={9} />

      {/* Reflections come from light panels built here, not from an HDR image fetched from a
          CDN: Nexus is served on a tailnet and has to render with no route to the internet. */}
      <Environment resolution={256}>
        <Lightformer form="rect" intensity={2.2} position={[0, 6, 2]} scale={[14, 3, 1]} />
        <Lightformer form="rect" intensity={1.4} position={[-8, 3, 4]} scale={[3, 5, 1]} />
        <Lightformer form="rect" intensity={1.4} position={[8, 3, 4]} scale={[3, 5, 1]} />
        <Lightformer form="rect" intensity={0.9} position={[0, 2, 10]} scale={[12, 3, 1]} />
      </Environment>

      <Room bays={bays} alarm={alarm} />
      <Rack
        nodes={nodes}
        selection={selection}
        hovered={hovered}
        alerting={alerting}
        interaction={interaction}
      />
      <Desk nodes={nodes} selection={selection} hovered={hovered} interaction={interaction} />

      {services.map((service) => {
        const placement = placements.get(service.id);
        if (!placement) return null;
        const self: Selection = { kind: "service", id: service.id };
        return (
          <ServicePlinth
            key={service.id}
            service={service}
            placement={placement}
            active={isActive(self)}
            alerting={alerting.has(selectionKey(self))}
            interaction={interaction}
          />
        );
      })}

      <Tailnet anchors={anchors} hub={hub} />

      <CameraRig pose={pose} homeNonce={homeNonce} />

      <EffectComposer multisampling={4}>
        <Bloom mipmapBlur intensity={0.75} luminanceThreshold={0.85} luminanceSmoothing={0.2} />
        <Vignette offset={0.3} darkness={0.5} />
        <ToneMapping mode={ToneMappingMode.ACES_FILMIC} />
      </EffectComposer>
    </Canvas>
  );
}
