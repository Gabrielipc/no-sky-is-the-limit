# Plan: búsqueda de análogos por referencia en tiempo real

Fecha: 15 de noviembre de 2026. Estado: **propuesta aprobada en lo esencial (camino B)**; las decisiones abiertas están en la sección 9.

## Estado de implementación (15 de noviembre de 2026)

| Fase | Estado | Detalle |
|---|---|---|
| 0. Línea base | Hecha (`47c9ee0`) | [`scripts/benchmark_motor.py`](../../../scripts/benchmark_motor.py) compara el camino SQL con el pool y puede simular 1,5 M filas. |
| 1. Motor residente | Hecha (`47c9ee0`) | `CandidatePool` y `search(pool=...)`; el test de equivalencia da la misma respuesta que el camino SQL. Con el almacén local: 1,39 s → 0,010 s (solo elegibles) y 1,71 s → 0,26 s (todas). Pool simulado de 1,5 M filas: ~2,1 s. |
| 2. Espejo de datos | Hecha (`64ffa79`) | Manifiesto de 11 productos (8,3 GB de nivel 1), descarga reanudable con verificación y CLI. El ETL lunar usa la copia local si está completa. Probada en real con THEMIS y la iluminación lunar; el resto del nivel 1 **no se ha descargado**. |
| 3. Catálogo | Parcial (`a5c2568`) | Metadatos (tipo, limitaciones, fuentes, centro) de las tres referencias actuales. **Faltan los sitios nuevos**: requieren fijar la lista con fuentes oficiales y coordenadas. |
| 4. API | Hecha (`d47d888`, `442a5af`) | Cuatro rutas, caché, 404/422/503 y contrato [`similitud-api-v1`](../../../specs/api/similitud-api-v1.schema.json) validado contra las respuestas reales. Con el almacén real: ~11 ms (solo elegibles), ~260 ms (188 mil ventanas). |
| 5. Frontend | **Solo el contrato** (`73570d6`) | El frontend del repositorio está desactualizado respecto al del equipo, así que se entregan tipos, cliente y pruebas contra los esquemas, y una vista de ejemplo desacoplada en [`docs/contratos/ejemplo-frontend-similitud`](../../contratos/ejemplo-frontend-similitud/README.md). No se tocó el shell ni el estado de la aplicación. |
| 6. Rendimiento y operación | Parcial | Benchmark simulado a 1,5 M filas; **pendiente** medir con el almacén real de la nube. |
| 7. Documentación | Hecha (`73570d6`) | Guías de backend y frontend y README de contratos actualizados. |
| 8. Ventanas arbitrarias | No iniciada | Sigue fuera de alcance. |

**Nube.** Los trabajos `scripts/etl_referencias.py luna|marte` y `cloud/unir-almacen-azure-gcs.sh` están listos para correr un trabajo por nube y unir en GCS, pero **no se lanzó ninguna VM**: las VM clonan el repositorio desde GitHub, así que antes hay que publicar la rama, y la medición de DTM de sitios nuevos de Marte no existe hasta fijar los sitios. El trabajo `marte` solo espeja hoy.

## 1. Objetivo y alcance

Permitir que el frontend envíe una petición con una **referencia lunar o marciana** y reciba, en menos de 20 s (objetivo real: menos de 1 s para referencias del catálogo), las ventanas terrestres más parecidas, con la explicación por vista y por feature que ya produce el motor ([`pipelines/similarity_ml.py`](../../../pipelines/similarity_ml.py)).

**Decisión de alcance (camino B).** Las referencias son un **catálogo curado de sitios candidatos** de la Luna y Marte, no cualquier ventana de los dos cuerpos. Motivos:

- El reto pide análogos de *«candidate permanent Moon-base locations or future Mars landing and exploration sites»*: el lado planetario es un conjunto finito de candidatos. La búsqueda global y sistemática es del lado terrestre, que ya está en el almacén.
- El reto valora analogías multidimensionales y explicar dónde falla la analogía. Una comparación solo topográfica a 200 m de un punto cualquiera de Marte es la analogía superficial que desaconseja.
- No existe un DEM global de Marte a ~30 m. El mejor global (HRSC+MOLA) es de 200 m: una ventana de 3 km son 15 × 15 celdas, no comparable con las ventanas terrestres de 30 m.

**Fuera de alcance por ahora:** ventanas arbitrarias (camino A, ver fase 8, opcional), vistas de Marte sin datos procesados fuera de Jezero.

## 2. Qué se midió (evidencia de partida)

| Hallazgo | Dato |
|---|---|
| Almacén local | 188.003 ventanas terrestres rankables (+46.807 con tierra insuficiente, +65 con DEM insuficiente). No hay filas de Marte ni de la Luna. |
| `search()` completo | 1,4 s con `only_eligible=True` (2.474 filas); 2,2 s sin filtro. |
| Parte fija por consulta | ~1,3 s: conectar DuckDB y registrar vistas (0,6–0,7), importar elegibilidad y armar el SQL (0,44), `DESCRIBE` (0,12), leer Parquet (0,57–0,64). |
| Cálculo escalable | 0,14 s con 2.474 filas; 0,9 s con 188 mil; **7,25 s extrapolado a 1,5 M**. Dominan `np.unique` de patrones de ausencia (~0,36 s), la GMM (0,25 s) y la Mahalanobis (0,23 s). |
| Almacén de la nube | ~1,45 M ventanas. Con la extrapolación, ~12–15 s por consulta, que cuadra con la documentación del motor. |

Los scripts de medición eran locales y no se conservan en el repo; la fase 1 los reemplaza por un benchmark versionado.

## 3. Arquitectura

```
                        ┌────────────── precálculo (offline, ETL) ──────────────┐
 Espejo de rásteres ──▶ │ referencias curadas → features + percentiles + estado │──▶ catálogo de referencias (JSON/Parquet, MB)
 (data/raw, hash)       └───────────────────────────────────────────────────────┘
                                                                                      │
 Almacén terrestre ──▶ ResidentEngine (arranque del servidor: z, patrones, máscaras) ─┤
                                                                                      ▼
 Frontend ── GET /api/similarity/references ───────────────────────────────▶ lista de referencias
          ── POST /api/similarity/search {reference_id, weights, …} ───────▶ resultados + explicación + timings
```

En tiempo de consulta **no se lee ningún ráster**. Los rásteres solo alimentan el ETL que precalcula las referencias. Por eso el espejado es una decisión de reproducibilidad e independencia de las APIs, no de latencia.

## 4. Espejado de datos

### 4.1 Tamaños (medidos con HEAD o tomados de los specs)

| Producto | Tamaño | Cuerpo | Nivel |
|---|---|---|---|
| LOLA `LDEM_80S_20MPP_ADJ.TIF` (COG) | 2,70 GB | Luna | 1 |
| LOLA `LPSR_80S_20MPP_ADJ.TIF` (PSR) | 154 MB | Luna | 1 |
| Iluminación `AVGVISIB_85S_060M_201608.TIF` | 34 MB | Luna | 1 |
| Diviner `dlre_prp_south.tab` | 605 MB | Luna | 1 |
| Mini-RF `global_cpr_128ppd_simp_0c.img` | 4,25 GB | Luna | 1 (o recorte polar) |
| CRISM `FRT000047A3` SR + IN | 189 MB | Marte | 1 |
| HiRISE DTM de Jezero | por medir | Marte | 1 |
| THEMIS inercia térmica de Jezero | por medir (100 m) | Marte | 1 |
| MOLA DEM 463 m (global) | 2,13 GB | Marte | 2 (contexto) |
| CRISM cubo `if` completo | 1,34 GB | Marte | 3 (opcional) |
| HRSC+MOLA 200 m (global) | 11,4 GB | Marte | 3, solo si se activa la fase 8 |

**Conclusión:** el nivel 1 son unos **8 GB**; con el nivel 2, ~10 GB. No son masivos. Se espejan completos, salvo HRSC+MOLA (11,4 GB), que no hace falta para el camino B.

### 4.2 Diseño

- **Ubicación:** `data/raw/espejo/<cuerpo>/<producto>/` (excluido de Git, como ya está `data/raw/`). Copia secundaria en el bucket de la nube que ya usan `cloud/`.
- **Manifiesto versionado** (`specs/sources/espejo-referencias-v1.json`, sí en Git): URL de origen, `bytes`, SHA-256, fecha de descarga, ETag/Last-Modified, licencia y versión del producto. Sin datos, solo identidad.
- **Script** `scripts/espejar_referencias.py` con `plan` (muestra qué falta y cuánto pesa), `fetch` (reanudable, con presupuesto, verifica hash y tamaño) y `verify`. Reutiliza el patrón de `adquirir_marte.py` y de `source_path()` en [`etl_lunar.py`](../../../pipelines/etl_lunar.py), que ya prefiere la copia local sobre `/vsicurl/`.
- **Regla de lectura:** el ETL usa la copia local verificada si existe; si falta, falla con un error claro en lugar de caer silenciosamente a la red.
- **Orden de descarga:** primero lo ligero (iluminación, PSR, CRISM, Diviner), después LOLA 20 m y Mini-RF.

## 5. Catálogo de referencias

Una referencia = un sitio candidato con su vector de features, la procedencia y el estado de cada vista.

### 5.1 Esquema (`specs/analysis/referencias-v1.json`)

Cada entrada: `id`, `name`, `body`, `kind` (`base_candidate` | `landing_site` | `control`), `center` (lon/lat, marco del cuerpo), `window_m` y `cell_m`, `features`, `percentiles` (intra-cuerpo para los puentes), `view_status` por vista, `sources` (ids del manifiesto de espejo), `limitations` (texto corto que la interfaz muestra), `status` (`measured` | `partial` | `pending_data`).

### 5.2 Contenido inicial

- **Ya existen:** `jezero` (HiRISE, completo), `haworth-fondo` y `de-gerlache-cresta` (LOLA; el spec hoy las deja con `features: {}` y las resuelve desde el almacén por `region_id`).
- **Luna, candidatas a añadir:** otras regiones del polo sur propuestas para Artemis III, medidas con la misma tubería polar (LOLA 20 m, PSR, iluminación, Diviner, Mini-RF). **Pendiente de verificar con la fuente oficial de NASA** el conjunto exacto y las coordenadas antes de fijarlos; no usar la memoria como fuente.
- **Marte, candidatas a añadir:** solo sitios donde exista un DTM de ≤ ~30 m (HiRISE o CTX) para que la topografía sea comparable. **Cada sitio se verifica por separado**; los que no tengan DTM no entran como referencia directa. Fuera de Jezero no hay hoy THEMIS ni CRISM procesados, así que esos sitios tendrán solo vistas topográficas, y `view_status` lo dice.
  - **Comprobado el 15 de nov de 2026:** el catálogo de DTM de HiRISE ([uahirise.org/dtm](https://www.uahirise.org/dtm/)) lista **1.377 DTM** en sus resúmenes de publicación, y entre ellos figura un «Candidate Landing Site for SpaceX Starship at Phlegra Montes». Así que Jezero no es el único sitio con topografía de alta resolución. Falta por comprobar, por sitio, la huella del DTM (que quepa una ventana de 3 km más 480 m de margen), su tamaño de descarga y su calidad.
  - **La restricción es de trabajo del proyecto, no de disponibilidad.** THEMIS (inercia térmica, mosaico global a 100 m) y CRISM (cobertura parcial, ya existe el patrón de adquisición en `adquirir_marte.py`) son productos públicos; solo hay que procesarlos para cada sitio nuevo. Cuántos sitios tienen CRISM de alta resolución no se ha comprobado.
- **Controles:** los sitios de control ya definidos en el contrato.

### 5.3 Generación

`scripts/etl_referencias.py build` mide cada referencia con los operadores del contrato (mismos descriptores, misma huella y celda que en la Tierra) y escribe el catálogo y un informe. Debe ser determinista: mismas entradas verificadas, mismo catálogo.

## 6. Backend

### 6.1 Motor residente (`backend/app/similarity_engine.py`)

- **`lifespan` de FastAPI:** una sola vez carga el modelo y lee del almacén solo las columnas ajustadas de las ventanas `Earth` con `qa_status = 'rankable'`.
- **Precálculo en memoria:** matriz `Z[N, F]` en `float32` con la transformación de cuantiles ya aplicada; patrón de ausencia por vista codificado como entero (en vez de `np.unique` por consulta); máscaras booleanas de elegibilidad por perfil; `region_id`, lon, lat y banda UTM en arrays contiguos. Memoria estimada: ~70 MB para 1,45 M ventanas.
- **Por consulta:** `zref` de la referencia, distancia por vista (Mahalanobis, GMM) solo sobre las filas que pasan las máscaras, fusión y `np.argpartition` para el top-k. El desglose por feature se calcula solo para el top-k, como hoy.
- **Equivalencia:** un test compara `ResidentEngine` con `SimilarityEngine.search` sobre las mismas consultas (puntuaciones, orden, intervalos, vistas ausentes). El motor actual es la referencia científica y no se modifica.
- **Recarga:** la clave de caché y el estado incluyen `release` y `spec_hash`. Cambiar de release recarga sin reiniciar.
- **Varios workers:** cada uno duplica la memoria (~70 MB); aceptable. Si crece, `np.memmap` sobre un `.npy` generado en `publish`.

### 6.2 Endpoints (`backend/app/similarity.py`)

- `GET /api/similarity/references`: catálogo con `id`, `name`, `body`, `kind`, `status`, `view_status`, `limitations`, `sources`.
- `GET /api/similarity/references/{id}`: ficha completa (features, percentiles, procedencia).
- `POST /api/similarity/search`: reutiliza `SearchRequest` de [`motor-busqueda-v1.schema.json`](../../../specs/api/motor-busqueda-v1.schema.json). `reference` acepta `id` del catálogo (principal), `region_id` del almacén o una referencia explícita con features ya calculadas. Responde `SearchResponse` + `query_id` + `timings` (`engine_ms`, `explain_ms`, `cache_hit`).
- Errores: `422` por pesos, política o referencia inválidos; `404` por referencia desconocida; `503` si el motor no está cargado.
- **Caché de resultados:** clave = hash de la petición normalizada + `release` + `spec_hash`, con el mismo patrón que `query_id` en `/api/atlas/search`. Los pesos se normalizan antes de calcular el hash.
- **Trabajos asíncronos:** no se implementan. El camino B no los necesita; solo se reabre la discusión si las mediciones de la fase 1 lo justifican.

### 6.3 Presupuesto de latencia esperado

| Consulta | Objetivo |
|---|---|
| Referencia del catálogo, solo elegibles | < 0,3 s |
| Referencia del catálogo, todas las ventanas (almacén completo, 1,45 M) | < 3 s |
| Consulta repetida | < 50 ms (caché) |
| Referencia explícita con features | igual que las anteriores |

Se aceptan como umbral de prueba de rendimiento los 20 s del requisito; el objetivo operativo es mucho menor.

## 7. Frontend (`frontend/src/features/world`)

1. **Selector de referencia:** lista agrupada por cuerpo y tipo (candidata de base, sitio de aterrizaje, control), con una ficha corta (fuentes, escala, vistas disponibles y `limitations`). Se marca el globo Cesium en la ubicación del sitio.
2. **Controles:** sliders de peso por vista, interruptor «solo ventanas elegibles», política de ausencia y fusión. Los pesos por defecto vienen del `default_weights` del cuerpo.
3. **Envío correcto:** `debounce` de ~300 ms, `AbortController` para cancelar peticiones obsoletas, una sola petición viva, el estado anterior atenuado mientras llega el nuevo. Solo se reenvía `reference_id` y pesos.
4. **Resultados:** tabla ordenada y marcadores en el globo; intervalo `[score_low, score_high]`; vistas ausentes con su aviso; desglose por vista y feature; enlace a `/api/atlas/candidates/{region_id}`.
5. **Honestidad científica visible:** aviso permanente de `unsupervised_pending_blind_validation`, cobertura baja y `limitations` de la referencia (qué se parece y dónde falla la analogía, tal como pide el reto).
6. **Tipos:** generados desde el JSON Schema (`json-schema-to-typescript`) para que el contrato no derive. El cliente vive en `data/api.ts` y los adaptadores en `data/adapters.ts`.
7. **Estados:** carga, vacío, error con reintento, timeout de 30 s.
8. **Modo avanzado:** pegar o subir un JSON con features de una referencia propia.

## 8. Fases, entregables y criterios de aceptación

Cada fase termina en un commit con sus pruebas. Se conservan los cambios ajenos fuera del commit.

| Fase | Entregable | Criterio de aceptación |
|---|---|---|
| **0. Línea base** | Benchmark versionado `scripts/benchmark_motor.py` que repite las mediciones de la sección 2. | Reproduce la tabla de la sección 2 en la misma máquina (±15 %). |
| **1. Motor residente** | `ResidentEngine` + test de equivalencia con `search()`. | Mismo ranking, puntuaciones e intervalos que el motor actual; búsqueda por defecto < 0,3 s con el almacén local. |
| **2. Espejo de datos** | Manifiesto + `espejar_referencias.py` (`plan`, `fetch`, `verify`). Descarga del nivel 1. | `verify` pasa; el ETL falla con error claro si falta un archivo; ningún original en Git. |
| **3. Catálogo de referencias** | `referencias-v1.json` + `etl_referencias.py build`, con las tres referencias actuales y las candidatas verificadas. | Catálogo determinista; cada referencia con `view_status` y `limitations`; tests de contrato contra el esquema. |
| **4. API** | Los tres endpoints, caché y `timings`. | Respuestas válidas contra el schema; 422/404/503 cubiertos por tests; caché con pesos equivalentes da el mismo `query_id`. |
| **5. Frontend** | Selector, sliders con `debounce`, resultados, avisos. | Una sola petición viva; cambiar pesos no vuelve a resolver la referencia; funciona a ancho móvil. |
| **6. Rendimiento y operación** | Prueba con el almacén de la nube (1,45 M). Recarga por release. Guía de despliegue (memoria, workers). | Búsqueda sobre todo el almacén < 3 s y el máximo de la prueba < 20 s. |
| **7. Documentación** | Actualizar [`guia-backend.md`](../../contratos/guia-backend.md), [`guia-frontend.md`](../../contratos/guia-frontend.md) y el índice de `docs/`. | Las guías describen los endpoints reales. |
| **8. Opcional: ventanas arbitrarias** | Almacén terrestre recalculado a 200 m y espejo de HRSC+MOLA (11,4 GB). | Solo si se aprueba: modo etiquetado «grueso, solo topografía». No bloquea nada anterior. |

Orden recomendado: 0 → 1 → 2 → 3 → 4 → 5 → 6 → 7. Las fases 2 y 3 pueden avanzar en paralelo a la 1 (no comparten archivos). Las 4 y 5 dependen de la 1 y de la 3.

## 9. Riesgos y decisiones abiertas

- **Datos de Marte.** Es el riesgo principal. Fuera de Jezero hay que comprobar sitio por sitio si existe un DTM de ≤ ~30 m. Si pocos lo tienen, el catálogo de Marte será pequeño; es coherente con el reto, que prefiere profundidad a cobertura, pero hay que decirlo en la interfaz.
- **Elegir los sitios candidatos.** Hay que fijar con fuentes oficiales qué sitios lunares y marcianos entran, y registrar la fuente de cada elección en el manifiesto.
- **Tamaños por confirmar.** HiRISE DTM y THEMIS de Jezero no tienen tamaño en los specs; se miden en la fase 2.
- **Validación científica.** El motor sigue en estado `unsupervised_pending_blind_validation` y solo dos vistas están ajustadas (`escabrosidad`, `regimen_morfologico`). Esto es una limitación a comunicar, no a ocultar. Con la compuerta por defecto hoy hay 8 ventanas elegibles locales.
- **Memoria del servidor.** ~70 MB por worker con el almacén completo; revisar si se despliega con muchos workers.
- **Dependencia de la red.** El espejo la elimina del ETL; verificar licencias de redistribución antes de publicar copias en un bucket público.
- **Alcance de la fase 8.** Decidir más adelante si merece su coste (un almacén nuevo y 11,4 GB).
