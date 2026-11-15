/**
 * Análogos en Nicaragua: lectura del precálculo `analysis/nicaragua/analogos-nicaragua-v1.json`
 * (generado por `scripts/analogos_nicaragua.py compute`) y la lógica de ranking de la vista.
 * Todo es puro para poder probarlo sin navegador.
 */

export type Scope = 'volcanic' | 'all';
/** Interface language (same values as `i18n/lang`; kept local so this module stays import-free). */
export type Lang = 'es' | 'en';

export type Volcano = {
  id: string; name: string; longitude: number; latitude: number; type: string | null;
  last_eruption_year: number | null; rock: string | null; elevation_m: number | null; url: string;
};
export type Source = { citation: string; url: string };
export type KnownSite = {
  id: string; name: string; volcano_number: number | null; longitude: number; latitude: number;
  coordinates_source: string; analog_of: string; process: string; why: string; sources: string[];
  window_id: string | null; window_rankable: boolean;
};
export type ReferenceInfo = {
  id: string; name: string; body: 'Mars' | 'Moon' | 'Earth'; kind: 'planetary' | 'earth_analog';
  weights_effective: Record<string, number>; warnings: string[]; earth_windows_ranked: number;
  site_id?: string; window_id?: string; excluded_near_km?: number; excluded_windows?: number;
};
export type Ranking = {
  score: (number | null)[]; coverage: (number | null)[]; global_rank: (number | null)[];
};
export type NicaraguaData = {
  spec_id: string; generated_at: string;
  engine: { id: string; fitted_at: string; status: string; profile: string; earth_windows_ranked: number };
  method: { window_m: number; cell_m: number; volcanic_radius_km: number; dense_stride_m: number;
    self_exclusion_km: number; water_dominated_fraction: number; notes: string[] };
  boundary: { geometry: { type: 'Polygon' | 'MultiPolygon'; coordinates: number[][][] | number[][][][] };
    properties: { source: string; source_url: string; note: string } };
  volcanoes: { source: string; source_url: string; volcanoes: Volcano[] };
  known_sites: { sources: Record<string, Source>; sites: KnownSite[] };
  references: ReferenceInfo[];
  windows: { columns: string[]; rows: unknown[][] };
  rankings: Record<string, Ranking>;
};

export type Window = {
  index: number; region_id: string; source: 'atlas' | 'grid' | 'known_site' | 'volcano_summit';
  longitude: number; latitude: number; qa_status: string; eligibility: string | null;
  volcano_id: string | null; volcano_km: number | null; volcanic: boolean; water_dominated: boolean;
  relief_p95_p05_m: number | null; slope_240m_p50_deg: number | null; slope_240m_p90_deg: number | null;
  hypsometric_integral: number | null; trees_fraction: number | null; bare_or_sparse_fraction: number | null;
};

export type Scored = Window & {
  score: number; coverage: number | null;
  global_rank: number | null; rank: number; level: number;
};

export const DATA_URL = 'analysis/nicaragua/analogos-nicaragua-v1.json';
/** Rampa secuencial ámbar (validada sobre #1C1511): de menos a más parecido. */
export const LEVEL_COLORS = ['#6b4a2c', '#8f6234', '#b57d3b', '#da9a45', '#f7c071'] as const;
export const LEVEL_LABELS = ['Poco parecido', 'Algo parecido', 'Parecido medio', 'Bastante parecido', 'Muy parecido'] as const;
export const LEVEL_LABELS_EN = ['Barely similar', 'Somewhat similar', 'Moderately similar', 'Quite similar', 'Very similar'] as const;
export const levelLabel = (level: number, lang: Lang = 'es') => (lang === 'en' ? LEVEL_LABELS_EN : LEVEL_LABELS)[level];
/** Separación mínima entre lugares propuestos: las ventanas densas se solapan cada 2 km. */
export const DISCOVERY_SEPARATION_KM = 4;
/** Una propuesta a menos de esto de un sitio conocido es ese mismo sitio, no un hallazgo. */
export const KNOWN_RADIUS_KM = 3;

export function decodeWindows(data: NicaraguaData): Window[] {
  const cols = data.windows.columns;
  return data.windows.rows.map((row, index) => {
    const w: Record<string, unknown> = { index };
    cols.forEach((c, i) => { w[c] = row[i]; });
    return w as Window;
  });
}

export function haversineKm(lon1: number, lat1: number, lon2: number, lat2: number): number {
  const r = Math.PI / 180, p1 = lat1 * r, p2 = lat2 * r, dp = p2 - p1, dl = (lon2 - lon1) * r;
  const a = Math.sin(dp / 2) ** 2 + Math.cos(p1) * Math.cos(p2) * Math.sin(dl / 2) ** 2;
  return 2 * 6371.0088 * Math.asin(Math.min(1, Math.sqrt(a)));
}

/** Ventanas con distancia para la referencia, en el ámbito elegido, de la más a la menos parecida. */
export function rankWindows(data: NicaraguaData, windows: Window[], referenceId: string, scope: Scope): Scored[] {
  const r = data.rankings[referenceId];
  if (!r) return [];
  const out: Omit<Scored, 'rank' | 'level'>[] = [];
  for (const w of windows) {
    const score = r.score[w.index];
    if (score == null || (scope === 'volcanic' && !w.volcanic)) continue;
    out.push({ ...w, score, coverage: r.coverage[w.index], global_rank: r.global_rank[w.index] });
  }
  out.sort((a, b) => a.score - b.score || a.region_id.localeCompare(b.region_id));
  const n = out.length;
  // Nivel por quintil dentro del ámbito: el color dice «más o menos parecido que el resto de aquí».
  return out.map((w, i) => ({ ...w, rank: i + 1, level: n <= 1 ? 4 : 4 - Math.min(4, Math.floor((i / n) * 5)) }));
}

/** Sitio conocido más cercano a una ventana, si está a `KNOWN_RADIUS_KM` o menos. */
export function nearKnown(w: { longitude: number; latitude: number }, sites: KnownSite[]): KnownSite | undefined {
  let best: KnownSite | undefined, bestKm = Infinity;
  for (const s of sites) {
    const d = haversineKm(w.longitude, w.latitude, s.longitude, s.latitude);
    if (d < bestKm) { best = s; bestKm = d; }
  }
  return bestKm <= KNOWN_RADIUS_KM ? best : undefined;
}

/**
 * Lugares propuestos: las ventanas mejor clasificadas que no son un sitio conocido, separadas al menos
 * `DISCOVERY_SEPARATION_KM` entre sí para que un mismo cono no ocupe toda la lista.
 */
export function discoveries(ranked: Scored[], sites: KnownSite[], limit = 12): Scored[] {
  const out: Scored[] = [];
  for (const w of ranked) {
    if (out.length >= limit) break;
    if (nearKnown(w, sites)) continue;
    if (out.some(o => haversineKm(o.longitude, o.latitude, w.longitude, w.latitude) < DISCOVERY_SEPARATION_KM)) continue;
    out.push(w);
  }
  return out;
}

/** «Top 0,4 %» del puesto mundial entre todas las ventanas clasificables de la Tierra. */
export function worldShare(globalRank: number | null, total: number, lang: Lang = 'es'): string {
  if (globalRank == null || !total) return lang === 'en' ? 'no world rank' : 'sin puesto mundial';
  const pct = (globalRank / total) * 100;
  const text = pct < 1 ? pct.toLocaleString(lang, { maximumFractionDigits: 2 }) : pct.toLocaleString(lang, { maximumFractionDigits: 0 });
  return lang === 'en' ? `top ${text}% of Earth` : `top ${text} % de la Tierra`;
}

const COVER: Record<string, string> = {
  excluded_dense_canopy: 'Bosque denso',
  excluded_vegetated_non_tree: 'Vegetación baja o cultivos',
  excluded_permanent_water: 'Agua permanente',
  excluded_built: 'Zona urbana',
  excluded_snow_ice: 'Nieve o hielo',
  excluded_insufficient_land: 'Poca tierra firme',
  excluded_warm_climate: 'Clima cálido',
  eligible_arid_exposed: 'Suelo árido expuesto',
};
const COVER_EN: Record<string, string> = {
  excluded_dense_canopy: 'Dense forest',
  excluded_vegetated_non_tree: 'Low vegetation or crops',
  excluded_permanent_water: 'Permanent water',
  excluded_built: 'Urban area',
  excluded_snow_ice: 'Snow or ice',
  excluded_insufficient_land: 'Little dry land',
  excluded_warm_climate: 'Warm climate',
  eligible_arid_exposed: 'Exposed arid ground',
};

/** Cobertura en palabras: la etiqueta del filtro árido y el porcentaje de suelo desnudo. */
export function coverText(w: Window, lang: Lang = 'es'): string {
  const en = lang === 'en';
  const label = w.eligibility ? (en ? COVER_EN : COVER)[w.eligibility] ?? w.eligibility.replace(/_/g, ' ') : en ? 'No land-cover data' : 'Sin dato de cobertura';
  const bare = w.bare_or_sparse_fraction;
  return bare == null ? label : en ? `${label} · ${Math.round(bare * 100)}% bare ground` : `${label} · ${Math.round(bare * 100)} % suelo desnudo`;
}

/** Nombres del GVP (sin tildes, en orden de catálogo) tal como se escriben en Nicaragua. */
const VOLCANO_NAMES: Record<string, string> = {
  Cosiguina: 'Cosigüina', 'San Cristobal': 'San Cristóbal', 'Negro, Cerro': 'Cerro Negro',
  'Las Pilas-El Hoyo Complex': 'Las Pilas-El Hoyo', Concepcion: 'Concepción',
};
export const displayVolcano = (name: string) => VOLCANO_NAMES[name] ?? name;

export function volcanoName(data: NicaraguaData, id: string | null): string | undefined {
  const name = id ? data.volcanoes.volcanoes.find(v => v.id === id)?.name : undefined;
  return name && displayVolcano(name);
}

/** Nombre corto de una referencia para selectores y frases. */
const REFERENCE_NAMES: Record<string, string> = {
  jezero: 'Jezero, delta de un antiguo río (Marte)',
  'haworth-fondo': 'Haworth, fondo de un cráter polar (Luna)',
  'de-gerlache-cresta': 'De Gerlache, cresta polar (Luna)',
};
const REFERENCE_NAMES_EN: Record<string, string> = {
  jezero: 'Jezero, delta of an ancient river (Mars)',
  'haworth-fondo': 'Haworth, floor of a polar crater (Moon)',
  'de-gerlache-cresta': 'De Gerlache, polar ridge (Moon)',
};
/** Earth analogues are named after their site («Relieve parecido a Cerro Negro»). */
export function referenceName(r: ReferenceInfo, lang: Lang = 'es', siteName?: string): string {
  if (lang !== 'en') return REFERENCE_NAMES[r.id] ?? r.name;
  if (REFERENCE_NAMES_EN[r.id]) return REFERENCE_NAMES_EN[r.id];
  const site = siteName ?? /^Relieve parecido a (.+)$/.exec(r.name)?.[1];
  return site ? `Relief similar to ${site}` : r.name;
}

export function placeText(data: NicaraguaData, w: Window, lang: Lang = 'es'): string {
  const v = volcanoName(data, w.volcano_id);
  const en = lang === 'en';
  if (!v || w.volcano_km == null) return `${w.latitude.toFixed(3)}° N, ${Math.abs(w.longitude).toFixed(3)}° ${en ? 'W' : 'O'}`;
  const km = w.volcano_km.toLocaleString(lang, { maximumFractionDigits: 1 });
  if (en) return w.volcano_km < 1.5 ? `Summit of ${v}` : `${km} km from ${v}`;
  return w.volcano_km < 1.5 ? `Cumbre de ${v}` : `A ${km} km de ${v}`;
}

export function defaultReference(data: NicaraguaData): string {
  return data.references.find(r => r.id === 'jezero')?.id ?? data.references[0]?.id ?? '';
}

export const BODY_TEXT = { Mars: 'Marte', Moon: 'Luna', Earth: 'Tierra' } as const;
