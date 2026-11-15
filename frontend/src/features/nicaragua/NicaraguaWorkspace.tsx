import { useEffect, useMemo, useState } from 'react';
import type { AtlasState } from '../../app/useAtlasState';
import { NicaraguaMap } from './NicaraguaMap';
import {
  DATA_URL, LEVEL_COLORS, coverText, decodeWindows, defaultReference, discoveries, levelLabel,
  nearKnown, placeText, rankWindows, referenceName, worldShare, type Lang, type NicaraguaData, type ReferenceInfo,
  type Scored, type Window,
} from './model';
import { dataText } from './english';
import { tr, warningText } from '../../i18n/lang';
import { useI18n } from '../../i18n/I18nProvider';
import './nicaragua.css';

type Load = { data?: NicaraguaData; error?: string };

function useNicaraguaData(): Load {
  const [state, setState] = useState<Load>({});
  useEffect(() => {
    const controller = new AbortController();
    fetch(`${import.meta.env.BASE_URL}${DATA_URL}`, { signal: controller.signal })
      .then(r => { if (!r.ok) throw new Error(tr(`No se pudo cargar el precálculo (HTTP ${r.status}).`, `The precomputation could not be loaded (HTTP ${r.status}).`)); return r.json(); })
      .then(data => { if (!controller.signal.aborted) setState({ data }); })
      .catch(error => { if (!controller.signal.aborted) setState({ error: error.message }); });
    return () => controller.abort();
  }, []);
  return state;
}

const num = (v: number | null | undefined, digits = 0, unit = '', lang: Lang = 'es') =>
  v == null ? '—' : `${v.toLocaleString(lang, { maximumFractionDigits: digits, minimumFractionDigits: digits })}${unit}`;
const pctText = (v: number, lang: Lang) => `${Math.round(v * 100)}${lang === 'en' ? '' : ' '}%`;

/** Reference name in the interface language; Earth analogues take their (translated) site name. */
function refLabel(data: NicaraguaData, r: ReferenceInfo, lang: Lang) {
  const site = r.site_id ? data.known_sites.sites.find(s => s.id === r.site_id) : undefined;
  return referenceName(r, lang, site && dataText(site.name, lang));
}

export function NicaraguaWorkspace({ state, update }: { state: AtlasState; update: (p: Partial<AtlasState>) => void }) {
  const { lang, t } = useI18n();
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
  if (!data || !ref) return <section className="nic-workspace"><p role="status">{t('Cargando análogos de Nicaragua…', 'Loading Nicaragua analogues…')}</p></section>;
  const planetary = data.references.filter(r => r.kind === 'planetary');
  const earth = data.references.filter(r => r.kind === 'earth_analog');
  const siteRow = (id: string | null) => ranked.find(r => r.region_id === id);
  const refSite = ref.site_id ? sites.find(s => s.id === ref.site_id) : undefined;
  const refName = refLabel(data, ref, lang);
  return (
    <section className="nic-workspace">
      <header className="u-heading">
        <div>
          <span className="u-kicker">REGOLITH / NICARAGUA</span>
          <h1>{t('Análogos planetarios en Nicaragua', 'Planetary analogues in Nicaragua')}</h1>
        </div>
        <p>
          {t('Volcanes de Nicaragua comparados con Marte y la Luna.', 'Volcanoes of Nicaragua compared with Mars and the Moon.')}
          <br />
          <span>{t('Sitios ya estudiados y lugares que el motor propone.', 'Sites already studied and places the engine suggests.')}</span>
        </p>
      </header>

      <div className="u-toolbar nic-toolbar">
        <label>
          {t('Comparar con', 'Compare with')}
          <select value={refId} onChange={e => update({ nicRef: e.target.value, regionId: '' })}>
            <optgroup label={t('Marte y Luna', 'Mars and Moon')}>
              {planetary.map(r => <option key={r.id} value={r.id}>{refLabel(data, r, lang)}</option>)}
            </optgroup>
            {earth.length > 0 && (
              <optgroup label={t('Análogos conocidos de Nicaragua', 'Known analogues in Nicaragua')}>
                {earth.map(r => <option key={r.id} value={r.id}>{lang === 'en' ? refLabel(data, r, lang) : r.name}</option>)}
              </optgroup>
            )}
          </select>
        </label>
        <div className="u-segment" role="group" aria-label={t('Ámbito', 'Scope')}>
          <button aria-pressed={scope === 'volcanic'} onClick={() => update({ nicScope: 'volcanic', regionId: '' })}>{t('Zonas volcánicas', 'Volcanic zones')}</button>
          <button aria-pressed={scope === 'all'} onClick={() => update({ nicScope: 'all', regionId: '' })}>{t('Todo el país', 'Whole country')}</button>
        </div>
        <p className="nic-toolbar-note">
          {ranked.length.toLocaleString(lang)} {t('ventanas de 3 km', '3 km windows')}
          {scope === 'volcanic'
            ? t(` a ${data.method.volcanic_radius_km} km o menos de un volcán`, ` within ${data.method.volcanic_radius_km} km of a volcano`)
            : t(' en Nicaragua', ' in Nicaragua')}
        </p>
      </div>

      {refSite && (
        <p className="nic-notice">
          {t(
            `Se buscan lugares con un relieve parecido al de ${refSite.name}, un análogo de Marte ya estudiado. Se omiten las ventanas a menos de ${ref.excluded_near_km} km del propio sitio.`,
            `Searching for places with relief similar to ${dataText(refSite.name, lang)}, an already studied Mars analogue. Windows within ${ref.excluded_near_km} km of the site itself are left out.`,
          )}
        </p>
      )}

      <div className="nic-layout">
        <NicaraguaMap data={data} ranked={ranked} water={water} scope={scope} selected={selected?.region_id} total={total}
          sites={sites} onSelect={id => update({ regionId: id })} />
        <aside className="nic-panel" aria-live="polite">
          {selected ? <Detail data={data} w={selected} n={ranked.length} total={total} site={selectedSite && dataText(selectedSite.name, lang)} refName={refName} /> : <p>{t('No hay ventanas con distancia en este ámbito.', 'No windows with a distance in this scope.')}</p>}
        </aside>
      </div>

      <section className="nic-section">
        <h2>{t('Lugares por descubrir', 'Places to discover')}</h2>
        <p className="nic-lead">
          {t(
            `Las ventanas más parecidas a «${refName}» que no coinciden con un análogo ya publicado, separadas al menos 4 km. Son hipótesis para revisar sobre el terreno, no análogos confirmados.`,
            `The windows most similar to “${refName}” that do not match an already published analogue, at least 4 km apart. They are hypotheses to check in the field, not confirmed analogues.`,
          )}
        </p>
        <ol className="nic-list">
          {found.map(w => (
            <li key={w.region_id}>
              <button aria-pressed={selected?.region_id === w.region_id} onClick={() => update({ regionId: w.region_id })}>
                <i style={{ background: LEVEL_COLORS[w.level] }} aria-hidden="true" />
                <span className="nic-rank">{w.rank}</span>
                <span className="nic-place"><strong>{placeText(data, w, lang)}</strong><small>{coverText(w, lang)}</small></span>
                <span className="nic-share">{worldShare(w.global_rank, total, lang)}<small>{t('relieve', 'relief')} {num(w.relief_p95_p05_m, 0, ' m', lang)} · {t('pendiente', 'slope')} {num(w.slope_240m_p50_deg, 1, '°', lang)}</small></span>
              </button>
            </li>
          ))}
        </ol>
      </section>

      <section className="nic-section">
        <h2>{t('Análogos conocidos', 'Known analogues')}</h2>
        <p className="nic-lead">
          {t(
            'Sitios estudiados en publicaciones como análogos de Marte. Lo son por su química y sus procesos hidrotermales; el motor solo dice si, además, su relieve se parece a la referencia elegida.',
            'Sites studied in publications as Mars analogues. They are analogues because of their chemistry and hydrothermal processes; the engine only tells whether their relief also resembles the chosen reference.',
          )}
        </p>
        <div className="nic-cards">
          {sites.map(s => {
            const row = siteRow(s.window_id);
            const isRef = ref.site_id === s.id;
            return (
              <article key={s.id} className="nic-card">
                <header>
                  <h3>{dataText(s.name, lang)}</h3>
                  <small>{t('Análogo de', 'Analogue of')} {dataText(s.analog_of, lang)}</small>
                </header>
                <p>{dataText(s.process, lang)}</p>
                <p className="nic-muted">{dataText(s.why, lang)}</p>
                <p className="nic-engine">
                  {isRef ? t('Es la referencia elegida.', 'This is the chosen reference.')
                    : row ? <>{t('Relieve: puesto', 'Relief: rank')} {row.rank} {t('de', 'of')} {ranked.length} · {worldShare(row.global_rank, total, lang)} <button className="nic-link" onClick={() => update({ regionId: row.region_id })}>{t('Ver en el mapa', 'Show on the map')}</button></>
                      : t('Su ventana no tiene distancia para esta referencia.', 'Its window has no distance for this reference.')}
                </p>
                <ul className="nic-sources">
                  {s.sources.map(id => {
                    const src = data.known_sites.sources[id];
                    return src ? <li key={id}><a href={src.url} target="_blank" rel="noreferrer">{dataText(src.citation, lang)}</a></li> : null;
                  })}
                </ul>
                <small className="nic-muted">{t('Coordenadas', 'Coordinates')}: {dataText(s.coordinates_source, lang)}</small>
              </article>
            );
          })}
        </div>
      </section>

      <details className="nic-method">
        <summary>{t('Cómo se calculó', 'How it was computed')}</summary>
        <ul>{data.method.notes.map(n => <li key={n}>{dataText(n, lang)}</li>)}</ul>
        {ref.warnings.length > 0 && <p className="nic-muted">{t('Avisos del motor', 'Engine warnings')}: {ref.warnings.map(w => warningText(w, lang)).join(' · ')}</p>}
        <p className="nic-muted">
          {t('Motor', 'Engine')} {data.engine.id} {t('ajustado el', 'fitted on')} {new Date(data.engine.fitted_at).toLocaleDateString(lang)}; {t('precálculo del', 'precomputed on')}{' '}
          {new Date(data.generated_at).toLocaleDateString(lang)}. {t('Volcanes', 'Volcanoes')}:{' '}
          <a href={data.volcanoes.source_url} target="_blank" rel="noreferrer">{dataText(data.volcanoes.source, lang)}</a>. {t('Contorno', 'Outline')}:{' '}
          <a href={data.boundary.properties.source_url} target="_blank" rel="noreferrer">{dataText(data.boundary.properties.source, lang)}</a>.
          {' '}{dataText(data.boundary.properties.note, lang)}
        </p>
      </details>
    </section>
  );
}

function Detail({ data, w, n, total, site, refName }: { data: NicaraguaData; w: Scored; n: number; total: number; site?: string; refName: string }) {
  const { lang, t } = useI18n();
  const facts: [string, string][] = [
    [t('Distancia del motor', 'Engine distance'), num(w.score, 3, '', lang)],
    [t('Cobertura de vistas', 'View coverage'), w.coverage == null ? '—' : pctText(w.coverage, lang)],
    [t('Relieve (p95−p5)', 'Relief (p95−p5)'), num(w.relief_p95_p05_m, 0, ' m', lang)],
    [t('Pendiente mediana', 'Median slope'), num(w.slope_240m_p50_deg, 1, '°', lang)],
    [t('Pendiente p90', 'Slope p90'), num(w.slope_240m_p90_deg, 1, '°', lang)],
    [t('Integral hipsométrica', 'Hypsometric integral'), num(w.hypsometric_integral, 2, '', lang)],
    [t('Árboles', 'Trees'), w.trees_fraction == null ? '—' : pctText(w.trees_fraction, lang)],
  ];
  return (
    <>
      <small className="u-kicker">{t('VENTANA SELECCIONADA', 'SELECTED WINDOW')}</small>
      <h2>{placeText(data, w, lang)}</h2>
      {site && <p className="nic-badge">{t('Análogo conocido', 'Known analogue')}: {site}</p>}
      <p className="nic-big">
        <span style={{ background: LEVEL_COLORS[w.level] }} aria-hidden="true" />
        {levelLabel(w.level, lang)} {t('a', 'to')} {refName}
      </p>
      <p>{t('Puesto', 'Rank')} {w.rank} {t('de', 'of')} {n} {t('aquí', 'here')} · {worldShare(w.global_rank, total, lang)}</p>
      <p className="nic-muted">{coverText(w, lang)}</p>
      <dl className="nic-facts">
        {facts.map(([k, v]) => <div key={k}><dt>{k}</dt><dd>{v}</dd></div>)}
      </dl>
      <p className="nic-muted">
        {w.latitude.toFixed(4)}° N, {Math.abs(w.longitude).toFixed(4)}° {t('O', 'W')} ·{' '}
        <a href={`https://www.openstreetmap.org/?mlat=${w.latitude}&mlon=${w.longitude}#map=14/${w.latitude}/${w.longitude}`} target="_blank" rel="noreferrer">{t('Ver en OpenStreetMap', 'View on OpenStreetMap')}</a>
      </p>
      <small className="nic-muted">{sourceText(w)}</small>
    </>
  );
}

function sourceText(w: Window) {
  if (w.source === 'atlas') return tr('Ventana del atlas global (una cada 10 km).', 'Window from the global atlas (one every 10 km).');
  if (w.source === 'known_site') return tr('Ventana centrada en el sitio conocido.', 'Window centred on the known site.');
  if (w.source === 'volcano_summit') return tr('Ventana centrada en la cumbre del volcán.', 'Window centred on the volcano summit.');
  return tr('Ventana añadida para Nicaragua (rejilla de 2 km cerca de los volcanes).', 'Window added for Nicaragua (2 km grid near the volcanoes).');
}
