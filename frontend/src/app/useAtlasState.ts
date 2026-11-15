import { useCallback, useEffect, useState } from 'react';
import type { Layer, Profile, Sort } from '../domain/analysis';
import type { SurfaceMetric } from '../domain/dimensions';
import { crismLayers, type CrismLayer, type MineralLayer } from '../domain/minerals';

export type AtlasState = {
  view: 'surface' | 'compare' | 'explore' | 'sensitivity' | 'dimensions' | 'world'; surfaceSite: string; site: string; cell: 60 | 120; layer: Layer; surfaceMetric: SurfaceMetric;
  area: string; regionalCell: 300 | 600; profile: Profile; excluded: boolean; sort: Sort;
  regionalSite: string; sensitivitySite: string; sensitivityCell: number;
  dimensionSection: 'minerals' | 'geometry' | 'thermal'; mineralGroup: 1 | 2; mineralLayer: MineralLayer;
  mineralId: number; mineralFit: number; mineralMaxSlope: number; crismLayer: CrismLayer;
};
export const defaults: AtlasState = { view: 'compare', surfaceSite: 'mars-jezero-fan', site: 'earth-utah', cell: 60, layer: 'slope', surfaceMetric: 'roughness_rms', area: 'utah', regionalCell: 300, profile: 'baseline', excluded: false, sort: 'slope_distance', regionalSite: '', sensitivitySite: 'utah-010-007', sensitivityCell: 300, dimensionSection: 'minerals', mineralGroup: 1, mineralLayer: 'minerals', mineralId: 0, mineralFit: 0, mineralMaxSlope: 90, crismLayer: 'OLINDEX3' };
export function parseState(search: string): { state: AtlasState; adjusted: boolean } {
  const q = new URLSearchParams(search);
  const state = { ...defaults }; let adjusted = false;
  function choice<K extends keyof AtlasState>(key: K, values: readonly AtlasState[K][]) {
    const raw = q.get(key); if (raw === null) return;
    const value = typeof defaults[key] === 'number' ? Number(raw) : typeof defaults[key] === 'boolean' ? raw === 'true' ? true : raw === 'false' ? false : raw : raw;
    if (values.includes(value as AtlasState[K])) state[key] = value as AtlasState[K]; else adjusted = true;
  }
  choice('surfaceSite', ['mars-jezero-fan', 'earth-utah', 'earth-atacama']);
  choice('view', ['surface', 'compare', 'explore', 'sensitivity', 'dimensions', 'world']); choice('site', ['earth-utah', 'earth-atacama']);
  choice('surfaceMetric', ['roughness_rms', 'topographic_position', 'laplacian']);
  choice('dimensionSection', ['minerals', 'geometry', 'thermal']); choice('mineralGroup', [1, 2]);
  choice('mineralLayer', ['minerals', 'fit', 'uncertainty', 'slope']);
  choice('crismLayer', crismLayers);
  for (const [key, max] of [['mineralId', 10000], ['mineralFit', 1], ['mineralMaxSlope', 90]] as const) {
    const raw = q.get(key);
    if (raw !== null) {
      const n = Number(raw);
      if (raw.trim() && Number.isFinite(n) && n >= 0 && n <= max && (key === 'mineralFit' || Number.isInteger(n)) && (key !== 'mineralMaxSlope' || n <= 25 || n === 90)) {
        state[key] = key === 'mineralFit' ? Math.round(n * 20) / 20 : n;
        if (state[key] !== n) adjusted = true;
      }
      else adjusted = true;
    }
  }
  choice('cell', [60, 120]); choice('layer', ['slope', 'elevation']); choice('area', ['utah', 'mojave', 'atacama']);
  choice('regionalCell', [300, 600]); choice('profile', ['strict', 'baseline', 'relaxed']); choice('excluded', [true, false]);
  choice('sort', ['slope_distance', 'abs_relief_difference']); choice('sensitivityCell', [60, 120, 300, 600]);
  for (const key of ['regionalSite', 'sensitivitySite'] as const) {
    const raw = q.get(key);
    if (raw !== null) { if (/^(?:utah|mojave|atacama)-\d{3}-\d{3}$|^control-(?:utah|mojave|atacama)$|^$/.test(raw)) state[key] = raw; else adjusted = true; }
  }
  if (state.regionalSite && !state.regionalSite.startsWith(state.area + '-') && state.regionalSite !== `control-${state.area}`) { state.regionalSite = ''; adjusted = true; }
  return { state, adjusted };
}
function stateURL(state: AtlasState) {
  const q = new URLSearchParams();
  for (const key of Object.keys(defaults) as (keyof AtlasState)[]) {
    const value = state[key] ?? defaults[key];
    if (value !== defaults[key]) q.set(key, String(value));
  }
  return `${window.location.pathname}${q.size ? '?' + q.toString() : ''}`;
}
export function useAtlasState() {
  const [initial] = useState(() => parseState(window.location.search));
  const [state, setState] = useState(initial.state);
  const [adjusted, setAdjusted] = useState(initial.adjusted);
  useEffect(() => {
    window.history.replaceState(null, '', stateURL(initial.state));
    const pop = () => { const parsed = parseState(window.location.search); setState(parsed.state); setAdjusted(parsed.adjusted); };
    window.addEventListener('popstate', pop); return () => window.removeEventListener('popstate', pop);
  }, [initial]);
  const update = useCallback((patch: Partial<AtlasState>) => {
    setState(previous => {
      const next = { ...defaults, ...previous, ...patch };
      const url = stateURL(next);
      if (window.location.pathname + window.location.search !== url) window.history.pushState(null, '', url);
      return next;
    });
  }, []);
  // Fast Refresh can retain an older state object while new controls are added.
  return { state: { ...defaults, ...state }, update, adjusted, dismissAdjustment: () => setAdjusted(false) };
}
