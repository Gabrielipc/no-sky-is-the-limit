import { useEffect, useState } from "react";
import { placeLabel } from "../../domain/similarity";

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
  const [mode, setMode] = useState<Mode>();
  const [request, setRequest] = useState<{ mode: Mode; result?: Pilot; error?: string }>();
  useEffect(() => {
    if (!mode) return;
    const controller = new AbortController();
    fetch(`/api/similarity/jezero-pilot?mode=${mode}`, { signal: controller.signal })
      .then(async (response) => {
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || "No se pudo consultar el piloto.");
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
    <section className="u-card" aria-label="Piloto de materiales de Jezero">
      <h2>Piloto de materiales de Jezero</h2>
      <div className="u-segment" role="group" aria-label="Ranking del piloto">
        <button aria-pressed={mode === "combined"} onClick={() => setMode("combined")}>Relieve y espectro</button>
        <button aria-pressed={mode === "topography"} onClick={() => setMode("topography")}>Solo relieve</button>
      </div>
      {mode && !current && <p role="status">Consultando el piloto…</p>}
      {current?.error && <p role="status">{current.error}</p>}
      {pilot && (
        <>
          <p>
            {pilot.coverage.spectral_windows} de {pilot.coverage.windows} ventanas con espectro comparable.
            {" "}Bloques evaluados: {pilot.coverage.bounds.map((block) => block.id).join(", ")}.
          </p>
          <p>
            Relieve de {pilot.reference.topographic_side_m / 1000} km con {pilot.weights.topografia * 100} % de peso.
            {pilot.weights.espectral ? ` Espectro de ${pilot.reference.spectral_side_m / 1000} km con ${pilot.weights.espectral * 100} % de peso.` : ""}
          </p>
          {pilot.warnings.map((warning) => <p key={warning}>{warning}</p>)}
          <div className="table-wrap">
            <table>
              <caption>{pilot.version} · {pilot.candidates_ranked} resultados · menor distancia indica mayor similitud</caption>
              <thead><tr><th>Puesto</th><th>Ventana</th><th>Distancia</th></tr></thead>
              <tbody>{pilot.results.map((row, index) => (
                <tr key={row.region_id}>
                  <td>{index + 1}</td><td>{placeLabel(row.latitude, row.longitude)}</td>
                  <td>{row.score.toLocaleString("es", { maximumFractionDigits: 4 })}</td>
                </tr>
              ))}</tbody>
            </table>
          </div>
        </>
      )}
    </section>
  );
}
