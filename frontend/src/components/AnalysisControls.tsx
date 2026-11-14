import { useId } from 'react';
import { fmt, profileNames, profiles, type Profile } from '../domain/analysis';

export function ScaleControl({ values, value, onChange, label = 'Tamaño de celda', hint }: { values: number[]; value: number; onChange: (value: number) => void; label?: string; hint?: string }) {
  const id = useId();
  return <div className="scale-control"><div className="control-label"><label htmlFor={id}>{label}</label><strong>{value} m</strong></div>
    <input id={id} type="range" min="0" max={values.length - 1} step="1" value={Math.max(0, values.indexOf(value))} aria-valuetext={`${value} metros`} onChange={e => onChange(values[Number(e.target.value)])} />
    <div className="scale-stops" aria-hidden="true">{values.map(v => <span key={v}>{v} m</span>)}</div>
    <small>{hint ?? `La inclinación se mide sobre una base de ${value * 2} m.`}</small></div>;
}
export function ProfileControl({ value, onChange, thresholds }: { value: Profile; onChange: (value: Profile) => void; thresholds?: { slope_distance_max_deg: number; abs_relief_difference_max_m: number } }) {
  const id = useId();
  return <div className="scale-control"><div className="control-label"><label htmlFor={id}>Tolerancia del filtro</label><strong>{profileNames[value]}</strong></div>
    <input id={id} type="range" min="0" max="2" step="1" value={profiles.indexOf(value)} aria-valuetext={profileNames[value]} onChange={e => onChange(profiles[Number(e.target.value)])} />
    <div className="scale-stops" aria-hidden="true"><span>Estricto</span><span>Base</span><span>Amplio</span></div>
    {thresholds && <small>Pendientes ≤ {fmt(thresholds.slope_distance_max_deg, '°')} · diferencia de relieve ≤ {fmt(thresholds.abs_relief_difference_max_m, ' m')}</small>}</div>;
}
