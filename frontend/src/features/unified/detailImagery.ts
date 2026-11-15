/**
 * Progressive display imagery for the unified globes.
 *
 * Mars and Moon references are fixed, so their detail is baked into nested patches
 * (frontend/scripts/prepare-detail-imagery.py) that load coarse → fine, the selected
 * reference first. Earth candidates change with every search: their detail streams
 * from Esri World Imagery around each candidate, added after a short delay so the
 * first paint never competes with it, and the first candidates are prefetched.
 * None of this changes a measurement; it only sharpens what the camera shows.
 */
import {
  ArcGisMapServerImageryProvider,
  ImageryLayer,
  Rectangle,
  SingleTileImageryProvider,
  type Viewer,
} from "cesium";
import { asset } from "../surface/assets";
import { tr } from "../../i18n/lang";

export type Body = "Mars" | "Moon" | "Earth";
export type DetailPatch = {
  id: string;
  mark: string;
  file: string;
  rectangle: [number, number, number, number];
  width: number;
  height: number;
  pixel_m: { latitude: number; longitude_center: number };
  credit: string;
};
type BodyDetail = {
  base: { file: string; width: number; height: number; credit: string };
  patches: DetailPatch[];
  live?: { url: string; credit: string };
};
export type DetailCatalog = { version: number; bodies: Record<Body, BodyDetail> };

let catalog: Promise<DetailCatalog | null> | undefined;
/** Loaded once per page; a missing catalog only means no extra detail. */
export function detailCatalog() {
  catalog ??= fetch(asset("detail/catalog.json?v=3"))
    .then((r) => (r.ok ? (r.json() as Promise<DetailCatalog>) : null))
    .catch(() => null);
  return catalog;
}

const wait = (ms: number, signal: AbortSignal) =>
  new Promise<void>((resolve) => {
    const t = window.setTimeout(resolve, ms);
    signal.addEventListener("abort", () => {
      clearTimeout(t);
      resolve();
    });
  });

/** Smallest patch that fully contains a geographic window (for textured meshes). */
export function patchCovering(
  detail: DetailCatalog | null | undefined,
  body: Body,
  west: number,
  south: number,
  east: number,
  north: number,
) {
  return detail?.bodies[body]?.patches
    .filter(
      ({ rectangle: [w, s, e, n] }) => w <= west && s <= south && e >= east && n >= north,
    )
    .sort((a, b) => (a.rectangle[2] - a.rectangle[0]) - (b.rectangle[2] - b.rectangle[0]))[0];
}

/**
 * Fixed references (Mars, Moon): 4k base, then nested patches one at a time,
 * those of `first` before the rest. Layers stack above the context image.
 */
export async function loadBakedDetail(
  v: Viewer,
  body: Body,
  first: () => string,
  signal: AbortSignal,
  progress: (loaded: number, total: number, finest?: DetailPatch) => void,
) {
  const detail = await detailCatalog();
  const entry = detail?.bodies[body];
  if (!entry || signal.aborted) return;
  const ellipsoid = v.scene.globe.ellipsoid;
  // Patch layers stay ordered wide → fine (fine on top) whatever order they arrive in.
  const placed: { area: number; layer: ImageryLayer }[] = [];
  const add = async (url: string, credit: string, rect?: DetailPatch["rectangle"]) => {
    const rectangle = rect && Rectangle.fromDegrees(...rect);
    const provider = await SingleTileImageryProvider.fromUrl(asset(url), {
      ellipsoid,
      credit,
      ...(rectangle ? { rectangle } : {}),
    });
    if (signal.aborted || v.isDestroyed()) return false;
    const layer = new ImageryLayer(provider, rectangle ? { rectangle } : {});
    if (!rect) {
      // The 4k base goes right above the 2k context image, below every patch.
      v.imageryLayers.add(layer, Math.min(1, v.imageryLayers.length));
    } else {
      const area = (rect[2] - rect[0]) * (rect[3] - rect[1]);
      const above = placed.find((p) => p.area < area);
      v.imageryLayers.add(
        layer,
        above ? v.imageryLayers.indexOf(above.layer) : undefined,
      );
      placed.push({ area, layer });
      placed.sort((a, b) => b.area - a.area);
    }
    v.scene.requestRender();
    return true;
  };
  // Let terrain root tiles and the 2k context settle before heavier downloads.
  await wait(600, signal);
  const total = entry.patches.length;
  let loaded = 0,
    finest: DetailPatch | undefined;
  try {
    if (!signal.aborted) await add(
      body === "Mars" ? "mars-globe.png" : entry.base.file,
      body === "Mars" ? tr("NASA MGS / MOLA · relieve en tonos naturales", "NASA MGS / MOLA · natural-colour relief") : entry.base.credit,
    );
  } catch {
    /* the 2k context image stays */
  }
  // A patch shared by several marks (the lunar cap) first, then the selected
  // reference's patches (wide → fine, as catalogued), then the rest.
  const selected = first();
  const rank = (p: DetailPatch) =>
    p.mark.includes(",") ? 0 : p.mark === selected ? 1 : 2;
  const order = [...entry.patches].sort((a, b) => rank(a) - rank(b));
  for (const [i, patch] of order.entries()) {
    if (signal.aborted) return;
    try {
      if (await add(patch.file, patch.credit, patch.rectangle)) {
        loaded += 1;
        if (!finest || patch.pixel_m.latitude < finest.pixel_m.latitude) finest = patch;
        progress(loaded, total, finest);
      }
    } catch {
      /* a missing patch only leaves the coarser layer visible */
    }
    // Background patches yield to interaction and terrain streaming.
    if (i < order.length - 1) await wait(250, signal);
  }
}

// ---------------------------------------------------------------- Earth (live)
export type LiveMark = { id: string; longitude: number; latitude: number };
const ESRI =
  "https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer";
/** ~±40 km: the 24 km regional frame plus its surroundings. */
const HALF_DEG = 0.36;
const providers = new WeakMap<Viewer, Promise<ArcGisMapServerImageryProvider>>();
const live = new WeakMap<Viewer, Map<string, ImageryLayer>>();

function esri(v: Viewer) {
  let p = providers.get(v);
  if (!p) {
    p = ArcGisMapServerImageryProvider.fromUrl(ESRI);
    providers.set(v, p);
  }
  return p;
}

function candidateRectangle(m: LiveMark) {
  const lat = Math.max(-89, Math.min(89, m.latitude));
  const halfLon = Math.min(10, HALF_DEG / Math.max(0.05, Math.cos((lat * Math.PI) / 180)));
  return Rectangle.fromDegrees(
    Math.max(-180, m.longitude - halfLon),
    Math.max(-90, lat - HALF_DEG),
    Math.min(180, m.longitude + halfLon),
    Math.min(90, lat + HALF_DEG),
  );
}

/**
 * Keep one Esri layer per current candidate (bounded), added after `delay` ms so a
 * new search result first paints with the global context. Layers of candidates that
 * left the ranking are removed. Returns a cleanup for the pending timer.
 */
export function scheduleLiveDetail(
  v: Viewer,
  marks: LiveMark[],
  selected: string,
  delay: number,
  onReady: (count: number) => void,
) {
  const c = new AbortController();
  void (async () => {
    await wait(delay, c.signal);
    if (c.signal.aborted || v.isDestroyed()) return;
    let provider: ArcGisMapServerImageryProvider;
    try {
      provider = await esri(v);
    } catch {
      return; // offline: the Blue Marble context remains
    }
    if (c.signal.aborted || v.isDestroyed()) return;
    const current = live.get(v) ?? new Map<string, ImageryLayer>();
    live.set(v, current);
    const wanted = new Map(
      [...marks]
        .sort((a, b) => Number(b.id === selected) - Number(a.id === selected))
        .slice(0, 30)
        .map((m) => [`${m.id}:${m.longitude.toFixed(4)}:${m.latitude.toFixed(4)}`, m]),
    );
    for (const [key, layer] of current)
      if (!wanted.has(key)) {
        v.imageryLayers.remove(layer, false);
        current.delete(key);
      }
    for (const [key, m] of wanted) {
      if (current.has(key)) continue;
      const layer = new ImageryLayer(provider, {
        rectangle: candidateRectangle(m),
        // Only once the camera is close enough for Blue Marble to blur.
        minimumTerrainLevel: 6,
      });
      v.imageryLayers.add(layer);
      current.set(key, layer);
    }
    v.scene.requestRender();
    onReady(current.size);
    // Warm the browser cache for the frames people open first.
    const first = [...wanted.values()].slice(0, 3);
    await prefetch(first, c.signal);
  })();
  return () => c.abort();
}

/** Web Mercator tiles of the regional frame (±0.12°) at the zooms it displays. */
function mercatorTiles(m: LiveMark) {
  const urls: string[] = [];
  const lat = Math.max(-85, Math.min(85, m.latitude));
  const tx = (lon: number, z: number) => Math.floor(((lon + 180) / 360) * 2 ** z);
  const ty = (la: number, z: number) => {
    const r = (la * Math.PI) / 180;
    return Math.floor(((1 - Math.log(Math.tan(r) + 1 / Math.cos(r)) / Math.PI) / 2) * 2 ** z);
  };
  for (let z = 9; z <= 12; z++) {
    const half = 0.12;
    const x0 = tx(m.longitude - half, z),
      x1 = tx(m.longitude + half, z),
      y0 = ty(lat + half, z),
      y1 = ty(lat - half, z);
    for (let y = y0; y <= y1; y++)
      for (let x = x0; x <= x1; x++)
        if (x >= 0 && x < 2 ** z) urls.push(`${ESRI}/tile/${z}/${y}/${x}`);
  }
  return urls;
}

const warmed = new Set<string>();
async function prefetch(marks: LiveMark[], signal: AbortSignal) {
  const queue = marks.flatMap(mercatorTiles).filter((u) => !warmed.has(u));
  // Safari has no requestIdleCallback: fall back to a short timer.
  const idle = (cb: () => void) =>
    typeof window.requestIdleCallback === "function"
      ? window.requestIdleCallback(cb, { timeout: 1500 })
      : setTimeout(cb, 50);
  const worker = async () => {
    while (queue.length && !signal.aborted) {
      const url = queue.shift()!;
      warmed.add(url);
      await new Promise<void>((resolve) =>
        idle(() => {
          const img = new Image();
          img.crossOrigin = "anonymous";
          img.onload = img.onerror = () => resolve();
          img.src = url;
        }),
      );
    }
  };
  await Promise.all([worker(), worker(), worker()]);
}
