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
export function useGrid(site: VisualSite | undefined, enabled: boolean) {
  const key = site?.heightmap;
  const [result, setResult] = useState<{
    key?: string;
    grid?: Grid;
    error?: string;
  }>({});
  useEffect(() => {
    if (!site || !enabled) return;
    const c = new AbortController();
    pixels(asset(site.heightmap), c.signal, site.width, site.height)
      .then((data) => {
        if (!c.signal.aborted)
          setResult({ key, grid: { site, heights: decodeGray(data, site) } });
      })
      .catch((e) => {
        if (!c.signal.aborted) setResult({ key, error: e.message });
      });
    return () => c.abort();
  }, [site, key, enabled]);
  return result.key === key ? result : {};
}
