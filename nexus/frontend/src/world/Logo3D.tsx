import { useEffect, useMemo } from "react";
import { ExtrudeGeometry } from "three";
import { SVGLoader } from "three/examples/jsm/loaders/SVGLoader.js";
import type { Brand } from "./logos";

// A brand mark as a solid: the SVG outline extruded and bevelled, so it catches light along its
// edges like a cast metal badge rather than sitting flat like a sticker.
export function Logo3D({
  brand,
  size,
  dimmed,
}: {
  brand: Brand;
  size: number;
  dimmed: boolean;
}) {
  const geometry = useMemo(() => {
    const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path d="${brand.path}"/></svg>`;
    const shapes = new SVGLoader().parse(svg).paths.flatMap((path) => path.toShapes());
    const extruded = new ExtrudeGeometry(shapes, {
      depth: 3.2,
      bevelEnabled: true,
      bevelThickness: 0.4,
      bevelSize: 0.22,
      bevelSegments: 4,
      curveSegments: 20,
    });
    extruded.center();
    // SVG's y axis points down. Half a turn about x stands the mark upright without mirroring
    // it, and unlike a negative scale it leaves the triangle winding intact.
    extruded.rotateX(Math.PI);
    extruded.scale(size / 24, size / 24, size / 24);
    return extruded;
  }, [brand.path, size]);

  useEffect(() => () => geometry.dispose(), [geometry]);

  return (
    <mesh geometry={geometry} castShadow>
      <meshPhysicalMaterial
        color={dimmed ? "#4a5261" : brand.color}
        metalness={0.55}
        roughness={0.24}
        clearcoat={1}
        clearcoatRoughness={0.18}
        emissive={brand.color}
        emissiveIntensity={dimmed ? 0 : 0.22}
      />
    </mesh>
  );
}
