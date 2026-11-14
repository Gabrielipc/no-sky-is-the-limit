export type MineralClass = { id: number; name: string; label: string; sample: string; group: number; library: string };
export type MineralGroup = {
  ids: (number | null)[]; depth: (number | null)[]; fit: (number | null)[]; uncertainty: (number | null)[];
  usable: boolean[]; data_cells: number; matched_cells: number; no_match_cells: number; classes: MineralClass[];
};
export type MineralAudit = { product_id: string; date: string; footprint_cells: number; available_classification_cells: number; selected: boolean; groups: Record<string, { data_cells: number; matched_cells: number; no_match_cells: number }> };
export type MineralData = {
  candidate: { id: string; name: string; status: string; window_m: number;
    grid: { product_id: string; date: string; rows: number; columns: number; inside: boolean[]; footprint_cells: number; glt_cells: number; unique_raw_samples: number; bounds: number[]; groups: Record<string, MineralGroup>; sources: { input: string; sha256: string; bytes: number; url: string; role: string }[] };
    slope_deg: (number | null)[]; slope_source: { cell_m: number; resampling: string }; scene_audits: MineralAudit[] };
  release_id: string; window_m: number; quality_note: string; documentation: string; limitations: string[];
  mars: { status: string; name: string; reason: string; documentation: string };
  evidence: Record<string, string>;
};
export type MineralLayer = 'minerals' | 'fit' | 'uncertainty' | 'slope';

/** Fractions always use all in-window GLT cells; filters never change the denominator. */
export function mineralSelection(group: MineralGroup, inside: boolean[], slopes: (number | null)[], minFit: number, maxSlope: number | null) {
  const accepted = group.ids.map((id, i) => inside[i] && id != null && id > 0 && group.usable[i]
    && (minFit === 0 || (group.fit[i] != null && group.fit[i]! >= minFit))
    && (maxSlope === null || (slopes[i] != null && slopes[i]! <= maxSlope)));
  const total = inside.filter(Boolean).length;
  const counts = group.classes.map(c => ({ ...c, cells: group.ids.reduce<number>((count, id, i) => count + (accepted[i] && id === c.id ? 1 : 0), 0) }))
    .map(c => ({ ...c, fraction: total ? c.cells / total : 0 })).sort((a, b) => b.cells - a.cells || a.id - b.id);
  return { accepted, counts, total, acceptedCount: accepted.filter(Boolean).length };
}
export function mineralColor(id: number) { return `hsl(${(id * 137.508) % 360} 50% 62%)`; }

export const crismLayers = ['OLINDEX3', 'BD530_2', 'D2300', 'MIN2295_2480', 'BD1900R2', 'atm_residual', 'coverage'] as const;
export type CrismLayer = typeof crismLayers[number];
export type CrismData = {
  observation_id: string;
  date: string;
  documentation: string;
  grid: { rows: number; columns: number; step_m: [number, number]; inside: boolean[]; mask: (0 | 1 | null)[] };
  coverage: { total: number; supported: number; excluded: number; missing: number };
  layers: {
    id: Exclude<CrismLayer, 'coverage'>;
    label: string;
    description: string;
    valid_cells: number;
    p02: number | null;
    median: number | null;
    p98: number | null;
    values: (number | null)[];
  }[];
  evidence: Record<string, string>;
};
