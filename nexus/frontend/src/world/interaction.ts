import type { ThreeEvent } from "@react-three/fiber";
import type { Selection } from "../selection";

export interface Interaction {
  onSelect: (selection: Selection) => void;
  onHover: (selection: Selection | null) => void;
}

// Pointer handlers that make a group of meshes behave as one clickable object. Each stops the
// event, so a server unit inside the rack selects the unit and not the rack behind it.
export function pointerHandlers(selection: Selection, { onSelect, onHover }: Interaction) {
  return {
    onClick: (event: ThreeEvent<MouseEvent>) => {
      event.stopPropagation();
      onSelect(selection);
    },
    onPointerOver: (event: ThreeEvent<PointerEvent>) => {
      event.stopPropagation();
      onHover(selection);
    },
    onPointerOut: () => onHover(null),
  };
}

export const STATUS_COLOR = {
  up: "#34d399",
  down: "#f87171",
  unknown: "#7c8aa0",
  alert: "#ff3b3b",
} as const;

// A stable number in [0, 1) per id, so each object's idle motion is out of step with its
// neighbours' without anything random changing between renders.
export function phaseOf(id: string): number {
  let hash = 0;
  for (let i = 0; i < id.length; i++) hash = (hash * 31 + id.charCodeAt(i)) % 1000;
  return hash / 1000;
}
