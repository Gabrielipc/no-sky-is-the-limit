# Guía de backend

Contratos: [README](README.md). Esta guía parte de lo que ya existe en `backend/app/atlas_store.py` y `backend/app/routers/atlas_router.py` (rama `fuentes-de-datos`).

## 0. Lo que ya funciona y lo que cambia

- `/api/atlas`, `/api/atlas/coverage`, `/api/atlas/search` y `/api/atlas/candidates/{region_id}` leen `releases/atlas30/<versión>/` y **no necesitan cambios** para la release v1:
  - `atlas_store.candidate()` hace `SELECT * EXCLUDE (slope_cdf)`, así que las columnas nuevas (capa global `*_cmg`, forma) aparecen solas en `window`.
  - `atlas_store.search()` selecciona columnas explícitas: si queréis mostrar en el ranking simple alguna columna nueva, añadidla a ese `SELECT`.
- **Releases antiguas:** no traen las columnas nuevas. Usad `row.get(col)` y tratad la ausencia como nula.
- **Cómo publica el ETL una release nueva:**
  ```bash
  bash scripts/ejecutar_minerales.sh scripts/etl_pipeline.py publish --version etl-30m-r2 \
    --similarity-model data/features/modelos-similitud/motor-similitud-ml-v1.joblib --set-current
  ```
  El ETL entrega `releases/atlas30/etl-30m-r2/`. Se copia al servidor y `current` apunta a la versión activa.

## 1. Similitud precalculada (implementado)

Si `manifest.json` trae `similarity`, la release incluye `similarity/<referencia>.json` con la respuesta del motor ([`motor-busqueda-v1`](../../specs/api/motor-busqueda-v1.schema.json)) para `jezero`, `haworth-fondo` y `de-gerlache-cresta`, con sus pesos por defecto. Servirlo no requiere el modelo ni el almacén.

| Método y ruta (`backend/app/routers/atlas_router.py`) | Respuesta | Errores |
|---|---|---|
| `GET /api/atlas/similarity?version=` | `manifest.similarity`: estado del motor y una entrada por referencia (`status`, `file`, `profile`, `results`, `warnings`) | 404 si la release no lo incluye, 503 sin release |
| `GET /api/atlas/similarity/{referencia}?version=&limit=&offset=` | La respuesta `motor-busqueda-v1` de la referencia, paginada (`limit` 1–100), más `version`, `limit` y `offset` | 404 si la referencia no está publicada o el manifiesto apunta fuera de la release, 422 por paginación inválida |

Nunca se calcula al pedirla: sirve el archivo de la release, así que un resultado fijado por `version` es reproducible. Es lo que consume la vista de simulación del frontend (`frontend/src/features/simulation/source.ts`): ante un 404 o un 5xx muestra su demostración incluida. `results[i].region_id` enlaza con `/api/atlas/candidates/{region_id}`. Para pesos personalizados usad la sección 2.

## 2. Motor en tiempo de consulta (implementado)

`backend/app/routers/similarity_router.py` sirve el motor con pesos personalizados (el servicio residente está en `services/similarity_service.py` y los modelos de petición en `schemas/similarity.py`). Contrato HTTP: [`specs/api/similitud-api-v1.schema.json`](../../specs/api/similitud-api-v1.schema.json) (catálogo, ficha, sobre de la búsqueda, estado y errores) y, para la petición y la respuesta del motor, [`motor-busqueda-v1`](../../specs/api/motor-busqueda-v1.schema.json).

| Método y ruta | Respuesta | Errores |
|---|---|---|
| `GET /api/similarity/references` | `ReferencesResponse`: referencias con `available`, `kind`, `limitations`, `sources`, estado por vista, más `default_weights` por cuerpo | 503 |
| `GET /api/similarity/references/{id}` | `ReferenceDetail`: añade `features` y `percentiles` | 404, 503 |
| `POST /api/similarity/search` | `SearchResponse` + `query_id` + `timings` | 404, 422, 503 |
| `GET /api/similarity/status` | `ServiceStatus` | — |

Cómo funciona:
- **Arranque.** El `lifespan` de FastAPI carga el modelo y las ventanas terrestres rankables con sus puntuaciones normales en un `CandidatePool`. Cada consulta solo calcula distancias y fusión: con el almacén local (188 mil ventanas) tarda ~10 ms con `only_eligible` y ~260 ms sobre todas. Un pool simulado de 1,5 M filas tarda ~2 s (`scripts/benchmark_motor.py`). Si falta el modelo o el almacén, el resto de la API sigue y estas rutas devuelven 503. `ANALOGOS_SIMILARITY_PRELOAD=0` desactiva la carga al arrancar.
- **Variables:** `ANALOGOS_FEATURE_STORE_DIR`, `ANALOGOS_SIMILARITY_MODEL`, `ANALOGOS_SIMILARITY_CACHE` (entradas, 256 por defecto) y `ANALOGOS_SIMILARITY_CONCURRENCY` (búsquedas simultáneas, 4).
- **Caché.** `query_id` es el SHA-256 de la petición normalizada (los pesos se normalizan, así que `{a: 1, b: 1}` y `{a: 2, b: 2}` son la misma consulta) más el modelo y su `spec_hash`. `timings.cache_hit` indica si se sirvió de la caché.
- **Referencias.** Se resuelven una vez al arrancar. Una referencia cuya ventana no está en el almacén aparece con `available: false` y `reason`, y buscar con ella da 404.
- **Perfiles.** El pool del perfil por defecto se carga al arrancar; los otros se cargan en la primera petición que los use.
- **Orden determinista.** La consulta de candidatos ordena por `region_id` para que los empates de la fusión RRF no dependan del orden de escaneo.

## Requisitos de la VM del backend (disco y memoria)

**Disco: ~1 GB**, sin el espejo. El motor solo lee `data/feature_store_v1/base` (375 MB) y `enrichment` (40 MB), el modelo (`similarity/model.joblib`, 0,3 MB) y, para `/api/atlas`, la release activa (`etl-30m-r2b`, 120 MB). No necesita `manifests/` (184 MB) ni la evidencia (37 MB). Los 8,3 GB de rásteres del espejo **no se despliegan**: son entrada del ETL y viven en GCS (`data/raw/espejo/`). DuckDB puede volcar a `duckdb_spill/` dentro del almacén si una consulta excede su límite; tras cargar el pool el límite baja a 512 MB.

**Memoria: 8 GB recomendados, 4 GB como mínimo, con un solo worker de uvicorn.** Cada worker carga su propio pool. Lo medido y lo extrapolado:

| Qué | Dato |
|---|---|
| Medido con el almacén local (188.003 ventanas, 9 features ajustadas) | El pool retiene 49 MB; el pico del proceso al cargar es ~820 MB (incluye Python, numpy, scipy, scikit-learn y DuckDB). Antes de recortar el pool eran 79 MB. |
| Extrapolado a la release `etl-30m-r2b` (1,46 M ventanas, 17 features ajustadas) | El pool retendría unos 0,6 GB (~390 B por fila). El pico al cargar, con las columnas completas y DuckDB, sería de varios GB (estimado 3–4 GB). |

La extrapolación **no se ha medido en el almacén real de la nube**: mide `peak_rss_mb` de `GET /api/similarity/status` en la VM antes de fijar el tamaño. La estimación de ~70 MB que figuraba aquí era errónea.

## 3. Imágenes por ventana (propuesto)

No serviremos GeoTIFF originales al navegador. Propuesta: `GET /api/atlas/candidates/{region_id}/dem.tif` y `hillshade.png`, que leen por rangos HTTP solo los 3 km de la ventana en el GLO-30 público (COG) y devuelven ~100×100 celdas sin pérdida. Para el contexto, el frontend usa teselas públicas (NASA GIBS, WMS de ESA WorldCover). El mapa `terrain.png` de los expedientes sigue disponible.

## 4. Pruebas de contrato

- Validad las respuestas del endpoint contra `motor-busqueda-v1.schema.json`. `tests/test_contratos.py` incluye un validador mínimo sin dependencias (`validate`) que podéis reutilizar.
- Para `windows.parquet`, las columnas esperadas, en orden, están en `specs/api/release-atlas30-v1.json` (`windows_columns`).
- Ante una release nueva, comprobad `manifest['release_contract'] == 'atlas30-release-v1'`. Una `v2` indicaría un cambio incompatible.
