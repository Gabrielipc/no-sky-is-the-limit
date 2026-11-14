# Atlas de 30 m

La vista **Búsqueda mundial** está en `/?view=world`. La publicación local `mundial-30m-r1` contiene **3.782 ventanas** en **50 de 22.303 lotes** del plan de muestreo, de las cuales **3.054** son clasificables. Otras 704 tienen poca tierra y 24 tienen soporte DEM insuficiente. Cada ventana mide nominalmente 3 × 3 km, con centros separados 10 km y celdas de 30 m. El mapa agrupa los centros por celdas de 2° y muestra la cobertura parcial de esta publicación.

La versión `piloto-contexto-30m` contiene 500 ventanas y 491 candidatas. WorldCover y JRC aportan datos en desierto, montaña, costa y trópico. Los faltantes del bloque antártico quedan registrados. Seleccionar esta versión en la interfaz para usar los filtros de suelo desnudo y ocurrencia de agua en el piloto.

## Preparación y reanudación

Para inventariar o descargar WorldCover, JRC, HLS y Landsat por separado, consulta la [preparación multidimensional](Atlas%20de%2030%20m%20-%20preparacion%20multidimensional.md).

Ejecutar desde la raíz con el entorno Pixi del proyecto.

```sh
PY=.pixi/envs/default/bin/python
"$PY" scripts/atlas30.py inventory
"$PY" scripts/atlas30.py acquire --plan-only --check-cdse
"$PY" scripts/atlas30.py acquire --max-gb 2
"$PY" scripts/atlas30.py run
"$PY" scripts/atlas30.py benchmark
"$PY" scripts/atlas30.py run --mode range --context
"$PY" scripts/atlas30.py benchmark --mode range --context
"$PY" scripts/atlas30.py publish piloto-contexto-30m-v2 --mode range --context --refine
```

El inventario y la adquisición guardan identificadores y verifican las copias locales. El modo `cache` lee originales verificados, `range` lee los COG remotos y `auto` prefiere una copia verificada antes de solicitar rangos. La caché de originales de este pipeline está limitada a 100 GB. El seguimiento CDSE lista los productos del catálogo para las teselas ausentes del inventario público. La descarga desde CDSE depende del acceso de la cuenta.

En `acquire --plan-only`, `estimated_new_bytes` indica el tamaño de los originales que faltan. Una adquisición ejecutada muestra `new_files`, `reused_files` y `newly_verified_bytes`. Este último es el tamaño completo de los archivos terminados durante la ejecución, que puede incluir bytes de un parcial anterior. El plan de lotes mundial se guarda por versión de malla e identidad de la máscara, con el mismo orden y los mismos desplazamientos `--start`.

Para continuar el muestreo mundial, repetir el comando de procesamiento. `--max-batches` cuenta los lotes nuevos y `--max-hours` fija el presupuesto de la ejecución. El comando reutiliza las particiones verificadas y el orden de lotes es estable. Cada publicación tiene un nombre nuevo y activa el índice tras validar sus particiones. El stride de 3 km se puede evaluar con `--stride 3000`, en una ejecución separada.

```sh
PY=.pixi/envs/default/bin/python
"$PY" scripts/atlas30.py run --scope world --mode auto --max-batches 50 --max-hours 2
"$PY" scripts/atlas30.py benchmark --scope world --mode auto
"$PY" scripts/atlas30.py publish mundial-30m-r2 --scope world --mode auto --refine
make backend
# En otra terminal
make frontend
```

El piloto temporal se ejecuta con `"$PY" scripts/atlas30.py temporal`. HLS usa la credencial existente de Earthdata a través del entorno y consulta NASA CMR. Landsat se descubre en el catálogo USGS y se lee desde la copia del mismo identificador de producto en Planetary Computer cuando el enlace de USGS requiere inicio de sesión. Se muestrean dos períodos de 2024 y se conservan las fechas, los activos y el soporte por indicador. La malla distribuida de Landsat es de 30 m y el dato térmico de origen tiene un paso nominal de 100 m. Los resultados del piloto temporal quedan en `data/manifests/atlas30/temporal-2024.json`.

## Evidencia y límites

| Medición | Resultado |
| --- | --- |
| Referencia Jezero | 10.000 celdas válidas de elevación, pendiente y rugosidad. Mediana de pendiente 3,82°, relieve 120,27 m, rugosidad mediana 7,57 m. |
| Benchmark local | Cinco bloques de 100 × 100 km, entre 5,15 y 5,70 s por bloque con datos en disco y pico de memoria de 509 MB. Se verificaron 1,41 GB de teselas e inventarios durante la preparación. |
| Prueba de densificación | Un bloque desértico con stride de 3 km produjo 1.089 ventanas en 58,90 s con datos locales. Extrapolado a todos los lotes, serían unos 15,2 días. Es una estimación de un solo bloque. |
| Lectura HTTP de GLO-30 | Un bloque de desierto necesitó 38,46 MB de cuerpos HTTP 206 en 23 respuestas y tardó 16,35 s. |
| Benchmark remoto con contexto | Entre 29 y 68 s por bloque, con una proyección inicial de 7,6 a 17,4 días para el mismo dominio mundial. Esta proyección es el motivo para procesar el contexto por separado. |
| Piloto temporal de 2024 | 24 escenas leídas en cuatro bloques, con NDVI, NDMI, NDSI y temperatura superficial. El catálogo no devolvió escenas elegibles en el bloque antártico. |
| Orden refinado | 20 candidatas recalculadas a 30 m con distribuciones completas. El top 20 conserva 17 integrantes con el baseline pendiente y relieve, y 15 con pesos iguales. |
| Expedientes de la versión mundial | Tres candidatas de México, Gales y Madagascar. Las tres tienen mapas, contraste SRTM y sensibilidad medida a 60 y 120 m. |

Entre los tres expedientes, GLO-30 a 30 m ordenó México, Gales y Madagascar. A 60 y 120 m, Madagascar quedó primero. SRTM a 30 m mantuvo a México primero e intercambió Gales y Madagascar.

La comprobación separada de tres ventanas, elegidas por hash del identificador en tres bandas de latitud, también cambió los dos primeros puestos al pasar de GLO-30 a 30 m a GLO-30 a 60 o 120 m, o a SRTM a 30 m. El registro local `data/manifests/atlas30/world-holdout-30m.json` conserva sus identificadores y distancias.

Los informes completos de tiempos, RAM y bytes lógicos leídos quedan en `data/manifests/atlas30/`. El tamaño completo de los activos, el volumen de píxeles descomprimidos leídos y el tráfico de red son mediciones distintas. Los manifiestos y las particiones Parquet de las versiones publicadas quedan en `releases/atlas30/`. La API guarda la versión y los parámetros de cada consulta local para que pueda repetirse por su ID.

El ranking mide forma del terreno. GLO-30 es un modelo digital de superficie que puede incluir árboles y edificios. La cuadrícula de 30 m comparte el paso de análisis con Jezero, aunque el soporte efectivo de los productos difiere. Los expedientes son comparaciones exploratorias con contraste entre sensores. Quedan pendientes la validación científica externa, el barrido completo, la densificación y los perfiles planetarios adicionales.

**Atribución del relieve** — produced using Copernicus WorldDEM-30 © DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018 provided under COPERNICUS by the European Union and ESA; all rights reserved. [Condiciones de Copernicus DEM](https://dataspace.copernicus.eu/explore-data/data-collections/copernicus-contributing-missions/collections-description/COP-DEM)

**Contexto** — ESA WorldCover 2021 v200 y EC JRC/Google Global Surface Water v1.5. [ESA WorldCover](https://esa-worldcover.org/en/data-access), [EC JRC](https://global-surface-water.appspot.com/download)
