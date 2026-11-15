import { useEffect, useMemo, useState } from "react";
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
import { JezeroPilot } from "./JezeroPilot";
import {
  candidateFocus,
  exactSite,
  sharedRange,
  type VisualSite,
} from "./terrainModel";
import { useCatalog, useGrid } from "./resources";
import "./unified.css";

const EMPTY: never[] = [];
type Reference = (typeof references)[number];
type ReferenceId = AtlasState["reference"];

/** Plain-language description of each study site, for the public mode. */
const SITE_TEXT: Record<ReferenceId, string> = {
  jezero: "Cráter con un antiguo delta de río",
  "haworth-fondo": "Fondo de un cráter junto al polo sur",
  "de-gerlache-cresta": "Cresta junto al polo sur",
};
const BODY_TEXT = { Mars: "Marte", Moon: "Luna", Earth: "Tierra" } as const;
/** The three measurements a non-specialist can read, with what each one means. */
const PLAIN_FEATURES = [
  { id: "relief_p95_p05_m", label: "Desnivel", hint: "entre las partes altas y bajas", unit: "m", digits: 0 },
  { id: "slope_240m_p50_deg", label: "Inclinación típica", hint: "del terreno", unit: "°", digits: 1 },
  { id: "roughness_360m_p50_m", label: "Rugosidad", hint: "qué tan irregular es el suelo", unit: "m", digits: 1 },
] as const;

export function UnifiedWorkspace({
  state,
  update,
}: {
  state: AtlasState;
  update: (patch: Partial<AtlasState>) => void;
}) {
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
  const changeRef = (reference: ReferenceId) => {
    setOverview(false);
    update({ reference, regionId: "", method: "engine" });
  };
  const missing = (id: string, error?: string) =>
    error ||
    catalog.error ||
    (catalog.data?.missing[id]
      ? "No hay un derivado válido de esta ubicación en el catálogo."
      : catalog.data
        ? "Esta ubicación no tiene un DEM preparado para el navegador."
        : "Cargando catálogo de relieve…");
  const earthName = row ? (science ? `Tierra · candidata ${row.rank}` : `Tierra · lugar ${row.rank}`) : "Tierra";
  return (
    <section className={`unified-workspace${science ? " is-science" : " is-simple"}`}>
      <header className="u-heading">
        <div>
          {science && <span className="u-kicker">REGOLITH / MODO CIENTÍFICO</span>}
          <h1>{science ? "Explorar y comparar" : "¿Dónde se parece la Tierra a otros mundos?"}</h1>
        </div>
        {!science && (
          <p>
            Elige un lugar de Marte o de la Luna.
            <br />
            <span>Te mostramos los terrenos de la Tierra con una forma más parecida.</span>
          </p>
        )}
      </header>
      <div className="u-toolbar">
        <div className="u-segment" role="group" aria-label="Cuerpo de referencia">
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
              {BODY_TEXT[body]}
            </button>
          ))}
        </div>
        <div className="u-sites" role="group" aria-label="Lugar de estudio">
          {references
            .filter((r) => r.body === ref.body)
            .map((r) => (
              <button key={r.id} aria-pressed={r.id === ref.id} onClick={() => changeRef(r.id)}>
                <strong>{r.name}</strong>
                <small>{SITE_TEXT[r.id]}</small>
              </button>
            ))}
        </div>
        <div className="u-scales" role="group" aria-label="Escala de estudio">
          {(
            [
              { id: "space", label: science ? "Órbita" : "Planeta" },
              { id: "regional", label: science ? "Relieve regional" : "Región" },
              { id: "mesh", label: science ? "Superficie local" : "De cerca" },
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
            Capa activa
            <select
              value={state.visualLayer}
              onChange={(e) => update({ visualLayer: e.target.value as AtlasState["visualLayer"] })}
            >
              <option value="elevation">Altura relativa · m</option>
              <option value="slope">Pendiente · °</option>
              <option disabled>Rugosidad · sin capa comparable</option>
            </select>
          </label>
        )}
        {science && (state.surfaceMode !== "space" || state.exaggeration !== 1) && (
          <label className="u-exaggeration">
            Altura
            <select
              aria-label="Exageración vertical"
              value={state.exaggeration}
              onChange={(e) => update({ exaggeration: Number(e.target.value) })}
            >
              {[1, 1.5, 2, 2.5, 3, 3.5, 4, 4.5, 5].map((n) => (
                <option key={n} value={n}>
                  {n}×{n === 1 ? " · escala real" : ""}
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
              {ref.name} <em>· {BODY_TEXT[ref.body]}</em>
              <small>{science ? location(ref) : placeLabel(ref.latitude, ref.longitude)}</small>
            </span>
            <span>
              <i className="u-dot u-Earth" />
              {row ? earthName : "Tierra"}
              <small>
                {row
                  ? science
                    ? location(row)
                    : placeLabel(row.latitude, row.longitude)
                  : "Elige un lugar de la lista"}
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
              name={row ? `lugar ${row.rank}` : "lugares terrestres"}
              longitude={row?.longitude ?? candidateFocus(rows)[0]}
              latitude={row?.latitude ?? candidateFocus(rows)[1]}
              marks={earthMarks}
              selected={row?.region_id ?? ""}
              choose={(regionId) => update({ regionId })}
              mode={state.surfaceMode}
              grid={right.grid}
              layer={state.visualLayer}
              range={range}
              exaggeration={state.exaggeration}
              pending={!!row && !catalog.error && !right.error && (!catalog.data || (!!rightSite && !right.grid))}
              missing={row ? missing(row.region_id, right.error) : "Elige un lugar de la lista."}
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
          <aside className="u-inspector" aria-label="Comparación seleccionada" aria-busy={search.loading}>
            {science ? (
              <ScienceInspector refInfo={ref} row={row} loaded={loaded} search={search} leftSite={leftSite} rightSite={rightSite} />
            ) : (
              <SimpleInspector refInfo={ref} row={row} loaded={loaded} search={search} />
            )}
          </aside>
        </div>
        <section className="u-candidates" aria-label="Lugares parecidos en la Tierra" aria-busy={search.loading}>
          <header>
            <h2>
              {science ? "Candidatas en la Tierra" : "Lugares parecidos en la Tierra"}{" "}
              <span>{rows.length.toString().padStart(2, "0")}</span>
            </h2>
            <small>{search.stale ? "Actualizando…" : "Toca un lugar o un marcador del globo"}</small>
          </header>
          {rows.length > 0 ? (
            <div className={`u-candidate-list${search.stale ? " is-stale" : ""}`}>
              {rows.map((r) => (
                <button
                  key={r.region_id}
                  aria-pressed={row?.region_id === r.region_id}
                  onClick={() => update({ regionId: r.region_id })}
                >
                  <b>{r.rank.toString().padStart(2, "0")}</b>
                  {science ? (
                    <>
                      <span>
                        {location(r)}
                        <small>{eligibility(r.scenario_eligibility)}</small>
                      </span>
                      <strong>
                        {distance(r.score)}
                        <small>distancia</small>
                      </strong>
                    </>
                  ) : (
                    <>
                      <span>{placeLabel(r.latitude, r.longitude)}</span>
                      <strong>
                        {pct(similarity(r.score))}
                        <small>parecido</small>
                      </strong>
                    </>
                  )}
                </button>
              ))}
            </div>
          ) : (
            <p className="u-empty">
              {search.loading
                ? "Buscando lugares parecidos…"
                : search.error
                  ? "No hay resultados para mostrar."
                  : "La búsqueda no encontró lugares con estos parámetros."}
            </p>
          )}
        </section>
      </div>
      {science && ref.id === "jezero" && <JezeroPilot />}
    </section>
  );
}

function SearchState({ search, simple }: { search: EngineSearch; simple?: boolean }) {
  if (search.loading && !search.loaded) return <p role="status">{simple ? "Buscando lugares parecidos…" : "Consultando el motor…"}</p>;
  if (search.error)
    return (
      <div className="u-empty" role="alert">
        <h3>{simple ? "No pudimos completar la búsqueda" : "La búsqueda no respondió"}</h3>
        <p>{search.error}</p>
        <button onClick={search.retry}>Reintentar</button>
      </div>
    );
  return null;
}

function SimpleInspector({
  refInfo,
  row,
  loaded,
  search,
}: {
  refInfo: Reference;
  row?: Match;
  loaded?: LoadedSearch;
  search: EngineSearch;
}) {
  const values = loaded && row ? featureRows(loaded.data, row) : [];
  return (
    <>
      <h2>
        {refInfo.name}
        <span>{row ? `↔ lugar ${row.rank} en la Tierra` : "↔ la Tierra"}</span>
      </h2>
      <SearchState search={search} simple />
      {row && (
        <div key={`${refInfo.id}/${row.region_id}`} className="u-comparison" aria-live="polite">
          <p className="u-place">{placeLabel(row.latitude, row.longitude)}</p>
          <div className="u-similarity">
            <strong>{pct(similarity(row.score))}</strong>
            <span>de parecido en la forma del terreno</span>
            <div className="u-meter" aria-hidden="true">
              <i style={{ width: `${similarity(row.score) * 100}%` }} />
            </div>
          </div>
          <h3>Cómo se comparan</h3>
          {PLAIN_FEATURES.map((f) => {
            const v = values.find((x) => x.id === f.id);
            if (!v) return null;
            return (
              <div className="u-plain-row" key={f.id}>
                <span>
                  {f.label}
                  <small>{f.hint}</small>
                </span>
                <div>
                  <span>
                    <small>{refInfo.name}</small>
                    {number(v.reference, f.digits)} {f.unit}
                  </span>
                  <span>
                    <small>Tierra</small>
                    {number(v.candidate, f.digits)} {f.unit}
                  </span>
                </div>
              </div>
            );
          })}
          <p className="u-note">
            Comparamos la forma del relieve en zonas de 3 km medidas por satélite. Es un resultado
            experimental: no indica si un vehículo podría recorrer el terreno.
          </p>
        </div>
      )}
      {loaded?.source === "demo" && <p className="u-note">Ejemplo guardado: el buscador no está disponible ahora.</p>}
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
  const data = loaded?.data;
  const allFeatures = data && row ? featureRows(data, row) : [];
  const core = allFeatures.filter((f) =>
    ["relief_p95_p05_m", "slope_240m_p50_deg", "roughness_360m_p50_m"].includes(f.id),
  );
  return (
    <>
      <div className="u-panel-title">
        <span className="u-kicker">LA COMPARACIÓN</span>
        <span className="u-status-dot" />
      </div>
      <h2>
        {refInfo.name}
        <span>↔ {row ? `candidata ${row.rank}` : "Tierra"}</span>
      </h2>
      {loaded && (
        <>
          <div className="u-badges">
            <span>{loaded.source === "live" ? "Búsqueda en vivo" : loaded.source === "demo" ? "Demostración precalculada" : "Release publicada"}</span>
            <span>{data?.status === "unsupervised_pending_blind_validation" ? "Experimental" : data?.status}</span>
            {search.stale && <span>Recalculando</span>}
          </div>
          <p className="u-notice">{loaded.notice}</p>
        </>
      )}
      <SearchState search={search} />
      {loaded && data && !row && data.results.length > 0 && (
        <p className="u-empty">La selección guardada no aparece en este ranking. Elige una candidata de la lista.</p>
      )}
      {row && data && (
        <div key={`${refInfo.id}/${row.region_id}`} className="u-comparison" aria-live="polite">
          <p className="u-id">{row.region_id}</p>
          <p className="u-eligibility">{eligibility(row.scenario_eligibility)}</p>
          <div className="u-distance">
            <small>DISTANCIA DE SIMILITUD</small>
            <strong>{distance(row.score)}</strong>
            <span>Menor distancia = mayor parecido · parecido {pct(similarity(row.score))}</span>
            <svg viewBox="0 0 300 22" role="img" aria-label={`Intervalo ${distance(row.score_low)} a ${distance(row.score_high)}`}>
              <path d="M6 11H294" stroke="#85705A" />
              <path d={`M${6 + row.score_low * 288} 11H${6 + row.score_high * 288}`} stroke="#F2A64E" strokeWidth="4" />
              <circle cx={6 + row.score * 288} cy="11" r="5" fill="#F6EDE0" />
            </svg>
            <div>
              <span>
                Intervalo{" "}
                <b>
                  {distance(row.score_low)} – {distance(row.score_high)}
                </b>
              </span>
              <span>
                Cobertura <b>{pct(row.coverage)}</b>
              </span>
            </div>
            <small>Intervalo por dimensiones ausentes; no es una precisión geográfica.</small>
          </div>
          <h3>Relieve que comparten</h3>
          <div className="u-core-head">
            <span>Descriptor · soporte</span>
            <span>{refInfo.name} / Tierra</span>
          </div>
          {core.map((f) => (
            <div className="u-core-row" key={f.id}>
              <span>{features[f.id]?.label || f.id}</span>
              <strong>
                {number(f.reference, 2)} / {number(f.candidate, 2)} <small>{features[f.id]?.unit}</small>
              </strong>
            </div>
          ))}
          {!core.length && <p>Sin métricas topográficas comparables en esta respuesta.</p>}
          <p className="u-notice">
            Análisis del motor: ventanas de 3 km. El visor local muestra un subconjunto de 1,8 km y conserva
            las métricas originales.
          </p>
          {row.missing_views.length > 0 && (
            <p className="u-notice">Sin datos: {row.missing_views.map((v) => viewNames[v] || v).join(", ")}.</p>
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
          Datos y método <span>Fuentes, medidas y dimensiones</span>
        </summary>
        <div>
          <h3>Fuentes del visor</h3>
          {refInfo.body === "Moon" && (
            <p>
              {refInfo.id === "haworth-fondo"
                ? "Haworth: centro aproximado del fondo, no un punto oficial de aterrizaje."
                : "De Gerlache: coordenadas publicadas con dos decimales, incertidumbre de ubicación de ~300 m."}{" "}
              Marco MOON_ME_DE421. El muestreo LOLA de 20 m no implica una precisión efectiva uniforme.
            </p>
          )}
          <Source site={leftSite} name={refInfo.name} />
          <Source site={rightSite} name={row ? `Candidata ${row.rank}` : "Tierra"} />
          <p>
            Contexto global:{" "}
            <a href="https://svs.gsfc.nasa.gov/4720/" target="_blank" rel="noreferrer">
              NASA LROC + LOLA
            </a>
            , MOLA y NASA Blue Marble. El color lunar polar se completa con albedo LOLA; no mide composición.
            Los colores de los cuerpos identifican ubicaciones; la rampa mide una variable.
          </p>
          <p>
            Los derivados visuales se cargan bajo demanda. No modifican distancias, métricas ni elegibilidad.
            Rugosidad visual no disponible: se conserva el descriptor original del motor.
          </p>
          <a href={`${import.meta.env.BASE_URL}analysis/surface/unified/catalog.json`} target="_blank" rel="noreferrer">
            Catálogo de derivados y huellas SHA-256 ↗
          </a>
          {loaded && data && (
            <>
              <h3>Procedencia del ranking</h3>
              <p>{loaded.notice}</p>
              <p>
                {data.engine_id} · ajuste {data.model_fitted_at} · perfil {data.profile} · fusión {data.fusion}
                {loaded.queryId ? ` · consulta ${loaded.queryId}` : ""}
              </p>
              {row && (
                <>
                  <h3>Mediciones y contribuciones</h3>
                  <p>
                    Valores originales por descriptor. Δ = candidata − referencia; los aportes firmados suman
                    100 % dentro de cada dimensión. La correlación permite aportes negativos o superiores a 100 %.
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
                          <dt>Tierra</dt>
                          <dd>{number(f.candidate)}</dd>
                        </div>
                        <div>
                          <dt>Δ original</dt>
                          <dd>{f.reference == null ? "Sin dato" : signed(f.candidate - f.reference)}</dd>
                        </div>
                        <div>
                          <dt>Aporte / Δ normalizada</dt>
                          <dd>
                            {signed(f.share * 100)} % / {signed(f.z_delta)}
                          </dd>
                        </div>
                      </dl>
                      {data.reference.features[f.id]?.earth_percentile != null && (
                        <p>Percentil terrestre de la referencia: {pct(data.reference.features[f.id].earth_percentile)}.</p>
                      )}
                      {data.reference.features[f.id]?.outside_earth_range && (
                        <p>La referencia está fuera del rango terrestre de este descriptor.</p>
                      )}
                    </article>
                  ))}
                  <h3>Evidencia por dimensión</h3>
                  {Object.entries(row.views).map(([id, view]) => (
                    <article className="u-feature" key={id}>
                      <h4>{viewNames[id] || id}</h4>
                      {view.available ? (
                        <>
                          <p>
                            Distancia {distance(view.distance)} · peso efectivo {pct(view.weight)}.
                          </p>
                          {view.pool_percentile != null && (
                            <p>Percentil en la población de esta dimensión: {pct(view.pool_percentile)}.</p>
                          )}
                          {view.component != null && (
                            <p>
                              Familia morfológica {view.component}
                              {view.posterior != null && ` · probabilidad de asignación ${pct(view.posterior)}`}.
                            </p>
                          )}
                        </>
                      ) : (
                        <p>Sin cobertura de esta dimensión para la candidata.</p>
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
  const unit = state.visualLayer === "elevation" ? "m" : "°";
  if (state.surfaceMode === "mesh")
    return (
      <>
        <div className="u-shared-legend">
          <strong>
            {state.visualLayer === "elevation"
              ? science
                ? "Altura respecto a la mediana"
                : "Altura relativa"
              : "Pendiente · base visual 60 m"}
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
              ? `Rango compartido · altura ${state.exaggeration}×${complete ? "" : " · comparación visual incompleta"}`
              : "Misma escala de color en los dos lugares"}
          </small>
        </div>
        <p className="u-support">
          {science
            ? `Ventana visual: 1,8 × 1,8 km · celda: 30 m · ${
                state.visualLayer === "slope"
                  ? "pendiente visual calculada sobre 60 m; no es la pendiente del ranking"
                  : "cero = mediana de cada ventana; los datums absolutos no son equivalentes"
              }. La rampa representa datos válidos; las zonas vacías conservan sus huecos.`
            : "Cada vista cubre 1,8 × 1,8 km. Arrastra para girar el terreno."}
        </p>
      </>
    );
  return (
    <>
      <p className="u-support">
        {science
          ? `${
              state.surfaceMode === "space"
                ? "Cobertura visual global · detalle limitado por cada fuente. Pulsa una referencia o una candidata en los globos."
                : "Encuadres comparables de ~24 km · huella de análisis: 3 × 3 km · N indica norte geográfico · barra de distancia medida en el centro."
            } Zoom y capa no recalculan el ranking. ${
              state.exaggeration === 1 ? "Escala vertical real · 1×." : `Exageración vertical ${state.exaggeration}×.`
            }`
          : state.surfaceMode === "space"
            ? "Toca un marcador para ver cada lugar."
            : "Zonas de unos 24 km alrededor de cada lugar, a la misma escala."}
      </p>
      {science && state.surfaceMode === "regional" && (
        <div className="u-native-pair">
          <small>
            {refName}:{" "}
            {leftSite
              ? `${leftSite.source} · nativo ${leftSite.native_resolution_m} m · celda visual ${leftSite.cell_m} m`
              : "MOLA ~463 m · imagen CTX remuestreada ~81 m/píxel; resolución efectiva variable"}
            .
          </small>
          <small>
            Tierra:{" "}
            {rightSite
              ? `${rightSite.source} · nativo ${rightSite.native_resolution_m} · celda visual ${rightSite.cell_m} m`
              : "Contexto Esri; resolución nativa sin verificar. Sin DEM preparado de esta candidata"}
            .
          </small>
        </div>
      )}
    </>
  );
}

function Source({ site, name }: { site?: VisualSite; name: string }) {
  return (
    <div className="u-source">
      <h4>{name}</h4>
      {site?.body === "Earth" && (
        <p>
          Derivado de Copernicus WorldDEM-30. © DLR e.V. 2010–2014 y Airbus Defence and Space GmbH 2014–2018,
          proporcionado bajo COPERNICUS por la Unión Europea y ESA.{" "}
          <a
            href="https://dataspace.copernicus.eu/explore-data/data-collections/copernicus-contributing-missions/collections-description/COP-DEM"
            target="_blank"
            rel="noreferrer"
          >
            Atribución y licencia de la fuente ↗
          </a>
        </p>
      )}
      {site ? (
        <>
          <a href={site.source_url} target="_blank" rel="noreferrer">
            {site.source} ↗
          </a>
          <p>
            Centro: {location(site)} · ventana {number(site.window_m / 1000, 1)} km · celda {site.cell_m} m · nativo{" "}
            {site.native_resolution_m}
            {typeof site.native_resolution_m === "number" ? " m" : ""}.
          </p>
          <p>
            Datum: {site.datum}. Cobertura visual {pct(site.coverage)}. Error de cuantización ≤{" "}
            {number(site.quantization_error_m, 3)} m.
          </p>
        </>
      ) : (
        <p className="u-no-data">Sin DEM preparado para esta ubicación y escala.</p>
      )}
    </div>
  );
}
