import { useEffect, useState } from "react";
import { UnifiedWorkspace } from "../features/unified/UnifiedWorkspace";
import { useAtlasState } from "./useAtlasState";
import { CompareWorkspace } from "../features/compare/CompareWorkspace";
import { ExploreWorkspace } from "../features/explore/ExploreWorkspace";
import { WorldWorkspace } from "../features/world/WorldWorkspace";
import { DimensionsWorkspace } from "../features/dimensions/DimensionsWorkspace";
import {
  SimulationWorkspace,
  EngineCompare,
  EngineSensitivity,
} from "../features/simulation/SimulationWorkspace";
import { ExploreJourney } from "../features/simulation/ExploreJourney";
import { LocalScaleReview } from "../features/simulation/LocalScaleReview";
import { useSimulation } from "../features/simulation/useSimulation";
import { location, references } from "../features/simulation/model";
import { AtlasReview } from "../features/simulation/AtlasReview";
import "../features/simulation/simulation.css";
import { LandingPage } from "../features/landing/LandingPage";

export function AtlasShell() {
  const { state, update, adjusted, dismissAdjustment } = useAtlasState();
  const [help, setHelp] = useState(false);
  const resource = useSimulation(state);
  const active = ["surface", "explore"].includes(state.view)
    ? "surface"
    : ["simulation", "world"].includes(state.view)
      ? "simulation"
      : ["compare", "dimensions"].includes(state.view)
        ? "compare"
        : "sensitivity";
  useEffect(() => {
    window.scrollTo({ top: 0, behavior: "instant" });
  }, [state.view]);
  const reference = references.find((r) => r.id === state.reference)!;
  useEffect(() => {
    if (
      resource.loaded?.source === "published" &&
      resource.loaded.version &&
      state.release !== resource.loaded.version
    )
      update({ release: resource.loaded.version });
  }, [resource.loaded, state.release, update]);
  const selected = resource.loaded?.data.results.find(
    (r) => r.region_id === state.regionId,
  );
  const masthead = (
    <header className="regolith-header">
      <a
        href="/"
        className="regolith-brand"
        aria-label="Regolith, inicio"
        onClick={(e) => {
          e.preventDefault();
          update({ view: "unified", method: "engine" });
        }}
      >
        <img
          src={`${import.meta.env.BASE_URL}analysis/brand/regolith-noche.png`}
          alt="Regolith · No Sky Is the Limit"
        />
      </a>
      <nav aria-label="Navegación principal">
        <button
          aria-current={state.view === "unified" ? "page" : undefined}
          onClick={() => update({ view: "unified", method: "engine" })}
        >
          Explorar y comparar
        </button>
        <details className="regolith-tools">
          <summary>Otros análisis</summary>
          <div>
            {(
              [
                {
                  view: "world",
                  method: "atlas",
                  label: "Atlas global a 30 m",
                },
                {
                  view: "compare",
                  method: "local",
                  label: "Controles locales",
                },
                {
                  view: "sensitivity",
                  method: "local",
                  label: "Sensibilidad de resolución",
                },
                {
                  view: "dimensions",
                  method: "local",
                  label: "Dimensiones de Jezero",
                },
                {
                  view: "explore",
                  method: "local",
                  label: "Muestreo regional",
                },
              ] as const
            ).map((t) => (
              <button
                key={t.view}
                onClick={(e) => {
                  e.currentTarget.closest("details")?.removeAttribute("open");
                  update({
                    view: t.view,
                    method: t.method,
                    reference: "jezero",
                  });
                }}
              >
                {t.label}
              </button>
            ))}
          </div>
        </details>
      </nav>
      <span className="regolith-descriptor">NO SKY IS THE LIMIT</span>
    </header>
  );
  if (state.view === "landing")
    return <LandingPage onStart={() => update({ view: "unified", method: "engine" })} />;
  if (state.view === "unified")
    return (
      <>
        <a className="skip-link" href="#main-content">
          Saltar al contenido
        </a>
        {masthead}
        <main className="regolith-main" id="main-content">
          {adjusted && (
            <div className="parameter-notice" role="status">
              Se ajustaron parámetros del enlace.
              <button onClick={dismissAdjustment}>Entendido</button>
            </div>
          )}
          <UnifiedWorkspace state={state} update={update} resource={resource} />
        </main>
        <footer className="regolith-footer">
          <span>REGOLITH · EXPLORACIÓN CON CONTEXTO</span>
          <span>
            Datos medidos · límites visibles · resultados exploratorios
          </span>
        </footer>
      </>
    );
  return (
    <>
      <a className="skip-link" href="#main-content">
        Saltar al contenido
      </a>
      {masthead}
      <main id="main-content">
        <section className="journey-context" aria-label="Contexto compartido">
          <label>
            Referencia planetaria
            <select
              value={state.reference}
              onChange={(e) =>
                update({
                  view: active,
                  reference: e.target.value as typeof state.reference,
                  regionId: "",
                  method: "engine",
                  explorePanel: "reference",
                  surfaceSite: "mars-jezero-fan",
                  surfaceMode: "space",
                  exaggeration: 1,
                })
              }
            >
              {references.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.name} · {r.detail}
                </option>
              ))}
            </select>
          </label>
          <div>
            <small>CANDIDATA CONSERVADA</small>
            <strong>
              {state.method === "local"
                ? state.site === "earth-utah"
                  ? "Utah · control local"
                  : "Atacama · control local"
                : state.regionId
                  ? selected
                    ? `Puesto ${selected.rank} · ${location(selected)}`
                    : state.regionId
                  : "Selecciona una ventana en el ranking"}
            </strong>
          </div>
          <div>
            <small>PUBLICACIÓN / MÉTODO</small>
            <strong>
              {state.method === "local"
                ? "Evidencia local revisada"
                : state.method === "atlas"
                  ? state.release || "Atlas · sin versión confirmada"
                  : resource.loaded?.source === "demo"
                    ? "Ejemplo precalculado · sin release"
                    : resource.loaded?.version ||
                      state.release ||
                      (resource.error
                        ? "Motor · sin resultados disponibles"
                        : "Motor · comprobando disponibilidad")}
            </strong>
          </div>
        </section>
        {adjusted && (
          <div className="parameter-notice" role="status">
            Se ajustaron parámetros del enlace a las opciones disponibles.
            <button onClick={dismissAdjustment}>Entendido</button>
          </div>
        )}
        {help && (
          <section id="atlas-help" className="help-panel">
            <h2>Cómo leer este simulador</h2>
            <p>
              Elige una referencia, revisa el ranking y abre una candidata. Una
              distancia menor indica mayor parecido dentro del método mostrado.
              La cobertura explica cuánto pudo evaluarse; los datos ausentes
              conservan su estado. La comparación local de 1,8 km y el motor de
              ventanas de 3 km usan evidencia distinta.
            </p>
            <p>
              La exageración vertical ayuda a leer el relieve. A 1× se conservan
              las proporciones reales. Las candidatas son hipótesis de estudio;
              el sistema no evalúa movilidad.
            </p>
          </section>
        )}
        <div
          className="journey-subnav"
          role="group"
          aria-label="Herramientas del recorrido"
        >
          {active === "surface" ? (
            <>
              <button
                aria-pressed={
                  state.view === "surface" && state.explorePanel === "reference"
                }
                onClick={() =>
                  update({
                    view: "surface",
                    method: "engine",
                    explorePanel: "reference",
                    surfaceSite: "mars-jezero-fan",
                  })
                }
              >
                Referencia
              </button>
              <button
                aria-pressed={
                  state.view === "surface" &&
                  state.explorePanel === "candidates"
                }
                onClick={() =>
                  update({
                    view: "surface",
                    method: "engine",
                    explorePanel: "candidates",
                  })
                }
              >
                Candidatas del motor
              </button>
              <button
                aria-pressed={
                  state.view === "surface" && state.explorePanel === "controls"
                }
                onClick={() =>
                  update({
                    view: "surface",
                    method: "local",
                    explorePanel: "controls",
                    reference: "jezero",
                  })
                }
              >
                Controles con DEM local
              </button>
              <button
                aria-pressed={state.view === "explore"}
                onClick={() =>
                  update({
                    view: "explore",
                    method: "local",
                    reference: "jezero",
                  })
                }
              >
                Muestreo regional
              </button>
            </>
          ) : active === "simulation" ? (
            <>
              <button
                aria-pressed={state.view === "simulation"}
                onClick={() => update({ view: "simulation", method: "engine" })}
              >
                Motor multidimensional
              </button>
              <button
                aria-pressed={state.view === "world"}
                onClick={() =>
                  update({
                    view: "world",
                    method: "atlas",
                    reference: "jezero",
                  })
                }
              >
                Atlas a 30 m
              </button>
              <label className="source-control">
                Fuente del motor
                <select
                  value={state.engineSource}
                  onChange={(e) =>
                    update({ engineSource: e.target.value as "auto" | "demo" })
                  }
                >
                  <option value="auto">
                    Servicio; ejemplo si no hay publicación
                  </option>
                  <option value="demo">Demostración del repositorio</option>
                </select>
              </label>
            </>
          ) : (
            <>
              <button
                aria-pressed={state.method === "engine"}
                onClick={() => update({ method: "engine", view: active })}
              >
                Candidata del motor
              </button>
              <button
                aria-pressed={state.method === "atlas"}
                onClick={() =>
                  update({ method: "atlas", view: active, reference: "jezero" })
                }
              >
                Candidata del atlas
              </button>
              <button
                aria-pressed={
                  state.method === "local" && state.view !== "dimensions"
                }
                onClick={() =>
                  update({ method: "local", view: active, reference: "jezero" })
                }
              >
                Controles locales · 1,8 km
              </button>
              {active === "compare" && (
                <button
                  aria-pressed={state.view === "dimensions"}
                  onClick={() =>
                    update({
                      view: "dimensions",
                      method: "local",
                      reference: "jezero",
                    })
                  }
                >
                  Más dimensiones locales
                </button>
              )}
            </>
          )}
        </div>
        {state.view === "surface" ? (
          <ExploreJourney state={state} update={update} resource={resource} />
        ) : state.view === "simulation" ? (
          <SimulationWorkspace
            state={state}
            update={update}
            resource={resource}
          />
        ) : state.view === "world" ? (
          <WorldWorkspace state={state} update={update} />
        ) : state.view === "dimensions" ? (
          <DimensionsWorkspace state={state} update={update} />
        ) : state.view === "explore" ? (
          <ExploreWorkspace state={state} update={update} />
        ) : state.method === "atlas" ? (
          <AtlasReview state={state} update={update} />
        ) : state.view === "compare" ? (
          state.method === "engine" ? (
            <EngineCompare state={state} update={update} resource={resource} />
          ) : (
            <CompareWorkspace state={state} update={update} />
          )
        ) : state.method === "engine" ? (
          <EngineSensitivity
            state={state}
            update={update}
            resource={resource}
          />
        ) : (
          <LocalScaleReview state={state} update={update} />
        )}
      </main>
      <footer className="app-footer">
        <span>✳ NO SKY IS THE LIMIT · SIMULADOR GEOESPACIAL</span>
        <span>
          Datos medidos · cobertura explícita · resultados exploratorios
        </span>
      </footer>
    </>
  );
}
