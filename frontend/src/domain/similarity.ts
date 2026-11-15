/** Types and pure helpers of the similarity search (`/api/similarity`, contract `motor-busqueda-v1`). */
import { getLang, localized, tr } from '../i18n/lang';

export type ViewId = 'escabrosidad' | 'forma_hipsometrica' | 'organizacion' | 'regimen_morfologico'
  | 'espectral' | 'termica' | 'radar' | 'entorno_superficial' | 'emisividad_cmg';
export type Body = 'Mars' | 'Moon';
export type ViewStatus = 'reference_has_data' | 'reference_missing' | 'not_fitted';
export type Fusion = 'weighted' | 'rrf';
export type MissingPolicy = 'neutral' | 'renormalize' | 'require';
export type Profile = 'arid_mars_surface_v2' | 'paleolake_margin_v1' | 'polar_cold_v1';

export type ReferenceEntry = {
  id: string; name: string; body: Body; available: boolean; reason?: string;
  kind: 'landing_site' | 'base_candidate' | 'control' | null; status: string | null;
  center: { longitude: number; latitude: number } | null; sources: string[]; limitations: string[];
  views: Record<string, ViewStatus>; source?: string | null;
};
export type ReferenceCatalog = {
  references: ReferenceEntry[]; default_weights: Record<Body, Record<string, number>>;
  views: Record<string, { fitted: boolean; kind: string }>; engine_status: string;
};
export type FeatureExplanation = { candidate: number; reference: number | null; z_delta: number; share: number };
export type ResultView = {
  distance: number | null; weight: number; available: boolean; pool_percentile?: number;
  features?: Record<string, FeatureExplanation>;
};
export type SearchResult = {
  rank: number; region_id: string; longitude: number; latitude: number; utm_zone_band: string;
  scenario_eligibility: string; score: number; score_low: number; score_high: number; coverage: number;
  missing_views: string[]; views: Record<string, ResultView>;
};
export type SearchResponse = {
  query_id: string; status: string; model_fitted_at: string; warnings: string[]; candidates_in_pool: number;
  candidates_ranked: number; weights_effective: Record<string, number>; results: SearchResult[];
  reference: { id: string; name: string; body: string };
  views: Record<string, { status: string; weight: number; coverage_fraction?: number }>;
  timings: { engine_ms: number; total_ms: number; cache_hit: boolean };
};
export type SearchRequest = {
  reference: string; weights?: Record<string, number>; only_eligible: boolean; limit: number;
  fusion: Fusion; missing_policy: MissingPolicy; profile?: Profile;
};
export type Controls = {
  weights: Record<string, number>; touched: boolean; onlyEligible: boolean; fusion: Fusion;
  missingPolicy: MissingPolicy; limit: number; profile?: Profile;
};

export const VIEW_LABELS: Record<string, string> = localized({
  escabrosidad: ['Escabrosidad', 'Ruggedness'], forma_hipsometrica: ['Forma hipsométrica', 'Hypsometric shape'],
  organizacion: ['Organización', 'Organisation'], regimen_morfologico: ['Régimen morfológico', 'Morphological regime'],
  espectral: ['Espectral', 'Spectral'], termica: ['Térmica', 'Thermal'], radar: ['Radar', 'Radar'],
  entorno_superficial: ['Entorno superficial', 'Surface setting'], emisividad_cmg: ['Emisividad', 'Emissivity'],
});
export const KIND_LABELS: Record<string, string> = localized({
  landing_site: ['Sitio de aterrizaje', 'Landing site'], base_candidate: ['Candidata de base', 'Base candidate'],
  control: ['Sitio de contraste', 'Control site'],
});
export const BODY_LABELS: Record<Body, string> = localized({ Mars: ['Marte', 'Mars'], Moon: ['Luna', 'Moon'] });
export const STATUS_TEXT: Record<ViewStatus, string> = localized({
  reference_has_data: ['con datos de la referencia', 'the reference has data'],
  reference_missing: ['la referencia no tiene estos datos', 'the reference has no such data'],
  not_fitted: ['sin ajustar en el motor', 'not fitted in the engine'],
});
export const PROFILE_LABELS: Record<Profile, string> = localized({
  arid_mars_surface_v2: ['Suelo árido expuesto', 'Exposed arid ground'],
  paleolake_margin_v1: ['Margen de paleolago', 'Palaeolake margin'], polar_cold_v1: ['Polar frío', 'Cold polar'],
});
export const FUSION_LABELS: Record<Fusion, string> = localized({
  weighted: ['Media ponderada de distancias', 'Weighted mean of distances'], rrf: ['Fusión por rangos (RRF)', 'Rank fusion (RRF)'],
});
export const MISSING_LABELS: Record<MissingPolicy, string> = localized({
  neutral: ['Neutral: la vista ausente cuenta como una candidata típica', 'Neutral: a missing view counts as a typical candidate'],
  renormalize: ['Repartir el peso entre las vistas presentes', 'Spread the weight over the views present'],
  require: ['Descartar candidatas con vistas ausentes', 'Drop candidates with missing views'],
});
export const SEARCH_LIMIT = 25;

/** Views the engine can use for this reference: fitted and measured on the reference. */
export function usableViews(reference: ReferenceEntry | undefined): string[] {
  return reference ? Object.entries(reference.views).filter(([, s]) => s === 'reference_has_data').map(([v]) => v) : [];
}

export function defaultControls(reference: ReferenceEntry | undefined, catalog: ReferenceCatalog | undefined): Controls {
  const defaults = reference && catalog ? catalog.default_weights[reference.body] ?? {} : {};
  return { weights: { ...defaults }, touched: false, onlyEligible: true, fusion: 'weighted', missingPolicy: 'neutral', limit: SEARCH_LIMIT };
}

/** The request for these controls. Untouched weights are omitted so the server applies its own defaults. */
export function buildRequest(referenceId: string, controls: Controls): SearchRequest {
  const request: SearchRequest = { reference: referenceId, only_eligible: controls.onlyEligible, limit: controls.limit,
    fusion: controls.fusion, missing_policy: controls.missingPolicy };
  if (controls.profile) request.profile = controls.profile;
  if (controls.touched) request.weights = Object.fromEntries(Object.entries(controls.weights).map(([v, w]) => [v, round(w)]));
  return request;
}

const round = (value: number) => Math.round(value * 1000) / 1000;
export const requestKey = (request: SearchRequest) => JSON.stringify(request);

/** True when every view the engine could use has weight zero: the search would be refused. */
export function noWeight(request: SearchRequest, usable: string[]): boolean {
  if (!request.weights) return false;
  const w = request.weights;
  return usable.length > 0 && usable.every(v => !(w[v] > 0)) && Object.values(w).every(x => !(x > 0));
}

/** FastAPI returns `detail` as text, or as a list of validation errors. */
export function errorMessage(detail: unknown, status: number): string {
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    const text = detail.map(item => typeof item?.msg === 'string' ? item.msg : '').filter(Boolean).join('; ');
    if (text) return text;
  }
  if (status === 503) return tr('El motor de similitud no está disponible en este servidor.', 'The similarity engine is not available on this server.');
  return tr('No se pudo completar la búsqueda.', 'The search could not be completed.');
}

/** Largest contributions of the reference-to-candidate difference in a view, as readable lines. */
export function topFeatures(view: ResultView | undefined, count = 3): [string, FeatureExplanation][] {
  return Object.entries(view?.features ?? {}).sort(([, a], [, b]) => Math.abs(b.share) - Math.abs(a.share)).slice(0, count);
}

/** Similarity shown to the public: 1 − distance, the same definition everywhere in the interface. */
export function similarity(score: number) {
  return Math.min(1, Math.max(0, 1 - score));
}

export function scoreWidth(low: number, high: number) {
  const clamp = (x: number) => Math.min(1, Math.max(0, x));
  return { left: clamp(low) * 100, width: Math.max(0.5, (clamp(high) - clamp(low)) * 100) };
}

export function placeLabel(latitude: number, longitude: number) {
  const lang = getLang();
  const f = (v: number) => Math.abs(v).toLocaleString(lang, { maximumFractionDigits: 3 });
  return `${f(latitude)}° ${latitude >= 0 ? 'N' : 'S'}, ${f(longitude)}° ${longitude >= 0 ? 'E' : lang === 'en' ? 'W' : 'O'}`;
}
