/** Types and pure helpers of the similarity search (`/api/similarity`, contract `motor-busqueda-v1`). */

export type ViewId = 'escabrosidad' | 'forma_hipsometrica' | 'organizacion' | 'regimen_morfologico'
  | 'espectral' | 'termica' | 'radar' | 'entorno_superficial' | 'emisividad_cmg';
export type Body = 'Mars' | 'Moon';
export type ViewStatus = 'reference_has_data' | 'reference_missing' | 'not_fitted';
export type Fusion = 'weighted' | 'rrf';
export type MissingPolicy = 'neutral' | 'renormalize' | 'require';

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
  fusion: Fusion; missing_policy: MissingPolicy;
};
export type Controls = {
  weights: Record<string, number>; touched: boolean; onlyEligible: boolean; fusion: Fusion;
  missingPolicy: MissingPolicy; limit: number;
};

export const VIEW_LABELS: Record<string, string> = {
  escabrosidad: 'Escabrosidad', forma_hipsometrica: 'Forma hipsométrica', organizacion: 'Organización',
  regimen_morfologico: 'Régimen morfológico', espectral: 'Espectral', termica: 'Térmica', radar: 'Radar',
  entorno_superficial: 'Entorno superficial', emisividad_cmg: 'Emisividad',
};
export const KIND_LABELS: Record<string, string> = {
  landing_site: 'Sitio de aterrizaje', base_candidate: 'Candidata de base', control: 'Sitio de contraste',
};
export const BODY_LABELS: Record<Body, string> = { Mars: 'Marte', Moon: 'Luna' };
export const STATUS_TEXT: Record<ViewStatus, string> = {
  reference_has_data: 'con datos de la referencia', reference_missing: 'la referencia no tiene estos datos',
  not_fitted: 'sin ajustar en el motor',
};
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
  if (status === 503) return 'El motor de similitud no está disponible en este servidor.';
  return 'No se pudo completar la búsqueda.';
}

/** Largest contributions of the reference-to-candidate difference in a view, as readable lines. */
export function topFeatures(view: ResultView | undefined, count = 3): [string, FeatureExplanation][] {
  return Object.entries(view?.features ?? {}).sort(([, a], [, b]) => Math.abs(b.share) - Math.abs(a.share)).slice(0, count);
}

export function scoreWidth(low: number, high: number) {
  const clamp = (x: number) => Math.min(1, Math.max(0, x));
  return { left: clamp(low) * 100, width: Math.max(0.5, (clamp(high) - clamp(low)) * 100) };
}

export function placeLabel(latitude: number, longitude: number) {
  const f = (v: number) => Math.abs(v).toLocaleString('es', { maximumFractionDigits: 3 });
  return `${f(latitude)}° ${latitude >= 0 ? 'N' : 'S'}, ${f(longitude)}° ${longitude >= 0 ? 'E' : 'O'}`;
}
