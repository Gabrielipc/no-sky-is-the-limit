import { useEffect, useMemo, useRef, useState } from 'react';
import type { AtlasState } from '../../app/useAtlasState';
import { useResource } from '../../data/api';
import { sortFeatures } from '../../data/adapters';
import { fmt, percent, reasonLabel, type FeatureCollection, type RegionalSummary, type RegionalDetail, type Metric } from '../../domain/analysis';
import { ProfileControl, ScaleControl } from '../../components/AnalysisControls';
import { EvidenceStatus, MissingDimensions, RequestState } from '../../components/EvidenceStatus';
import { MethodDrawer } from '../../components/MethodDrawer';
import { LocationContext } from '../../components/LocationContext';
import { ReliefComparison } from '../../components/ReliefComparison';
import { SlopeComparison } from '../../components/SlopeComparison';
import { RegionalMap } from './RegionalMap';

function DetailMetrics({ metrics, title }: { metrics: Metric[]; title: string }) {
  return <div className="table-wrap"><table><caption>{title}</caption><thead><tr><th>Celda</th><th>Diferencia de pendientes</th><th>Diferencia de relieve</th><th>Cobertura elevación / inclinación</th></tr></thead><tbody>{metrics.map(m => <tr key={m.cell_m}><th>{m.cell_m} m</th><td>{fmt(m.slope_wasserstein_deg, '°', 3)}</td><td>{fmt(m.candidate_minus_reference_relief_m, ' m', 3, true)}</td><td>{m.valid_elevation_cells}/{m.cells} · {m.valid_slope_cells}/{m.cells}</td></tr>)}</tbody></table></div>;
}
function RegionalReview({ id, cell, reference, edges, autoScroll, onScrolled, onSensitivity, onClose }: { id: string; cell: number; reference?: Metric; edges: number[]; autoScroll: boolean; onScrolled: () => void; onSensitivity: (id: string) => void; onClose: () => void }) {
  const result = useResource<RegionalDetail>(`/api/regional-search/candidates/${encodeURIComponent(id)}`);
  const detail = result.data, metric = detail?.metrics.find(m => m.cell_m === cell);
  const review = useRef<HTMLElement>(null);
  useEffect(() => { if (detail && autoScroll) { review.current?.scrollIntoView({ block: 'start', behavior: 'instant' }); onScrolled(); } }, [detail?.id, autoScroll]);
  return <article ref={review} className="regional-review" aria-label={`Revisión de ${id}`}><div className="review-heading"><div><p className="eyebrow">VENTANA SELECCIONADA · 3 × 3 KM</p><h2>{detail?.name ?? id}</h2></div><a href="#regional-map">Volver al mapa ↑</a><button onClick={onClose}>Cerrar revisión</button></div><RequestState {...result} />
    {detail && <><div className="review-meta"><EvidenceStatus status={detail.local_detail.evaluation_status} /><span>{fmt(detail.latitude, '°', 3)} lat. · {fmt(detail.longitude, '°', 3)} lon.</span></div>
      {metric && reference && <div className="metric-pair"><SlopeComparison reference={{ ...reference, histogram_edges_deg: edges }} candidate={{ ...metric, histogram_edges_deg: edges }} name="Esta ventana" distance={metric.slope_wasserstein_deg} /><ReliefComparison reference={reference.relief_p95_p5_m} candidate={metric.relief_p95_p5_m} name="Esta ventana" difference={metric.candidate_minus_reference_relief_m} /></div>}
      <div className="detail-empty"><span aria-hidden="true">▧</span><div><strong>Sin capa visual local publicada</strong><p>{detail.local_detail.metrics ? 'Hay medidas locales con SRTM. Puedes consultarlas debajo; no hay una imagen local integrada para esta ventana.' : 'Hay medidas regionales con GMTED. Falta evaluar el detalle con SRTM; esto no significa una mala coincidencia.'}</p></div><button onClick={() => onSensitivity(id)}>Ver qué cambia →</button></div>
      <LocationContext sites={[{ ...detail, body: 'Earth', window_m: 3000 }]} />
      <MethodDrawer title="Medidas, fuentes y evaluación local"><DetailMetrics metrics={detail.metrics} title="GMTED frente a Jezero · misma ventana de 3 km" />
        {detail.local_detail.metrics ? <DetailMetrics metrics={detail.local_detail.metrics} title="Detalle exploratorio SRTM · entrega original de fase 4" /> : <p>La evaluación local está pendiente. Las medidas ausentes no se representan con cero.</p>}
        <h3>Fuentes de detalle propuestas</h3>{detail.detail_plan.tiles.map(t => <p key={t.filename}><a href={t.url} target="_blank" rel="noreferrer">{t.filename} ↗</a></p>)}<p>Consultar la aplicación no descarga ni procesa estos archivos. La fase 5 conserva un procedimiento propio y no sobrescribe el detalle publicado de fase 4.</p>{detail.local_detail.limitations?.map(l => <p key={l}>{l}</p>)}</MethodDrawer>
    </>}
  </article>;
}

export function ExploreWorkspace({ state, update }: { state: AtlasState; update: (patch: Partial<AtlasState>) => void }) {
  const summaryResult = useResource<RegionalSummary>('/api/regional-search');
  const query = new URLSearchParams({ area_id: state.area, cell_m: String(state.regionalCell), profile: state.profile, include_excluded: 'true' });
  const catalogResult = useResource<FeatureCollection>(`/api/regional-search/export?${query}`);
  const [page, setPage] = useState({ key: '', number: 0 });
  const scrollRequest = useRef('');
  const summary = summaryResult.data;
  const area = summary?.config.areas.find(a => a.id === state.area);
  const selectionKey = `${query}&excluded=${state.excluded}&sort=${state.sort}`;
  const sorted = useMemo(() => sortFeatures((catalogResult.data?.features ?? []).filter(f => state.excluded || f.properties.passes_filter), state.sort), [catalogResult.data, state.excluded, state.sort]);
  const selectedIndex = sorted.findIndex(f => f.properties.id === state.regionalSite);
  const pageNumber = page.key === selectionKey ? Math.min(page.number, Math.max(0, Math.ceil(sorted.length / 6) - 1)) : selectedIndex >= 0 ? Math.floor(selectedIndex / 6) : 0;
  const rows = sorted.slice(pageNumber * 6, pageNumber * 6 + 6);
  const all = catalogResult.data?.features ?? [], accepted = all.filter(f => f.properties.passes_filter).length;
  const sampling = summary?.area_summaries.find(a => a.area_id === state.area);
  const reference = summary?.reference.metrics.find(m => m.cell_m === state.regionalCell);
  const exportURL = `/api/regional-search/export?${new URLSearchParams({ area_id: state.area, cell_m: String(state.regionalCell), profile: state.profile, include_excluded: String(state.excluded) })}`;
  // Reset transient pagination on browser Back or a new selected window.
  useEffect(() => { setPage({ key: '', number: 0 }); }, [state.regionalSite]);
  function select(id: string) { scrollRequest.current = id; const index = sorted.findIndex(f => f.properties.id === id); setPage({ key: selectionKey, number: Math.max(0, Math.floor(index / 6)) }); update({ regionalSite: id }); }
  const controls = summary?.config.controls.filter(c => c.area_id === state.area) ?? [];
  return <section className="workspace-view" aria-label="Explorar zonas"><div className="view-heading"><div><p className="eyebrow">ENCUENTRA LUGARES PARA INVESTIGAR</p><h1>Explorar zonas</h1></div><span className="context-chip">Ventanas 3 km · GMTED · celda {state.regionalCell} m</span></div>
    <div className="regional-controls"><label className="select-field">Área<select value={state.area} onChange={e => update({ area: e.target.value, regionalSite: '' })}><option value="utah">Utah interior</option><option value="mojave">Mojave interior</option><option value="atacama">Atacama interior</option></select></label><ScaleControl values={[300, 600]} value={state.regionalCell} onChange={regionalCell => update({ regionalCell: regionalCell as 300 | 600, regionalSite: '' })} /><ProfileControl value={state.profile} onChange={profile => update({ profile, regionalSite: '' })} thresholds={summary?.config.profiles[state.profile]} /></div>
    <RequestState {...summaryResult} /><RequestState {...catalogResult} />
    {summary && catalogResult.data && area && <><div className="search-summary" aria-live="polite"><p><strong>{accepted}</strong> de {all.length} ventanas cumplen este filtro</p><span>{percent(sampling?.sampled_fraction)} del área muestreada</span><a href={exportURL}>Exportar selección GeoJSON ↗</a></div>
      <div className="explore-layout"><RegionalMap key={state.area} area={area} features={sorted} selected={state.regionalSite} onSelect={select} controls={controls} />
        <section className="candidate-list" aria-label="Ventanas del mapa"><div className="list-tools"><label className="select-field">Ordenar por<select value={state.sort} onChange={e => update({ sort: e.target.value as AtlasState['sort'] })}><option value="slope_distance">Diferencia de pendientes</option><option value="abs_relief_difference">Diferencia absoluta de relieve</option></select></label><label className="check-field"><input type="checkbox" checked={state.excluded} onChange={e => update({ excluded: e.target.checked, regionalSite: '' })} />Mostrar fuera del filtro</label></div>
          {!rows.length && <div className="empty-state"><h3>Ninguna ventana cumple este perfil</h3><p>Prueba una tolerancia más amplia o muestra las ventanas fuera del filtro. Esto no descarta la región.</p></div>}
          <div className="window-list">{rows.map(f => { const row = f.properties; return <button key={row.id} className="window-row" aria-pressed={state.regionalSite === row.id} onClick={() => select(row.id)}><span className="window-row-title"><strong>{row.name.replace(' interior', '')}</strong><span aria-hidden="true">↗</span></span><span className="window-measures"><span>{fmt(row.metric.slope_wasserstein_deg, '°', 2)} <small>pendientes</small></span><span>{fmt(row.metric.candidate_minus_reference_relief_m, ' m', 1, true)} <small>relieve</small></span></span><span className={row.passes_filter ? 'filter-state' : 'filter-state outside'}>{row.passes_filter ? '✓ Cumple el filtro' : '— Fuera del filtro'}</span><EvidenceStatus status={summary.local_evaluations.includes(row.id) ? 'locally_evaluated_exploratory' : row.evaluation_status} /></button>; })}</div>
          <div className="pagination"><button disabled={pageNumber === 0} onClick={() => setPage({ key: selectionKey, number: pageNumber - 1 })}>Anterior</button><span>{sorted.length ? pageNumber + 1 : 0} / {Math.ceil(sorted.length / 6)}</span><button disabled={(pageNumber + 1) * 6 >= sorted.length} onClick={() => setPage({ key: selectionKey, number: pageNumber + 1 })}>Siguiente</button></div>
        </section></div>
      <section className="context-controls"><h3>Los sitios conocidos también se revisan</h3><p className="subtle-note">Controles contextuales, separados de las 970 ventanas nuevas.</p><div className="control-list">{summary.control_filter_outcomes.map(c => { const outcome = c.outcomes.find(o => o.cell_m === state.regionalCell && o.profile === state.profile); const controlArea = c.id.replace('control-', ''); return <button key={c.id} aria-pressed={state.regionalSite === c.id} onClick={() => { scrollRequest.current = c.id; update({ area: controlArea, regionalSite: c.id }); }}><strong>{c.name}</strong><span>{outcome?.reasons.length ? 'Fuera del filtro' : 'Cumple el filtro'}</span></button>; })}</div></section>
      {state.regionalSite && <><div className="selection-caption" aria-live="polite">Selección: {state.regionalSite}{!state.regionalSite.startsWith('control-') && selectedIndex < 0 ? ' · No visible con los filtros actuales' : ''}</div><RegionalReview key={state.regionalSite} id={state.regionalSite} cell={state.regionalCell} reference={reference} edges={summary.config.slope_histogram_edges_deg} autoScroll={scrollRequest.current === state.regionalSite} onScrolled={() => { scrollRequest.current = ''; }} onClose={() => update({ regionalSite: '' })} onSensitivity={id => update({ view: 'sensitivity', sensitivitySite: id, sensitivityCell: state.regionalCell })} /></>}
      <MissingDimensions /><MethodDrawer title="Qué cubre esta búsqueda y cómo se filtra"><p>Se muestrean {fmt(sampling?.sampled_window_area_km2, ' km²')} de {fmt(sampling?.bbox_geodesic_area_km2, ' km²')} en {area.name}. No es un barrido continuo. Cobertura válida mínima por variable: {percent(summary.config.min_coverage)}.</p><p>El filtro aplica por separado dos condiciones. Los controles pueden quedar fuera sin ser errores demostrados del método. Las medidas regionales no se mezclan con el primer caso de 1,8 km.</p><ul>{summary.limitations.map(l => <li key={l}>{l}</li>)}</ul><h3>Motivos de exclusión de la selección</h3>{state.regionalSite && all.find(f => f.properties.id === state.regionalSite)?.properties.filter_reasons.map(r => <p key={r}>{reasonLabel(r)}</p>)}<div className="evidence-links">{summary.documentation.map(d => <a key={d.url} href={d.url} target="_blank" rel="noreferrer">{d.title} ↗</a>)}{['auditoria-gmted.json', 'procesamiento.json', 'manifest-local.json'].map(file => <a key={file} href={`/api/regional-search/evidence/${file}`} target="_blank" rel="noreferrer">{file} ↗</a>)}</div></MethodDrawer>
    </>}
  </section>;
}
