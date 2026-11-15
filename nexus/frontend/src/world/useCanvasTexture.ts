import { useEffect, useMemo } from "react";
import { CanvasTexture, SRGBColorSpace } from "three";

export const MONO = 'ui-monospace, "SF Mono", Menlo, Consolas, monospace';
export const SANS = 'system-ui, -apple-system, "Segoe UI", Roboto, sans-serif';

// A texture painted with the 2D canvas API: the displays on the servers, the nameplates on the
// plinths, the lettering on the floor. Text is drawn with the viewer's own system fonts, so no
// font file is shipped or fetched. `draw` runs again whenever `deps` change, which is how a
// display follows live data.
export function useCanvasTexture(
  width: number,
  height: number,
  draw: (ctx: CanvasRenderingContext2D) => void,
  deps: unknown[],
): CanvasTexture {
  const texture = useMemo(() => {
    const canvas = document.createElement("canvas");
    canvas.width = width;
    canvas.height = height;
    const created = new CanvasTexture(canvas);
    created.colorSpace = SRGBColorSpace;
    created.anisotropy = 8;
    return created;
  }, [width, height]);

  useEffect(() => {
    const ctx = (texture.image as HTMLCanvasElement).getContext("2d");
    if (!ctx) return;
    ctx.clearRect(0, 0, width, height);
    draw(ctx);
    // Flagging a texture for re-upload is how three.js is told its canvas changed.
    // oxlint-disable-next-line react/immutability
    texture.needsUpdate = true;
    // `draw` is a fresh closure on every render; `deps` names the data it actually reads.
    // oxlint-disable-next-line react-hooks/exhaustive-deps
  }, [texture, width, height, ...deps]);

  useEffect(() => () => texture.dispose(), [texture]);

  return texture;
}

// Draws `text` centred, shrinking the font until it fits `maxWidth`.
export function fitText(
  ctx: CanvasRenderingContext2D,
  text: string,
  x: number,
  y: number,
  maxWidth: number,
  size: number,
  font: (size: number) => string,
) {
  let current = size;
  ctx.font = font(current);
  while (ctx.measureText(text).width > maxWidth && current > 10) {
    current -= 2;
    ctx.font = font(current);
  }
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText(text, x, y);
}
