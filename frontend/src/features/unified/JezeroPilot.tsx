import { useEffect, useState } from "react";
import { placeLabel } from "../../domain/similarity";
import { useI18n } from "../../i18n/I18nProvider";
import { tr, warningText } from "../../i18n/lang";

type Mode = "combined" | "topography";
type Pilot = {
  version: string;
  coverage: { windows: number; spectral_windows: number; bounds: { id: string }[] };
  weights: { topografia: number; espectral?: number };
  reference: { spectral_side_m: number; topographic_side_m: number };
  candidates_ranked: number;
  results: { region_id: string; longitude: number; latitude: number; score: number }[];
  warnings: string[];
};

export function JezeroPilot() {
  const { lang, t } = useI18n();
  const [mode, setMode] = useState<Mode>();
  const [request, setRequest] = useState<{ mode: Mode; result?: Pilot; error?: string }>();
  useEffect(() => {
    if (!mode) return;
    const controller = new AbortController();
    fetch(`/api/similarity/jezero-pilot?mode=${mode}`, { signal: controller.signal })
      .then(async (response) => {
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || tr("No se pudo consultar el piloto.", "The pilot could not be queried."));
        if (!controller.signal.aborted) setRequest({ mode, result: data });
      })
      .catch((error: Error) => {
        if (!controller.signal.aborted) setRequest({ mode, error: error.message });
      });
    return () => controller.abort();
  }, [mode]);

  const current = request?.mode === mode ? request : undefined;
  const pilot = current?.result;
  return (
    <section className="u-card" aria-label={t("Piloto de materiales de Jezero", "Jezero materials pilot")}>
      <h2>{t("Piloto de materiales de Jezero", "Jezero materials pilot")}</h2>
      <div className="u-segment" role="group" aria-label={t("Ranking del piloto", "Pilot ranking")}>
        <button aria-pressed={mode === "combined"} onClick={() => setMode("combined")}>{t("Relieve y espectro", "Relief and spectrum")}</button>
        <button aria-pressed={mode === "topography"} onClick={() => setMode("topography")}>{t("Solo relieve", "Relief only")}</button>
      </div>
      {mode && !current && <p role="status">{t("Consultando el piloto…", "Querying the pilot…")}</p>}
      {current?.error && <p role="status">{current.error}</p>}
      {pilot && (
        <>
          <p>
            {t(
              `${pilot.coverage.spectral_windows} de ${pilot.coverage.windows} ventanas con espectro comparable.`,
              `${pilot.coverage.spectral_windows} of ${pilot.coverage.windows} windows with a comparable spectrum.`,
            )}
            {" "}{t("Bloques evaluados", "Blocks assessed")}: {pilot.coverage.bounds.map((block) => block.id).join(", ")}.
          </p>
          <p>
            {t(
              `Relieve de ${pilot.reference.topographic_side_m / 1000} km con ${pilot.weights.topografia * 100} % de peso.`,
              `Relief over ${pilot.reference.topographic_side_m / 1000} km with ${pilot.weights.topografia * 100}% weight.`,
            )}
            {pilot.weights.espectral
              ? t(
                  ` Espectro de ${pilot.reference.spectral_side_m / 1000} km con ${pilot.weights.espectral * 100} % de peso.`,
                  ` Spectrum over ${pilot.reference.spectral_side_m / 1000} km with ${pilot.weights.espectral * 100}% weight.`,
                )
              : ""}
          </p>
          {pilot.warnings.map((warning) => <p key={warning}>{warningText(warning, lang)}</p>)}
          <div className="table-wrap">
            <table>
              <caption>{pilot.version} · {pilot.candidates_ranked} {t("resultados · menor distancia indica mayor similitud", "results · lower distance means more similar")}</caption>
              <thead><tr><th>{t("Puesto", "Rank")}</th><th>{t("Ventana", "Window")}</th><th>{t("Distancia", "Distance")}</th></tr></thead>
              <tbody>{pilot.results.map((row, index) => (
                <tr key={row.region_id}>
                  <td>{index + 1}</td><td>{placeLabel(row.latitude, row.longitude)}</td>
                  <td>{row.score.toLocaleString(lang, { maximumFractionDigits: 4 })}</td>
                </tr>
              ))}</tbody>
            </table>
          </div>
        </>
      )}
    </section>
  );
}
