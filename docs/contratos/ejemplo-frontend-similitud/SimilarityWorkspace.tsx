import { useEffect, useMemo, useState } from 'react';
import { useResource } from '../../data/api';
import { useSimilaritySearch } from '../../data/similarityApi';
import {
  BODY_LABELS, KIND_LABELS, STATUS_TEXT, VIEW_LABELS, buildRequest, defaultControls, noWeight, placeLabel,
  scoreWidth, topFeatures, usableViews, type Controls, type ReferenceCatalog, type ReferenceEntry,
  type SearchResponse, type SearchResult,
} from '../../domain/similarity';
import './similarity.css';

const num = (value: number, digits = 2) => value.toLocaleString('es', { maximumFractionDigits: digits });
const label = (view: string) => VIEW_LABELS[view] ?? view;

function ReferencePicker({ catalog, selected, choose }: { catalog: ReferenceCatalog; selected: string; choose: (id: string) => void }) {
  return <section aria-labelledby="sim-ref-title" className="sim-card">
    <h2 id="sim-ref-title">Sitio de referencia</h2>
    {(['Moon', 'Mars'] as const).map(body => {
      const refs = catalog.references.filter(r => r.body === body);
      return refs.length ? <div key={body} className="sim-group"><h3>{BODY_LABELS[body]}</h3>
        <ul>{refs.map(ref => <li key={ref.id}>
          <button aria-pressed={ref.id === selected} disabled={!ref.available} onClick={() => choose(ref.id)}>
            <strong>{ref.name}</strong>
            <small>{ref.kind ? KIND_LABELS[ref.kind] : 'Referencia'}{ref.available ? '' : ' · no disponible'}</small>
          </button></li>)}</ul></div> : null;
    })}
  </section>;
}

function ReferenceCard({ reference }: { reference: ReferenceEntry }) {
  return <section aria-labelledby="sim-card-title" className="sim-card">
    <h2 id="sim-card-title">{reference.name}</h2>
    <p className="sim-meta">{BODY_LABELS[reference.body]}{reference.kind ? ` · ${KIND_LABELS[reference.kind]}` : ''}
      {reference.center ? ` · ${placeLabel(reference.center.latitude, reference.center.longitude)}` : ''}</p>
    {!reference.available && <p role="alert">{reference.reason}</p>}
    <h3>Qué compara</h3>
    <ul className="sim-chips">{Object.entries(reference.views).map(([view, status]) =>
      <li key={view} className={`sim-chip ${status}`} title={STATUS_TEXT[status]}>{label(view)}<span className="sr-only"> · {STATUS_TEXT[status]}</span></li>)}</ul>
    {!!reference.limitations.length && <><h3>Dónde la analogía se rompe</h3>
      <ul className="sim-limits">{reference.limitations.map(text => <li key={text}>{text}</li>)}</ul></>}
    {!!reference.sources.length && <details><summary>Fuentes ({reference.sources.length})</summary>
      <ul>{reference.sources.map(id => <li key={id}><code>{id}</code></li>)}</ul></details>}
  </section>;
}

function WeightControls({ reference, controls, setControls, reset }: { reference: ReferenceEntry; controls: Controls; setControls: (c: Controls) => void; reset: () => void }) {
  const usable = usableViews(reference);
  const set = (patch: Partial<Controls>) => setControls({ ...controls, ...patch });
  return <section aria-labelledby="sim-weights-title" className="sim-card">
    <h2 id="sim-weights-title">Pesos por vista</h2>
    <p className="sim-note">Cada vista mide una dimensión distinta. Un peso 0 la apaga. Solo se usan las vistas con datos de la referencia.</p>
    <div className="sim-weights">{Object.keys(controls.weights).map(view => {
      const on = usable.includes(view); const w = controls.weights[view] ?? 0;
      return <label key={view} className={on ? undefined : 'sim-off'}>
        <span>{label(view)} <output>{num(w)}</output></span>
        <input type="range" min="0" max="1" step="0.05" value={w} disabled={!on}
          onChange={event => set({ touched: true, weights: { ...controls.weights, [view]: Number(event.target.value) } })} />
        {!on && <small>{STATUS_TEXT[reference.views[view] ?? 'not_fitted']}</small>}
      </label>;
    })}</div>
    <div className="sim-options">
      <label><input type="checkbox" checked={controls.onlyEligible} onChange={event => set({ onlyEligible: event.target.checked })} /> Solo ventanas elegibles</label>
      <label>Fusión<select value={controls.fusion} onChange={event => set({ fusion: event.target.value as Controls['fusion'] })}>
        <option value="weighted">Media ponderada</option><option value="rrf">Rangos (RRF)</option></select></label>
      <label>Vistas ausentes<select value={controls.missingPolicy} onChange={event => set({ missingPolicy: event.target.value as Controls['missingPolicy'] })}>
        <option value="neutral">Neutral</option><option value="renormalize">Repartir el peso</option><option value="require">Exigir todas</option></select></label>
      <button onClick={reset} disabled={!controls.touched && controls.onlyEligible && controls.fusion === 'weighted' && controls.missingPolicy === 'neutral'}>Restablecer</button>
    </div>
  </section>;
}

function ResultsMap({ results, selected, choose }: { results: SearchResult[]; selected: string; choose: (id: string) => void }) {
  return <figure className="sim-map"><svg viewBox="0 0 720 360" role="group" aria-label="Mapa de las ventanas terrestres más parecidas">
    <image href="/textures/earth.png" width="720" height="360" opacity=".5" />
    {results.map(row => <circle key={row.region_id} cx={(row.longitude + 180) * 2} cy={(90 - row.latitude) * 2}
      r={row.region_id === selected ? 6.5 : 4} tabIndex={0} role="button" aria-label={`Candidata ${row.rank}, ${placeLabel(row.latitude, row.longitude)}`}
      className={row.region_id === selected ? 'selected' : undefined} onClick={() => choose(row.region_id)}
      onKeyDown={event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); choose(row.region_id); } }} />)}
  </svg></figure>;
}

function ResultDetail({ row }: { row: SearchResult }) {
  return <section aria-labelledby="sim-detail-title" className="sim-card">
    <h3 id="sim-detail-title">Candidata {row.rank} · {placeLabel(row.latitude, row.longitude)}</h3>
    <p className="sim-note">Distancia {num(row.score, 3)} (entre {num(row.score_low, 3)} y {num(row.score_high, 3)}) · cobertura de pesos {num(row.coverage * 100, 0)} %.
      {' '}<a href={`/api/atlas/candidates/${encodeURIComponent(row.region_id)}`}>Ficha de la ventana (JSON)</a></p>
    <ul className="sim-views">{Object.entries(row.views).map(([view, v]) => <li key={view}>
      <div><strong>{label(view)}</strong> · {v.available && v.distance !== null ? `distancia ${num(v.distance, 3)}` : 'sin dato en esta ventana'} · peso {num(v.weight * 100, 0)} %
        {v.pool_percentile !== undefined && ` · más cercana que el ${num((1 - v.pool_percentile) * 100, 1)} % de las candidatas`}</div>
      {topFeatures(v).map(([feature, f]) => <div key={feature} className="sim-feature"><code>{feature}</code> candidata {num(f.candidate)} · referencia {f.reference === null ? '—' : num(f.reference)} · aporta {num(f.share * 100, 0)} %</div>)}
    </li>)}</ul>
  </section>;
}

function Results({ data, stale, selected, setSelected }: { data: SearchResponse; stale: boolean; selected: string; setSelected: (id: string) => void }) {
  const active = data.results.find(r => r.region_id === selected) ?? data.results[0];
  return <section aria-labelledby="sim-results-title" className={`sim-results${stale ? ' stale' : ''}`} aria-busy={stale}>
    <h2 id="sim-results-title">Ventanas terrestres más parecidas</h2>
    <p className="sim-note">{num(data.candidates_ranked, 0)} candidatas evaluadas de {num(data.candidates_in_pool, 0)} · una distancia menor indica mayor parecido · la barra muestra el intervalo por vistas ausentes.</p>
    {data.results.length ? <>
      <ResultsMap results={data.results} selected={active?.region_id ?? ''} choose={setSelected} />
      <div className="sim-table"><table><thead><tr><th scope="col">Orden</th><th scope="col">Ubicación</th><th scope="col">Distancia</th><th scope="col">Intervalo</th><th scope="col">Cobertura</th><th scope="col">Sin dato</th></tr></thead>
        <tbody>{data.results.map(row => { const bar = scoreWidth(row.score_low, row.score_high); return <tr key={row.region_id} className={row.region_id === active?.region_id ? 'selected' : undefined}>
          <td>{row.rank}</td>
          <td><button aria-pressed={row.region_id === active?.region_id} onClick={() => setSelected(row.region_id)}>{placeLabel(row.latitude, row.longitude)}</button></td>
          <td>{num(row.score, 3)}</td>
          <td><span className="sim-range" role="img" aria-label={`entre ${num(row.score_low, 3)} y ${num(row.score_high, 3)}`}><i style={{ left: `${bar.left}%`, width: `${bar.width}%` }} /></span></td>
          <td>{num(row.coverage * 100, 0)} %</td>
          <td>{row.missing_views.length ? row.missing_views.map(label).join(', ') : '—'}</td></tr>; })}</tbody></table></div>
      {active && <ResultDetail row={active} />}
    </> : <p>Ninguna ventana cumple estas condiciones. Prueba a incluir las no elegibles o a cambiar la política de vistas ausentes.</p>}
  </section>;
}

/** `referenceId` and `onReferenceChange` are the only coupling with the host app (a URL param, a store, local state). */
export function SimilarityWorkspace({ referenceId: requested, onReferenceChange }: { referenceId: string; onReferenceChange: (id: string) => void }) {
  const catalog = useResource<ReferenceCatalog>('/api/similarity/references');
  const refs = catalog.data?.references ?? [];
  const reference = refs.find(r => r.id === requested && r.available) ?? refs.find(r => r.available);
  const [controls, setControls] = useState<Controls>(() => defaultControls(undefined, undefined));
  const [selected, setSelected] = useState('');
  const referenceId = reference?.id ?? '';
  useEffect(() => { setControls(defaultControls(reference, catalog.data)); setSelected(''); },
    // Reset the controls only when the reference or the catalogue changes, not on each slider move.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [referenceId, catalog.data]);
  const request = useMemo(() => reference ? buildRequest(reference.id, controls) : null, [reference, controls]);
  const blocked = !!request && !!reference && noWeight(request, usableViews(reference));
  const search = useSimilaritySearch(blocked ? null : request);
  const data = search.data && search.data.reference.id === reference?.id ? search.data : undefined;
  return <section className="sim-workspace" aria-labelledby="sim-title">
    <header><p className="sim-kicker">LUNA · MARTE → TIERRA</p><h1 id="sim-title">Buscar análogos en la Tierra</h1>
      <p>Elige un sitio de la Luna o de Marte y mira qué ventanas de 3 × 3 km de la Tierra se le parecen, y en qué dimensiones.</p></header>
    {catalog.error && <p role="alert">{catalog.error} <button onClick={catalog.retry}>Reintentar</button></p>}
    {catalog.loading && <p role="status">Cargando referencias…</p>}
    {catalog.data && <>
      {catalog.data.engine_status.includes('pending') && <p className="sim-banner" role="note"><strong>Experimental.</strong> Los pesos son un valor declarado, todavía sin calibrar con revisión ciega, y solo dos vistas están ajustadas.</p>}
      <div className="sim-layout">
        <aside><ReferencePicker catalog={catalog.data} selected={referenceId} choose={onReferenceChange} />
          {reference && <ReferenceCard reference={reference} />}</aside>
        <div>
          {reference && <WeightControls reference={reference} controls={controls} setControls={setControls} reset={() => setControls(defaultControls(reference, catalog.data))} />}
          <p className="sim-status" role="status" aria-live="polite">
            {blocked ? 'Todos los pesos son 0: sube al menos uno.' : search.loading ? (search.stale ? 'Actualizando resultados…' : 'Buscando…')
              : data ? `${num(data.timings.total_ms, 0)} ms${data.timings.cache_hit ? ' (en caché)' : ''} · consulta ${data.query_id.slice(0, 8)}` : ''}</p>
          {search.error && <p role="alert">{search.error} <button onClick={search.retry}>Reintentar</button></p>}
          {!!data?.warnings.length && <ul className="sim-warnings" aria-label="Avisos del motor">{data.warnings.map(w => <li key={w}>{w}</li>)}</ul>}
          {data && <Results data={data} stale={search.stale || search.loading} selected={selected} setSelected={setSelected} />}
        </div>
      </div>
      <p className="sim-note">Una ventana parecida en estas dimensiones no es un análogo validado: la gravedad, la atmósfera y la radiación no se reproducen en la Tierra, y las vistas sin dato no puntúan.</p>
    </>}
  </section>;
}
