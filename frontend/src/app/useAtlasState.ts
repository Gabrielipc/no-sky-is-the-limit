import { useCallback, useEffect, useState } from 'react';
import type { Layer, Profile, Sort } from '../domain/analysis';
import type { SurfaceMetric } from '../domain/dimensions';
import type { ReferenceId } from '../features/simulation/model';
import { crismLayers, type CrismLayer, type MineralLayer } from '../domain/minerals';

export type AtlasState = {
  explorePanel: 'reference' | 'candidates' | 'controls'; atlasSlope: number; atlasRelief: number; atlasRoughness: number; reference: ReferenceId; regionId: string; release: string; method: 'engine' | 'atlas' | 'local'; engineSource: 'auto' | 'demo'; surfaceMode: 'space' | 'regional' | 'mesh'; exaggeration: number;
  visualLayer: 'elevation' | 'slope'; view: 'landing' | 'unified' | 'simulation' | 'surface' | 'compare' | 'explore' | 'sensitivity' | 'dimensions' | 'world'; surfaceSite: string; site: string; cell: 60 | 120; layer: Layer; surfaceMetric: SurfaceMetric;
  area: string; regionalCell: 300 | 600; profile: Profile; excluded: boolean; sort: Sort;
  regionalSite: string; sensitivitySite: string; sensitivityCell: number;
  dimensionSection: 'minerals' | 'geometry' | 'thermal'; mineralGroup: 1 | 2; mineralLayer: MineralLayer;
  mineralId: number; mineralFit: number; mineralMaxSlope: number; crismLayer: CrismLayer;
};
export const defaults: AtlasState = { explorePanel: 'reference', atlasSlope: 50, atlasRelief: 30, atlasRoughness: 20, reference: 'jezero', regionId: '', release: '', method: 'engine', engineSource: 'auto', surfaceMode: 'space', exaggeration: 1, visualLayer: 'elevation', view: 'landing', surfaceSite: 'mars-jezero-fan', site: 'earth-utah', cell: 60, layer: 'slope', surfaceMetric: 'roughness_rms', area: 'utah', regionalCell: 300, profile: 'baseline', excluded: false, sort: 'slope_distance', regionalSite: '', sensitivitySite: 'utah-010-007', sensitivityCell: 300, dimensionSection: 'minerals', mineralGroup: 1, mineralLayer: 'minerals', mineralId: 0, mineralFit: 0, mineralMaxSlope: 90, crismLayer: 'OLINDEX3' };
export function parseState(search: string): { state: AtlasState; adjusted: boolean } {
  const q = new URLSearchParams(search);
  const state = { ...defaults }; let adjusted = false;
  function choice<K extends keyof AtlasState>(key: K, values: readonly AtlasState[K][]) {
    const raw = q.get(key); if (raw === null) return;
    const value = typeof defaults[key] === 'number' ? Number(raw) : typeof defaults[key] === 'boolean' ? raw === 'true' ? true : raw === 'false' ? false : raw : raw;
    if (values.includes(value as AtlasState[K])) state[key] = value as AtlasState[K]; else adjusted = true;
  }
  choice('explorePanel', ['reference', 'candidates', 'controls']);
  for(const key of ['atlasSlope','atlasRelief','atlasRoughness'] as const){const raw=q.get(key);if(raw!==null){const n=Number(raw);if(raw.trim()&&Number.isFinite(n)&&n>=0&&n<=100)state[key]=n;else adjusted=true;}}
  choice('reference', ['jezero', 'haworth-fondo', 'de-gerlache-cresta']);
  choice('method', ['engine', 'atlas', 'local']); choice('engineSource', ['auto', 'demo']); choice('surfaceMode', ['space', 'regional', 'mesh']);
  for (const key of ['regionId', 'release'] as const) { const raw=q.get(key); if(raw!==null){if(/^[a-zA-Z0-9][a-zA-Z0-9_.:-]{0,159}$|^$/.test(raw))state[key]=raw;else adjusted=true;} }
  const ex=q.get('exaggeration');if(ex!==null){const n=Number(ex);if(ex.trim()&&Number.isFinite(n)&&n>=1&&n<=5&&n*2===Math.round(n*2))state.exaggeration=n;else adjusted=true;}
  choice('surfaceSite', ['mars-jezero-fan', 'earth-utah', 'earth-atacama']);
  choice('visualLayer', ['elevation','slope']);
  choice('view', ['landing','unified','simulation', 'surface', 'compare', 'explore', 'sensitivity', 'dimensions', 'world']); choice('site', ['earth-utah', 'earth-atacama']);
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
  if (!q.has('method') && ['compare','dimensions','sensitivity','explore'].includes(state.view)) state.method='local';
  if (!q.has('explorePanel') && state.view==='surface' && state.surfaceSite!=='mars-jezero-fan') {state.explorePanel='controls';state.method='local';state.site=state.surfaceSite;}
  if (state.view==='world')state.method='atlas';
  if (state.regionalSite && !state.regionalSite.startsWith(state.area + '-') && state.regionalSite !== `control-${state.area}`) { state.regionalSite = ''; adjusted = true; }
  return { state, adjusted };
}
export function stateQuery(state: AtlasState) {
  const q = new URLSearchParams();
  for (const key of Object.keys(defaults) as (keyof AtlasState)[]) {
    const value = state[key] ?? defaults[key];
    if (value !== defaults[key]) q.set(key, String(value));
  }
  // Historical comparison links without a method refer to the local reviewed evidence.
  if(['compare','sensitivity'].includes(state.view))q.set('method',state.method);
  return q.size ? '?' + q.toString() : '';
}
function stateURL(state:AtlasState) {
  return `${window.location.pathname}${stateQuery(state)}`;
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
