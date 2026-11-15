# Motor de similitud · modelo de la release `etl-30m-r2b`

> **Sustituido por [`etl-30m-r2c`](../etl-30m-r2c/README.md).** Este modelo se ajustó con una muestra dependiente del orden de lectura y una covarianza degenerada; se conserva como histórico.

Modelo ajustado del motor de similitud ML no supervisado (`motor-similitud-ml-v1`) que acompaña a la release del atlas `etl-30m-r2b` (activa en `gs://regolith-analogos-gabi0808/releases/atlas30/`). Sustituye a [`etl-30m-r1b`](../etl-30m-r1b/README.md).

| Archivo | Contenido |
|---|---|
| `model.joblib` | Modelo ajustado (284 KB): transformaciones cuantil-normal, covarianzas robustas por vista y GMM de regímenes |
| `model.json` | Informe legible del ajuste: vistas, features, población y grados de libertad |
| `jezero.json` | Respuesta del motor para Jezero con los pesos por defecto (top 100), perfil `arid_mars_surface_v2` |
| `haworth-fondo.json` | Lo mismo para el fondo del cráter Haworth, perfil `polar_cold_v1` |
| `de-gerlache-cresta.json` | Lo mismo para la cresta de de Gerlache, perfil `polar_cold_v1` |
| `release-manifest.json` | Manifiesto de la release de la que sale este modelo |

Las tres respuestas siguen el contrato [`motor-busqueda-v1`](../../../specs/api/motor-busqueda-v1.schema.json) y sirven de ejemplo real para el frontend.

## Procedencia

- **Ajustado:** 2026-11-15T09:11:16Z, en una VM de GCP (`europe-west3`), con el código de la rama `etl-30m-r2` en el commit `77bd28b`.
- **Población de ajuste:** 1 459 164 ventanas terrestres rankables del barrido mundial, sin la cuenca reservada de Mojave; muestra de 200 000 ventanas, semilla 20261114.
- **Hash del spec** (`specs/analysis/motor-similitud-ml-v1.json`): `4520fe49764a…`.
- **SHA-256 de `model.joblib`:** `a2864ffde49074f416f99934219419fa0d73755e229662c70ade3b7874de6075`.
- **Verificación de la release:** 0 errores y 0 avisos (`scripts/verificar_release.py`).

## Qué cambia respecto a r1b

- **Más vistas ajustadas.** Además de `escabrosidad`, `forma_hipsometrica`, `organizacion` y `regimen_morfologico`, ahora lo están `termica` (2 000 ventanas tras el remuestreo por probabilidad de inclusión), `entorno_superficial` y `emisividad_cmg` (con las capas globales muestreadas en las 1,79 M ventanas).
- **Referencias lunares.** Haworth y de Gerlache dejan de fallar: sus ventanas lunares están medidas en el almacén (topografía, iluminación, PSR, Tmax de Diviner y CPR de Mini‑RF).
- **Filtro de clima frío en `polar_cold_v1`.** Además de la cobertura del suelo, la ventana necesita nieve al menos 3 de cada 12 meses o permafrost en al menos el 10 % de la huella. El pool de Haworth pasó de 213 791 candidatas (r2, sin filtro) a 45 309, y los desiertos cálidos dejaron de salir como análogos.

## Qué no cubre

- **Vistas sin ajustar:** `espectral` y `radar` (sin mediciones terrestres). Aparecen como `not_fitted` y quedan fuera de la fusión con aviso.
- **`termica`, `entorno_superficial` y `emisividad_cmg` no puntúan con Jezero ni con las referencias lunares.** Son columnas solo terrestres: con referencias de otro cuerpo la vista queda `reference_missing`. Con una referencia terrestre (`--ref-region-id`) sí intervienen.
- **Lunar incompleto:** sin Tmin, amplitud térmica, abundancia de rocas, parámetro H ni S1. Esas fuentes no existen en los polos o no tienen calibración documentada (ver [`luna-polar-sur-v1.json`](../../../specs/sources/luna-polar-sur-v1.json)).
- **Antártida:** sin cobertura de suelo (WorldCover no llega al sur de 60° S), así que no hay análogos allí.
- **Estado:** `unsupervised_pending_blind_validation`. Mostradlo como experimental.

## Limitaciones conocidas

- **Este modelo se ajustó con dos fallos que ya están corregidos en el código** (ver [Reproducibilidad del motor y filtro de clima frío](../../../docs/01-vigentes/etapa-actual-armonizacion/Reproducibilidad%20del%20motor%20y%20filtro%20de%20clima%20frio.md)):
  - la muestra de ajuste dependía del orden de lectura del almacén, así que dos ajustes con la misma semilla daban muestras distintas (el top 100 de Jezero coincidió solo en 73 resultados entre r2 y r2b);
  - la covarianza robusta de `escabrosidad` salió degenerada: la variable `slope_240m_gt25_fraction` tiene varianza cero y el motor la descarta en silencio.

  Hay que reajustar y publicar una release nueva para que los rankings de este directorio reflejen la corrección. La corrección no se ha probado todavía sobre el barrido mundial.
- **De Gerlache queda fuera de su propia compuerta de base:** pendiente P90 de 22,4° frente al umbral inicial de 15° (`excluded_steep`). El ranking de análogos terrestres sí se calcula.
- **El filtro de clima es burdo.** Un resultado del top 6 de Haworth está en Mongolia (43,9° N, 103,1° E), una zona de montaña de frío continental que cumple el criterio de nieve o permafrost.

## Uso

```python
from pathlib import Path
from pipelines import similarity_ml as sim

engine = sim.SimilarityEngine.load(Path('ml/modelos/etl-30m-r2b/model.joblib'))
result = engine.search(Path('data/feature_store_v1'), 'haworth-fondo', profile='polar_cold_v1', limit=25)   # necesita el almacén
```

Para búsquedas en tiempo de consulta hace falta el almacén del bucket (`data/feature_store_v1`). Para servir los resultados precalculados basta con la release. Ver la [guía de backend](../../../docs/contratos/guia-backend.md).
