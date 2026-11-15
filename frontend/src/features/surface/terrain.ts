/** Data math kept independent of WebGL so orientation, units and holes are testable. */
export type SurfaceSite = {
  id: string; name: string; body: 'Mars' | 'Earth' | 'Moon'; longitude: number; latitude: number;
  width: number; height: number; cell_m: number; window_m: number;
  offset_m: number; scale_m: number; nodata: number; center_m: number; min_m: number; max_m: number;
  coverage: number; heightmap: string; texture: string; source: string; source_url: string;
};
export type SurfaceManifest = {
  version: number; sites: SurfaceSite[];
  mola: { radius_m: number; tile_size: number; max_level: number; source_resolution_km: number; url: string; regional?: { max_level: number; tiles: string[]; sample_spacing_m: number } };
};
export type SurfaceMode = 'space' | 'regional' | 'mesh';
export type RemoteLayer = { kind: 'terrain' | 'tiles'; url: string } | null;

export function decodeGray(data: Uint8ClampedArray, site: SurfaceSite): Float32Array {
  if (data.length !== site.width * site.height * 4 || !Number.isFinite(site.scale_m) || site.scale_m <= 0) {
    throw new Error('Dimensiones o escala del DEM inválidas.');
  }
  return Float32Array.from({ length: site.width * site.height }, (_, i) =>
    data[i * 4] === site.nodata || data[i * 4 + 3] === 0 ? NaN : site.offset_m + data[i * 4] * site.scale_m);
}
export function decodeMola(data: Uint8ClampedArray): Float32Array {
  return Float32Array.from({ length: data.length / 4 }, (_, i) => data[i * 4] * 256 + data[i * 4 + 1] - 32768);
}
export function meshArrays(heights: Float32Array, site: SurfaceSite, exaggeration: number) {
  const { width, height, cell_m, center_m } = site;
  if (width < 2 || height < 2 || heights.length !== width * height || !Number.isFinite(exaggeration) || exaggeration < 0 || exaggeration > 8) {
    throw new Error('Geometría del DEM inválida.');
  }
  const positions = new Float64Array(width * height * 3), uv = new Float32Array(width * height * 2);
  const indices: number[] = [];
  for (let y = 0; y < height; y++) for (let x = 0; x < width; x++) {
    const i = y * width + x;
    positions.set([(x - (width-1)/2) * cell_m, ((height-1)/2 - y) * cell_m,
      Number.isFinite(heights[i]) ? (heights[i] - center_m) * exaggeration : 0], i*3);
    // Raster row zero is north; texture t=1 is the top of the image.
    uv.set([x / (width-1), 1 - y / (height-1)], i*2);
    if (x === width-1 || y === height-1) continue;
    const a=i,b=i+1,c=i+width,d=c+1;
    for (const triangle of [[a,c,b],[b,c,d]]) {
      if (triangle.every(index => Number.isFinite(heights[index]))) indices.push(...triangle);
    }
  }
  return { positions, uv, indices: new Uint32Array(indices) };
}
export function layerURL(input: string, base: string): string {
  const url = new URL(input.trim(), base);
  if (!input.trim() || url.username || url.password || !['http:', 'https:'].includes(url.protocol)) {
    throw new Error('Introduce una URL HTTP(S) sin credenciales.');
  }
  if (new URL(base).protocol === 'https:' && url.protocol !== 'https:') throw new Error('Este visor requiere una fuente HTTPS.');
  return url.href;
}

/** Official Regolith sequential ramp, shared by both terrain views. */
export const elevationStops = [[43,29,20],[92,53,26],[148,74,32],[208,103,43],[242,166,78],[248,211,143],[253,241,214]];
export function elevationColor(value: number, min: number, max: number): number[] {
  const t = Math.max(0,Math.min(1,(value-min)/(max-min || 1)))*(elevationStops.length-1);
  const i = Math.min(elevationStops.length-2,Math.floor(t)), f=t-i;
  return elevationStops[i].map((v,c)=>Math.round(v*(1-f)+elevationStops[i+1][c]*f));
}
export function terrainProfile(heights: Float32Array, site: SurfaceSite) {
  const row=Math.floor(site.height/2);
  return Array.from({length:site.width},(_,i)=>({distance:i*site.cell_m,height:heights[row*site.width+i]}));
}
export function metricScale(metresPerPixel: number, maxPixels=120) {
  if (!Number.isFinite(metresPerPixel) || metresPerPixel<=0) return null;
  const limit=metresPerPixel*maxPixels, power=10**Math.floor(Math.log10(limit));
  const distance=([5,2,1].find(n=>n*power<=limit) || 1)*power;
  return {distance,pixels:distance/metresPerPixel};
}
