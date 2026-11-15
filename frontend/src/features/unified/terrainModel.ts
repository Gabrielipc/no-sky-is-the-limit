import type { SurfaceSite } from "../surface/terrain";
export type VisualSite = SurfaceSite & {
  datum: string;
  native_resolution_m: number | string;
  quantization_error_m: number;
  sha256: string;
  grid_crs: string;
};
export type Catalog = {
  version: number;
  sites: Record<string, { local?: VisualSite; regional?: VisualSite }>;
  missing: Record<string, string>;
  moon: {
    radius_m: number;
    tile_size: number;
    max_level: number;
    native_spacing_m: number;
    source_url: string;
    color_note: string;
  };
};
export type Grid = { site: VisualSite; heights: Float32Array };
export type VisualLayer = "elevation" | "slope";
/** Exact identity AND centre are required. A release may move a window without changing a label. */
export function exactSite(
  catalog: Catalog | undefined,
  id: string,
  lon: number,
  lat: number,
  kind: "local" | "regional",
) {
  const site = catalog?.sites[id]?.[kind];
  return site &&
    Math.abs(site.longitude - lon) < 1e-6 &&
    Math.abs(site.latitude - lat) < 1e-6
    ? site
    : undefined;
}
/** Display slope uses a 60 m central-difference base on a common 30 m grid.
 * It is deliberately distinct from the published 240 m ranking descriptor. */
export function visualValues(grid: Grid, layer: VisualLayer): Float32Array {
  const { site: s, heights: h } = grid;
  if (layer === "elevation")
    return Float32Array.from(h, (z) =>
      Number.isFinite(z) ? z - s.center_m : NaN,
    );
  const out = new Float32Array(h.length).fill(NaN);
  for (let y = 1; y < s.height - 1; y++)
    for (let x = 1; x < s.width - 1; x++) {
      const i = y * s.width + x,
        a = h[i - 1],
        b = h[i + 1],
        c = h[i - s.width],
        d = h[i + s.width];
      if ([h[i], a, b, c, d].every(Number.isFinite))
        out[i] =
          (Math.atan(
            Math.hypot((b - a) / (2 * s.cell_m), (d - c) / (2 * s.cell_m)),
          ) *
            180) /
          Math.PI;
    }
  return out;
}
export function sharedRange(
  grids: (Grid | undefined)[],
  layer: VisualLayer,
): [number, number] {
  let lo = Infinity,
    hi = -Infinity;
  for (const grid of grids)
    if (grid)
      for (const v of visualValues(grid, layer))
        if (Number.isFinite(v)) {
          lo = Math.min(lo, v);
          hi = Math.max(hi, v);
        }
  return lo === Infinity
    ? [0, 1]
    : [layer === "slope" ? 0 : lo, hi === lo ? lo + 1 : hi];
}
/** Spherical direct geodesic. Local x=east/y=north remains correct at lunar poles. */
export function offsetDegrees(
  lon: number,
  lat: number,
  east: number,
  north: number,
  radius: number,
): [number, number] {
  const p = (lat * Math.PI) / 180,
    l = (lon * Math.PI) / 180,
    d = Math.hypot(east, north) / radius,
    b = Math.atan2(east, north);
  const p2 = Math.asin(
    Math.sin(p) * Math.cos(d) + Math.cos(p) * Math.sin(d) * Math.cos(b),
  );
  const l2 =
    l +
    Math.atan2(
      Math.sin(b) * Math.sin(d) * Math.cos(p),
      Math.cos(d) - Math.sin(p) * Math.sin(p2),
    );
  return [(((l2 * 180) / Math.PI + 540) % 360) - 180, (p2 * 180) / Math.PI];
}

/** A spherical mean frames an unselected result set, including the date line. */
export function candidateFocus(rows:{longitude:number;latitude:number}[]):[number,number]{
 if(!rows.length)return [0,10];
 let x=0,y=0,z=0;
 for(const row of rows){const a=row.longitude*Math.PI/180,b=row.latitude*Math.PI/180;x+=Math.cos(b)*Math.cos(a);y+=Math.cos(b)*Math.sin(a);z+=Math.sin(b);}
 return Math.hypot(x,y,z)<1e-8?[0,10]:[Math.atan2(y,x)*180/Math.PI,Math.atan2(z,Math.hypot(x,y))*180/Math.PI];
}
