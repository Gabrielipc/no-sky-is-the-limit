import type { Grid } from "./terrainModel";
import { number } from "../simulation/model";
export function Profiles({
  left,
  right,
  range,
  names,
}: {
  left?: Grid;
  right?: Grid;
  range: [number, number];
  names: [string, string];
}) {
  const lo = range[0],
    hi = range[1],
    y = (h: number) => 65 - ((h - lo) / (hi - lo || 1)) * 52;
  return (
    <section
      className="u-profiles"
      aria-label="Perfiles de terreno comparables"
    >
      <header>
        <strong>Un mismo corte, 1.800 m</strong>
        <small>
          A → B · oeste a este · altura respecto a la mediana · sin exageración
        </small>
      </header>
      <div>
        {[left, right].map((g, index) => (
          <figure key={index}>
            <figcaption>{names[index]}</figcaption>
            {g ? (
              <>
                <svg
                  viewBox="0 0 300 90"
                  role="img"
                  aria-label={`Perfil de ${names[index]}, 1800 metros de longitud, altura relativa de ${number(lo, 0)} a ${number(hi, 0)} metros`}
                >
                  <path d="M8 65H292" stroke="#85705A" />
                  <path
                    d={Array.from({ length: g.site.width }, (_, x) => {
                      const h =
                        g.heights[
                          Math.floor(g.site.height / 2) * g.site.width + x
                        ] - g.site.center_m;
                      return Number.isFinite(h)
                        ? `${x === 0 || !Number.isFinite(g.heights[Math.floor(g.site.height / 2) * g.site.width + x - 1]) ? "M" : "L"}${8 + (x / (g.site.width - 1)) * 284} ${y(h)}`
                        : "";
                    }).join(" ")}
                    fill="none"
                    stroke={index ? "#72AED6" : "#E8DAC2"}
                    strokeWidth="2"
                  />
                  <text x="8" y="84">
                    A · 0 m
                  </text>
                  <text x="292" y="84" textAnchor="end">
                    1.800 m · B
                  </text>
                  <text x="8" y="11">
                    {number(hi, 0)} m
                  </text>
                  <text x="292" y="60" textAnchor="end">
                    {number(lo, 0)} m
                  </text>
                </svg>
              </>
            ) : (
              <p className="u-no-profile">Sin DEM válido para este perfil</p>
            )}
          </figure>
        ))}
      </div>
    </section>
  );
}
