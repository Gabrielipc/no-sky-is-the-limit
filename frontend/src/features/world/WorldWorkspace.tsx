import { useState, type FormEvent } from 'react';
import { useResource } from '../../data/api';
import './world.css';

type Profile = {
  site: string; slope_p50_deg: number; relief_m: number; roughness_m: number;
  slope_baseline_m: number; roughness_radius_m: number;
};
type Release = {
  version: string; cell_m: number; stride_m: number; window_m: number; scope: 'pilot' | 'world';
  coverage_status: string; batch_count: number; planned_batches: number; counts: Record<string, number>;
  profile: Profile; expedients: string[]; context_counts: { bare: number; water: number };
  refinement: { region_id: string; initial_rank: number; refined_rank?: number }[];
};
type Bin = { west: number; south: number; sampled: number; rankable: number; gaps: number; excluded: number };
type Match = {
  region_id: string; rank: number; latitude: number; longitude: number; area: string;
  slope_distance_deg: number; relief_difference_m: number; roughness_difference_m: number; distance: number;
};
type QueryResult = { query_id: string; total: number; matches: Match[] };
type Distances = { slope_distance_deg: number; relief_difference_m: number; roughness_difference_m: number };
type Case = {
  map_url: string; potential_use: string; limitations: string[];
  signed_differences: { slope_p50_deg: number; relief_m: number; roughness_m: number };
  sensitivity: { cell_m: number; status: string; comparison: Distances | null }[];
  source_contrast: { product?: string; reason?: string; distances?: Distances };
};
type Candidate = {
  window: Match & {
    valid_slope: number; valid_elevation: number; valid_roughness: number; land_fraction: number;
    slope_p50_deg: number; relief_m: number; roughness_m: number;
    bare_fraction: number | null; water_occurrence_pct: number | null;
  };
  expedient: Case | null;
  assets: { id: string; source: string; url: string }[];
};
type Criteria = { slope: string; relief: string; roughness: string; bare: string; water: string };
const initial: Criteria = { slope: '50', relief: '30', roughness: '20', bare: '', water: '' };
const labels = { slope: 'Pendiente', relief: 'Relieve', roughness: 'Rugosidad' };
const format = (value: number, decimals = 2) => value.toLocaleString('es', { maximumFractionDigits: decimals });
const percent = (fraction: number) => format(fraction * 100, 1) + ' %';
const signed = (value: number) => (value > 0 ? '+' : '') + format(value);
const location = ({ latitude, longitude }: { latitude: number; longitude: number }) =>
  `${format(Math.abs(latitude), 3)}° ${latitude >= 0 ? 'N' : 'S'}, ${format(Math.abs(longitude), 3)}° ${longitude >= 0 ? 'E' : 'O'}`;
const limit = 25;

function WorldMap({ bins, matches, selected, choose }: { bins: Bin[]; matches: Match[]; selected: string; choose: (id: string) => void }) {
  return <figure className="world-map">
    <svg viewBox="0 0 720 360" aria-label="Mapa mundial de cobertura y resultados" role="group">
      <image href="/textures/earth.png" width="720" height="360" opacity=".48" />
      {bins.map(bin => <rect key={`${bin.west}/${bin.south}`} x={(bin.west + 180) * 2} y={(88 - bin.south) * 2}
        width="4" height="4" className={bin.gaps ? 'world-map-gap' : bin.rankable ? 'world-map-sampled' : 'world-map-excluded'}>
        <title>{bin.sampled} ventanas muestreadas, {bin.rankable} clasificables, {bin.gaps} con huecos del DEM, {bin.excluded} con poca tierra</title>
      </rect>)}
      {matches.map(row => <circle key={row.region_id} cx={(row.longitude + 180) * 2} cy={(90 - row.latitude) * 2}
        r={row.region_id === selected ? 6 : 4} tabIndex={0} role="button" aria-label={`Candidata ${row.rank}, ${location(row)}`}
        onClick={() => choose(row.region_id)} onKeyDown={event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); choose(row.region_id); } }} />)}
    </svg>
    <figcaption><span className="world-legend sampled">Muestreo con candidatas</span><span className="world-legend gap">Huecos del DEM</span>
      <span className="world-legend excluded">Tierra insuficiente</span><span className="world-legend candidate">Candidatas de esta página</span>
      <span>Las celdas del mapa agrupan centros en 2°. Las zonas sin marca carecen de ventanas en esta publicación.</span></figcaption>
  </figure>;
}

function CandidateDetail({ version, regionId }: { version: string; regionId: string }) {
  const { data, loading, error } = useResource<Candidate>(`/api/atlas/candidates/${encodeURIComponent(regionId)}?version=${encodeURIComponent(version)}`);
  if (error) return <p role="alert">{error}</p>;
  if (loading || !data) return <p role="status">Cargando ventana…</p>;
  const { window: row, expedient: caseFile, assets } = data;
  return <section className="world-detail" aria-labelledby="world-detail-title">
    <h3 id="world-detail-title">{caseFile ? 'Expediente' : 'Ventana candidata'} · {location(row)}</h3>
    <p>Terreno terrestre {percent(row.land_fraction)} · soporte de elevación {percent(row.valid_elevation)}, pendiente {percent(row.valid_slope)} y rugosidad {percent(row.valid_roughness)}.</p>
    <p>Pendiente mediana {format(row.slope_p50_deg)}° · relieve {format(row.relief_m)} m · rugosidad mediana {format(row.roughness_m)} m.</p>
    <p>Suelo desnudo {row.bare_fraction === null ? 'sin datos suficientes' : percent(row.bare_fraction)} · ocurrencia de agua {row.water_occurrence_pct === null ? 'sin datos suficientes' : format(row.water_occurrence_pct) + ' %'}.</p>
    {caseFile && <>
      <p>{caseFile.potential_use}</p>
      <p>Diferencias respecto de Jezero en pendiente mediana {signed(caseFile.signed_differences.slope_p50_deg)}°, relieve {signed(caseFile.signed_differences.relief_m)} m y rugosidad {signed(caseFile.signed_differences.roughness_m)} m.</p>
      <img src={caseFile.map_url} alt="Comparación de pendiente y rugosidad de Jezero y la candidata, con escalas de color compartidas" loading="lazy" />
      <h4>Sensibilidad y límites</h4>
      <ul>{caseFile.sensitivity.map(item => <li key={item.cell_m}>{item.cell_m} m · {item.comparison ?
        `Distancia de pendientes ${format(item.comparison.slope_distance_deg)}° y diferencia de relieve ${format(item.comparison.relief_difference_m)} m.` : 'soporte insuficiente.'}</li>)}
        <li>{caseFile.source_contrast.distances ? `Contraste ${caseFile.source_contrast.product}, distancia de pendientes ${format(caseFile.source_contrast.distances.slope_distance_deg)}°.` : caseFile.source_contrast.reason || 'Contraste de fuente con soporte insuficiente.'}</li>
        {caseFile.limitations.map(note => <li key={note}>{note}</li>)}</ul>
    </>}
    <details><summary>Activos utilizados ({assets.length})</summary><ul>{assets.map(asset => <li key={asset.id}><a href={asset.url}>{asset.id}</a></li>)}</ul></details>
  </section>;
}

export function WorldWorkspace() {
  const [version, setVersion] = useState('');
  const [draft, setDraft] = useState(initial);
  const [criteria, setCriteria] = useState(initial);
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState('');
  const summary = useResource<Release>('/api/atlas' + (version ? '?version=' + encodeURIComponent(version) : ''));
  const { data: releases } = useResource<string[]>('/api/atlas/versions');
  const release = summary.data;
  const parameters = new URLSearchParams({ version: release?.version || '', slope: criteria.slope, relief: criteria.relief,
    roughness: criteria.roughness, offset: String(offset), limit: String(limit) });
  if (criteria.bare) parameters.set('bare_min', String(Number(criteria.bare) / 100));
  if (criteria.water) parameters.set('water_max', criteria.water);
  const ranking = useResource<QueryResult>(release ? `/api/atlas/search?${parameters}` : null);
  const coverage = useResource<{ bins: Bin[] }>(release ? `/api/atlas/coverage?version=${encodeURIComponent(release.version)}` : null);
  const matches = ranking.data?.matches ?? [];
  const active = selected || matches[0]?.region_id;
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setCriteria({ ...draft }); setOffset(0); setSelected('');
  };
  return <section className="world-workspace" aria-labelledby="world-title">
    <header><p className="world-kicker">JEZERO / TIERRA · TOPOGRAFÍA</p><h1 id="world-title">Búsqueda mundial a 30 m</h1>
      <p>Explora ventanas terrestres de 3 × 3 km que se acercan a la forma del terreno del abanico de Jezero.</p></header>
    {summary.error && <p role="alert">{summary.error} <button onClick={summary.retry}>Reintentar</button></p>}
    {summary.loading && <p role="status">Cargando índice…</p>}
    {release && <>
      <section className="world-profile" aria-label="Referencia y cobertura">
        <div><h2>{release.profile.site}</h2><p>Pendiente mediana {format(release.profile.slope_p50_deg)}° · relieve {format(release.profile.relief_m)} m · rugosidad {format(release.profile.roughness_m)} m.</p>
          <p>Celdas de {release.cell_m} m, base de pendiente {release.profile.slope_baseline_m} m y radio de rugosidad {release.profile.roughness_radius_m} m.</p>
          <p className="world-note">Evidencia complementaria de Jezero · <a href="/?view=dimensions&dimensionSection=minerals">Minerales CRISM</a> · <a href="/?view=dimensions&dimensionSection=thermal">Inercia térmica THEMIS</a></p></div>
        <div><label>Publicación <select value={release.version} onChange={event => { setVersion(event.target.value); setDraft({ ...draft, bare: '', water: '' }); setCriteria({ ...criteria, bare: '', water: '' }); setOffset(0); setSelected(''); }}>
          {(releases ?? [release.version]).map(id => <option key={id}>{id}</option>)}</select></label>
          <p>{release.coverage_status === 'partial' ? 'Cobertura parcial' : 'Muestreo completado'} · {format(release.batch_count, 0)} de {format(release.planned_batches, 0)} lotes {release.scope === 'pilot' ? 'del piloto' : 'previstos'}</p>
          <p>{format(release.counts.rankable || 0, 0)} ventanas clasificables · centros cada {format(release.stride_m / 1000)} km.</p></div>
      </section>
      {coverage.error && <p role="alert">{coverage.error}</p>}
      <WorldMap bins={coverage.data?.bins ?? []} matches={matches} selected={active ?? ''} choose={setSelected} />
      <form className="world-filters" onSubmit={submit}>
        <fieldset><legend>Pesos del ranking</legend>{(['slope', 'relief', 'roughness'] as const).map(key =>
          <label key={key}>{labels[key]}<input type="number" min="0" max="100" required value={draft[key]}
            onChange={event => setDraft({ ...draft, [key]: event.target.value })} /></label>)}</fieldset>
        <fieldset><legend>Filtros opcionales</legend>
          <label>Suelo desnudo o vegetación escasa mín. %<input type="number" min="0" max="100" disabled={!release.context_counts.bare} value={draft.bare} onChange={event => setDraft({ ...draft, bare: event.target.value })} /></label>
          <label>Ocurrencia de agua máx. %<input type="number" min="0" max="100" disabled={!release.context_counts.water} value={draft.water} onChange={event => setDraft({ ...draft, water: event.target.value })} /></label>
        </fieldset>
        <button type="submit">Aplicar</button>
      </form>
      <p className="world-note">WorldCover disponible en {format(release.context_counts.bare, 0)} candidatas y JRC en {format(release.context_counts.water, 0)}.
        {!release.context_counts.bare && !release.context_counts.water && ' Selecciona la publicación piloto para explorar estos filtros.'}</p>
      {ranking.error && <p role="alert">{ranking.error}</p>}
      {ranking.loading && <p role="status">Calculando ranking…</p>}
      {ranking.data && <section className="world-results" aria-labelledby="world-results-title"><h2 id="world-results-title">Candidatas · {format(ranking.data.total, 0)}</h2>
        <p>Una distancia menor indica mayor parecido en los criterios seleccionados. El orden refinado corresponde a la consulta de referencia.</p>
        {matches.length ? <div className="world-table"><table><thead><tr><th scope="col">Orden</th><th scope="col">Ubicación</th><th scope="col">Pendiente °</th>
          <th scope="col">Relieve m</th><th scope="col">Rugosidad m</th><th scope="col">Distancia</th><th scope="col">Refinado</th></tr></thead>
          <tbody>{matches.map(row => <tr key={row.region_id} className={row.region_id === active ? 'world-selected' : undefined}>
            <td>{row.rank}</td><td><button onClick={() => setSelected(row.region_id)} aria-pressed={row.region_id === active}>{location(row)}</button></td>
            <td>{format(row.slope_distance_deg)}</td><td>{format(row.relief_difference_m)}</td><td>{format(row.roughness_difference_m)}</td><td>{format(row.distance, 3)}</td>
            <td>{release.refinement.find(item => item.region_id === row.region_id)?.refined_rank ?? '—'}</td></tr>)}</tbody></table></div>
          : <p>No hay ventanas con datos que cumplan estos filtros.</p>}
        <div className="world-pages"><button disabled={!offset} onClick={() => { setOffset(offset - limit); setSelected(''); }}>Anterior</button>
          <button disabled={offset + limit >= ranking.data.total} onClick={() => { setOffset(offset + limit); setSelected(''); }}>Siguiente</button>
          <a href={`/api/atlas/search/${ranking.data.query_id}`}>Consulta reproducible (JSON)</a></div>
      </section>}
      {!!release.expedients.length && <section className="world-cases"><h2>Expedientes disponibles</h2>
        <div>{release.expedients.map((id, index) => <button key={id} aria-pressed={id === active} onClick={() => setSelected(id)}>Expediente {index + 1}</button>)}</div></section>}
      {active && <CandidateDetail version={release.version} regionId={active} />}
      <p className="world-note">El DEM GLO‑30 mide la superficie e incluye vegetación y construcciones. Las candidatas son hipótesis de comparación topográfica. Datos de cobertura de ESA WorldCover y agua de EC JRC/Google.</p>
    </>}
  </section>;
}
