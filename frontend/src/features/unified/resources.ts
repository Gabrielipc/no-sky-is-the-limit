import { useEffect, useState } from "react";
import { asset, pixels } from "../surface/assets";
import { decodeGray } from "../surface/terrain";
import type { Catalog, Grid, VisualSite } from "./terrainModel";
export function useCatalog() {
  const [result, setResult] = useState<{ data?: Catalog; error?: string }>({});
  useEffect(() => {
    const c = new AbortController();
    fetch(asset("unified/catalog.json"), { signal: c.signal })
      .then((r) => {
        if (!r.ok) throw Error("Catálogo de relieve no disponible");
        return r.json();
      })
      .then((data) => {
        if (!c.signal.aborted) setResult({ data });
      })
      .catch((e) => {
        if (!c.signal.aborted) setResult({ error: e.message });
      });
    return () => c.abort();
  }, []);
  return result;
}
// A decoded grid is shared across selections and kept only while this page is open.
const grids = new Map<string, Promise<Grid>>();
function loadGrid(site: VisualSite): Promise<Grid> {
  const key = site.heightmap;
  let pending = grids.get(key);
  if (!pending) {
    pending = pixels(asset(key), new AbortController().signal, site.width, site.height)
      .then((data) => ({ site, heights: decodeGray(data, site) }))
      .catch((error) => { grids.delete(key); throw error; });
    grids.set(key, pending);
    if (grids.size > 80) grids.delete(grids.keys().next().value!);
  }
  return pending;
}

/** Warm the prepared local and regional grids, without blocking the selected view. */
export function prefetchGrids(sites: VisualSite[]): () => void {
  let cancelled = false;
  let next = 0;
  async function worker() {
    while (!cancelled && next < sites.length) {
      const site = sites[next++];
      try { await loadGrid(site); } catch { /* Selection can retry a failed grid. */ }
    }
  }
  void Promise.all([worker(), worker(), worker()]);
  return () => { cancelled = true; };
}

export function useGrid(site: VisualSite | undefined, enabled: boolean) {
  const key = site?.heightmap;
  const [result, setResult] = useState<{ key?: string; grid?: Grid; error?: string }>({});
  useEffect(() => {
    if (!site || !enabled) return;
    let cancelled = false;
    loadGrid(site)
      .then((grid) => { if (!cancelled) setResult({ key, grid }); })
      .catch((e) => { if (!cancelled) setResult({ key, error: e.message }); });
    return () => { cancelled = true; };
  }, [site, key, enabled]);
  return result.key === key ? result : {};
}
