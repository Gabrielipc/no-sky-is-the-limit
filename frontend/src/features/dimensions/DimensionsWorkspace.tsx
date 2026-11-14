import { useState } from 'react';
import type { AtlasState } from '../../app/useAtlasState';
import { useResource } from '../../data/api';
import { percent, shortName } from '../../domain/analysis';
import { surfaceFmt as fmt } from '../../domain/dimensions';
import type { SurfaceComparison, SurfaceGrid, SurfaceMetric, SurfaceSource, SurfaceSummary, Thermal } from '../../domain/dimensions';
import { ScaleControl } from '../../components/AnalysisControls';
import { RequestState } from '../../components/EvidenceStatus';
import { EvidenceLinks, MethodDrawer } from '../../components/MethodDrawer';
import './dimensions.css';
import { MineralPanel } from './MineralPanel';

function range(grids: SurfaceGrid[], signed: boolean): [number, number] {
  const values = grids.flatMap(g => g.values).filter((n): n is number => n !== null);
  const min = values.length ? Math.min(...values) : 0;
  const max = values.length ? Math.max(...values) : 0;
  return signed ? [-Math.max(Math.abs(min), Math.abs(max), 1e-9), Math.max(Math.abs(min), Math.abs(max), 1e-9)] : [0, max || 1];
}
function color(value: number | null, extent: [number, number], signed: boolean) {
  if (value === null) return 'var(--nodata)';
  const t = Math.max(0, Math.min(1, (value - extent[0]) / (extent[1] - extent[0])));
  if (!signed) return `hsl(${155 - t * 100} ${30 + t * 35}% ${20 + t * 55}%)`;
  return t < .5 ? `hsl(210 45% ${30 + t * 110}%)` : `hsl(28 60% ${85 - (t - .5) * 110}%)`;
}
function Summary({ value, unit, digits }: { value: SurfaceSummary; unit: string; digits: number }) {
  return <dl className="dimension-summary"><div><dt>Mediana</dt><dd>{fmt(value.quantiles?.p50, ` ${unit}`, digits)}</dd></div><div><dt>p10 a p90</dt><dd>{fmt(value.quantiles?.p10, '', digits)} a {fmt(value.quantiles?.p90, ` ${unit}`, digits)}</dd></div><div><dt>Soporte válido</dt><dd>{percent(value.coverage)} <small>({value.valid_cells}/{value.total_cells})</small></dd></div></dl>;
}
function GridMap({ grid, extent, signed, name, unit, digits }: { grid: SurfaceGrid; extent: [number, number]; signed: boolean; name: string; unit: string; digits: number }) {
  const [index, setIndex] = useState(0);
  const selected = Math.min(index, grid.values.length - 1);
  const row = Math.floor(selected / grid.columns), col = selected % grid.columns;
  return <div className="dimension-map"><svg role="img" aria-label={`${name}. Mapa de valores; flechas para examinar celdas.`} tabIndex={0}
    viewBox={`0 0 ${grid.columns} ${grid.rows}`} style={{ aspectRatio: `${grid.columns}/${grid.rows}` }} onKeyDown={e => {
      const step = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -grid.columns, ArrowDown: grid.columns }[e.key];
      if (step !== undefined) { e.preventDefault(); setIndex(Math.max(0, Math.min(grid.values.length - 1, selected + step))); }
    }} onPointerMove={e => {
      const box = e.currentTarget.getBoundingClientRect();
      const c = Math.min(grid.columns - 1, Math.max(0, Math.floor((e.clientX - box.left) / box.width * grid.columns)));
      const r = Math.min(grid.rows - 1, Math.max(0, Math.floor((e.clientY - box.top) / box.height * grid.rows)));
      setIndex(r * grid.columns + c);
    }}>
    <title>{name}: escala {fmt(extent[0], ` ${unit}`, digits)} a {fmt(extent[1], ` ${unit}`, digits)}</title>
    {grid.values.map((value, i) => <rect key={i} x={i % grid.columns} y={Math.floor(i / grid.columns)} width={1} height={1} fill={color(value, extent, signed)} />)}
    <rect x={col} y={row} width={1} height={1} fill="none" stroke="white" strokeWidth={.12} />
  </svg><p className="dimension-inspection">Fila {row + 1}, columna {col + 1}: <strong>{grid.values[selected] === null ? 'Sin soporte' : fmt(grid.values[selected], ` ${unit}`, digits)}</strong></p></div>;
}
function ThermalPanel({ value, name }: { value: Thermal; name: string }) {
  return <article className="dimension-card"><div className="dimension-card-heading"><h3>{name}</h3><span className={`dimension-status ${value.status === 'measured' ? 'measured' : ''}`}>{value.status === 'measured' ? 'Medido en este lugar' : value.status === 'insufficient_quality' ? 'Soporte insuficiente' : 'Falta adquirir'}</span></div>
    {value.grid && value.summary && value.source ? <><GridMap grid={value.grid} extent={range([value.grid], false)} signed={false} name={`Inercia térmica de ${name}`} unit={value.source.units} digits={1} /><Summary value={value.summary} unit={value.source.units} digits={1} /><p className="dimension-note">Paso proyectado nativo: {value.native_step_projected_m?.join(' × ')} m. Esta capa conserva su cuadrícula al cambiar la escala topográfica.</p><a href={value.source.url} target="_blank" rel="noreferrer">Edwards y Buz (2021) · {value.source.license} ↗</a></> : <div className="dimension-empty"><span aria-hidden="true">◷</span><p>Inercia térmica sin medir</p><small>La ausencia no significa un valor cero.</small></div>}
    <p className="dimension-note">{value.reason}</p>
  </article>;
}
function sourceLink(source: SurfaceSource) {
  if (Array.isArray(source.urls)) return source.urls[0];
  return source.urls.portal ?? source.urls.catalog ?? source.urls.collection ?? source.urls.doi ?? source.urls.documentation ?? source.urls.download ?? source.urls.index ?? Object.values(source.urls)[0];
}
function sourceStatus(source: SurfaceSource) {
  if (source.status === 'local_inputs_available' || source.status.startsWith('downloaded_checksum')) return 'Original local verificado';
  if (source.status === 'product_identified_head_200') return 'Archivo localizado';
  if (source.status.includes('head_403')) return 'Publicado · acceso pendiente';
  if (source.status.startsWith('cmr_')) return 'Escenas localizadas · calidad pendiente';
  if (source.status === 'context_only_not_quantitative_input') return 'Solo contexto';
  return 'Selección y calidad pendientes';
}

export function DimensionsWorkspace({ state, update }: { state: AtlasState; update: (patch: Partial<AtlasState>) => void }) {
  const result = useResource<SurfaceComparison>(`/api/multidimensional?cell_m=${state.cell}&candidate_id=${state.site}`);
  const data = result.data;
  const metric = state.surfaceMetric;
  const name = state.site === 'earth-utah' ? 'Utah' : 'Atacama';
  const signed = metric !== 'roughness_rms';
  const digits = metric === 'laplacian' ? 5 : 2;
  const definition = data?.metrics[metric];
  const extent = data ? range([data.reference.scale.grids[metric], data.candidate.scale.grids[metric]], signed) : [0, 1] as [number, number];
  return <section className="workspace-view dimensions-view" aria-label="Dimensiones de superficie">
    <div className="view-heading"><div><p className="eyebrow">MÁS ASPECTOS DE LA SUPERFICIE</p><h1>{state.dimensionSection === 'minerals' ? <>Jezero <span className="heading-arrow">↔</span> {name}</> : <>Dimensiones de Jezero <span className="heading-arrow">↔</span> {name}</>}</h1></div><span className="context-chip">Ventana 1,8 km · {state.dimensionSection === 'minerals' ? 'CRISM y EMIT' : `celda ${state.cell} m`}</span></div>
    <p className="view-description">{state.dimensionSection === 'minerals' ? 'Jezero muestra indicadores espectrales. La Tierra muestra identificaciones EMIT.' : 'Compara las formas del terreno y revisa la evidencia térmica disponible.'}</p>
    <div className="comparison-toolbar"><div className="candidate-choices" role="group" aria-label="Candidata terrestre">{(['earth-utah', 'earth-atacama'] as const).map(id => <button key={id} aria-pressed={state.site === id} onClick={() => update({ site: id, mineralId: 0 })}>{id === 'earth-utah' ? 'Utah' : 'Atacama'}</button>)}</div>{state.dimensionSection !== 'minerals' && <div className="toolbar-scale"><ScaleControl values={[60, 120]} value={state.cell} onChange={cell => update({ cell: cell as 60 | 120 })} hint="El vecindario conserva su radio de 360 m. La térmica mantiene su paso nativo." /></div>}</div>
    <div className="segmented dimension-section-tabs" role="group" aria-label="Aspecto de la superficie">{([{ id: 'minerals', name: 'Minerales' }, { id: 'geometry', name: 'Formas del terreno' }, { id: 'thermal', name: 'Térmica y pendientes' }] as const).map(section => <button key={section.id} aria-pressed={state.dimensionSection === section.id} onClick={() => update({ dimensionSection: section.id })}>{section.name}</button>)}</div>
    {state.dimensionSection === 'minerals' ? <MineralPanel state={state} update={update} /> : <RequestState {...result} />}
    {data && definition && <>
      {state.dimensionSection === 'geometry' && <section aria-labelledby="geometry-title"><div className="section-heading"><div><h2 id="geometry-title">Formas del terreno</h2><p>{metric === 'laplacian' ? `Centro y cuatro vecinos a ${state.cell} m; separación entre extremos: ${2 * state.cell} m.` : `Vecindario: ±${data.neighborhood_radius_m} m entre centros de muestra; ${data.reference.scale.neighborhood_width_samples} × ${data.reference.scale.neighborhood_width_samples} celdas.`} Se exige soporte completo en cada cálculo.</p></div></div>
        <div className="segmented dimension-tabs" role="group" aria-label="Descriptor de superficie">{(Object.keys(data.metrics) as SurfaceMetric[]).map(key => <button key={key} aria-pressed={metric === key} onClick={() => update({ surfaceMetric: key })}>{data.metrics[key].name}</button>)}</div>
        <p className="dimension-explanation">{definition.description}</p>
        <div className="dimension-pair">{[data.reference, data.candidate].map(site => <article key={site.id} className="dimension-card"><div className="dimension-card-heading"><h3>{shortName(site.name)}</h3><span className={`dimension-status ${site.scale.descriptors[metric].status === 'measured' ? 'measured' : ''}`}>{site.scale.descriptors[metric].status === 'measured' ? 'Medido' : 'Soporte insuficiente'}</span></div><GridMap grid={site.scale.grids[metric]} extent={extent} signed={signed} name={`${definition.name}, ${shortName(site.name)}`} unit={definition.unit} digits={digits} /><Summary value={site.scale.descriptors[metric]} unit={definition.unit} digits={digits} /><a href={site.source.url} target="_blank" rel="noreferrer">{site.source.product_id} ↗</a></article>)}</div>
        <div className="dimension-legend"><span>{fmt(extent[0], ` ${definition.unit}`, digits)}</span><span className={`dimension-ramp ${signed ? 'signed' : ''}`} /><span>{fmt(extent[1], ` ${definition.unit}`, digits)}</span><small>Misma escala de color en ambos lugares · gris: sin soporte</small></div>
        <div className="finding"><span aria-hidden="true">↳</span><p>{data.comparison.metrics[metric].status === 'comparable' ? <>Diferencia entre distribuciones: <strong>{fmt(data.comparison.metrics[metric].wasserstein, ` ${definition.unit}`, digits)}</strong>. Diferencia de medianas ({name} − Jezero): <strong>{fmt(data.comparison.metrics[metric].candidate_minus_reference_median, ` ${definition.unit}`, digits, true)}</strong>.</> : <>Falta soporte suficiente para comparar este descriptor. Se requiere {percent(data.min_coverage)} de celdas válidas en cada ventana.</>}</p></div>
        <p className="dimension-note">La distancia de Wasserstein es menor cuando las distribuciones se acercan; no compara dónde está cada forma. Estos descriptores comparten información con pendiente y relieve.</p>
      </section>}
      {state.dimensionSection === 'thermal' && <><section className="dimension-section" aria-labelledby="thermal-title"><div className="section-heading"><div><h2 id="thermal-title">Inercia térmica</h2><p>Respuesta del material al calentamiento. Su unidad y su escala son distintas de las medidas de geometría.</p></div></div><div className="dimension-pair"><ThermalPanel value={data.reference.thermal} name="Jezero" /><ThermalPanel value={data.candidate.thermal} name={name} /></div><p className="dimension-callout"><strong>Comparación pendiente.</strong> {data.comparison.thermal.reason} La temperatura superficial de Landsat describe otra propiedad.</p></section>
      <section className="dimension-section" aria-labelledby="pending-title"><div className="section-heading"><div><h2 id="pending-title">Lo que falta medir</h2><p>Cada dimensión conserva su estado. La ausencia de evidencia no suma semejanza ni recibe una mala nota.</p></div></div><div className="dimension-pair">{data.candidate.pending_dimensions.map(d => <article key={d.id} className="dimension-card"><div className="dimension-card-heading"><h3>{d.name}</h3><span className="dimension-status">{d.id === 'geology_and_materials' ? 'Comparación con Marte pendiente' : 'Sin evaluar'}</span></div><p>{d.id === 'geology_and_materials' ? 'Consulta los indicadores de Jezero y las identificaciones terrestres en Minerales. Una comparación de materiales requiere un método común.' : d.reason}</p><details className="dimension-source-details"><summary>Fuentes para esta dimensión</summary><ul>{d.source_ids.map(id => { const s = data.sources.find(x => x.id === id); return s ? <li key={id}><a href={sourceLink(s)} target="_blank" rel="noreferrer">{s.name} ↗</a><small> · {sourceStatus(s)}</small></li> : null; })}</ul></details></article>)}</div></section>
      </>}
      {state.dimensionSection !== 'minerals' && <MethodDrawer title="Fuentes, soporte y método"><p>La comparación usa el mismo tamaño de ventana y radio de vecindario en los tres lugares. Cada elevación agregada exige soporte válido completo. Los descriptores solo se comparan cuando al menos {percent(data.min_coverage)} de la ventana tiene valores válidos.</p><p>Rugosidad: ajuste por mínimos cuadrados de un plano y RMS residual. Posición: elevación central menos la media local. Curvatura discreta: suma de diferencias a cuatro vecinos dividida por celda². Las distribuciones se comparan por Wasserstein en sus propias unidades; sin puntuación combinada.</p><p>{data.reference.thermal.spatial_assumption}</p><ul>{data.limitations.map(text => <li key={text}>{text}</li>)}</ul><h3>Catálogo de fuentes</h3><p>Fuentes investigadas y productos seleccionados. Un archivo localizado todavía puede requerir descarga, control de calidad o un método compatible.</p><div className="table-wrap"><table><thead><tr><th>Fuente</th><th>Cuerpo</th><th>Estado de investigación</th><th>Tamaño conocido</th></tr></thead><tbody>{data.sources.map(s => <tr key={s.id}><th>{sourceLink(s) ? <a href={sourceLink(s)} target="_blank" rel="noreferrer">{s.name} ↗</a> : s.name}</th><td>{s.body === 'Earth' ? 'Tierra' : s.body === 'Mars' ? 'Marte' : 'Marte/Tierra'}</td><td>{sourceStatus(s)}</td><td>{s.bytes == null ? 'Por seleccionar' : fmt(s.bytes / 1e6, ' MB', 2)}</td></tr>)}</tbody></table></div><EvidenceLinks links={data.evidence} /></MethodDrawer>}
    </>}
  </section>;
}
