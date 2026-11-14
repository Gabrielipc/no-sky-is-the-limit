export type Profile = 'strict' | 'baseline' | 'relaxed';
export type Sort = 'slope_distance' | 'abs_relief_difference';
export type Layer = 'slope' | 'elevation';
export type Geometry = { type?: string; coordinates: number[][][] };
export type Area = { properties?: { side_m?: number }; geometry: Geometry };
export type Metric = {
  cell_m: number; cells: number; valid_elevation_cells: number; valid_slope_cells: number;
  elevation_coverage: number; slope_coverage: number; relief_p95_p5_m: number | null;
  slope_quantiles_deg?: { p10?: number | null; p50: number | null; p90?: number | null };
  slope_histogram_counts?: number[]; histogram_edges_deg?: number[];
  slope_wasserstein_deg?: number | null; candidate_minus_reference_relief_m?: number | null;
  filter_outcomes?: Record<Profile, string[]>;
};
export type Difference = { cell_m: number; slope_wasserstein_deg: number | null; candidate_minus_reference_relief_m: number | null };
export type Location = { id: string; name: string; body: string; latitude: number; longitude: number; radius_m?: number | null; area: Area; window_m: number };
export type Site = Omit<Location, 'window_m'> & {
  measurements: Metric; limitations: string[]; figures: { analysis: string; native: string };
  source: { product_id: string; url: string; version: string; sha256: string; bytes: number; vertical_reference: string; observation_dates: string[]; native_step_at_center_m: number[] };
};
export type Comparison = {
  case_id: string; evidence_identity: string; cell_m: number; reference: Site;
  candidates: { site: Site; comparison: Difference; sensitivity: Difference[] }[];
  method: Record<string, string>; limitations: string[]; not_evaluated: { id: string; name: string }[];
  evidence: Record<string, string>; orthoimage_figure: string;
};
export type TerrainGrid = { rows: number; columns: number; slope: (number | null)[]; elevation: (number | null)[]; bounds_m: number[] };
export type Terrain = { case_id: string; results_sha256: string; window_m: number; slope_range: [number, number]; height_range: [number, number]; sites: Record<string, Record<string, TerrainGrid>> };
export type RegionalRow = { id: string; name: string; latitude: number; longitude: number; evaluation_status: string; metric: Metric; filter_reasons: string[]; passes_filter: boolean };
export type RegionalFeature = { type: string; geometry: Geometry; properties: RegionalRow };
export type FeatureCollection = { features: RegionalFeature[] };
export type RegionalSummary = {
  config: { slope_histogram_edges_deg: number[]; window_m: number; stride_m: number; min_coverage: number; areas: { id: string; name: string; bbox: number[] }[]; controls: { id: string; name: string; latitude: number; longitude: number; area_id: string }[]; profiles: Record<Profile, { slope_distance_max_deg: number; abs_relief_difference_max_m: number }> };
  reference: { metrics: Metric[] };
  area_summaries: { area_id: string; bbox_geodesic_area_km2: number; sampled_window_area_km2: number; sampled_fraction: number }[];
  control_filter_outcomes: { id: string; name: string; outcomes: { cell_m: number; profile: Profile; reasons: string[] }[] }[];
  local_evaluations: string[]; limitations: string[]; documentation: { title: string; url: string }[];
};
export type RegionalDetail = Omit<Location, 'window_m'> & {
  metrics: Metric[]; detail_plan: { tiles: { filename: string; url: string }[] };
  local_detail: { evaluation_status: string; metrics: Metric[] | null; reference_metrics?: Metric[]; limitations?: string[] };
};
export type Contrast = { cell_m: number; status: string; candidate_source_wasserstein_deg: number | null; slope_distance_delta_deg: number | null; relief_difference_delta_m: number | null; filter_decisions: Record<Profile, { gmted_reasons: string[]; srtm_reasons: string[]; changed: boolean | null }> };
export type SensitivityCandidate = Omit<Location, 'body' | 'window_m'> & {
  area_id: string; selection: string; status: string; missing_tiles: string[]; regional_metrics: Metric[];
  local_metrics: Metric[] | null; source_contrasts: Contrast[] | null;
  inputs?: { file: string; sha256: string; url: string; vertical_reference: string }[];
};
export type ExpansionRelease = {
  candidates: SensitivityCandidate[]; reference: Location & { metrics: Metric[] };
  summary: { cell_m: number; profile: Profile; paired_count: number; changed_count: number }[];
  scenario: { name: string; question: string; selection_policy: string };
  limitations: string[]; method: Record<string, string>; evidence: Record<string, string>;
  strata: { area_id: string; decision: string; pool_count: number; locally_available_count: number; selected_ids: string[] }[];
  processing: { resources: { selected: number; evaluated: number; pending: number } };
};

export const profileNames: Record<Profile, string> = { strict: 'Estricto', baseline: 'Base', relaxed: 'Amplio' };
export const profiles: Profile[] = ['strict', 'baseline', 'relaxed'];
export const fmt = (n: number | null | undefined, unit = '', digits = 1, signed = false) => n == null ? 'Sin evaluar' : `${signed && n > 0 ? '+' : ''}${n.toLocaleString('es', { maximumFractionDigits: digits })}${unit}`;
export const percent = (fraction: number | null | undefined) => fmt(fraction == null ? null : fraction * 100, ' %', 2);
export const shortName = (name: string) => name.split(' — ')[0];
export const evaluationLabel = (status: string) => ['locally_evaluated_exploratory', 'evaluated_exploratory'].includes(status) ? 'Con evaluación local' : ['insufficient_detail_coverage'].includes(status) ? 'Cobertura local insuficiente' : 'Falta evaluación local';
export const reasonLabel = (reason: string) => ({ insufficient_coverage: 'Cobertura insuficiente', missing_measurements: 'Faltan medidas', slope_distance_above_threshold: 'Diferencia de pendientes por encima del límite', relief_difference_above_threshold: 'Diferencia de relieve por encima del límite' }[reason] ?? reason);
