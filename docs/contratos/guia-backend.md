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

## 1. Similitud precalculada (recomendado para empezar)

Si `manifest.json` trae `similarity`, la release incluye `similarity/<referencia>.json` con la respuesta del motor ([`motor-busqueda-v1`](../../specs/api/motor-busqueda-v1.schema.json)) para `jezero`, `haworth-fondo` y `de-gerlache-cresta`, con sus pesos por defecto. Servirlo no requiere el modelo ni el almacén.

Endpoint propuesto, con las convenciones de `atlas_router.py` (`release_for`, `read_optional`):

```python
@router.get('/similarity')
def similarity_index(version: Optional[str] = None):
    _, manifest = release_for(version)
    sim = manifest.get('similarity')
    if not sim:
        raise HTTPException(404, 'Esta versión no incluye resultados del motor de similitud')
    return sim  # engine_status, model_fitted_at, references: {id: {status, file, profile, results, warnings}}


@router.get('/similarity/{reference}')
def similarity(reference: str, version: Optional[str] = None,
               limit: int = Query(25, ge=1, le=100), offset: int = Query(0, ge=0)):
    path, manifest = release_for(version)
    entry = (manifest.get('similarity') or {}).get('references', {}).get(reference)
    if not store.TOKEN.fullmatch(reference) or not entry or entry.get('status') != 'published':
        raise HTTPException(404, 'Referencia sin resultados publicados')
    data = json.loads((path / entry['file']).read_text())
    data['results'] = data['results'][offset:offset + limit]
    return {**data, 'version': manifest['version'], 'limit': limit, 'offset': offset}
```

`results[i].region_id` enlaza con `/api/atlas/candidates/{region_id}` para la ficha completa.

## 2. Motor en tiempo de consulta (implementado)

`backend/app/similarity.py` ya sirve el motor con pesos personalizados. Contrato HTTP: [`specs/api/similitud-api-v1.schema.json`](../../specs/api/similitud-api-v1.schema.json) (catálogo, ficha, sobre de la búsqueda, estado y errores) y, para la petición y la respuesta del motor, [`motor-busqueda-v1`](../../specs/api/motor-busqueda-v1.schema.json).

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

Despliegue: cada worker de uvicorn mantiene su propio pool (~70 MB estimados para 1,45 M ventanas). Dependencias del entorno Pixi: `duckdb`, `numpy`, `scipy`, `scikit-learn`, `joblib`; `pipelines/` se añade solo al `sys.path`.

## 3. Imágenes por ventana (propuesto)

No serviremos GeoTIFF originales al navegador. Propuesta: `GET /api/atlas/candidates/{region_id}/dem.tif` y `hillshade.png`, que leen por rangos HTTP solo los 3 km de la ventana en el GLO-30 público (COG) y devuelven ~100×100 celdas sin pérdida. Para el contexto, el frontend usa teselas públicas (NASA GIBS, WMS de ESA WorldCover). El mapa `terrain.png` de los expedientes sigue disponible.

## 4. Pruebas de contrato

- Validad las respuestas del endpoint contra `motor-busqueda-v1.schema.json`. `tests/test_contratos.py` incluye un validador mínimo sin dependencias (`validate`) que podéis reutilizar.
- Para `windows.parquet`, las columnas esperadas, en orden, están en `specs/api/release-atlas30-v1.json` (`windows_columns`).
- Ante una release nueva, comprobad `manifest['release_contract'] == 'atlas30-release-v1'`. Una `v2` indicaría un cambio incompatible.
