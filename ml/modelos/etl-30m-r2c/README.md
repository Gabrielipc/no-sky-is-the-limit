# Motor de similitud · modelo de la release `etl-30m-r2c`

Modelo ajustado del motor de similitud ML no supervisado (`motor-similitud-ml-v1`) que acompaña a la release del atlas `etl-30m-r2c`, la activa en `gs://regolith-analogos-gabi0808/releases/atlas30/`. Sustituye a [`etl-30m-r2b`](../etl-30m-r2b/README.md), que se ajustó con un muestreo dependiente del orden de lectura y una covarianza degenerada.

| Archivo | Contenido |
|---|---|
| `model.joblib` | Modelo ajustado (285 KB) |
| `model.json` | Informe legible del ajuste: vistas, estimador de covarianza, `fit_population` de las vistas puente |
| `jezero.json`, `haworth-fondo.json`, `de-gerlache-cresta.json` | Top 100 de cada referencia con los pesos por defecto (contrato [`motor-busqueda-v1`](../../../specs/api/motor-busqueda-v1.schema.json)) |
| `release-manifest.json` | Manifiesto de la release |

## Procedencia

- **Ajustado:** 2026-11-15T11:34:08Z, en una VM de GCP (`europe-west3`), con el código de la rama `etl-30m-r2` en el commit `7a90521`.
- **Población de ajuste:** 1 459 164 ventanas terrestres rankables, sin la cuenca reservada de Mojave; muestra de 200 000 ventanas por hash de `region_id` y semilla 20261114.
- **Hash del spec:** `4520fe49764a…`.
- **SHA-256 de `model.joblib`:** `3beb785f1bc5687d084e2ac708487e6bbfcc0580582c18c5b1d44e2689ce445e`.
- **Verificación de la release:** 0 errores y 0 avisos.

## Qué se corrigió respecto a r2b

- **Muestra reproducible.** Con la misma semilla y los mismos datos, el ranking es idéntico (comprobado en la nube con las tres referencias).
- **Covarianza degenerada.** En `escabrosidad`, `entorno_superficial` y `emisividad_cmg`, `MinCovDet` salió degenerado y se sustituyó por Ledoit‑Wolf (`ledoit_wolf_after_degenerate_min_cov_det`). Con el modelo r2b la variable de pendiente > 25° tenía varianza cero y se descartaba en silencio.

## Estabilidad medida: el modelo es reproducible, pero no del todo estable

Medida en la nube con [`scripts/estabilidad_motor.py`](../../../scripts/estabilidad_motor.py) ([resultado](../../../docs/evidencia-motor-similitud/estabilidad.json)): el ajuste de referencia frente a tres ajustes con otras semillas. Coincidencias de los 100 primeros resultados (en los 10 primeros, entre paréntesis):

| Referencia | Semilla 1 | Semilla 2 | Semilla 3 |
|---|---:|---:|---:|
| Jezero | 99 (10) | 79 (8) | 100 (10) |
| Haworth | 99 (10) | 79 (7) | 100 (10) |
| de Gerlache | 96 (9) | 34 (4) | 69 (4) |

- **Jezero y Haworth** son estables con dos de las tres semillas y pierden alrededor de una quinta parte con la otra.
- **de Gerlache no es fiable.** Con la semilla 2 cambian dos tercios del top 100 y con la 3, casi un tercio. Su referencia (pendiente P90 de 22°, relieve de 466 m) queda lejos de casi todo el pool, así que el orden entre las candidatas cercanas depende de detalles del ajuste.
- **Hipótesis sin comprobar sobre la semilla 2:** fue la única en que `escabrosidad` conservó `MinCovDet`; las otras dos usaron el respaldo de Ledoit‑Wolf. Si el estimador cambia el ranking, la guarda de degeneración es demasiado permisiva. No se ha aislado la causa.

**Cómo mostrarlo.** Tratad el ranking como una lista de candidatas plausibles, no como un orden exacto, y marcad de Gerlache con confianza baja.

## Sesgos y límites conocidos

- **Solo topografía.** Los rankings de Haworth y de Gerlache usan cuatro vistas topográficas; el radar (peso 0,2) se excluye y las vistas térmica, de entorno y de emisividad no intervienen con referencias de otro cuerpo.
- **Los análogos de las referencias polares salen solo del hemisferio norte.** Ninguna ventana del sur pasa el filtro de clima frío: la Antártida no tiene cobertura de suelo y las montañas del sur casi no tienen nieve.
- **El filtro significa «terreno frío», no «polar».** Un cuarto de las ventanas que pasan está al sur de 40° N, sobre todo en la meseta tibetana, por permafrost. Mongolia aparece en el top 10 de Haworth.
- **`termica` descansa en 100 ventanas medidas** (2 000 filas tras el remuestreo), de 40 teselas MODIS.
- **La vista de regímenes (GMM)** se comporta como un ranking grueso: sola, cambia entre semillas.
- **Sin ajustar:** `espectral` y `radar`. Lunar sin Tmin, amplitud, rocas, H ni S1.
- **de Gerlache queda fuera de su propia compuerta** de base (pendiente P90 de 22,4° frente al umbral inicial de 15°).
- **Estado:** `unsupervised_pending_blind_validation`. Mostradlo como experimental.

Detalle y cifras en [Reproducibilidad del motor y filtro de clima frío](../../../docs/01-vigentes/etapa-actual-armonizacion/Reproducibilidad%20del%20motor%20y%20filtro%20de%20clima%20frio.md).

## Para la siguiente release

1. Fijar un único estimador de covarianza para las vistas con variables llenas de ceros, o endurecer la guarda, y medir de nuevo con varias semillas.
2. Publicar un ranking de consenso entre varios ajustes, o intervalos por candidata, en vez de un solo ajuste.
3. Comprobar si el GMM se comporta como una vista de empates.
4. Resolver el hemisferio sur: otra fuente de cobertura de suelo o declararlo en la interfaz.

## Uso

```python
from pathlib import Path
from pipelines import similarity_ml as sim

engine = sim.SimilarityEngine.load(Path('ml/modelos/etl-30m-r2c/model.joblib'))
result = engine.search(Path('data/feature_store_v1'), 'haworth-fondo', profile='polar_cold_v1', limit=25)   # necesita el almacén
```

Para servir los resultados precalculados basta con la release. Ver la [guía de backend](../../../docs/contratos/guia-backend.md).
