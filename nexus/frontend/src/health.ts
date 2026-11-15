// One definition of the health thresholds, shared by the DOM health bars and the displays drawn
// inside the 3D room, so a figure is never amber in one place and green in another.
export function healthColor(pct: number): string {
  if (pct > 90) return "#f87171";
  if (pct > 75) return "#fbbf24";
  return "#4ade80";
}
