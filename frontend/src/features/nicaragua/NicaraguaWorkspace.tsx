import { useEffect, useMemo, useState } from 'react';
import type { AtlasState } from '../../app/useAtlasState';
import { NicaraguaMap } from './NicaraguaMap';
import {
  DATA_URL, LEVEL_COLORS, LEVEL_LABELS, coverText, decodeWindows, defaultReference, discoveries,
  nearKnown, placeText, rankWindows, referenceName, worldShare, type NicaraguaData, type Scored, type Window,
} from './model';
import './nicaragua.css';

type Load = { data?: NicaraguaData; error?: string };

function useNicaraguaData(): Load {
  const [state, setState] = useState<Load>({});
  useEffect(() => {
    const controller = new AbortController();
    fetch(`${import.meta.env.BASE_URL}${DATA_URL}`, { signal: controller.signal })
      .then(r => { if (!r.ok) throw new Error(`No se pudo cargar el precálculo (HTTP ${r.status}).`); return r.json(); })
      .then(data => { if (!controller.signal.aborted) setState({ data }); })
      .catch(error => { if (!controller.signal.aborted) setState({ error: error.message }); });
    return () => controller.abort();
  }, []);
  return state;
}

const num = (v: number | null | undefined, digits = 0, unit = '') =>
  v == null ? '—' : `${v.toLocaleString('es', { maximumFractionDigits: digits, minimumFractionDigits: digits })}${unit}`;

export function NicaraguaWorkspace({ state, update }: { state: AtlasState; update: (p: Partial<AtlasState>) => void }) {
  const { data, error } = useNicaraguaData();
  const windows = useMemo(() => (data ? decodeWindows(data) : []), [data]);
  const scope = state.nicScope;
  const refId = data && data.rankings[state.nicRef] ? state.nicRef : data ? defaultReference(data) : '';
  const ref = data?.references.find(r => r.id === refId);
  const ranked = useMemo(() => (data ? rankWindows(data, windows, refId, scope) : []), [data, windows, refId, scope]);
  const sites = data?.known_sites.sites ?? [];
  const found = useMemo(() => discoveries(ranked, sites), [ranked, sites]);
  const water = useMemo(
    () => windows.filter(w => w.water_dominated && (scope === 'all' || w.volcanic || (w.volcano_km ?? 99) <= 12)),
    [windows, scope],
  );
  const total = data?.engine.earth_windows_ranked ?? 0;
  const selected = ranked.find(r => r.region_id === state.regionId) ?? found[0];
  const selectedSite = selected ? nearKnown(selected, sites) : undefined;
  if (error) return <section className="nic-workspace"><p className="nic-error" role="alert">{error}</p></section>;
  if (!data || !ref) return <section className="nic-workspace"><p role="status">Cargando análogos de Nicaragua…</p></section>;
  const planetary = data.references.filter(r => r.kind === 'planetary');
  const earth = data.references.filter(r => r.kind === 'earth_analog');
  const siteRow = (id: string | null) => ranked.find(r => r.region_id === id);
  const refSite = ref.site_id ? sites.find(s => s.id === ref.site_id) : undefined;
  return (
    <section className="nic-workspace">
      <header className="u-heading">
        <div>
          <span className="u-kicker">REGOLITH / NICARAGUA</span>
          <h1>Análogos planetarios en Nicaragua</h1>
        </div>
        <p>
          Volcanes de Nicaragua comparados con Marte y la Luna.
          <br />
          <span>Sitios ya estudiados y lugares que el motor propone.</span>
        </p>
      </header>

      <div className="u-toolbar nic-toolbar">
        <label>
          Comparar con
          <select value={refId} onChange={e => update({ nicRef: e.target.value, regionId: '' })}>
            <optgroup label="Marte y Luna">
              {planetary.map(r => <option key={r.id} value={r.id}>{referenceName(r)}</option>)}
            </optgroup>
            {earth.length > 0 && (
              <optgroup label="Análogos conocidos de Nicaragua">
                {earth.map(r => <option key={r.id} value={r.id}>{r.name}</option>)}
              </optgroup>
            )}
          </select>
        </label>
        <div className="u-segment" role="group" aria-label="Ámbito">
          <button aria-pressed={scope === 'volcanic'} onClick={() => update({ nicScope: 'volcanic', regionId: '' })}>Zonas volcánicas</button>
          <button aria-pressed={scope === 'all'} onClick={() => update({ nicScope: 'all', regionId: '' })}>Todo el país</button>
        </div>
        <p className="nic-toolbar-note">
          {ranked.length.toLocaleString('es')} ventanas de 3 km
          {scope === 'volcanic' ? ` a ${data.method.volcanic_radius_km} km o menos de un volcán` : ' en Nicaragua'}
        </p>
      </div>

      {refSite && (
        <p className="nic-notice">
          Se buscan lugares con un relieve parecido al de {refSite.name}, un análogo de Marte ya estudiado. Se omiten las
          ventanas a menos de {ref.excluded_near_km} km del propio sitio.
        </p>
      )}

      <div className="nic-layout">
        <NicaraguaMap data={data} ranked={ranked} water={water} scope={scope} selected={selected?.region_id} total={total}
          sites={sites} onSelect={id => update({ regionId: id })} />
        <aside className="nic-panel" aria-live="polite">
          {selected ? <Detail data={data} w={selected} n={ranked.length} total={total} site={selectedSite?.name} refName={referenceName(ref)} /> : <p>No hay ventanas con distancia en este ámbito.</p>}
        </aside>
      </div>

      <section className="nic-section">
        <h2>Lugares por descubrir</h2>
        <p className="nic-lead">
          Las ventanas más parecidas a «{referenceName(ref)}» que no coinciden con un análogo ya publicado, separadas al menos 4 km.
          Son hipótesis para revisar sobre el terreno, no análogos confirmados.
        </p>
        <ol className="nic-list">
          {found.map(w => (
            <li key={w.region_id}>
              <button aria-pressed={selected?.region_id === w.region_id} onClick={() => update({ regionId: w.region_id })}>
                <i style={{ background: LEVEL_COLORS[w.level] }} aria-hidden="true" />
                <span className="nic-rank">{w.rank}</span>
                <span className="nic-place"><strong>{placeText(data, w)}</strong><small>{coverText(w)}</small></span>
                <span className="nic-share">{worldShare(w.global_rank, total)}<small>relieve {num(w.relief_p95_p05_m, 0, ' m')} · pendiente {num(w.slope_240m_p50_deg, 1, '°')}</small></span>
              </button>
            </li>
          ))}
        </ol>
      </section>

      <section className="nic-section">
        <h2>Análogos conocidos</h2>
        <p className="nic-lead">
          Sitios estudiados en publicaciones como análogos de Marte. Lo son por su química y sus procesos hidrotermales; el
          motor solo dice si, además, su relieve se parece a la referencia elegida.
        </p>
        <div className="nic-cards">
          {sites.map(s => {
            const row = siteRow(s.window_id);
            const isRef = ref.site_id === s.id;
            return (
              <article key={s.id} className="nic-card">
                <header>
                  <h3>{s.name}</h3>
                  <small>Análogo de {s.analog_of}</small>
                </header>
                <p>{s.process}</p>
                <p className="nic-muted">{s.why}</p>
                <p className="nic-engine">
                  {isRef ? 'Es la referencia elegida.'
                    : row ? <>Relieve: puesto {row.rank} de {ranked.length} · {worldShare(row.global_rank, total)} <button className="nic-link" onClick={() => update({ regionId: row.region_id })}>Ver en el mapa</button></>
                      : 'Su ventana no tiene distancia para esta referencia.'}
                </p>
                <ul className="nic-sources">
                  {s.sources.map(id => {
                    const src = data.known_sites.sources[id];
                    return src ? <li key={id}><a href={src.url} target="_blank" rel="noreferrer">{src.citation}</a></li> : null;
                  })}
                </ul>
                <small className="nic-muted">Coordenadas: {s.coordinates_source}</small>
              </article>
            );
          })}
        </div>
      </section>

      <details className="nic-method">
        <summary>Cómo se calculó</summary>
        <ul>{data.method.notes.map(n => <li key={n}>{n}</li>)}</ul>
        {ref.warnings.length > 0 && <p className="nic-muted">Avisos del motor: {ref.warnings.join(' · ')}</p>}
        <p className="nic-muted">
          Motor {data.engine.id} ajustado el {new Date(data.engine.fitted_at).toLocaleDateString('es')}; precálculo del{' '}
          {new Date(data.generated_at).toLocaleDateString('es')}. Volcanes:{' '}
          <a href={data.volcanoes.source_url} target="_blank" rel="noreferrer">{data.volcanoes.source}</a>. Contorno:{' '}
          <a href={data.boundary.properties.source_url} target="_blank" rel="noreferrer">{data.boundary.properties.source}</a>.
          {' '}{data.boundary.properties.note}
        </p>
      </details>
    </section>
  );
}

function Detail({ data, w, n, total, site, refName }: { data: NicaraguaData; w: Scored; n: number; total: number; site?: string; refName: string }) {
  const facts: [string, string][] = [
    ['Distancia del motor', num(w.score, 3)],
    ['Cobertura de vistas', w.coverage == null ? '—' : `${Math.round(w.coverage * 100)} %`],
    ['Relieve (p95−p5)', num(w.relief_p95_p05_m, 0, ' m')],
    ['Pendiente mediana', num(w.slope_240m_p50_deg, 1, '°')],
    ['Pendiente p90', num(w.slope_240m_p90_deg, 1, '°')],
    ['Integral hipsométrica', num(w.hypsometric_integral, 2)],
    ['Árboles', w.trees_fraction == null ? '—' : `${Math.round(w.trees_fraction * 100)} %`],
  ];
  return (
    <>
      <small className="u-kicker">VENTANA SELECCIONADA</small>
      <h2>{placeText(data, w)}</h2>
      {site && <p className="nic-badge">Análogo conocido: {site}</p>}
      <p className="nic-big">
        <span style={{ background: LEVEL_COLORS[w.level] }} aria-hidden="true" />
        {LEVEL_LABELS[w.level]} a {refName}
      </p>
      <p>Puesto {w.rank} de {n} aquí · {worldShare(w.global_rank, total)}</p>
      <p className="nic-muted">{coverText(w)}</p>
      <dl className="nic-facts">
        {facts.map(([k, v]) => <div key={k}><dt>{k}</dt><dd>{v}</dd></div>)}
      </dl>
      <p className="nic-muted">
        {w.latitude.toFixed(4)}° N, {Math.abs(w.longitude).toFixed(4)}° O ·{' '}
        <a href={`https://www.openstreetmap.org/?mlat=${w.latitude}&mlon=${w.longitude}#map=14/${w.latitude}/${w.longitude}`} target="_blank" rel="noreferrer">Ver en OpenStreetMap</a>
      </p>
      <small className="nic-muted">{sourceText(w)}</small>
    </>
  );
}

function sourceText(w: Window) {
  if (w.source === 'atlas') return 'Ventana del atlas global (una cada 10 km).';
  if (w.source === 'known_site') return 'Ventana centrada en el sitio conocido.';
  if (w.source === 'volcano_summit') return 'Ventana centrada en la cumbre del volcán.';
  return 'Ventana añadida para Nicaragua (rejilla de 2 km cerca de los volcanes).';
}
