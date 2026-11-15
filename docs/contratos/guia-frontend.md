# Guía de frontend

Contratos: [README](README.md). Hoy `frontend/src/features/world/WorldWorkspace.tsx` ya consume `/api/atlas`, `/api/atlas/versions`, `/api/atlas/coverage`, `/api/atlas/search` y `/api/atlas/candidates/{region_id}`.

## 1. Ficha de una ventana (`/api/atlas/candidates/{region_id}` → `window`)

Columnas, tipos, unidades y rangos: [`specs/api/release-atlas30-v1.json`](../../specs/api/release-atlas30-v1.json).

| Grupo | Columnas | Cómo mostrarlo |
|---|---|---|
| Identidad | `region_id`, `longitude`, `latitude`, `zone`, `status` | Huella cuadrada de 3 km centrada en (lon, lat). Solo `status = 'rankable'` tiene topografía comparable |
| Topografía | `relief_m`, `slope_p50_deg`, `slope_p90_deg`, `roughness_m` | Con unidades (m, °) |
| Forma | `hypsometric_integral`, `elevation_skew_p95_p05`, `aspect_240m_resultant_length`, `slope_240m_gt15_fraction`, `slope_240m_gt25_fraction` | Pueden ser `null` en releases antiguas |
| Cobertura | `bare_fraction`, `vegetation_fraction`, `urban_fraction`, `ice_fraction`, `worldcover_water_fraction`, `water_occurrence_pct`, `cover_status`, `eligibility` | Fracciones 0–1 como % |
| Contexto de superficie (capa global) | `precip_annual_mm_cmg`, `dry_months_fraction_cmg`, `snow_cover_mean_pct_cmg`, `snow_months_fraction_cmg`, `soil_moisture_mean_cmg`, `permafrost_fraction_cmg`, `ati_cmg_per_k`, `emis_*_cmg` | Ver abajo |

**Estados de la capa global.** Cada capa tiene `<capa>_cmg_status`:

| Estado | Texto sugerido |
|---|---|
| `measured` | Mostrar el valor |
| `insufficient_coverage` | «Sin dato válido en esta zona» |
| `unobserved_by_product` | «Fuera de la cobertura del producto» (p. ej. permafrost en el trópico) |
| `on_demand_fetchable` | «Pendiente de procesar» (estado actual hasta que se construyan las capas) |

Marcad estos valores como **contexto grueso**. Su soporte es de ~5–11 km, mayor que la ventana de 3 km, salvo la emisividad (huella de 3 km) y el permafrost (1 km). Un distintivo del tipo «contexto ~5 km» en la ficha basta.

Procedencia: `assets` de la misma respuesta (producto, DOI, versión, periodo), para citar fuentes.

## 2. Resultados del motor de similitud

Formato: [`motor-busqueda-v1`](../../specs/api/motor-busqueda-v1.schema.json) dentro del sobre de [`similitud-api-v1`](../../specs/api/similitud-api-v1.schema.json). Llega de `POST /api/similarity/search` (pesos personalizados, calculado al momento) o, precalculado, de `GET /api/atlas/similarity/{referencia}` (la que usa la vista de simulación; ambas devuelven el mismo formato del motor, pero la segunda es reproducible por `version` y la primera añade `query_id` y `timings`). Ver la [guía de backend](guia-backend.md).

**Qué hay en `frontend/src`:** [`domain/similarity.ts`](../../frontend/src/domain/similarity.ts) (tipos y funciones puras del contrato) y [`data/similarityApi.ts`](../../frontend/src/data/similarityApi.ts) (cliente: `postSearch` y el hook `useSimilaritySearch`). `frontend/tests/similarity.test.cjs` comprueba que no se desvían de los esquemas. Son archivos nuevos que no tocan el resto de la aplicación, para poder copiarlos a una versión más reciente del frontend. Una vista de ejemplo, desacoplada, está en [`ejemplo-frontend-similitud/`](ejemplo-frontend-similitud/README.md).

### Cómo enviar la petición

1. `GET /api/similarity/references` una vez. Devuelve las referencias, sus limitaciones, qué vistas tienen datos (`views`: `reference_has_data`, `reference_missing`, `not_fitted`) y `default_weights` por cuerpo para inicializar los controles.
2. `POST /api/similarity/search` con `{reference: <id>, ...}`. Reenviad solo el id de la referencia, no sus features.
3. **Pesos:** enviad `weights` solo si el usuario los cambió; si se omiten, el servidor aplica los pesos por defecto del cuerpo. Un peso 0 apaga la vista. Si todos los pesos son 0 la API responde 422: evitadlo en la interfaz.
4. **Cadencia:** una sola búsqueda viva. Esperad ~300 ms tras el último cambio de un control y cancelad la anterior con `AbortController`. Mientras llega la nueva, atenuad la tabla en lugar de vaciarla. Tiempo máximo del cliente: 30 s.
5. **Respuesta:** además de los campos del motor trae `query_id` (igual para peticiones equivalentes) y `timings` (`engine_ms`, `total_ms`, `cache_hit`).
6. **Errores:** `detail` es texto o una lista de errores de validación (422). 404: referencia desconocida o `available: false`. 503: el servidor no tiene el motor; el resto de la aplicación funciona.
7. **Referencia explícita:** el campo `reference` también acepta `{body, features, percentiles}` (ver `ReferenceInput`); `percentiles` solo para features puente y dentro de [0, 1].

### Cabecera
- **`status`:** mientras sea `unsupervised_pending_blind_validation`, etiquetad el ranking como **experimental**.
- **`reference.features[f]`:** valor de la referencia y su `earth_percentile` («Jezero está en el P76 del relieve terrestre»). Si `outside_earth_range` es `true`, avisad de que la referencia cae fuera del rango terrestre.
- **`warnings`:** mostradlos siempre, visibles (banner o lista). Dicen, por ejemplo, que una vista con mucho peso cubre muy pocas candidatas o se ajustó con sesgo de selección.

### Lista de resultados
- **`score`:** distancia en [0, 1]; **menor es más parecido**. Si preferís «similitud», usad `1 - score`, pero de forma coherente en toda la interfaz.
- **`[score_low, score_high]`:** incertidumbre por vistas ausentes. Dibujadla como barra de error. Si el intervalo es ancho, la posición en el ranking es poco firme.
- **`coverage`:** qué fracción del peso pudo evaluarse en esa candidata.
- **`missing_views`:** chips «sin dato espectral», etc.
- **Enlaces:** `region_id` lleva a la ficha (`/api/atlas/candidates/{region_id}`); `longitude` y `latitude` sitúan la ventana en el mapa.

### Detalle por vista (`results[i].views[v]`)
- **`distance` y `weight`:** barra por vista con su peso efectivo.
- **`pool_percentile`:** «más cercana que el 99,9 % de las candidatas en esta vista».
- **`features[f]` («por qué se parece»):**
  - `candidate` y `reference`: valores crudos;
  - `z_delta`: diferencia en desviaciones terrestres; el signo indica «más alto» o «más bajo» que la referencia;
  - `share`: cuánto pesa esa feature en la distancia de la vista. Suma 1 y puede ser negativo o mayor que 1 cuando hay features correlacionadas, así que conviene mostrarlo como barra divergente.
- **`regimen_morfologico`:** trae `component` (familia de relieve) y `posterior`.

### Controles de pesos
- Un control por vista (`ViewId`: `escabrosidad`, `forma_hipsometrica`, `organizacion`, `regimen_morfologico`, `espectral`, `termica`, `radar`, `entorno_superficial`, `emisividad_cmg`). Valores iniciales: `weights_requested`.
- **Deshabilitad la vista y mostrad el motivo** cuando `views[v].status` sea:
  - `not_fitted`: «sin datos para ajustarla todavía»;
  - `reference_missing`: «la referencia no tiene esta dimensión». Por ejemplo, `entorno_superficial` con una referencia de Marte: solo funciona con referencias terrestres;
  - `no_candidate_coverage`.
- **`views[v].coverage_fraction`:** mostradla junto al control («medida en el 0,3 % de las ventanas»), para que el usuario entienda por qué una vista pesa poco en la práctica.
- **`views[v].fit_population.mode`:** si vale `biased_enriched_only`, marcad la vista como provisional.

### Tipos TypeScript

Se pueden generar del schema (`npx json-schema-to-typescript specs/api/motor-busqueda-v1.schema.json`). El núcleo es:

```ts
export interface SearchResponse {
  engine_id: 'motor-similitud-ml-v1';
  model_fitted_at: string;
  status: string;
  reference: { id: string; name: string; body: 'Mars' | 'Moon' | 'Earth'; region_id: string | null;
               features: Record<string, { value?: number | null; earth_percentile?: number;
                                          outside_earth_range?: boolean; within_body_percentile?: number | null }> };
  weights_requested: Record<string, number>;
  weights_effective: Record<string, number>;
  views: Record<string, { weight: number; kind: 'metric' | 'gmm';
                          status: 'used' | 'not_fitted' | 'reference_missing' | 'no_candidate_coverage';
                          reason?: string | null; candidates_with_view?: number; coverage_fraction?: number;
                          fit_population?: { mode: 'background_weighted' | 'biased_enriched_only' | 'all_enriched' } }>;
  warnings: string[];
  results: Array<{
    rank: number; region_id: string; longitude: number; latitude: number; scenario_eligibility: string;
    score: number; score_low: number; score_high: number; coverage: number; missing_views: string[];
    views: Record<string, { distance: number | null; weight: number; available: boolean; pool_percentile?: number;
                            features?: Record<string, { candidate: number; reference?: number | null;
                                                        z_delta: number; share: number }>;
                            component?: number; posterior?: number }>;
  }>;
}
```

## 3. Imágenes

No descarguéis los GeoTIFF originales. Una tesela GLO-30 pesa decenas de MB, los HDF de NASA no son legibles en el navegador y Earthdata exige token. Usad:
- **Relieve de la ventana:** el recorte por ventana que exponga el backend (`dem.tif`, ~40 KB sin pérdida, o `hillshade.png`). Para expedientes, el `terrain.png` actual (`case.map_url`).
- **Contexto:** teselas públicas directas desde el navegador, como NASA GIBS (WMTS) para imagen MODIS/VIIRS, nieve o precipitación, y el WMS de ESA WorldCover para la cobertura.

## 4. A futuro: recoger preferencias

El motor calibra sus pesos con comparaciones por pares («¿cuál de estas dos se parece más a Jezero?»). Una interfaz que muestre dos candidatas a ciegas y guarde la elección (`{reference, preferred, other}`) alimenta directamente `motor_similitud.py calibrate`.
