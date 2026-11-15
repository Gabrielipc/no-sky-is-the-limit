import { useEffect, useMemo, useState } from "react";
import type { AtlasState } from "../../app/useAtlasState";
import type { SimulationResource } from "../simulation/useSimulation";
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
} from "../simulation/model";
import { EngineWarnings, WeightsPanel } from "../simulation/EnginePanels";
import { CandidateRecord } from "../simulation/CandidateRecord";
import { ScenePanel } from "./ScenePanel";
import { Profiles } from "./Profiles";
import {
  candidateFocus,
  exactSite,
  sharedRange,
  type VisualSite,
} from "./terrainModel";
import { useCatalog, useGrid } from "./resources";
import "./unified.css";
const EMPTY: never[] = [];
export function UnifiedWorkspace({
  state,
  update,
  resource,
}: {
  state: AtlasState;
  update: (patch: Partial<AtlasState>) => void;
  resource: SimulationResource;
}) {
  const ref = references.find((r) => r.id === state.reference)!,
    loaded = resource.loaded,
    data = loaded?.data,
    row = selectedMatch(data, state.regionId),
    rows = data?.results ?? EMPTY;
  const [overview, setOverview] = useState(false),
    catalog = useCatalog(),
    kind = state.surfaceMode === "regional" ? "regional" : "local";
  useEffect(() => {
    if (!state.regionId && data?.results[0])
      update({ regionId: data.results[0].region_id });
  }, [data, state.regionId, update]);
  const leftSite = exactSite(
      catalog.data,
      ref.id,
      ref.longitude,
      ref.latitude,
      kind,
    ),
    rightSite = row
      ? exactSite(
          catalog.data,
          row.region_id,
          row.longitude,
          row.latitude,
          kind,
        )
      : undefined;
  const left = useGrid(leftSite, state.surfaceMode !== "space"),
    right = useGrid(rightSite, state.surfaceMode !== "space");
  const range = useMemo(
    () => sharedRange([left.grid, right.grid], state.visualLayer),
    [left.grid, right.grid, state.visualLayer],
  );
  const profileRange = useMemo(
    () => sharedRange([left.grid, right.grid], "elevation"),
    [left.grid, right.grid],
  );
  const refMarks = useMemo(
    () =>
      references
        .filter((r) => r.body === ref.body)
        .map((r) => ({ ...r, name: r.name })),
    [ref.body],
  );
  const earthMarks = useMemo(
    () =>
      rows.map((r) => ({
        id: r.region_id,
        name: String(r.rank),
        longitude: r.longitude,
        latitude: r.latitude,
      })),
    [rows],
  );
  const changeRef = (reference: AtlasState["reference"]) => {
    setOverview(false);
    update({ reference, regionId: "", method: "engine" });
  };
  const layerName =
    state.visualLayer === "elevation"
      ? "Altura respecto a la mediana"
      : "Pendiente · base visual 60 m";
  const allFeatures = data && row ? featureRows(data, row) : [];
  const core = allFeatures.filter((f) =>
    ["relief_p95_p05_m", "slope_240m_p50_deg", "roughness_360m_p50_m"].includes(
      f.id,
    ),
  );
  const missing = (id: string, error?: string) =>
    error ||
    catalog.error ||
    (catalog.data?.missing[id]
      ? "No hay un derivado válido de esta ubicación en el catálogo."
      : catalog.data
        ? "Esta ubicación no tiene un DEM preparado para el navegador."
        : "Cargando catálogo de relieve…");
  return (
    <section className="unified-workspace">
      <header className="u-heading">
        <div>
          <span className="u-kicker">REGOLITH / ATLAS DE ANÁLOGOS</span>
          <h1>Explorar y comparar</h1>
        </div>
        <p>
          Del planeta al terreno.
          <br />
          <span>Elige un punto. Entiende su parecido.</span>
        </p>
      </header>
      <div className="u-toolbar">
        <label>
          Cuerpo
          <select
            aria-label="Cuerpo de referencia"
            value={ref.body}
            onChange={(e) => {
              const reference =
                e.target.value === "Mars" ? "jezero" : "haworth-fondo";
              changeRef(reference);
              setOverview(true);
              update({ surfaceMode: "space" });
            }}
          >
            <option value="Mars">Marte</option>
            <option value="Moon">Luna</option>
          </select>
        </label>
        <label>
          Zona de estudio
          <select
            aria-label="Zona de estudio"
            value={state.reference}
            onChange={(e) =>
              changeRef(e.target.value as AtlasState["reference"])
            }
          >
            {references
              .filter((r) => r.body === ref.body)
              .map((r) => (
                <option value={r.id} key={r.id}>
                  {r.name} ·{" "}
                  {r.body === "Mars"
                    ? "abanico"
                    : r.id === "haworth-fondo"
                      ? "fondo polar"
                      : "cresta polar"}
                </option>
              ))}
          </select>
        </label>
        <div className="u-scales" role="group" aria-label="Escala de estudio">
          {(
            [
              { id: "space", label: "Órbita" },
              { id: "regional", label: "Relieve regional" },
              { id: "mesh", label: "Superficie local" },
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
        {state.surfaceMode === "mesh" && (
          <label>
            Capa activa
            <select
              value={state.visualLayer}
              onChange={(e) =>
                update({
                  visualLayer: e.target.value as AtlasState["visualLayer"],
                })
              }
            >
              <option value="elevation">Altura relativa · m</option>
              <option value="slope">Pendiente · °</option>
              <option disabled>Rugosidad · sin capa comparable</option>
            </select>
          </label>
        )}
        {(state.surfaceMode !== "space" || state.exaggeration !== 1) && (
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
              {ref.name}
              <small>{location(ref)}</small>
            </span>
            <span>
              <i className="u-dot u-Earth" />
              {row ? `Tierra · candidata ${row.rank}` : "Tierra · candidatas"}
              <small>{row ? location(row) : "Selecciona una ventana"}</small>
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
              choose={(id) => changeRef(id as AtlasState["reference"])}
              mode={state.surfaceMode}
              grid={left.grid}
              layer={state.visualLayer}
              range={range}
              exaggeration={state.exaggeration}
              overview={overview}
              pending={
                !catalog.error &&
                !left.error &&
                (!catalog.data || (!!leftSite && !left.grid))
              }
              missing={missing(ref.id, left.error)}
            />
            <ScenePanel
              body="Earth"
              name={row ? `candidata ${row.rank}` : "candidatas terrestres"}
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
              pending={
                !!row &&
                !catalog.error &&
                !right.error &&
                (!catalog.data || (!!rightSite && !right.grid))
              }
              missing={
                row
                  ? missing(row.region_id, right.error)
                  : "Selecciona una candidata con ranking publicado."
              }
            />
          </div>
          {state.surfaceMode === "mesh" ? (
            <>
              <div className="u-shared-legend">
                <strong>{layerName}</strong>
                <div className="u-ramp" />
                <span>
                  {number(range[0], 1)}{" "}
                  {state.visualLayer === "elevation" ? "m" : "°"}
                </span>
                <span>
                  {number(range[1], 1)}{" "}
                  {state.visualLayer === "elevation" ? "m" : "°"}
                </span>
                <small>
                  Rango compartido · altura {state.exaggeration}×
                  {!left.grid || !right.grid
                    ? " · comparación visual incompleta"
                    : ""}
                </small>
              </div>
              <p className="u-support">
                Ventana visual: 1,8 × 1,8 km · celda: 30 m ·{" "}
                {state.visualLayer === "slope"
                  ? "pendiente visual calculada sobre 60 m; no es la pendiente del ranking"
                  : "cero = mediana de cada ventana; los datums absolutos no son equivalentes"}
                . La rampa representa datos válidos; las zonas vacías conservan
                sus huecos.
              </p>
              <Profiles
                left={left.grid}
                right={right.grid}
                range={profileRange}
                names={[
                  ref.name,
                  row ? `Tierra · candidata ${row.rank}` : "Tierra",
                ]}
              />
            </>
          ) : (
            <p className="u-support">
              {state.surfaceMode === "space"
                ? "Cobertura visual global · detalle limitado por cada fuente. Pulsa una referencia o una candidata en los globos."
                : "Encuadres comparables de ~24 km · huella de análisis: 3 × 3 km · N indica norte geográfico · barra de distancia medida en el centro."}{" "}
              Zoom y capa no recalculan el ranking.{" "}
              {state.exaggeration === 1
                ? "Escala vertical real · 1×."
                : `Exageración vertical ${state.exaggeration}×.`}
            </p>
          )}
          {state.surfaceMode === "regional" && (
            <div className="u-native-pair">
              <small>
                {ref.name}:{" "}
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
        </div>
        <aside className="u-inspector" aria-label="Comparación seleccionada">
          <div className="u-panel-title">
            <span className="u-kicker">LA COMPARACIÓN</span>
            <span className="u-status-dot" />
          </div>
          <h2>
            {ref.name}
            <span>↔ {row ? `candidata ${row.rank}` : "Tierra"}</span>
          </h2>
          {loaded && (
            <>
              <div className="u-badges">
                <span>
                  {loaded.source === "demo"
                    ? "Demostración precalculada"
                    : "Release publicada"}
                </span>
                <span>
                  {data?.status === "unsupervised_pending_blind_validation"
                    ? "Experimental"
                    : data?.status}
                </span>
              </div>
              <p className="u-notice">
                {loaded.source === "demo"
                  ? "Ejemplo del repositorio · sin release activa."
                  : `Release ${loaded.version || state.release}`}
              </p>
            </>
          )}
          {resource.loading && <p role="status">Consultando comparaciones…</p>}
          {resource.error && (
            <div className="u-empty" role="status">
              <h3>Sin comparaciones publicadas</h3>
              <p>{resource.error}</p>
              <button onClick={resource.retry}>Reintentar servicio</button>
            </div>
          )}
          {loaded && !row && (
            <p className="u-empty">
              La selección guardada no aparece en este ranking. Elige una
              candidata de la lista.
            </p>
          )}
          {row && (
            <div
              key={`${ref.id}/${row.region_id}`}
              className="u-comparison"
              aria-live="polite"
            >
              <p className="u-id">{row.region_id}</p>
              <p className="u-eligibility">
                {eligibility(row.scenario_eligibility)}
              </p>
              <div className="u-distance">
                <small>DISTANCIA DE SIMILITUD</small>
                <strong>{distance(row.score)}</strong>
                <span>Menor distancia = mayor parecido</span>
                <svg
                  viewBox="0 0 300 22"
                  role="img"
                  aria-label={`Intervalo ${distance(row.score_low)} a ${distance(row.score_high)}`}
                >
                  <path d="M6 11H294" stroke="#85705A" />
                  <path
                    d={`M${6 + row.score_low * 288} 11H${6 + row.score_high * 288}`}
                    stroke="#F2A64E"
                    strokeWidth="4"
                  />
                  <circle
                    cx={6 + row.score * 288}
                    cy="11"
                    r="5"
                    fill="#F6EDE0"
                  />
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
                <small>
                  Intervalo por dimensiones ausentes; no es una precisión
                  geográfica.
                </small>
              </div>
              <h3>Relieve que comparten</h3>
              <div className="u-core-head">
                <span>Descriptor · soporte</span>
                <span>{ref.name} / Tierra</span>
              </div>
              {core.map((f) => (
                <div className="u-core-row" key={f.id}>
                  <span>{features[f.id]?.label || f.id}</span>
                  <strong>
                    {number(f.reference, 2)} / {number(f.candidate, 2)}{" "}
                    <small>{features[f.id]?.unit}</small>
                  </strong>
                </div>
              ))}
              {!core.length && (
                <p>Sin métricas topográficas comparables en esta respuesta.</p>
              )}
              <p className="u-notice">
                Análisis del motor: ventanas de 3 km. El visor local muestra un
                subconjunto de 1,8 km y conserva las métricas originales.
              </p>
              {row.missing_views.length > 0 && (
                <p className="u-notice">
                  Sin datos:{" "}
                  {row.missing_views.map((v) => viewNames[v] || v).join(", ")}.
                </p>
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
              {ref.body === "Moon" && (
                <p>
                  {ref.id === "haworth-fondo"
                    ? "Haworth: centro aproximado del fondo, no un punto oficial de aterrizaje."
                    : "De Gerlache: coordenadas publicadas con dos decimales, incertidumbre de ubicación de ~300 m."}{" "}
                  Marco MOON_ME_DE421. El muestreo LOLA de 20 m no implica una
                  precisión efectiva uniforme.
                </p>
              )}
              <Source site={leftSite} name={ref.name} />
              <Source
                site={rightSite}
                name={row ? `Candidata ${row.rank}` : "Tierra"}
              />
              <p>
                Contexto global:{" "}
                <a
                  href="https://svs.gsfc.nasa.gov/4720/"
                  target="_blank"
                  rel="noreferrer"
                >
                  NASA LROC + LOLA
                </a>
                , MOLA y NASA Blue Marble. El color lunar polar se completa con
                albedo LOLA; no mide composición. Los colores de los cuerpos
                identifican ubicaciones; la rampa mide una variable.
              </p>
              <p>
                Los derivados visuales se cargan bajo demanda. No modifican
                distancias, métricas ni elegibilidad. Rugosidad visual no
                disponible: se conserva el descriptor original del motor.
              </p>
              <a
                href={`${import.meta.env.BASE_URL}analysis/surface/unified/catalog.json`}
                target="_blank"
                rel="noreferrer"
              >
                Catálogo de derivados y huellas SHA-256 ↗
              </a>
              {loaded && (
                <>
                  <h3>Procedencia del ranking</h3>
                  <p>{loaded.notice}</p>
                  <p>
                    {loaded.data.engine_id} · ajuste{" "}
                    {loaded.data.model_fitted_at} ·{" "}
                    {loaded.version || "sin release asociada"}
                  </p>
                  <a
                    href={`${import.meta.env.BASE_URL}analysis/simulation/provenance.json`}
                    target="_blank"
                    rel="noreferrer"
                  >
                    Identidades de las demostraciones ↗
                  </a>
                  {row && (
                    <>
                      <h3>Mediciones y contribuciones</h3>
                      <p>
                        Valores originales por descriptor. Δ = candidata −
                        referencia; los aportes firmados suman 100 % dentro de
                        cada dimensión. La correlación permite aportes negativos
                        o superiores a 100 %.
                      </p>
                      {allFeatures.map((f, i) => (
                        <article className="u-feature" key={`${f.id}/${i}`}>
                          <h4>
                            {features[f.id]?.label || f.id}{" "}
                            <small>{features[f.id]?.unit}</small>
                          </h4>
                          <small>{viewNames[f.view] || f.view}</small>
                          <dl>
                            <div>
                              <dt>{ref.name}</dt>
                              <dd>{number(f.reference)}</dd>
                            </div>
                            <div>
                              <dt>Tierra</dt>
                              <dd>{number(f.candidate)}</dd>
                            </div>
                            <div>
                              <dt>Δ original</dt>
                              <dd>
                                {f.reference == null
                                  ? "Sin dato"
                                  : signed(f.candidate - f.reference)}
                              </dd>
                            </div>
                            <div>
                              <dt>Aporte / Δ normalizada</dt>
                              <dd>
                                {signed(f.share * 100)} % / {signed(f.z_delta)}
                              </dd>
                            </div>
                          </dl>
                        </article>
                      ))}
                      <CandidateRecord
                        regionId={row.region_id}
                        version={loaded.version || ""}
                        demo={loaded.source === "demo"}
                      />
                    </>
                  )}
                  <WeightsPanel loaded={loaded} />
                </>
              )}
              <label>
                Fuente del motor
                <select
                  value={state.engineSource}
                  onChange={(e) =>
                    update({
                      engineSource: e.target
                        .value as AtlasState["engineSource"],
                    })
                  }
                >
                  <option value="auto">
                    Servicio; demostración si falta publicación
                  </option>
                  <option value="demo">Demostración del repositorio</option>
                </select>
              </label>
            </div>
          </details>
        </aside>
        <section className="u-candidates" aria-label="Candidatas terrestres">
          <header>
            <h2>
              Candidatas en la Tierra{" "}
              <span>{rows.length.toString().padStart(2, "0")}</span>
            </h2>
            <small>Selecciona un marcador o usa esta lista</small>
          </header>
          {rows.length > 0 ? (
            <div className="u-candidate-list">
              {rows.map((r) => (
                <button
                  key={r.region_id}
                  aria-pressed={row?.region_id === r.region_id}
                  onClick={() => update({ regionId: r.region_id })}
                >
                  <b>{r.rank.toString().padStart(2, "0")}</b>
                  <span>
                    {location(r)}
                    <small>{eligibility(r.scenario_eligibility)}</small>
                  </span>
                  <strong>
                    {distance(r.score)}
                    <small>distancia</small>
                  </strong>
                </button>
              ))}
            </div>
          ) : (
            <p className="u-empty">
              {resource.loading
                ? "Consultando ubicaciones…"
                : "Sin comparaciones publicadas para esta referencia. Puedes explorar su terreno."}
            </p>
          )}
        </section>
      </div>
    </section>
  );
}
function Source({ site, name }: { site?: VisualSite; name: string }) {
  return (
    <div className="u-source">
      <h4>{name}</h4>
      {site?.body === "Earth" && (
        <p>
          Derivado de Copernicus WorldDEM-30. © DLR e.V. 2010–2014 y Airbus
          Defence and Space GmbH 2014–2018, proporcionado bajo COPERNICUS por la
          Unión Europea y ESA.{" "}
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
            Centro: {location(site)} · ventana {number(site.window_m / 1000, 1)}{" "}
            km · celda {site.cell_m} m · nativo {site.native_resolution_m}
            {typeof site.native_resolution_m === "number" ? " m" : ""}.
          </p>
          <p>
            Datum: {site.datum}. Cobertura visual {pct(site.coverage)}. Error de
            cuantización ≤ {number(site.quantization_error_m, 3)} m.
          </p>
        </>
      ) : (
        <p className="u-no-data">
          Sin DEM preparado para esta ubicación y escala.
        </p>
      )}
    </div>
  );
}
