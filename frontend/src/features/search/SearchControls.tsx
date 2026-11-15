import {
  FUSION_LABELS,
  MISSING_LABELS,
  PROFILE_LABELS,
  STATUS_TEXT,
  VIEW_LABELS,
  type Controls,
  type Fusion,
  type MissingPolicy,
  type Profile,
  type ReferenceCatalog,
  type ReferenceEntry,
} from "../../domain/similarity";
import { pct, viewReason, type LoadedSearch } from "../simulation/model";
import type { EngineSearch } from "./useEngineSearch";
import { useI18n } from "../../i18n/I18nProvider";

type Props = {
  reference?: ReferenceEntry;
  catalog?: ReferenceCatalog;
  catalogError?: string;
  controls: Controls;
  setControls: (controls: Controls) => void;
  reset: () => void;
  blocked: boolean;
  search: EngineSearch;
};

const LIMITS = [10, 25, 50, 100];

/** Scientific mode: every parameter `POST /api/similarity/search` accepts, with the reason a view is off. */
export function SearchControls({
  reference,
  catalog,
  catalogError,
  controls,
  setControls,
  reset,
  blocked,
  search,
}: Props) {
  const { lang, t } = useI18n();
  const loaded: LoadedSearch | undefined = search.loaded;
  const live = loaded?.source === "live" ? loaded : undefined;
  const set = (patch: Partial<Controls>) => setControls({ ...controls, ...patch });
  // Share among the views that can score for this reference, as the engine renormalises them.
  const total = Object.entries(controls.weights).reduce(
    (a, [view, w]) => a + (reference?.views[view] === "reference_has_data" && w > 0 ? w : 0),
    0,
  );
  return (
    <section className="u-controls" aria-label={t("Parámetros de la búsqueda", "Search parameters")}>
      <header>
        <h3>{t("Parámetros de la búsqueda", "Search parameters")}</h3>
        <button type="button" onClick={reset} disabled={!controls.touched && !controls.profile && controls.limit === 25 && controls.fusion === "weighted" && controls.missingPolicy === "neutral" && controls.onlyEligible}>
          {t("Restablecer", "Reset")}
        </button>
      </header>
      <p className="u-controls-status" role="status">
        {search.unavailable
          ? t("Motor no disponible en este servidor: los controles no recalculan el ejemplo.", "Engine not available on this server: the controls do not recalculate the example.")
          : blocked
            ? t("Todas las dimensiones usables tienen peso 0: sube al menos una para buscar.", "Every usable dimension has weight 0: raise at least one to search.")
            : search.loading
              ? t("Recalculando…", "Recalculating…")
              : live
                ? `${live.data.candidates_ranked.toLocaleString(lang)} ${t("de", "of")} ${live.data.candidates_in_pool.toLocaleString(lang)} ${t("ventanas", "windows")} · ${live.timings?.cache_hit ? t("desde caché", "from cache") : `${live.timings?.engine_ms.toLocaleString(lang)} ms`}`
                : search.error || t("Esperando respuesta…", "Waiting for a response…")}
      </p>
      {catalogError && <p className="u-controls-note">{t("Catálogo de referencias", "Reference catalog")}: {catalogError}</p>}
      <fieldset>
        <legend>{t("Peso de cada dimensión", "Weight of each dimension")}</legend>
        {Object.keys(VIEW_LABELS).map((view) => {
          const status = reference?.views[view];
          const usable = status === "reference_has_data";
          const report = loaded?.data.views[view];
          const value = controls.weights[view] ?? 0;
          const share = usable && total > 0 && value > 0 ? value / total : 0;
          return (
            <div key={view} className={`u-weight${usable ? "" : " is-off"}`}>
              <label htmlFor={`w-${view}`}>
                {VIEW_LABELS[view]}
                <span>{usable ? `${pct(share)} ${t("del total", "of total")}` : t("apagada", "off")}</span>
              </label>
              <input
                id={`w-${view}`}
                type="range"
                min="0"
                max="1"
                step="0.05"
                value={value}
                disabled={!usable || search.unavailable}
                aria-describedby={`w-${view}-why`}
                onChange={(e) =>
                  set({ touched: true, weights: { ...controls.weights, [view]: Number(e.target.value) } })
                }
              />
              <small id={`w-${view}-why`}>
                {!status
                  ? t("Sin información del catálogo.", "No catalog information.")
                  : !usable
                    ? `${t("No puntúa", "Does not score")}: ${STATUS_TEXT[status]}.`
                    : report
                      ? `${report.status === "used" ? `${t("Peso efectivo", "Effective weight")} ${pct(loaded?.data.weights_effective[view] ?? 0)}` : viewReason(report)}${report.coverage_fraction != null ? ` · ${t("medida en", "measured in")} ${pct(report.coverage_fraction)} ${t("de las ventanas", "of the windows")}` : ""}${report.fit_population?.mode === "biased_enriched_only" ? ` · ${t("ajuste provisional", "provisional fit")}` : ""}.`
                      : t("Con datos de la referencia.", "The reference has data.")}
              </small>
            </div>
          );
        })}
      </fieldset>
      <div className="u-control-grid">
        <label>
          {t("Perfil de elegibilidad", "Eligibility profile")}
          <select
            value={controls.profile ?? ""}
            onChange={(e) => set({ profile: (e.target.value || undefined) as Profile | undefined })}
          >
            <option value="">{t("Por defecto del servidor", "Server default")}</option>
            {(Object.keys(PROFILE_LABELS) as Profile[]).map((p) => (
              <option key={p} value={p}>
                {PROFILE_LABELS[p]}
              </option>
            ))}
          </select>
        </label>
        <label>
          {t("Fusión de dimensiones", "Dimension fusion")}
          <select value={controls.fusion} onChange={(e) => set({ fusion: e.target.value as Fusion })}>
            {(Object.keys(FUSION_LABELS) as Fusion[]).map((f) => (
              <option key={f} value={f}>
                {FUSION_LABELS[f]}
              </option>
            ))}
          </select>
        </label>
        <label>
          {t("Dimensiones ausentes", "Missing dimensions")}
          <select
            value={controls.missingPolicy}
            onChange={(e) => set({ missingPolicy: e.target.value as MissingPolicy })}
          >
            {(Object.keys(MISSING_LABELS) as MissingPolicy[]).map((m) => (
              <option key={m} value={m}>
                {MISSING_LABELS[m]}
              </option>
            ))}
          </select>
        </label>
        <label>
          {t("Resultados", "Results")}
          <select value={controls.limit} onChange={(e) => set({ limit: Number(e.target.value) })}>
            {LIMITS.map((n) => (
              <option key={n} value={n}>
                {n} {t("candidatas", "candidates")}
              </option>
            ))}
          </select>
        </label>
        <label className="u-check">
          <input
            type="checkbox"
            checked={controls.onlyEligible}
            onChange={(e) => set({ onlyEligible: e.target.checked })}
          />
          {t("Solo ventanas que cumplen el perfil", "Only windows that meet the profile")}
        </label>
      </div>
      {reference?.body === "Moon" && controls.profile !== "polar_cold_v1" && (
        <p className="u-controls-note">
          {t(
            "La publicación del atlas usa el perfil polar frío para las referencias lunares. Este servidor solo tiene ventanas elegibles si su almacén incluye ese perfil.",
            "The atlas release uses the cold polar profile for lunar references. This server only has eligible windows if its store includes that profile.",
          )}
        </p>
      )}
      {catalog && (
        <p className="u-controls-note">
          {t("Motor", "Engine")} {catalog.engine_status === "unsupervised_pending_blind_validation" ? t("experimental, sin validación ciega", "experimental, not blind-validated") : catalog.engine_status}
          {live?.queryId && <> · {t("consulta", "query")} <code title={live.queryId}>{live.queryId.slice(0, 10)}</code></>}
        </p>
      )}
    </section>
  );
}
