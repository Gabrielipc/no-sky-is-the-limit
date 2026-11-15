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
  const loaded: LoadedSearch | undefined = search.loaded;
  const live = loaded?.source === "live" ? loaded : undefined;
  const set = (patch: Partial<Controls>) => setControls({ ...controls, ...patch });
  // Share among the views that can score for this reference, as the engine renormalises them.
  const total = Object.entries(controls.weights).reduce(
    (a, [view, w]) => a + (reference?.views[view] === "reference_has_data" && w > 0 ? w : 0),
    0,
  );
  return (
    <section className="u-controls" aria-label="Parámetros de la búsqueda">
      <header>
        <h3>Parámetros de la búsqueda</h3>
        <button type="button" onClick={reset} disabled={!controls.touched && !controls.profile && controls.limit === 25 && controls.fusion === "weighted" && controls.missingPolicy === "neutral" && controls.onlyEligible}>
          Restablecer
        </button>
      </header>
      <p className="u-controls-status" role="status">
        {search.unavailable
          ? "Motor no disponible en este servidor: los controles no recalculan el ejemplo."
          : blocked
            ? "Todas las dimensiones usables tienen peso 0: sube al menos una para buscar."
            : search.loading
              ? "Recalculando…"
              : live
                ? `${live.data.candidates_ranked.toLocaleString("es")} de ${live.data.candidates_in_pool.toLocaleString("es")} ventanas · ${live.timings?.cache_hit ? "desde caché" : `${live.timings?.engine_ms.toLocaleString("es")} ms`}`
                : search.error || "Esperando respuesta…"}
      </p>
      {catalogError && <p className="u-controls-note">Catálogo de referencias: {catalogError}</p>}
      <fieldset>
        <legend>Peso de cada dimensión</legend>
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
                <span>{usable ? `${pct(share)} del total` : "apagada"}</span>
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
                  ? "Sin información del catálogo."
                  : !usable
                    ? `No puntúa: ${STATUS_TEXT[status]}.`
                    : report
                      ? `${report.status === "used" ? `Peso efectivo ${pct(loaded?.data.weights_effective[view] ?? 0)}` : viewReason(report)}${report.coverage_fraction != null ? ` · medida en ${pct(report.coverage_fraction)} de las ventanas` : ""}${report.fit_population?.mode === "biased_enriched_only" ? " · ajuste provisional" : ""}.`
                      : "Con datos de la referencia."}
              </small>
            </div>
          );
        })}
      </fieldset>
      <div className="u-control-grid">
        <label>
          Perfil de elegibilidad
          <select
            value={controls.profile ?? ""}
            onChange={(e) => set({ profile: (e.target.value || undefined) as Profile | undefined })}
          >
            <option value="">Por defecto del servidor</option>
            {(Object.keys(PROFILE_LABELS) as Profile[]).map((p) => (
              <option key={p} value={p}>
                {PROFILE_LABELS[p]}
              </option>
            ))}
          </select>
        </label>
        <label>
          Fusión de dimensiones
          <select value={controls.fusion} onChange={(e) => set({ fusion: e.target.value as Fusion })}>
            {(Object.keys(FUSION_LABELS) as Fusion[]).map((f) => (
              <option key={f} value={f}>
                {FUSION_LABELS[f]}
              </option>
            ))}
          </select>
        </label>
        <label>
          Dimensiones ausentes
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
          Resultados
          <select value={controls.limit} onChange={(e) => set({ limit: Number(e.target.value) })}>
            {LIMITS.map((n) => (
              <option key={n} value={n}>
                {n} candidatas
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
          Solo ventanas que cumplen el perfil
        </label>
      </div>
      {reference?.body === "Moon" && controls.profile !== "polar_cold_v1" && (
        <p className="u-controls-note">
          La publicación del atlas usa el perfil polar frío para las referencias lunares. Este servidor
          solo tiene ventanas elegibles si su almacén incluye ese perfil.
        </p>
      )}
      {catalog && (
        <p className="u-controls-note">
          Motor {catalog.engine_status === "unsupervised_pending_blind_validation" ? "experimental, sin validación ciega" : catalog.engine_status}
          {live?.queryId && <> · consulta <code title={live.queryId}>{live.queryId.slice(0, 10)}</code></>}
        </p>
      )}
    </section>
  );
}
