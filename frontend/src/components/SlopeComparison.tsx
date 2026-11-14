import { useState } from 'react';
import { fmt, type Metric } from '../domain/analysis';
import { useElementWidth } from './useElementWidth';

/** Published histogram edges only; paths do not reconstruct raw samples. */
export function SlopeComparison({ reference, candidate, name, distance }: { reference: Metric; candidate: Metric; name: string; distance?: number | null }) {
  const [ceiling, setCeiling] = useState<30 | 90>(30);
  const { ref, width } = useElementWidth();
  const right = width - 18, plotWidth = right - 40;
  const hasData = [reference, candidate].every(m => m.valid_slope_cells > 0 && m.slope_histogram_counts && m.histogram_edges_deg);
  function path(m: Metric) {
    let cumulative = 0;
    const points = [[0, 0], ...m.slope_histogram_counts!.map((n, i) => { cumulative += n; return [m.histogram_edges_deg![i + 1], cumulative / m.valid_slope_cells]; })];
    // The right edge coincides with an existing published bin boundary.
    return points.filter(([x]) => x <= ceiling).map(([x, y], i) => `${i ? 'L' : 'M'}${40 + x / ceiling * plotWidth},${132 - y * 112}`).join(' ');
  }
  return <section className="metric-panel"><div className="metric-heading"><div><p className="eyebrow">INCLINACIÓN</p><h3>¿Se reparten igual las pendientes?</h3></div><div className="metric-value">{fmt(distance, '°', 2)}<small>de diferencia</small></div></div>
    {hasData ? <><div className="chart-controls"><small>Fracción de celdas con esta inclinación o menos</small><button className="quiet-button" onClick={() => setCeiling(ceiling === 30 ? 90 : 30)}>{ceiling === 30 ? 'Ver hasta 90°' : 'Ampliar 0–30°'}</button></div>
      <svg ref={ref} className="slope-chart" viewBox={`0 0 ${width} 164`} role="img" aria-label={`Distribución acumulada por intervalos: Jezero y ${name}. Menor distancia indica distribuciones más cercanas.`}>
        {[0, .5, 1].map(y => <g key={y}><line x1="40" x2={right} y1={132 - y * 112} y2={132 - y * 112} className="chart-grid" /><text x="32" y={136 - y * 112} textAnchor="end">{y * 100}%</text></g>)}
        {(ceiling === 30 ? [0, 10, 20, 30] : [0, 30, 60, 90]).map(x => <text key={x} x={40 + x / ceiling * plotWidth} y="155" textAnchor="middle">{x}°</text>)}
        <path d={path(reference)} className="reference-line" fill="none" /><path d={path(candidate)} className="candidate-line" fill="none" />
      </svg><div className="chart-legend"><span className="reference-key">━ Jezero</span><span className="candidate-key">┄ {name}</span><small>Curvas por intervalos</small></div></> : <p className="empty-state">No hay distribución disponible para esta ventana.</p>}
    <p className="chart-caption">Menor diferencia = distribuciones más cercanas. No compara dónde se sitúan las laderas.</p>
  </section>;
}
