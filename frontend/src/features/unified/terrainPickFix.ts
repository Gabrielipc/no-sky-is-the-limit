/**
 * Workaround for CesiumJS 1.147 on non-Earth bodies.
 *
 * TerrainMesh.getTransform (used by the terrain picker) rebuilds the tile frame
 * with `Ellipsoid.default` (WGS84) instead of the body's ellipsoid, and writes the
 * result into the mesh's oriented bounding box. On the Mars and Moon spheres the
 * picker then drops triangles, globe.pick misses, and the camera controller falls
 * back to the height above the ellipsoid: zooming stops ~40 m above the sphere even
 * where the ground lies kilometres below (Jezero, Haworth). Here the default is the
 * tile's own body only for that synchronous call. Several viewers (Mars + Earth)
 * share the page, so the global default can never be changed permanently.
 */
import * as Cesium from "cesium";
import { Ellipsoid } from "cesium";

type MeshLike = {
  center: { x: number; y: number; z: number };
  getTransform: (mode: unknown, projection: unknown) => unknown;
};
const bodies = new Set<Ellipsoid>([Ellipsoid.WGS84]);
let installed = false;

export function registerBodyEllipsoid(ellipsoid: Ellipsoid) {
  bodies.add(ellipsoid);
  if (installed) return;
  installed = true;
  const TerrainMesh = (Cesium as unknown as { TerrainMesh?: { prototype: MeshLike } }).TerrainMesh;
  const original = TerrainMesh?.prototype.getTransform;
  if (!TerrainMesh || typeof original !== "function") return;
  TerrainMesh.prototype.getTransform = function (this: MeshLike, mode, projection) {
    const { x, y, z } = this.center;
    const r = Math.hypot(x, y, z);
    let body: Ellipsoid | undefined,
      gap = Infinity;
    // Tile centers sit on the surface; the radii of the bodies differ by >1500 km.
    for (const e of bodies) {
      const d = Math.abs(e.maximumRadius - r);
      if (d < gap) [gap, body] = [d, e];
    }
    const previous = Ellipsoid.default;
    if (!body || body === previous) return original.call(this, mode, projection);
    Ellipsoid.default = body;
    try {
      return original.call(this, mode, projection);
    } finally {
      Ellipsoid.default = previous;
    }
  };
}
