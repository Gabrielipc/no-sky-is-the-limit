import { fmt, type Metric } from '../../domain/analysis';
import { useElementWidth } from '../../components/useElementWidth';
export function ScaleChart({ metrics, kind, selected, onSelect }: { metrics: Metric[]; kind: 'slope' | 'relief'; selected: number; onSelect: (cell: number) => void }) {
  const get = (m: Metric) => kind === 'slope' ? m.slope_wasserstein_deg : m.candidate_minus_reference_relief_m;
  const points = metrics.filter(m => get(m) != null), values = points.map(m => get(m)!);
  const low = Math.min(0, ...values), high = Math.max(0, ...values), span = high - low || 1;
  const { ref, width } = useElementWidth(520);
  const x = (cell: number) => 35 + (cell - 60) / 540 * (width - 70), y = (value: number) => 143 - (value - low) / span * 100;
  return <section className="metric-panel scale-chart-panel"><p className="eyebrow">{kind === 'slope' ? 'PENDIENTES' : 'RELIEVE'}</p><h3>{kind === 'slope' ? 'Diferencia de pendientes a Jezero' : 'Diferencia de relieve a Jezero'}</h3>
    {points.length ? <svg ref={ref} viewBox={`0 0 ${width} 195`} className="scale-chart" role="group" aria-label={`${kind === 'slope' ? 'Pendientes en grados' : 'Relieve en metros'} por tamaño de celda, SRTM frente a Jezero. Selecciona un punto para ver su valor.`}>
      <line x1="35" x2={width - 35} y1={y(0)} y2={y(0)} className="chart-grid" /><text x="20" y={y(0) + 4} textAnchor="end">0</text>
      <polyline points={points.map(m => `${x(m.cell_m)},${y(get(m)!)}`).join(' ')} fill="none" className="scale-trend" />
      {points.map(m => <g key={m.cell_m}>{(width > 420 || m.cell_m === selected) && <text x={x(m.cell_m)} y={Math.max(18, y(get(m)!) - 16)} textAnchor="middle">{fmt(get(m), kind === 'slope' ? '°' : ' m', 2, kind === 'relief')}</text>}<circle cx={x(m.cell_m)} cy={y(get(m)!)} r={m.cell_m === selected ? 7 : 5} className={m.cell_m === selected ? 'scale-dot selected-dot' : 'scale-dot'} role="button" tabIndex={0} aria-pressed={m.cell_m === selected} aria-label={`Celda ${m.cell_m} m: ${fmt(get(m), kind === 'slope' ? ' grados' : ' metros', 3)}`} onClick={() => onSelect(m.cell_m)} onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onSelect(m.cell_m); } }} /><text x={x(m.cell_m)} y="176" textAnchor="middle">{m.cell_m}</text></g>)}
      <text x={width / 2} y="194" textAnchor="middle">Tamaño de celda (m)</text></svg> : <p>Faltan datos para representar esta comparación.</p>}
    <p className="chart-caption">Puntos calculados a cuatro escalas. Las líneas solo guían la lectura.</p>
  </section>;
}
