import { useEffect, useMemo, useState } from "react";
import { countryAt } from "../../domain/countries";
import { loadCountries } from "../../data/countries";
import type { AtlasState } from "../../app/useAtlasState";
import {
  references,
  featureRows,
  features,
  number,
  pct,
  distance,
  signed,
  location,
  eligibility,
  selectedMatch,
  viewNames,
  type LoadedSearch,
  type Match,
} from "../simulation/model";
import { EngineWarnings } from "../simulation/EnginePanels";
import { CandidateRecord } from "../simulation/CandidateRecord";
import { useReferenceCatalog } from "../../data/similarityApi";
import {
  buildRequest,
  defaultControls,
  noWeight,
  placeLabel,
  similarity,
  usableViews,
  type Controls,
} from "../../domain/similarity";
import { SIMPLE_CONTROLS, useEngineSearch, type EngineSearch } from "../search/useEngineSearch";
import { SearchControls } from "../search/SearchControls";
import { ScenePanel } from "./ScenePanel";
import { Profiles } from "./Profiles";
import {
  candidateFocus,
  exactSite,
  sharedRange,
  type VisualSite,
} from "./terrainModel";
import { prefetchGrids, useCatalog, useGrid } from "./resources";
import { useI18n } from "../../i18n/I18nProvider";
import type { Lang } from "../../i18n/lang";
import "./unified.css";

const EMPTY: never[] = [];
type Reference = (typeof references)[number];
type ReferenceId = AtlasState["reference"];

/** Plain-language description of each study site, for the public mode. */
const SITE_TEXT: Record<Lang, Record<ReferenceId, string>> = {
  es: {
    jezero: "Cráter con un antiguo delta de río",
    "haworth-fondo": "Fondo de un cráter junto al polo sur",
    "de-gerlache-cresta": "Cresta junto al polo sur",
  },
  en: {
    jezero: "Crater with an ancient river delta",
    "haworth-fondo": "Crater floor near the south pole",
    "de-gerlache-cresta": "Ridge near the south pole",
  },
};
const BODY_TEXT: Record<Lang, Record<"Mars" | "Moon" | "Earth", string>> = {
  es: { Mars: "Marte", Moon: "Luna", Earth: "Tierra" },
  en: { Mars: "Mars", Moon: "Moon", Earth: "Earth" },
};

export function UnifiedWorkspace({
  state,
  update,
}: {
  state: AtlasState;
  update: (patch: Partial<AtlasState>) => void;
}) {
  const { lang, t } = useI18n();
  const science = state.science;
  const ref = references.find((r) => r.id === state.reference)!;
  // --- search: the same endpoint in both modes; the scientific one sends its own parameters.
  const refCatalog = useReferenceCatalog();
  const refEntry = refCatalog.data?.references.find((r) => r.id === ref.id);
  const initial = useMemo(() => defaultControls(refEntry, refCatalog.data), [refEntry, refCatalog.data]);
  const [custom, setCustom] = useState<{ reference: ReferenceId; controls: Controls }>();
  const controls = custom?.reference === ref.id ? custom.controls : initial;
  const blocked = science && noWeight(buildRequest(ref.id, controls), usableViews(refEntry));
  const search = useEngineSearch(ref.id, science ? (blocked ? null : controls) : SIMPLE_CONTROLS);
  const loaded = search.loaded,
    data = loaded?.data,
    row = selectedMatch(data, state.regionId),
    rows = data?.results ?? EMPTY;
  const [countries, setCountries] = useState<Awaited<ReturnType<typeof loadCountries>>>([]);
  useEffect(() => { loadCountries().then(setCountries).catch(() => {}); }, []);
  const countryNames = useMemo(() => new Map(rows.map(r => [r.region_id, countryAt(countries, r.latitude, r.longitude, lang)])), [countries, rows, lang]);
  const country = row ? countryNames.get(row.region_id) : undefined;
  // --- scenes
  const [overview, setOverview] = useState(false),
    catalog = useCatalog(),
    kind = state.surfaceMode === "regional" ? "regional" : "local";
  useEffect(() => {
    if (data?.results[0] && !data.results.some((r) => r.region_id === state.regionId))
      update({ regionId: data.results[0].region_id });
  }, [data, state.regionId, update]);
  const leftSite = exactSite(catalog.data, ref.id, ref.longitude, ref.latitude, kind),
    rightSite = row ? exactSite(catalog.data, row.region_id, row.longitude, row.latitude, kind) : undefined;
  useEffect(() => {
    if (ref.id !== "jezero" || !catalog.data || !data) return;
    const sites = data.results.slice(0, 10).flatMap((candidate) =>
      (["regional", "local"] as const).map((scale) =>
        exactSite(catalog.data, candidate.region_id, candidate.longitude, candidate.latitude, scale),
      ).filter((site): site is VisualSite => !!site),
    );
    return prefetchGrids(sites);
  }, [ref.id, catalog.data, data]);
  const left = useGrid(leftSite, state.surfaceMode !== "space"),
    right = useGrid(rightSite, state.surfaceMode !== "space");
  const range = useMemo(
    () => sharedRange([left.grid, right.grid], state.visualLayer),
    [left.grid, right.grid, state.visualLayer],
  );
  const profileRange = useMemo(() => sharedRange([left.grid, right.grid], "elevation"), [left.grid, right.grid]);
  const refMarks = useMemo(() => references.filter((r) => r.body === ref.body).map((r) => ({ ...r })), [ref.body]);
  const earthMarks = useMemo(
    () => rows.map((r) => ({ id: r.region_id, name: String(r.rank), longitude: r.longitude, latitude: r.latitude })),
    [rows],
  );
  const [focusToken, setFocusToken] = useState(0);
  const chooseCandidate = (regionId: string) => {
    update({ regionId });
    setFocusToken((n) => n + 1);
  };
  const changeRef = (reference: ReferenceId) => {
    setOverview(false);
    update({ reference, regionId: "", method: "engine" });
  };
  const missing = (id: string, error?: string) =>
    error ||
    catalog.error ||
    (catalog.data?.missing[id]
      ? t("No hay un derivado válido de esta ubicación en el catálogo.", "The catalog has no valid derivative for this location.")
      : catalog.data
        ? t("Esta ubicación no tiene un DEM preparado para el navegador.", "This location has no DEM prepared for the browser.")
        : t("Cargando catálogo de relieve…", "Loading relief catalog…"));
  const earthLabel = BODY_TEXT[lang].Earth;
  const earthName = row
    ? science
      ? t(`Tierra · candidata ${row.rank}`, `Earth · candidate ${row.rank}`)
      : t(`Tierra · lugar ${row.rank}`, `Earth · place ${row.rank}`)
    : earthLabel;
  return (
    <section className={`unified-workspace${science ? " is-science" : " is-simple"}`}>
      <header className="u-heading">
        <div>
          {science && <span className="u-kicker">{t("REGOLITH / MODO CIENTÍFICO", "REGOLITH / SCIENTIFIC MODE")}</span>}
          <h1>{science ? t("Explorar y comparar", "Explore and compare") : t("¿Dónde se parece la Tierra a otros mundos?", "Where does Earth look like other worlds?")}</h1>
        </div>
        {!science && (
          <p>
            {t("Elige un lugar de Marte o de la Luna.", "Pick a place on Mars or the Moon.")}
            <br />
            <span>{t("Te mostramos los terrenos de la Tierra con una forma más parecida.", "We show you the terrains on Earth with the most similar shape.")}</span>
          </p>
        )}
      </header>
      <div className="u-toolbar">
        <div className="u-segment" role="group" aria-label={t("Cuerpo de referencia", "Reference body")}>
          {(["Mars", "Moon"] as const).map((body) => (
            <button
              key={body}
              aria-pressed={ref.body === body}
              onClick={() => {
                if (ref.body === body) return;
                changeRef(references.find((r) => r.body === body)!.id);
                setOverview(true);
                update({ surfaceMode: "space" });
              }}
            >
              <i className={`u-dot u-${body}`} />
              {BODY_TEXT[lang][body]}
            </button>
          ))}
        </div>
        <div className="u-sites" role="group" aria-label={t("Lugar de estudio", "Study site")}>
          {references
            .filter((r) => r.body === ref.body)
            .map((r) => (
              <button key={r.id} aria-pressed={r.id === ref.id} onClick={() => changeRef(r.id)}>
                <strong>{r.name}</strong>
                <small>{SITE_TEXT[lang][r.id]}</small>
              </button>
            ))}
        </div>
        <div className="u-scales" role="group" aria-label={t("Escala de estudio", "Study scale")}>
          {(
            [
              { id: "space", label: science ? t("Órbita", "Orbit") : t("Planeta", "Planet") },
              { id: "regional", label: science ? t("Relieve regional", "Regional relief") : t("Región", "Region") },
              { id: "mesh", label: science ? t("Superficie local", "Local surface") : t("De cerca", "Up close") },
            ] as const
          ).map((m) => (
            <button
              key={m.id}
              aria-pressed={state.surfaceMode === m.id}
              onClick={() => {
                setOverview(false);
                update({ surfaceMode: m.id });
              }}
            >
              {m.label}
            </button>
          ))}
        </div>
        {science && state.surfaceMode === "mesh" && (
          <label>
            {t("Capa activa", "Active layer")}
            <select
              value={state.visualLayer}
              onChange={(e) => update({ visualLayer: e.target.value as AtlasState["visualLayer"] })}
            >
              <option value="elevation">{t("Altura relativa · m", "Relative height · m")}</option>
              <option value="slope">{t("Pendiente · °", "Slope · °")}</option>
              <option disabled>{t("Rugosidad · sin capa comparable", "Roughness · no comparable layer")}</option>
            </select>
          </label>
        )}
        {science && (state.surfaceMode !== "space" || state.exaggeration !== 1) && (
          <label className="u-exaggeration">
            {t("Altura", "Height")}
            <select
              aria-label={t("Exageración vertical", "Vertical exaggeration")}
              value={state.exaggeration}
              onChange={(e) => update({ exaggeration: Number(e.target.value) })}
            >
              {[1, 1.5, 2, 2.5, 3, 3.5, 4, 4.5, 5].map((n) => (
                <option key={n} value={n}>
                  {n}×{n === 1 ? t(" · escala real", " · true scale") : ""}
                </option>
              ))}
            </select>
          </label>
        )}
      </div>
      <div className="u-layout">
        <div className="u-maps-area">
          <div className="u-pair-labels">
            <span>
              <i className={`u-dot u-${ref.body}`} />
              {ref.name} <em>· {BODY_TEXT[lang][ref.body]}</em>
              <small>{science ? location(ref) : placeLabel(ref.latitude, ref.longitude)}</small>
            </span>
            <span>
              <i className="u-dot u-Earth" />
              {row ? earthName : earthLabel}{country && ` · ${country}`}
              <small>
                {row
                  ? science
                    ? location(row)
                    : placeLabel(row.latitude, row.longitude)
                  : t("Elige un lugar de la lista", "Pick a place from the list")}
              </small>
            </span>
          </div>
          <div className="u-pair">
            <ScenePanel
              body={ref.body}
              name={ref.name}
              longitude={ref.longitude}
              latitude={ref.latitude}
              marks={refMarks}
              selected={overview ? "" : ref.id}
              choose={(id) => changeRef(id as ReferenceId)}
              mode={state.surfaceMode}
              grid={left.grid}
              layer={state.visualLayer}
              range={range}
              exaggeration={state.exaggeration}
              overview={overview}
              pending={!catalog.error && !left.error && (!catalog.data || (!!leftSite && !left.grid))}
              missing={missing(ref.id, left.error)}
            />
            <ScenePanel
              body="Earth"
              name={row ? t(`lugar ${row.rank}`, `place ${row.rank}`) : t("lugares terrestres", "places on Earth")}
              longitude={row?.longitude ?? candidateFocus(rows)[0]}
              latitude={row?.latitude ?? candidateFocus(rows)[1]}
              marks={earthMarks}
              selected={row?.region_id ?? ""}
              choose={chooseCandidate}
              focusToken={focusToken}
              mode={state.surfaceMode}
              grid={right.grid}
              layer={state.visualLayer}
              range={range}
              exaggeration={state.exaggeration}
              pending={!!row && !catalog.error && !right.error && (!catalog.data || (!!rightSite && !right.grid))}
              missing={row ? missing(row.region_id, right.error) : t("Elige un lugar de la lista.", "Pick a place from the list.")}
            />
          </div>
          <SceneNotes
            science={science}
            state={state}
            range={range}
            complete={!!left.grid && !!right.grid}
            leftSite={leftSite}
            rightSite={rightSite}
            refName={ref.name}
          />
          {science && state.surfaceMode === "mesh" && (
            <Profiles left={left.grid} right={right.grid} range={profileRange} names={[ref.name, earthName]} />
          )}
        </div>
        <div className="u-side">
          {science && (
            <SearchControls
              reference={refEntry}
              catalog={refCatalog.data}
              catalogError={refCatalog.error}
              controls={controls}
              setControls={(next) => setCustom({ reference: ref.id, controls: next })}
              reset={() => setCustom(undefined)}
              blocked={blocked}
              search={search}
            />
          )}
          <aside className="u-inspector" aria-label={t("Comparación seleccionada", "Selected comparison")} aria-busy={search.loading}>
            {science ? (
              <ScienceInspector refInfo={ref} row={row} loaded={loaded} search={search} leftSite={leftSite} rightSite={rightSite} />
            ) : (
              <SimpleInspector refInfo={ref} row={row} loaded={loaded} search={search} country={country} />
            )}
          </aside>
        </div>
        <section className="u-candidates" aria-label={t("Lugares parecidos en la Tierra", "Similar places on Earth")} aria-busy={search.loading}>
          <header>
            <h2>
              {science ? t("Candidatas en la Tierra", "Candidates on Earth") : t("Lugares parecidos en la Tierra", "Similar places on Earth")}{" "}
              <span>{rows.length.toString().padStart(2, "0")}</span>
            </h2>
            <small>{search.stale ? t("Actualizando…", "Updating…") : t("Toca un lugar o un marcador del globo", "Tap a place or a marker on the globe")}</small>
          </header>
          {rows.length > 0 ? (
            <div className={`u-candidate-list${search.stale ? " is-stale" : ""}`}>
              {rows.map((r) => (
                <button
                  key={r.region_id}
                  aria-pressed={row?.region_id === r.region_id}
                  onClick={() => chooseCandidate(r.region_id)}
                >
                  <b>{r.rank.toString().padStart(2, "0")}</b>
                  {science ? (
                    <>
                      <span>
                        {countryNames.get(r.region_id) || location(r)}
                        <small>{countryNames.get(r.region_id) ? `${location(r)} · ` : ''}{eligibility(r.scenario_eligibility)}</small>
                      </span>
                      <strong>
                        {distance(r.score)}
                        <small>{t("distancia", "distance")}</small>
                      </strong>
                    </>
                  ) : (
                    <>
                      <span>{countryNames.get(r.region_id) || placeLabel(r.latitude, r.longitude)}{countryNames.get(r.region_id) && <small>{placeLabel(r.latitude, r.longitude)}</small>}</span>
                      <strong>
                        {pct(similarity(r.score))}
                        <small>{t("parecido", "similar")}</small>
                      </strong>
                    </>
                  )}
                </button>
              ))}
            </div>
          ) : (
            <p className="u-empty">
              {search.loading
                ? t("Buscando lugares parecidos…", "Searching for similar places…")
                : search.error
                  ? t("No hay resultados para mostrar.", "No results to show.")
                  : t("La búsqueda no encontró lugares con estos parámetros.", "The search found no places with these parameters.")}
            </p>
          )}
          {countries.length > 0 && <small>{t("Países: límites aproximados de", "Countries: approximate boundaries from")} <a href="https://www.naturalearthdata.com/" target="_blank" rel="noreferrer">Natural Earth</a>.</small>}
        </section>
      </div>
    </section>
  );
}

function SearchState({ search, simple }: { search: EngineSearch; simple?: boolean }) {
  const { t } = useI18n();
  if (search.loading && !search.loaded) return <p role="status">{simple ? t("Buscando lugares parecidos…", "Searching for similar places…") : t("Consultando el motor…", "Querying the engine…")}</p>;
  if (search.error)
    return (
      <div className="u-empty" role="alert">
        <h3>{simple ? t("No pudimos completar la búsqueda", "We could not complete the search") : t("La búsqueda no respondió", "The search did not respond")}</h3>
        <p>{search.error}</p>
        <button onClick={search.retry}>{t("Reintentar", "Retry")}</button>
      </div>
    );
  return null;
}

function SimpleInspector({
  refInfo,
  row,
  loaded,
  search,
  country,
}: {
  refInfo: Reference;
  row?: Match;
  loaded?: LoadedSearch;
  search: EngineSearch;
  country?: string;
}) {
  const { t } = useI18n();
  return (
    <>
      <h2>
        {refInfo.name}
        <span>{row ? t(`↔ lugar ${row.rank} en la Tierra`, `↔ place ${row.rank} on Earth`) : t("↔ la Tierra", "↔ Earth")}</span>
      </h2>
      <SearchState search={search} simple />
      {row && (
        <div key={`${refInfo.id}/${row.region_id}`} className="u-comparison" aria-live="polite">
          <p className="u-place">{country && `${country} · `}{placeLabel(row.latitude, row.longitude)}</p>
          <div className="u-similarity">
            <strong>{pct(similarity(row.score))}</strong>
            <span>{t("de parecido en la forma del terreno", "similarity in terrain shape")}</span>
            <div className="u-meter" aria-hidden="true">
              <i style={{ width: `${similarity(row.score) * 100}%` }} />
            </div>
          </div>
          <h3>{t("Resumen por dimensión", "Summary by dimension")}</h3>
          <div className="u-dimension-summary">
            {Object.entries(row.views).filter(([, view]) => view.weight > 0).map(([id, view]) => (
              <div key={id}>
                <span>{viewNames[id] || id}</span>
                <strong>{view.available && view.distance != null ? distance(view.distance) : t("Sin datos", "No data")}</strong>
              </div>
            ))}
          </div>
          <p className="u-dimension-help">{t("Distancia por dimensión: cuanto menor, mayor parecido. Consulta el modo científico para ver los detalles.", "Distance by dimension: the lower, the more similar. Switch to scientific mode for the details.")}</p>
          <p className="u-note">
            {t(
              "Comparamos la forma del relieve en zonas de 3 km medidas por satélite. Es un resultado experimental: no indica si un vehículo podría recorrer el terreno.",
              "We compare the shape of the relief in 3 km areas measured by satellite. This is an experimental result: it does not tell whether a vehicle could drive across the terrain.",
            )}
          </p>
        </div>
      )}
      {loaded?.source === "demo" && <p className="u-note">{t("Ejemplo guardado: el buscador no está disponible ahora.", "Saved example: the search is not available right now.")}</p>}
    </>
  );
}

function ScienceInspector({
  refInfo,
  row,
  loaded,
  search,
  leftSite,
  rightSite,
}: {
  refInfo: Reference;
  row?: Match;
  loaded?: LoadedSearch;
  search: EngineSearch;
  leftSite?: VisualSite;
  rightSite?: VisualSite;
}) {
  const { t } = useI18n();
  const data = loaded?.data;
  const allFeatures = data && row ? featureRows(data, row) : [];
  const core = allFeatures.filter((f) =>
    ["relief_p95_p05_m", "slope_240m_p50_deg", "roughness_360m_p50_m"].includes(f.id),
  );
  return (
    <>
      <div className="u-panel-title">
        <span className="u-kicker">{t("LA COMPARACIÓN", "THE COMPARISON")}</span>
        <span className="u-status-dot" />
      </div>
      <h2>
        {refInfo.name}
        <span>↔ {row ? t(`candidata ${row.rank}`, `candidate ${row.rank}`) : t("Tierra", "Earth")}</span>
      </h2>
      {loaded && (
        <>
          <div className="u-badges">
            <span>{loaded.source === "live" ? t("Búsqueda en vivo", "Live search") : loaded.source === "demo" ? t("Demostración precalculada", "Precomputed demo") : t("Release publicada", "Published release")}</span>
            <span>{data?.status === "unsupervised_pending_blind_validation" ? t("Experimental", "Experimental") : data?.status}</span>
            {search.stale && <span>{t("Recalculando", "Recalculating")}</span>}
          </div>
          <p className="u-notice">{loaded.notice}</p>
        </>
      )}
      <SearchState search={search} />
      {loaded && data && !row && data.results.length > 0 && (
        <p className="u-empty">{t("La selección guardada no aparece en este ranking. Elige una candidata de la lista.", "The saved selection is not in this ranking. Pick a candidate from the list.")}</p>
      )}
      {row && data && (
        <div key={`${refInfo.id}/${row.region_id}`} className="u-comparison" aria-live="polite">
          <p className="u-id">{row.region_id}</p>
          <p className="u-eligibility">{eligibility(row.scenario_eligibility)}</p>
          <div className="u-distance">
            <small>{t("DISTANCIA DE SIMILITUD", "SIMILARITY DISTANCE")}</small>
            <strong>{distance(row.score)}</strong>
            <span>{t("Menor distancia = mayor parecido · parecido", "Lower distance = more similar · similarity")} {pct(similarity(row.score))}</span>
            <svg viewBox="0 0 300 22" role="img" aria-label={t(`Intervalo ${distance(row.score_low)} a ${distance(row.score_high)}`, `Interval ${distance(row.score_low)} to ${distance(row.score_high)}`)}>
              <path d="M6 11H294" stroke="#85705A" />
              <path d={`M${6 + row.score_low * 288} 11H${6 + row.score_high * 288}`} stroke="#F2A64E" strokeWidth="4" />
              <circle cx={6 + row.score * 288} cy="11" r="5" fill="#F6EDE0" />
            </svg>
            <div>
              <span>
                {t("Intervalo", "Interval")}{" "}
                <b>
                  {distance(row.score_low)} – {distance(row.score_high)}
                </b>
              </span>
              <span>
                {t("Cobertura", "Coverage")} <b>{pct(row.coverage)}</b>
              </span>
            </div>
            <small>{t("Intervalo por dimensiones ausentes; no es una precisión geográfica.", "Interval due to missing dimensions; it is not a geographic accuracy.")}</small>
          </div>
          <h3>{t("Relieve que comparten", "Relief they share")}</h3>
          <div className="u-core-head">
            <span>{t("Descriptor · soporte", "Descriptor · support")}</span>
            <span>{refInfo.name} / {t("Tierra", "Earth")}</span>
          </div>
          {core.map((f) => (
            <div className="u-core-row" key={f.id}>
              <span>{features[f.id]?.label || f.id}</span>
              <strong>
                {number(f.reference, 2)} / {number(f.candidate, 2)} <small>{features[f.id]?.unit}</small>
              </strong>
            </div>
          ))}
          {!core.length && <p>{t("Sin métricas topográficas comparables en esta respuesta.", "No comparable topographic metrics in this response.")}</p>}
          <p className="u-notice">
            {t(
              "Análisis del motor: ventanas de 3 km. El visor local muestra un subconjunto de 1,8 km y conserva las métricas originales.",
              "Engine analysis: 3 km windows. The local viewer shows a 1.8 km subset and keeps the original metrics.",
            )}
          </p>
          {row.missing_views.length > 0 && (
            <p className="u-notice">{t("Sin datos", "No data")}: {row.missing_views.map((v) => viewNames[v] || v).join(", ")}.</p>
          )}
        </div>
      )}
      {loaded && (
        <div className="u-visible-warnings">
          <EngineWarnings loaded={loaded} />
        </div>
      )}
      <details className="u-method">
        <summary>
          {t("Datos y método", "Data and method")} <span>{t("Fuentes, medidas y dimensiones", "Sources, measurements and dimensions")}</span>
        </summary>
        <div>
          <h3>{t("Fuentes del visor", "Viewer sources")}</h3>
          {refInfo.body === "Moon" && (
            <p>
              {refInfo.id === "haworth-fondo"
                ? t("Haworth: centro aproximado del fondo, no un punto oficial de aterrizaje.", "Haworth: approximate centre of the floor, not an official landing point.")
                : t("De Gerlache: coordenadas publicadas con dos decimales, incertidumbre de ubicación de ~300 m.", "De Gerlache: coordinates published to two decimals, location uncertainty of ~300 m.")}{" "}
              {t("Marco MOON_ME_DE421. El muestreo LOLA de 20 m no implica una precisión efectiva uniforme.", "MOON_ME_DE421 frame. The 20 m LOLA sampling does not imply a uniform effective accuracy.")}
            </p>
          )}
          <Source site={leftSite} name={refInfo.name} />
          <Source site={rightSite} name={row ? t(`Candidata ${row.rank}`, `Candidate ${row.rank}`) : t("Tierra", "Earth")} />
          <p>
            {t("Contexto global:", "Global context:")}{" "}
            <a href="https://svs.gsfc.nasa.gov/4720/" target="_blank" rel="noreferrer">
              NASA LROC + LOLA
            </a>
            {t(
              ", MOLA y NASA Blue Marble. El color lunar polar se completa con albedo LOLA; no mide composición. Los colores de los cuerpos identifican ubicaciones; la rampa mide una variable.",
              ", MOLA and NASA Blue Marble. The polar lunar colour is filled in with LOLA albedo; it does not measure composition. Body colours identify locations; the ramp measures a variable.",
            )}
          </p>
          <p>
            {t(
              "Los derivados visuales se cargan bajo demanda. No modifican distancias, métricas ni elegibilidad. Rugosidad visual no disponible: se conserva el descriptor original del motor.",
              "Visual derivatives load on demand. They do not change distances, metrics or eligibility. Visual roughness is not available: the original engine descriptor is kept.",
            )}
          </p>
          <a href={`${import.meta.env.BASE_URL}analysis/surface/unified/catalog.json`} target="_blank" rel="noreferrer">
            {t("Catálogo de derivados y huellas SHA-256 ↗", "Catalog of derivatives and SHA-256 fingerprints ↗")}
          </a>
          {loaded && data && (
            <>
              <h3>{t("Procedencia del ranking", "Ranking provenance")}</h3>
              <p>{loaded.notice}</p>
              <p>
                {data.engine_id} · {t("ajuste", "fitted")} {data.model_fitted_at} · {t("perfil", "profile")} {data.profile} · {t("fusión", "fusion")} {data.fusion}
                {loaded.queryId ? ` · ${t("consulta", "query")} ${loaded.queryId}` : ""}
              </p>
              {row && (
                <>
                  <h3>{t("Mediciones y contribuciones", "Measurements and contributions")}</h3>
                  <p>
                    {t(
                      "Valores originales por descriptor. Δ = candidata − referencia; los aportes firmados suman 100 % dentro de cada dimensión. La correlación permite aportes negativos o superiores a 100 %.",
                      "Original values per descriptor. Δ = candidate − reference; signed contributions add up to 100% within each dimension. Correlation allows negative contributions or contributions above 100%.",
                    )}
                  </p>
                  {allFeatures.map((f, i) => (
                    <article className="u-feature" key={`${f.id}/${i}`}>
                      <h4>
                        {features[f.id]?.label || f.id} <small>{features[f.id]?.unit}</small>
                      </h4>
                      <small>{viewNames[f.view] || f.view}</small>
                      <dl>
                        <div>
                          <dt>{refInfo.name}</dt>
                          <dd>{number(f.reference)}</dd>
                        </div>
                        <div>
                          <dt>{t("Tierra", "Earth")}</dt>
                          <dd>{number(f.candidate)}</dd>
                        </div>
                        <div>
                          <dt>{t("Δ original", "Original Δ")}</dt>
                          <dd>{f.reference == null ? t("Sin dato", "No data") : signed(f.candidate - f.reference)}</dd>
                        </div>
                        <div>
                          <dt>{t("Aporte / Δ normalizada", "Contribution / normalised Δ")}</dt>
                          <dd>
                            {signed(f.share * 100)}{t(" %", "%")} / {signed(f.z_delta)}
                          </dd>
                        </div>
                      </dl>
                      {data.reference.features[f.id]?.earth_percentile != null && (
                        <p>{t("Percentil terrestre de la referencia:", "Earth percentile of the reference:")} {pct(data.reference.features[f.id].earth_percentile)}.</p>
                      )}
                      {data.reference.features[f.id]?.outside_earth_range && (
                        <p>{t("La referencia está fuera del rango terrestre de este descriptor.", "The reference is outside the Earth range of this descriptor.")}</p>
                      )}
                    </article>
                  ))}
                  <h3>{t("Evidencia por dimensión", "Evidence by dimension")}</h3>
                  {Object.entries(row.views).map(([id, view]) => (
                    <article className="u-feature" key={id}>
                      <h4>{viewNames[id] || id}</h4>
                      {view.available ? (
                        <>
                          <p>
                            {t("Distancia", "Distance")} {distance(view.distance)} · {t("peso efectivo", "effective weight")} {pct(view.weight)}.
                          </p>
                          {view.pool_percentile != null && (
                            <p>{t("Percentil en la población de esta dimensión:", "Percentile in the population of this dimension:")} {pct(view.pool_percentile)}.</p>
                          )}
                          {view.component != null && (
                            <p>
                              {t("Familia morfológica", "Morphological family")} {view.component}
                              {view.posterior != null && ` · ${t("probabilidad de asignación", "assignment probability")} ${pct(view.posterior)}`}.
                            </p>
                          )}
                        </>
                      ) : (
                        <p>{t("Sin cobertura de esta dimensión para la candidata.", "No coverage of this dimension for the candidate.")}</p>
                      )}
                    </article>
                  ))}
                  <CandidateRecord regionId={row.region_id} version={loaded.version || ""} demo={loaded.source === "demo"} />
                </>
              )}
            </>
          )}
        </div>
      </details>
    </>
  );
}

function SceneNotes({
  science,
  state,
  range,
  complete,
  leftSite,
  rightSite,
  refName,
}: {
  science: boolean;
  state: AtlasState;
  range: [number, number];
  complete: boolean;
  leftSite?: VisualSite;
  rightSite?: VisualSite;
  refName: string;
}) {
  const { t } = useI18n();
  const unit = state.visualLayer === "elevation" ? "m" : "°";
  if (state.surfaceMode === "mesh")
    return (
      <>
        <div className="u-shared-legend">
          <strong>
            {state.visualLayer === "elevation"
              ? science
                ? t("Altura respecto a la mediana", "Height relative to the median")
                : t("Altura relativa", "Relative height")
              : t("Pendiente · base visual 60 m", "Slope · 60 m visual baseline")}
          </strong>
          <div className="u-ramp" />
          <span>
            {number(range[0], 1)} {unit}
          </span>
          <span>
            {number(range[1], 1)} {unit}
          </span>
          <small>
            {science
              ? t(
                  `Rango compartido · altura ${state.exaggeration}×${complete ? "" : " · comparación visual incompleta"}`,
                  `Shared range · height ${state.exaggeration}×${complete ? "" : " · incomplete visual comparison"}`,
                )
              : t("Misma escala de color en los dos lugares", "Same colour scale in both places")}
          </small>
        </div>
        <p className="u-support">
          {science
            ? t(
                `Ventana visual: 1,8 × 1,8 km · celda: 30 m · ${
                  state.visualLayer === "slope"
                    ? "pendiente visual calculada sobre 60 m; no es la pendiente del ranking"
                    : "cero = mediana de cada ventana; los datums absolutos no son equivalentes"
                }. La rampa representa datos válidos; las zonas vacías conservan sus huecos.`,
                `Visual window: 1.8 × 1.8 km · cell: 30 m · ${
                  state.visualLayer === "slope"
                    ? "visual slope computed over 60 m; it is not the ranking slope"
                    : "zero = median of each window; absolute datums are not equivalent"
                }. The ramp shows valid data; empty areas keep their gaps.`,
              )
            : t("Cada vista cubre 1,8 × 1,8 km. Arrastra para girar el terreno.", "Each view covers 1.8 × 1.8 km. Drag to rotate the terrain.")}
        </p>
      </>
    );
  return (
    <>
      <p className="u-support">
        {science
          ? `${
              state.surfaceMode === "space"
                ? t(
                    "Cobertura visual global · detalle limitado por cada fuente. Pulsa una referencia o una candidata en los globos.",
                    "Global visual coverage · detail limited by each source. Click a reference or a candidate on the globes.",
                  )
                : t(
                    "Encuadres comparables de ~24 km · huella de análisis: 3 × 3 km · N indica norte geográfico · barra de distancia medida en el centro.",
                    "Comparable ~24 km frames · analysis footprint: 3 × 3 km · N marks geographic north · scale bar measured at the centre.",
                  )
            } ${t("Zoom y capa no recalculan el ranking.", "Zoom and layer do not recalculate the ranking.")} ${
              state.exaggeration === 1
                ? t("Escala vertical real · 1×.", "True vertical scale · 1×.")
                : t(`Exageración vertical ${state.exaggeration}×.`, `Vertical exaggeration ${state.exaggeration}×.`)
            }`
          : state.surfaceMode === "space"
            ? t("Toca un marcador para ver cada lugar.", "Tap a marker to see each place.")
            : t("Zonas de unos 24 km alrededor de cada lugar, a la misma escala.", "Areas of about 24 km around each place, at the same scale.")}
      </p>
      {science && state.surfaceMode === "regional" && (
        <div className="u-native-pair">
          <small>
            {refName}:{" "}
            {leftSite
              ? `${leftSite.source} · ${t("nativo", "native")} ${leftSite.native_resolution_m} m · ${t("celda visual", "visual cell")} ${leftSite.cell_m} m`
              : t("MOLA ~463 m · imagen CTX remuestreada ~81 m/píxel; resolución efectiva variable", "MOLA ~463 m · CTX image resampled to ~81 m/pixel; variable effective resolution")}
            .
          </small>
          <small>
            {t("Tierra", "Earth")}:{" "}
            {rightSite
              ? `${rightSite.source} · ${t("nativo", "native")} ${rightSite.native_resolution_m} · ${t("celda visual", "visual cell")} ${rightSite.cell_m} m`
              : t("Contexto Esri; resolución nativa sin verificar. Sin DEM preparado de esta candidata", "Esri context; native resolution unverified. No DEM prepared for this candidate")}
            .
          </small>
        </div>
      )}
    </>
  );
}

function Source({ site, name }: { site?: VisualSite; name: string }) {
  const { t } = useI18n();
  return (
    <div className="u-source">
      <h4>{name}</h4>
      {site?.body === "Earth" && (
        <p>
          {t(
            "Derivado de Copernicus WorldDEM-30. © DLR e.V. 2010–2014 y Airbus Defence and Space GmbH 2014–2018, proporcionado bajo COPERNICUS por la Unión Europea y ESA.",
            "Derived from Copernicus WorldDEM-30. © DLR e.V. 2010–2014 and Airbus Defence and Space GmbH 2014–2018, provided under COPERNICUS by the European Union and ESA.",
          )}{" "}
          <a
            href="https://dataspace.copernicus.eu/explore-data/data-collections/copernicus-contributing-missions/collections-description/COP-DEM"
            target="_blank"
            rel="noreferrer"
          >
            {t("Atribución y licencia de la fuente ↗", "Source attribution and licence ↗")}
          </a>
        </p>
      )}
      {site ? (
        <>
          <a href={site.source_url} target="_blank" rel="noreferrer">
            {site.source} ↗
          </a>
          <p>
            {t("Centro", "Centre")}: {location(site)} · {t("ventana", "window")} {number(site.window_m / 1000, 1)} km · {t("celda", "cell")} {site.cell_m} m · {t("nativo", "native")}{" "}
            {site.native_resolution_m}
            {typeof site.native_resolution_m === "number" ? " m" : ""}.
          </p>
          <p>
            Datum: {site.datum}. {t("Cobertura visual", "Visual coverage")} {pct(site.coverage)}. {t("Error de cuantización", "Quantisation error")} ≤{" "}
            {number(site.quantization_error_m, 3)} m.
          </p>
        </>
      ) : (
        <p className="u-no-data">{t("Sin DEM preparado para esta ubicación y escala.", "No DEM prepared for this location and scale.")}</p>
      )}
    </div>
  );
}
