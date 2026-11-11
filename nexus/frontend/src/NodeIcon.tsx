import type { TopologyNode } from "./api";

// Inline SVG outlines: they inherit the text colour and render identically on every OS.
const PATHS: Record<TopologyNode["type"], string> = {
  host: "M4 4h16v6H4z M4 14h16v6H4z M7 7h.01 M7 17h.01",
  vm: "M12 3l8 4.5v9L12 21l-8-4.5v-9z M12 12l8-4.5 M12 12v9 M12 12L4 7.5",
  laptop: "M5 5h14v10H5z M2 19h20",
  phone: "M8 2h8a1 1 0 0 1 1 1v18a1 1 0 0 1-1 1H8a1 1 0 0 1-1-1V3a1 1 0 0 1 1-1z M11 18h2",
};

export function NodeIcon({ type }: { type: TopologyNode["type"] }) {
  return (
    <svg
      className="node-icon"
      viewBox="0 0 24 24"
      width="16"
      height="16"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d={PATHS[type]} />
    </svg>
  );
}
