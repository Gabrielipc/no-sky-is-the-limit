# Barrido mundial: robustez, cobertura, costo y publicación

Estado y procedimiento al 14 de noviembre de 2026. Cierra los cuatro puntos de [«Qué corregir antes de lanzar otro barrido mundial»](../etapa-actual-armonizacion/Eleccion%20de%20fuentes%20y%20costo%20de%20cobertura%20mundial.md#qué-corregir-antes-de-lanzar-otro-barrido-mundial).

**Conclusión.** La topografía mundial ya está calculada en el almacén local: 22.303 lotes y 1,79 M ventanas, de las cuales 1,45 M tienen QA `rankable`. Lo que faltaba para buscar análogos era la cobertura, que no se había leído casi en ninguna ventana. Ahora se puede rellenar sin recalcular la topografía. La transferencia estimada es de ~140 GB, descargando una sola vez cada tesela WorldCover y JRC. Los lotes con fallos de acceso ya no se dan por terminados, y el resultado se puede publicar al mapa con un comando.

## Estado del almacén local antes de estos cambios

| QA / elegibilidad | Ventanas |
|---|---:|
| `rankable`, cobertura pendiente | 1.453.571 |
| `insufficient_land` | 331.371 |
| `dem_unavailable` (causa mezclada) | 6.522 |
| `insufficient_dem_support` | 1.711 |

Los manifiestos solo registran 8 teselas WorldCover y 5 JRC. Ninguna ventana tenía elegibilidad resuelta, así que el ranking por defecto devolvía una lista vacía.

## 1. Fallos de acceso frente a huecos de catálogo

- **Causa por activo.** `topo.Rasters` guarda en `failures` la causa de cada activo no disponible (`not_cached`, `http_404`, `network_error: …`, `open_error`, `read_error`). Ya no aborta el lote por una excepción de red.
- **Reintentos en el stream.** `download_tile_to_temp` reintenta códigos transitorios (408, 425, 429, 5xx) y errores de red con espera exponencial, y devuelve la causa. Un 404/403 no se reintenta. Si la descarga falla, el lector intenta una lectura por rangos HTTP antes de rendirse.
- **Estados por ventana.**
  - `qa_status = dem_fetch_failed`: una tesela del inventario no se pudo leer. Se distingue de `dem_unavailable`, que ahora significa solo hueco de catálogo.
  - `cover_status`: `measured`, `no_cover_tile`, `cover_fetch_failed`, `insufficient_cover_support` o `not_requested`. Una lectura de cobertura fallida no alimenta la compuerta de elegibilidad.
- **Cierre de lote.** El registro de cada lote (`manifests/batches/<id>.json`) guarda `status` (`complete` o `incomplete`), identidad de corrida, conteos por estado y activos fallidos. Un lote con `dem_fetch_failed` o `cover_fetch_failed` queda como `incomplete`.

## 2. Reanudación versionada

- **Qué se omite.** Solo los lotes `complete` cuya identidad coincide: malla, paso, ventana, celda, halo, base de pendiente y radio de rugosidad. Los `incomplete` se reintentan automáticamente.
- **Registros antiguos.** Los que no tienen identidad se consideran completos con los parámetros de la corrida mundial (paso de 10 km). Así no se repite el barrido entero.
- **Huecos antiguos.** `--reopen-legacy-gaps` reprocesa solo los lotes antiguos con `dem_unavailable` o soporte DEM insuficiente, porque en esa época las dos causas estaban mezcladas.

## 3. Relleno de cobertura sin recalcular topografía

- **Comando.** `etl_pipeline.py cover` selecciona ventanas `rankable` sin cobertura o con lectura fallida. Opcionalmente prioriza por cercanía topográfica a la referencia (`--limit`) o filtra por un `--bbox`.
- **Cómo lee.** Agrupa por tesela JRC (10°) y WorldCover (3°), y descarga cada tesela una vez (`--transport download`). Las ventanas cuyo halo cruza a una tesela vecina la leen por rangos.
- **Dónde escribe.** En la tabla `enrichment_cover`. La vista `base_windows` superpone esos valores (estado, fracciones y elegibilidad) a la fila base. Las columnas que faltan en archivos antiguos aparecen como nulas.
- **Ensayo en el almacén mundial.** Con las 100 ventanas más cercanas a Jezero, por rangos: 100 medidas, 94 s con 4 workers. **Solo 8 son áridas expuestas**; 48 son bosque, 30 vegetación sin árboles, 12 agua, 1 construido y 1 nieve. Rellenar la cobertura solo en una lista corta topográfica dejaría casi todo fuera: hay que aplicarla a escala.

## 4. Benchmark de costo por ventana utilizable

[`scripts/benchmark_barrido.py`](../../../scripts/benchmark_barrido.py) recorre los cinco bloques de 100 km de referencia sobre un almacén desechable, ignorando la caché local para medir la transferencia real. Usa 4 workers. [Resultados](../../evidencia-barrido/benchmark.json)

| Fase | Tiempo | Transferencia | Resultado |
|---|---:|---:|---|
| A. Topografía en stream, sin cobertura | 780 s | 730 MB (30 teselas GLO‑30) | 500 ventanas; 491 `rankable`; sin fallos |
| B. Cobertura descargando teselas | 829 s | 816 MB | 391 `measured` y 100 `no_cover_tile` (polo) |
| C. Cobertura por rangos (50 ventanas) | 19 s | — | 0,38 s por ventana con 4 workers |

| Estrato | `rankable` | Con cobertura medida | Árida expuesta |
|---|---:|---:|---:|
| Desierto (Utah) | 100 | 100 | 63 |
| Costa (Atacama) | 91 | 91 | 88 |
| Montaña (Alpes) | 100 | 100 | 0 |
| Trópico (Borneo) | 100 | 100 | 0 |
| Polo (Antártida) | 100 | 0 | 0 |

**Lectura.**
- **El cuello de botella es la red.** En ambas fases el ritmo efectivo fue de ~1 MB/s. Con teselas ya locales, la cobertura costó 0,03 s por ventana.
- **El benchmark sobrestima el costo por ventana.** Cada bloque usa unas 100 ventanas por tesela. En el almacén mundial, las ventanas pendientes tocan unas 2.700 teselas WorldCover con datos y 430 JRC, unas 490 ventanas por tesela WorldCover. La extrapolación lineal del script (2,4 TB y 680 h) es una cota superior.
- **Estimación por teselas.** WorldCover v200 publica 124 GB y las teselas JRC medidas pesan de 20 a 56 MB (≈ 16 GB para 430). En total, **~140 GB una sola vez**: ~39 h a la velocidad medida aquí o ~3 h a 100 Mb/s, más unas 3 h de CPU con 4 workers. Por rangos serían ~154 h con 4 workers.
- **Antártida.** Las 122.292 ventanas al sur de 60° S no tienen WorldCover (404). Quedan como `no_cover_tile` y no pueden pasar el perfil `polar_cold_v1` con esta fuente. Para un análogo lunar polar en la Antártida hace falta otra fuente de cobertura; el Ártico sí está cubierto.
- **Bug detectado.** El benchmark encontró que un 404 tras una descarga fallida se registraba como fallo de acceso, lo que habría dejado incompletos para siempre los lotes polares. Está corregido y probado.

## 5. Publicación al mapa

- **Comando.** `etl_pipeline.py publish --version <nombre> [--profile …] [--set-current]` escribe `releases/atlas30/<nombre>/` con el esquema que leen la API y el mapa: `manifest.json`, `windows/*.parquet`, `batches.json` y `sources.json`. Escribe en un directorio temporal que se renombra al final, y nunca sobrescribe una versión existente.
- **Método de ranking.** El manifiesto declara `ranking_method = etl-quantiles-v1`. Como el ETL guarda P50/P90 de pendiente a base de 240 m y no un histograma, la distancia de pendientes es la media de |ΔP50| y |ΔP90|. La API busca solo entre las ventanas con `search_eligibility`, mantiene todas en el mapa de cobertura, y cuenta `dem_fetch_failed` como hueco. Los releases de `atlas30.py` no cambian.
- **Referencia.** Jezero con el contrato del ETL: 120,27 m de relieve; P50 3,07°; P90 9,24°; rugosidad 7,57 m.

## Procedimiento recomendado

```sh
# 1. Reintentar lo que falló o quedó mezclado en el barrido existente
bash scripts/ejecutar_minerales.sh scripts/etl_pipeline.py stream --scope world --max-batches 0 --reopen-legacy-gaps --overwrite
# 2. Rellenar cobertura en todo el mundo (descarga por tesela; ~140 GB)
bash scripts/ejecutar_minerales.sh scripts/etl_pipeline.py cover --unordered --transport download --workers 4
# 3. Revisar estados
bash scripts/ejecutar_minerales.sh scripts/etl_pipeline.py stats
# 4. Publicar y activar en el mapa
bash scripts/ejecutar_minerales.sh scripts/etl_pipeline.py publish --version etl-30m-r1 --set-current
```

Para obtener resultados antes, el paso 2 se puede limitar a regiones con `--bbox` (por ejemplo, los grandes desiertos) y publicar una versión parcial. El manifiesto la marca como `coverage_status = partial`.

## Límites

- El benchmark usa cinco bloques y una sola máquina y red. Las cifras de horas dependen sobre todo del ancho de banda.
- Las ventanas antiguas no tienen descriptores de forma, que requieren releer el DEM. Solo los lotes reprocesados los tendrán.
- La elegibilidad publicada es la del perfil elegido. Otro escenario requiere publicar otra versión con `--profile`.
