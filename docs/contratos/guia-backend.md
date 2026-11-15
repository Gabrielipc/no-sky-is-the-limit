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

## 2. Motor en tiempo de consulta (pesos personalizados)

Hace falta cuando el usuario mueve los pesos, sube su propia referencia o filtra por región. Requisitos en el servidor:

- **Almacén** `data/feature_store_v1/` (`ANALOGOS_FEATURE_STORE_DIR`) y **modelo** `motor-similitud-ml-v1.joblib`, ambos del mismo ajuste que la release.
- **Dependencias del entorno Pixi del proyecto:** `duckdb`, `numpy`, `scipy`, `scikit-learn` y `joblib`. `pipelines/` debe estar en el `PYTHONPATH`.
- **Memoria y tiempo:** una búsqueda sobre ~1,8 M ventanas tarda del orden de 15 s y usa hasta `memory_limit`.

```python
from functools import lru_cache
from pathlib import Path
from fastapi.concurrency import run_in_threadpool
from pipelines import similarity_ml as sim

STORE = Path(os.environ['ANALOGOS_FEATURE_STORE_DIR'])
MODEL = Path(os.environ.get('ANALOGOS_SIMILARITY_MODEL', 'data/features/modelos-similitud/motor-similitud-ml-v1.joblib'))


@lru_cache(maxsize=1)
def engine() -> sim.SimilarityEngine:
    return sim.SimilarityEngine.load(MODEL)  # una vez por proceso


@router.post('/api/similarity/search')
async def similarity_search(req: SimilaritySearchRequest):  # = $defs.SearchRequest del schema
    try:
        return await run_in_threadpool(
            engine().search, STORE, req.reference, weights=req.weights, profile=req.profile,
            only_eligible=req.only_eligible, limit=req.limit, missing_policy=req.missing_policy,
            fusion=req.fusion, bbox=req.bbox, memory_limit='2GB', threads=4)
    except ValueError as exc:  # pesos inválidos, referencia desconocida, política no válida
        raise HTTPException(422, str(exc)) from exc
```

Recomendaciones:
- **Caché por consulta:** usad el hash de la petición normalizada, igual que `query_id` en `/api/atlas/search`. Las combinaciones repetidas son frecuentes.
- **Acotar:** con `bbox` o `only_eligible=true` la búsqueda es mucho más rápida. Para la interfaz conviene `limit <= 100`.
- **Validación:** `ValueError` se traduce en 422. Las vistas no ajustadas o sin referencia no son errores: vienen en `views[v].status` y en `warnings`.
- **Modelos Pydantic:** se pueden generar del JSON Schema (`datamodel-codegen --input specs/api/motor-busqueda-v1.schema.json --input-file-type jsonschema`) o declarar solo `SearchRequest` y devolver la respuesta como `dict`.

## 3. Imágenes por ventana (propuesto)

No serviremos GeoTIFF originales al navegador. Propuesta: `GET /api/atlas/candidates/{region_id}/dem.tif` y `hillshade.png`, que leen por rangos HTTP solo los 3 km de la ventana en el GLO-30 público (COG) y devuelven ~100×100 celdas sin pérdida. Para el contexto, el frontend usa teselas públicas (NASA GIBS, WMS de ESA WorldCover). El mapa `terrain.png` de los expedientes sigue disponible.

## 4. Pruebas de contrato

- Validad las respuestas del endpoint contra `motor-busqueda-v1.schema.json`. `tests/test_contratos.py` incluye un validador mínimo sin dependencias (`validate`) que podéis reutilizar.
- Para `windows.parquet`, las columnas esperadas, en orden, están en `specs/api/release-atlas30-v1.json` (`windows_columns`).
- Ante una release nueva, comprobad `manifest['release_contract'] == 'atlas30-release-v1'`. Una `v2` indicaría un cambio incompatible.
