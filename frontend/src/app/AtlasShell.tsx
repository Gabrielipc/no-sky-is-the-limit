import { lazy, Suspense, useEffect } from "react";
import { UnifiedWorkspace } from "../features/unified/UnifiedWorkspace";
import { useAtlasState } from "./useAtlasState";
// The landing brings its own 3D stack (three.js): load it only when the landing is shown.
const LandingPage = lazy(() =>
  import("../features/landing/LandingPage").then((m) => ({ default: m.LandingPage })),
);

export function AtlasShell() {
  const { state, update, adjusted, dismissAdjustment } = useAtlasState();
  useEffect(() => {
    window.scrollTo({ top: 0, behavior: "instant" });
    if (state.view !== "landing" && state.view !== "unified") {
      update({ view: "unified", method: "engine" });
    }
  }, [state.view, update]);
  const masthead = (
    <header className="regolith-header">
      <a
        href="/"
        className="regolith-brand"
        aria-label="Regolith, inicio"
        onClick={(e) => {
          e.preventDefault();
          update({ view: "landing" });
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
          Explorar
        </button>
      </nav>
      <label className="regolith-mode">
        <span>
          Modo científico
          <small>{state.science ? "Datos completos y pesos" : "Vista sencilla"}</small>
        </span>
        <input
          type="checkbox"
          role="switch"
          checked={state.science}
          aria-checked={state.science}
          onChange={(e) =>
            update(
              e.target.checked
                ? { science: true }
                : { science: false, view: "unified", method: "engine", exaggeration: 1, visualLayer: "elevation" },
            )
          }
        />
        <i aria-hidden="true" />
      </label>
    </header>
  );
  if (state.view === "landing")
    return (
      <Suspense fallback={<div className="landing-loading" role="status">Cargando Regolith…</div>}>
        <LandingPage onStart={() => update({ view: "unified", method: "engine" })} />
      </Suspense>
    );
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
          <UnifiedWorkspace state={state} update={update} />
        </main>
        <footer className="regolith-footer">
          <span>REGOLITH · NO SKY IS THE LIMIT</span>
          <span>Resultados experimentales basados en datos de NASA</span>
        </footer>
      </>
    );
}
