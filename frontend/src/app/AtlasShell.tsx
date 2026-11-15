import { lazy, Suspense, useEffect } from "react";
import { UnifiedWorkspace } from "../features/unified/UnifiedWorkspace";
import { NicaraguaWorkspace } from "../features/nicaragua/NicaraguaWorkspace";
import { useAtlasState } from "./useAtlasState";
import { LanguageSwitch, useI18n } from "../i18n/I18nProvider";
// The landing brings its own 3D stack (three.js): load it only when the landing is shown.
const LandingPage = lazy(() =>
  import("../features/landing/LandingPage").then((m) => ({ default: m.LandingPage })),
);

export function AtlasShell() {
  const { state, update, adjusted, dismissAdjustment } = useAtlasState();
  const { t } = useI18n();
  useEffect(() => {
    window.scrollTo({ top: 0, behavior: "instant" });
    if (state.view !== "landing" && state.view !== "unified" && state.view !== "nicaragua") {
      update({ view: "unified", method: "engine" });
    }
  }, [state.view, update]);
  const masthead = (
    <header className="regolith-header">
      <a
        href="/"
        className="regolith-brand"
        aria-label={t("Regolith, inicio", "Regolith, home")}
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
      <nav aria-label={t("Navegación principal", "Main navigation")}>
        <button
          aria-current={state.view === "unified" ? "page" : undefined}
          onClick={() => update({ view: "unified", method: "engine" })}
        >
          {t("Explorar", "Explore")}
        </button>
        <button
          aria-current={state.view === "nicaragua" ? "page" : undefined}
          onClick={() => update({ view: "nicaragua", regionId: "" })}
        >
          Nicaragua
        </button>
      </nav>
      <label className="regolith-mode">
        <span>
          {t("Modo científico", "Scientific mode")}
          <small>{state.science ? t("Datos completos y pesos", "Full data and weights") : t("Vista sencilla", "Simple view")}</small>
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
                : {
                    science: false,
                    view: state.view === "nicaragua" ? "nicaragua" : "unified",
                    method: "engine",
                    exaggeration: 1,
                    visualLayer: "elevation",
                  },
            )
          }
        />
        <i aria-hidden="true" />
      </label>
      <LanguageSwitch />
    </header>
  );
  if (state.view === "landing")
    return (
      <Suspense fallback={<div className="landing-loading" role="status">{t("Cargando Regolith…", "Loading Regolith…")}</div>}>
        <LandingPage onStart={() => update({ view: "unified", method: "engine" })} />
      </Suspense>
    );
  return (
      <>
        <a className="skip-link" href="#main-content">
          {t("Saltar al contenido", "Skip to content")}
        </a>
        {masthead}
        <main className="regolith-main" id="main-content">
          {adjusted && (
            <div className="parameter-notice" role="status">
              {t("Se ajustaron parámetros del enlace.", "Some link parameters were adjusted.")}
              <button onClick={dismissAdjustment}>{t("Entendido", "Got it")}</button>
            </div>
          )}
          {state.view === "nicaragua" ? (
            <NicaraguaWorkspace state={state} update={update} />
          ) : (
            <UnifiedWorkspace state={state} update={update} />
          )}
        </main>
        <footer className="regolith-footer">
          <span>REGOLITH · NO SKY IS THE LIMIT</span>
          <span>{t("Resultados experimentales basados en datos de NASA", "Experimental results based on NASA data")}</span>
        </footer>
      </>
    );
}
