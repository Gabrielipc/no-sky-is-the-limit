import type { AtlasState } from '../../app/useAtlasState';
import { useResource } from '../../data/api';
import { comparisonFinding } from '../../data/adapters';
import { fmt, shortName, type Comparison, type Terrain, type Site } from '../../domain/analysis';
import { ComparisonStage } from '../../components/ComparisonStage';
import { ScaleControl } from '../../components/AnalysisControls';
import { MissingDimensions, RequestState } from '../../components/EvidenceStatus';
import { MethodDrawer, EvidenceLinks } from '../../components/MethodDrawer';
import { LocationContext } from '../../components/LocationContext';
import { SlopeComparison } from '../../components/SlopeComparison';
import { ReliefComparison } from '../../components/ReliefComparison';

function Source({ site }: { site: Site }) {
  const m = site.measurements;
  return <section><h3>{shortName(site.name)}</h3><p><a href={site.source.url} target="_blank" rel="noreferrer">{site.source.product_id} ↗</a></p>
    <dl className="source-facts"><dt>Adquisición</dt><dd>{site.source.observation_dates.join(' · ')}</dd><dt>Versión</dt><dd>{site.source.version}</dd><dt>Referencia vertical</dt><dd>{site.source.vertical_reference}</dd><dt>Paso nativo aprox.</dt><dd>{site.source.native_step_at_center_m.map(n => fmt(n, ' m', 2)).join(' × ')}; no equivale a resolución efectiva.</dd><dt>Cobertura válida</dt><dd>Elevación {m.valid_elevation_cells}/{m.cells} · inclinación {m.valid_slope_cells}/{m.cells}</dd><dt>SHA-256</dt><dd className="hash">{site.source.sha256}</dd></dl>
    <ul>{site.limitations.map(l => <li key={l}>{l}</li>)}</ul></section>;
}

export function CompareWorkspace({ state, update }: { state: AtlasState; update: (patch: Partial<AtlasState>) => void }) {
  const result = useResource<Comparison>(`/api/scenarios/relieve-regional/comparison?reference_id=mars-jezero-fan&cell_m=${state.cell}`);
  const visual = useResource<Terrain>('/analysis/terrain.json');
  const data = result.data;
  const choice = data?.candidates.find(c => c.site.id === state.site);
  const name = choice ? shortName(choice.site.name) : state.site === 'earth-utah' ? 'Utah' : 'Atacama';
  const terrain = data && visual.data?.case_id === data.case_id && visual.data.results_sha256 === data.evidence_identity ? visual.data : undefined;
  const ordered = data ? [...data.candidates].sort((a, b) => {
    const get = (c: typeof a) => state.sort === 'slope_distance' ? c.comparison.slope_wasserstein_deg ?? Infinity : Math.abs(c.comparison.candidate_minus_reference_relief_m ?? Infinity);
    return get(a) - get(b);
  }) : [];
  const closest = data?.candidates.every(c => c.site.id === choice?.site.id || (choice?.comparison.slope_wasserstein_deg ?? Infinity) <= (c.comparison.slope_wasserstein_deg ?? Infinity)) ?? false;
  return <section className="workspace-view compare-view" aria-label="Comparar lugares">
    <div className="view-heading"><div><p className="eyebrow">UN LUGAR PARA ESTUDIAR OTRO</p><h1>Jezero <span className="heading-arrow">↔</span> {name}</h1></div><span className="context-chip">Ventana 1,8 km · celda {state.cell} m</span></div>
    <div className="comparison-toolbar"><div className="candidate-choices" role="group" aria-label="Candidata terrestre">
      {(ordered.length ? ordered.map(c => ({ id: c.site.id, name: shortName(c.site.name), distance: c.comparison.slope_wasserstein_deg, relief: c.comparison.candidate_minus_reference_relief_m })) : [{ id: 'earth-utah', name: 'Utah' }, { id: 'earth-atacama', name: 'Atacama' }]).map(c => <button key={c.id} aria-pressed={state.site === c.id} onClick={() => update({ site: c.id })}><strong>{c.name}</strong>{'distance' in c && <small>{state.sort === 'slope_distance' ? fmt(c.distance, '°', 2) + ' de diferencia' : fmt(c.relief, ' m', 1, true) + ' de relieve'}</small>}</button>)}
    </div><div className="segmented" role="group" aria-label="Capa medida"><button aria-pressed={state.layer === 'slope'} onClick={() => update({ layer: 'slope' })}>Inclinación</button><button aria-pressed={state.layer === 'elevation'} onClick={() => update({ layer: 'elevation' })}>Altura relativa</button></div><div className="toolbar-scale"><ScaleControl values={[60, 120]} value={state.cell} onChange={cell => update({ cell: cell as 60 | 120 })} /></div></div>
    <RequestState {...result} />
    {data && choice && <>
      <div className="finding" aria-live="polite"><span aria-hidden="true">↳</span><p>{comparisonFinding(name, choice.site.measurements, data.reference.measurements, closest)}</p></div>
      <RequestState {...visual} />
      {terrain ? <ComparisonStage terrain={terrain} candidateId={choice.site.id} name={name} cell={state.cell} layer={state.layer} /> : visual.data && <div className="request-error" role="alert">Las capas visuales no corresponden a esta evidencia. Las medidas siguen disponibles.<button onClick={visual.retry}>Reintentar capas</button></div>}
      <div className={`metric-pair focus-${state.layer}`}><SlopeComparison reference={data.reference.measurements} candidate={choice.site.measurements} name={name} distance={choice.comparison.slope_wasserstein_deg} /><ReliefComparison reference={data.reference.measurements.relief_p95_p5_m} candidate={choice.site.measurements.relief_p95_p5_m} name={name} difference={choice.comparison.candidate_minus_reference_relief_m} /></div>
      <div className="analysis-controls"><label className="select-field">Ordenar candidatas por<select value={state.sort} onChange={e => update({ sort: e.target.value as AtlasState['sort'] })}><option value="slope_distance">Diferencia de pendientes</option><option value="abs_relief_difference">Diferencia absoluta de relieve</option></select><small>Orden de una dimensión; sin puntuación combinada.</small></label></div>
      <MissingDimensions />
      <p className="subtle-note"><button className="quiet-button" onClick={() => update({ view: 'dimensions' })}>Ver rugosidad, formas del terreno y evidencia térmica →</button></p>
      <LocationContext sites={[{ ...data.reference, window_m: 1800 }, { ...choice.site, window_m: 1800 }]} />
      <MethodDrawer title="Ver medidas y cambios con la escala"><div className="table-wrap"><table><caption>Ventanas completas de 1,8 km; celda de {state.cell} m</caption><thead><tr><th>Medida</th><th>Jezero</th><th>{name}</th></tr></thead><tbody>{(['p10', 'p50', 'p90'] as const).map(q => <tr key={q}><th>Inclinación {q === 'p50' ? 'mediana' : q}</th><td>{fmt(data.reference.measurements.slope_quantiles_deg?.[q], '°', 3)}</td><td>{fmt(choice.site.measurements.slope_quantiles_deg?.[q], '°', 3)}</td></tr>)}<tr><th>Relieve p95−p5</th><td>{fmt(data.reference.measurements.relief_p95_p5_m, ' m', 3)}</td><td>{fmt(choice.site.measurements.relief_p95_p5_m, ' m', 3)}</td></tr></tbody></table></div>
        <div className="table-wrap"><table><caption>Misma ventana y candidata; otra agregación</caption><thead><tr><th>Celda / base de inclinación</th><th>Diferencia de pendientes</th><th>Diferencia de relieve</th></tr></thead><tbody>{choice.sensitivity.map(m => <tr key={m.cell_m}><th>{m.cell_m} / {m.cell_m * 2} m</th><td>{fmt(m.slope_wasserstein_deg, '°', 3)}</td><td>{fmt(m.candidate_minus_reference_relief_m, ' m', 3, true)}</td></tr>)}</tbody></table></div>
      </MethodDrawer>
      <MethodDrawer><div className="source-pair"><Source site={data.reference} /><Source site={choice.site} /></div><h3>Cómo se calcularon estas medidas</h3><dl>{Object.entries(data.method).map(([key, text]) => <div key={key}><dt>{{ elevation: 'Elevación', slope: 'Inclinación', slope_comparison: 'Diferencia de pendientes', relief: 'Relieve', coordinates: 'Coordenadas', score_policy: 'Presentación' }[key] ?? key}</dt><dd>{text}</dd></div>)}</dl><ul>{data.limitations.map(l => <li key={l}>{l}</li>)}</ul><EvidenceLinks links={data.evidence} /><a href="/analysis/manifest.json" target="_blank" rel="noreferrer">Procedencia de las capas visuales ↗</a><p>Las huellas digitales comprueban identidad local; no exactitud física. La cobertura incluye posibles interpolaciones o rellenos.</p><a href={data.orthoimage_figure} target="_blank" rel="noreferrer">Ver ortoimagen de Jezero usada en la inspección ↗</a></MethodDrawer>
    </>}
  </section>;
}
