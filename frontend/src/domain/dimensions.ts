import { fmt } from './analysis';

export function surfaceFmt(value: number | null | undefined, unit = '', digits = 2, signed = false) {
  if (value != null && value !== 0 && Math.abs(value) < 10 ** -digits) {
    return `${signed && value > 0 ? '+' : ''}${value.toLocaleString('es', { notation: 'scientific', maximumFractionDigits: 2 })}${unit}`;
  }
  return fmt(value, unit, digits, signed);
}

export type SurfaceMetric = 'roughness_rms' | 'topographic_position' | 'laplacian';
export type SurfaceSummary = {
  status: 'measured' | 'insufficient_quality'; valid_cells: number; total_cells: number; coverage: number;
  quantiles: { p10: number; p50: number; p90: number } | null;
};
export type SurfaceGrid = { rows: number; columns: number; values: (number | null)[] };
export type SurfaceSource = {
  id: string; name: string; body: string; status: string;
  urls: Record<string, string> | string[]; bytes?: number | null; authentication?: string;
  nominal_step_m?: number; limitations?: string[];
};
export type Thermal = {
  status: string; summary: SurfaceSummary | null; grid: SurfaceGrid | null; reason: string;
  native_step_projected_m?: number[]; spatial_assumption?: string;
  source: { product_id: string; url: string; units: string; license: string; sha256: string } | null;
};
export type SurfaceSite = {
  id: string; name: string; body: string;
  source: { product_id: string; url: string; sha256: string };
  scale: { cell_m: number; neighborhood_radius_m: number; neighborhood_width_samples: number;
    descriptors: Record<SurfaceMetric, SurfaceSummary>; grids: Record<SurfaceMetric, SurfaceGrid> };
  thermal: Thermal;
  pending_dimensions: { id: string; name: string; status: string; value: null; source_ids: string[]; reason: string }[];
};
export type SurfaceComparison = {
  cell_m: number; window_m: number; neighborhood_radius_m: number; min_coverage: number;
  reference: SurfaceSite; candidate: SurfaceSite;
  metrics: Record<SurfaceMetric, { name: string; unit: string; description: string }>;
  comparison: { metrics: Record<SurfaceMetric, { status: string; wasserstein: number | null; candidate_minus_reference_median: number | null }>;
    thermal: { status: string; reason: string; wasserstein: null } };
  sources: SurfaceSource[]; limitations: string[]; evidence: Record<string, string>;
};
