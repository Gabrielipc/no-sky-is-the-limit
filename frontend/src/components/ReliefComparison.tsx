import { fmt } from '../domain/analysis';
export function ReliefComparison({ reference, candidate, name, difference }: { reference: number | null; candidate: number | null; name: string; difference?: number | null }) {
  const max = Math.max(reference ?? 0, candidate ?? 0, 1) * 1.12;
  return <section className="metric-panel"><div className="metric-heading"><div><p className="eyebrow">RELIEVE</p><h3>¿Cuánto varía la altura?</h3></div><div className="metric-value">{fmt(difference, ' m', 1, true)}<small>{name} − Jezero</small></div></div>
    <div className="relief-bars" role="img" aria-label={`Relieve relativo: Jezero ${fmt(reference, ' metros')}; ${name} ${fmt(candidate, ' metros')}. Barras desde cero, misma escala.`}>
      {[{ name: 'Jezero', value: reference, className: 'reference' }, { name, value: candidate, className: 'candidate' }].map(row => <div className="relief-row" key={row.className}><span>{row.name}</span><div className="relief-track"><div className={`${row.className}-fill`} style={{ width: `${(row.value ?? 0) / max * 100}%` }} /></div><strong>{fmt(row.value, ' m')}</strong></div>)}
      <div className="relief-axis"><span>0 m</span><span>{fmt(max, ' m')}</span></div>
    </div><p className="chart-caption">Altura alta − altura baja, dejando fuera el 5 % de cada extremo (p95−p5).</p>
  </section>;
}
