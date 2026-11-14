import type { Metric, RegionalFeature, Sort } from '../domain/analysis';

export function sortFeatures(features: RegionalFeature[], sort: Sort) {
  const value = (feature: RegionalFeature) => sort === 'slope_distance' ? feature.properties.metric.slope_wasserstein_deg : Math.abs(feature.properties.metric.candidate_minus_reference_relief_m ?? NaN);
  return [...features].sort((a, b) => {
    if (a.properties.passes_filter !== b.properties.passes_filter) return a.properties.passes_filter ? -1 : 1;
    const av = value(a), bv = value(b);
    const an = av == null || !Number.isFinite(av), bn = bv == null || !Number.isFinite(bv);
    if (an !== bn) return an ? 1 : -1;
    return (!an && !bn ? av! - bv! : 0) || a.properties.id.localeCompare(b.properties.id);
  });
}
export function comparisonFinding(name: string, candidate: Metric, reference: Metric, closest: boolean) {
  const relief = candidate.relief_p95_p5_m, base = reference.relief_p95_p5_m;
  const part = relief == null || base == null ? 'Su relieve falta por evaluar.' : base === 0 ? `Relieve de ${relief.toLocaleString('es', { maximumFractionDigits: 1 })} m; referencia de 0 m.` : relief / base > .45 && relief / base < .55 ? 'Su relieve es aproximadamente la mitad del de Jezero.' : `Su relieve es ${relief > base ? 'mayor' : relief < base ? 'menor' : 'igual'} que el de Jezero.`;
  return `${name}: ${closest ? 'pendientes más cercanas a Jezero entre estas dos candidatas' : 'pendientes más distintas de Jezero que la otra candidata'}. ${part}`;
}
