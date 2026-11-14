import { useId, useState } from 'react';
import type { AtlasState } from '../../app/useAtlasState';
import { useResource } from '../../data/api';
import { fmt, percent } from '../../domain/analysis';
import { mineralColor, mineralSelection, type MineralData, type MineralLayer } from '../../domain/minerals';
import { RequestState } from '../../components/EvidenceStatus';
import { EvidenceLinks, MethodDrawer } from '../../components/MethodDrawer';
import { JezeroPanel } from './JezeroPanel';
import './minerals.css';

export function MineralPanel({ state, update }: { state: AtlasState; update: (patch: Partial<AtlasState>) => void }) {
  const resource = useResource<MineralData>(`/api/minerals?candidate_id=${state.site}`);
  return <section className="minerals-panel" aria-label="Mapas de Marte y Tierra">
    <div className="mineral-layout">
      <JezeroPanel layer={state.crismLayer} onLayer={crismLayer => update({ crismLayer })} />
      <div className="mineral-earth">
        <RequestState {...resource} />
        {resource.data && <MineralView key={state.site + ':' + state.mineralGroup} data={resource.data} state={state} update={update} />}
      </div>
    </div>
  </section>;
}

function MineralView({ data, state, update }: { data: MineralData; state: AtlasState; update: (patch: Partial<AtlasState>) => void }) {
  const [index, setIndex] = useState<number | null>(null);
  const patternId = 'mineral-missing-' + useId().replace(/:/g, '');
  const site = data.candidate, grid = site.grid, group = grid.groups[String(state.mineralGroup)];
  const selection = mineralSelection(group, grid.inside, site.slope_deg, state.mineralFit, state.mineralMaxSlope === 90 ? null : state.mineralMaxSlope);
  const selectedClass = group.classes.find(c => c.id === state.mineralId);
  const selectedCount = selection.counts.find(c => c.id === state.mineralId)?.cells ?? 0;
  const currentClass = index === null ? undefined : group.classes.find(c => c.id === group.ids[index]);
  const uncertaintyMax = .05;
  const [west, south, east, north] = grid.bounds;
  const aspect = (east - west) * Math.cos((south + north) / 2 * Math.PI / 180) / (north - south);
  function fill(i: number) {
    if (!grid.inside[i]) return 'transparent';
    if (group.ids[i] === null) return `url(#${patternId})`;
    if (group.ids[i] === 0) return 'var(--surface-raised)';
    if (!selection.accepted[i]) return 'var(--mineral-filtered)';
    if (state.mineralLayer === 'minerals') return mineralColor(group.ids[i]!);
    const value = state.mineralLayer === 'fit' ? group.fit[i] : state.mineralLayer === 'uncertainty' ? group.uncertainty[i] : site.slope_deg[i];
    if (value === null) return `url(#${patternId})`;
    const max = state.mineralLayer === 'fit' ? 1 : state.mineralLayer === 'uncertainty' ? uncertaintyMax : 25;
    const t = Math.max(0, Math.min(1, value / max));
    return state.mineralLayer === 'uncertainty' ? `hsl(${150 - 120 * t} 45% ${30 + t * 40}%)` : `hsl(${210 - 100 * t} ${45 + t * 15}% ${25 + t * 55}%)`;
  }
  function selectCell(i: number, selectMineral = false) {
    setIndex(i);
    if (selectMineral && group.ids[i] != null && group.ids[i]! > 0) update({ mineralId: group.ids[i]! });
  }
  function cellText() {
    if (index === null) return 'Pulsa una celda para ver su identificación y calidad. Las flechas permiten recorrer el mapa.';
    if (!grid.inside[index]) return 'Esta celda queda fuera de la ventana de análisis.';
    if (group.ids[index] === null) return 'Sin dato mineral válido en esta celda; no equivale a ausencia de minerales.';
    if (group.ids[index] === 0) return 'Sin coincidencia espectral en este grupo. Hay dato, pero no se identificó una entrada de biblioteca.';
    return `${currentClass?.label ?? 'Identificación'} · ajuste R² ${fmt(group.fit[index], '', 3)} · incertidumbre ${fmt(group.uncertainty[index], '', 5)} · inclinación ${fmt(site.slope_deg[index], '°')}${selection.accepted[index] ? '' : ' · Fuera de los filtros activos'}`;
  }
  return <>
    <section className="mineral-map-panel">
      <div className="mineral-map-title"><h2>{site.name}</h2><span>Tierra · EMIT · {grid.date.slice(0, 10)}</span></div>
      <label className="select-field mineral-map-select">Grupo espectral<select value={state.mineralGroup} onChange={e => update({ mineralGroup: Number(e.target.value) as 1 | 2, mineralId: 0 })}><option value="1">Grupo 1 · región espectral visible/infrarroja</option><option value="2">Grupo 2 · otra región del espectro</option></select></label>
      <svg className="mineral-map" style={{ aspectRatio: aspect }} viewBox={`0 0 ${grid.columns} ${grid.rows}`} preserveAspectRatio="none" role="img" tabIndex={0} aria-label={`Mapa mineral de ${site.name}, grupo ${state.mineralGroup}. ${selection.acceptedCount} celdas pasan los filtros de ${selection.total} dentro de la ventana. Flechas para recorrer, Enter para seleccionar un mineral.`}
        onPointerUp={e => { const box = e.currentTarget.getBoundingClientRect(); const col = Math.max(0, Math.min(grid.columns - 1, Math.floor((e.clientX - box.left) / box.width * grid.columns))); const row = Math.max(0, Math.min(grid.rows - 1, Math.floor((e.clientY - box.top) / box.height * grid.rows))); selectCell(row * grid.columns + col, true); }}
        onKeyDown={e => { const step = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -grid.columns, ArrowDown: grid.columns }[e.key]; if (step !== undefined) { e.preventDefault(); selectCell(Math.max(0, Math.min(grid.inside.length - 1, (index ?? 0) + step))); } else if (e.key === 'Enter' && index !== null) { e.preventDefault(); selectCell(index, true); } }}>
        <defs><pattern id={patternId} patternUnits="userSpaceOnUse" width="1" height="1"><rect width="1" height="1" fill="var(--nodata)" /><path d="M0,0 L1,1" stroke="var(--bg)" strokeWidth=".15" /></pattern></defs>
        {grid.inside.map((_, i) => <rect key={i} x={i % grid.columns} y={Math.floor(i / grid.columns)} width="1" height="1" fill={fill(i)} opacity={state.mineralId && selection.accepted[i] && group.ids[i] !== state.mineralId ? .18 : 1} />)}
        {index !== null && <rect x={index % grid.columns} y={Math.floor(index / grid.columns)} width="1" height="1" fill="none" stroke="var(--text)" strokeWidth=".15" />}
      </svg><div className="terrain-meta"><span>↑ N · cuadrícula geográfica nativa</span><span>Sin interpolar códigos minerales</span></div>
      <div className="mineral-legend">{state.mineralLayer !== 'minerals' && <><span>0{state.mineralLayer === 'slope' ? '°' : ''}</span><i className={`mineral-ramp ${state.mineralLayer === 'uncertainty' ? 'uncertainty' : ''}`} /><span>{state.mineralLayer === 'fit' ? '1 R²' : state.mineralLayer === 'uncertainty' ? '≥0,05' : '≥25°'}</span></>}<span><i className="mineral-key missing" />Sin dato</span><span><i className="mineral-key no-match" />Sin coincidencia</span><span><i className="mineral-key filtered" />Fuera del filtro</span></div>
      <p className="mineral-inspection" aria-live="polite">{cellText()}</p>{currentClass && <p className="dimension-note">Entrada {currentClass.id}: {currentClass.name}<br />Espectro de biblioteca: {currentClass.sample}</p>}
      <div className="mineral-layer-tools"><div className="segmented" role="group" aria-label="Capa del mapa mineral">{([{ id: 'minerals', name: 'Minerales' }, { id: 'fit', name: 'Ajuste' }, { id: 'uncertainty', name: 'Incertidumbre' }, { id: 'slope', name: 'Inclinación' }] as { id: MineralLayer; name: string }[]).map(layer => <button key={layer.id} aria-pressed={state.mineralLayer === layer.id} onClick={() => update({ mineralLayer: layer.id })}>{layer.name}</button>)}</div><button onClick={() => update({ mineralId: 0, mineralFit: 0, mineralMaxSlope: 90 })}>Ver todas las detecciones</button></div>
    <details className="mineral-filter-drawer"><summary>Filtrar detecciones · {state.mineralFit === 0 ? 'sin mínimo de ajuste' : `R² ≥ ${fmt(state.mineralFit, '', 2)}`}{state.mineralMaxSlope !== 90 ? ` · inclinación ≤ ${state.mineralMaxSlope}°` : ''}</summary><div className="mineral-controls">
      <div className="scale-control"><div className="control-label"><label htmlFor="mineral-fit">Ajuste mínimo de la detección (R²)</label><strong>{state.mineralFit === 0 ? 'Sin mínimo' : fmt(state.mineralFit, '', 2)}</strong></div><input id="mineral-fit" type="range" min="0" max="1" step="0.05" value={state.mineralFit} aria-valuetext={state.mineralFit === 0 ? 'Sin filtro mínimo de ajuste' : `R cuadrado mínimo ${state.mineralFit}`} onChange={e => update({ mineralFit: Number(e.target.value) })} /><div className="scale-stops" aria-hidden="true"><span>Sin mínimo</span><span>Mayor exigencia → 1</span></div><small>Es un filtro exploratorio; R² no es probabilidad de acierto.</small></div>
      <div className="scale-control"><label className="check-field"><input type="checkbox" checked={state.mineralMaxSlope !== 90} onChange={e => update({ mineralMaxSlope: e.target.checked ? 10 : 90 })} />Cruzar con la inclinación</label>{state.mineralMaxSlope !== 90 && <><div className="control-label"><label htmlFor="mineral-slope">Inclinación máxima</label><strong>{state.mineralMaxSlope}°</strong></div><input id="mineral-slope" type="range" min="0" max="25" step="1" value={Math.min(state.mineralMaxSlope, 25)} onChange={e => update({ mineralMaxSlope: Number(e.target.value) })} /><small>Inclinación derivada a 60 m; celdas sin inclinación quedan fuera.</small></>}</div></div></details>
    </section><section className="mineral-summary" aria-label="Resumen de detecciones"><h3>Identificaciones en esta ventana</h3><p className="dimension-note">Cada barra cuenta celdas del mapa, con los filtros activos. Porcentaje sobre las {selection.total} celdas de la ventana; no concentración química.</p><label className="select-field">Resaltar una identificación<select value={state.mineralId} onChange={e => update({ mineralId: Number(e.target.value) })}><option value="0">Todas las identificaciones</option>{state.mineralId !== 0 && !selectedClass && <option value={state.mineralId}>Entrada {state.mineralId} · sin detecciones en este grupo</option>}{group.classes.map(c => <option key={c.id} value={c.id}>{c.label}</option>)}</select></label>
      {selection.counts.filter(c => c.cells > 0).map(c => <button className="mineral-bar-row" key={c.id} aria-pressed={state.mineralId === c.id} onClick={() => update({ mineralId: state.mineralId === c.id ? 0 : c.id })}><span className="mineral-bar-label"><i style={{ background: mineralColor(c.id) }} /><strong>{c.label}</strong><span>{c.cells} · {percent(c.fraction)}</span></span><span className="mineral-bar-track"><span style={{ width: `${c.fraction * 100}%`, background: mineralColor(c.id) }} /></span></button>)}
      {selection.acceptedCount === 0 && <div className="empty-state"><h3>{group.matched_cells ? 'Ninguna detección pasa estos filtros' : 'Sin detecciones utilizables en este grupo'}</h3><p>{group.matched_cells ? 'Reduce el ajuste mínimo o desactiva el filtro de inclinación para revisar las detecciones originales.' : 'La ausencia de una detección no demuestra ausencia de minerales.'}</p></div>}
      <div className="mineral-counts" aria-live="polite"><strong>{state.mineralId ? selectedCount : selection.acceptedCount} / {selection.total}</strong><span>{state.mineralId ? 'celdas de la identificación resaltada' : 'celdas con detección que pasa los filtros'}</span><small>{group.no_match_cells} sin coincidencia · {selection.total - group.data_cells} sin dato mineral</small></div>
      <p className="dimension-note">Los dos grupos pueden detectar materiales en una misma celda. Sus porcentajes se leen por separado.</p>
    </section>
    <MethodDrawer title="Calidad, escenas examinadas y fuentes de minerales"><p>Se aplicó la tabla de geolocalización (GLT) del producto, con índices desde uno. Se conservaron la cuadrícula original y el polígono terrestre de 1,8 km. Cambiar la celda topográfica no crea más detalle mineral.</p><p>{grid.glt_cells} celdas tienen soporte GLT y remiten a {grid.unique_raw_samples} muestras originales únicas. Algunas celdas pueden repetir una muestra; no son observaciones independientes.</p><p>Incertidumbre: desviación estándar de la profundidad de banda, sin unidad. Ajuste: R² de la coincidencia con la biblioteca. No son porcentajes de composición ni probabilidad de identificación correcta.</p><div className="table-wrap"><table><caption>Escenas locales examinadas antes de aplicar filtros</caption><thead><tr><th>Producto</th><th>Fecha</th><th>Celdas con detección en algún grupo</th><th>Selección</th></tr></thead><tbody>{site.scene_audits.map(a => <tr key={a.product_id}><th>{a.product_id}</th><td>{a.date.slice(0, 10)}</td><td>{a.available_classification_cells}/{a.footprint_cells}</td><td>{a.selected ? 'Seleccionada por soporte disponible' : 'Conservada como control de cobertura'}</td></tr>)}</tbody></table></div>
      <ul>{data.limitations.map(l => <li key={l}>{l}</li>)}</ul><h3>Productos utilizados</h3>{grid.sources.map(source => <p key={source.role}><a href={source.url} target="_blank" rel="noreferrer">{source.input.split('/').pop()} ↗</a><br /><span className="hash">SHA-256 {source.sha256}</span></p>)}<a href={data.documentation} target="_blank" rel="noreferrer">Método y explicación oficial de EMIT ↗</a><EvidenceLinks links={data.evidence} /></MethodDrawer>
  </>;
}
