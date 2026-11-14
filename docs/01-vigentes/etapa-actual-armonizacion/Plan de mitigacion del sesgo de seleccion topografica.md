# Plan de mitigación del sesgo de selección topográfica

Estado: propuesta (14 de noviembre de 2026). No hay código implementado todavía.

## 1. Problema

El motor de similitud ([Motor de similitud ML no supervisado.md](Motor%20de%20similitud%20ML%20no%20supervisado.md)) ajusta cada vista por separado y tolera vistas ausentes. El sesgo no está en el motor, sino en **qué ventanas llegan a medirse** fuera de la topografía:

- El barrido mundial (`etl_pipeline.py stream`) mide en las ~1,8 M ventanas la topografía, los descriptores de forma, WorldCover y JRC.
- Las dimensiones de superficie (`etl_superficie.py`) y los puentes espectral, láser y radar (`etl_puentes.py`) solo se miden sobre `candidate_sites`. Esa función elige las mejores ventanas por relieve y pendientes frente a Jezero (`--arid-limit 8`) y frente al fondo de Haworth (`--polar-limit 12`). Son unas 20 ventanas, todas filtradas por topografía.

Consecuencias:

1. **Falsos negativos invisibles.** Una consulta con peso topográfico 0 solo puede elegir entre ventanas que ya pasaron un filtro topográfico. Un sitio excelente en espectro o en inercia térmica, pero plano, nunca se mide, y el motor lo trata como «vista ausente», no como «malo».
2. **Vistas puente mal ajustadas.** Las vistas puente comparan por rango dentro de cada cuerpo (`bridge_sample_size`, `min_body_population = 100`). Ajustadas sobre unas 20 candidatas, describen a las candidatas y no a la Tierra, y además no llegan al mínimo de población.
3. **Las dimensiones de entorno no son vistas.** La aridez, la humedad del suelo, la nieve, el permafrost, la emisividad y el retrodispersado OPERA no forman parte de ninguna vista de `motor-similitud-ml-v1`. De superficie solo entra la ATI, a través de `termica`.

## 2. Principio

Separar **quién se mide** de **quién se parece**. En lugar de una sola población elegida por topografía, se usan tres:

| Población | Qué mide | Para qué sirve |
|---|---|---|
| Global (todas las ventanas) | Capa barata de superficie desde rásteres globales | Vistas de entorno sin sesgo y señales previas para las demás vistas |
| Muestra de fondo estratificada | Enriquecimiento completo, igual que las candidatas | Ajustar las vistas puente sin sesgo y estimar el recall |
| Listas cortas por vista | Enriquecimiento completo | Candidatas propuestas por **cada** vista, no solo por la topográfica |

## 3. Fase A: capa global barata (`enrichment_global`)

La mitad de las dimensiones de superficie existen como productos globales de baja resolución. Lo caro hoy es pedirlas ventana por ventana. Se procesa cada producto **una sola vez** como ráster climatológico global y luego se muestrea en el centro de cada ventana: 1,8 M consultas sobre un ráster en memoria tardan segundos.

### Productos

Los tamaños por gránulo se consultaron en CMR el 14 de noviembre de 2026, sin descargar datos.

| Dimensión | Producto | Resolución | Periodo | Volumen estimado | Columna nueva |
|---|---|---|---|---|---|
| Aridez | `GPM_3IMERGM.07` (GES DISC) | 0,1° | 2019–2023, 60 meses | 60 × ~18 MB ≈ 1,1 GB | `precip_annual_mm_cmg` |
| Nieve | `MOD10CM.61` (NSIDC) | 0,05° | 2019–2023, 60 meses | 60 × ~2 MB ≈ 120 MB | `snow_months_fraction_cmg` |
| LST día y noche | `MYD11C3.061` (Aqua, 13:30/01:30) | 0,05° | 2023, 12 meses | 12 × ~73 MB ≈ 0,9 GB | entra en ATI gruesa |
| Albedo | `MCD43C3.061` | 0,05° | 2023, paso de 8 días | 46 × ~205 MB ≈ 9,4 GB | entra en ATI gruesa |
| ATI gruesa | derivada de las dos filas anteriores | 0,05° | 2023 | — | `ati_cmg_p50_per_k` |
| Emisividad | `AG1km.003` (ASTER GED 1 km) | 1 km | climatología 2000–2008 | 24 873 teselas × ~0,46 MB ≈ 11 GB | `emissivity_b10_b14_cmg`, `silicate_index_cmg` |
| Humedad del suelo | `SPL3SMP_E.006` | 9 km | 2019–2023, paso de 8 días | 228 días; solo `soil_moisture` AM por rangos, ~25 MB cada uno ≈ 6 GB (por verificar) | `soil_moisture_p50_cmg` |
| Permafrost | ESA CCI Permafrost v5 L4 PFR (CEDA) | 1 km | 2023 | un NetCDF por hemisferio (tamaño no verificado) | `permafrost_fraction_cmg` |

En total, unos **30 GB de transferencia una sola vez**, en `us-west1` (cerca de los DAAC), en pocas horas de una VM Spot. Como comparación, AG100 global serían 24 873 × 42 MB ≈ 1 TB, y por eso se usa AG1km.

### Reglas del contrato

- **Columnas separadas de las finas.** Todas llevan el sufijo `_cmg` y el nivel `context_coarse`. Nunca se mezclan con las medidas finas por ventana (`modis_ati_p50_per_k`, emisividad AG100, etc.).
- **Soporte declarado.** Una celda de 0,05° (~5,5 km) es mayor que la ventana de 3 km. Cada columna registra el soporte (`support_m`) y la fracción de celda válida; no se interpola.
- **La ATI gruesa no sustituye a la fina.** La amplitud entre medias mensuales de día y de noche no equivale a pares diarios despejados. Se usa para proponer candidatas y como vista de contexto, y se contrasta con la ATI fina donde ambas existan, informando la correlación de Spearman.
- **Procedencia.** Una fila de `source_manifests` por gránulo, con DOI y versión, como en `etl_surface_fetch.build_manifests`.

### Implementación

- `scripts/etl_capa_global.py build --product …` descarga los gránulos por streaming, reduce cada producto a un ráster climatológico (COG en su rejilla nativa), lo sube a `gs://…/global_layers/<producto>/v1/` y borra los originales. Reutiliza los lectores de `pipelines/etl_surface_fetch.py`: `open_h5`, `read_hdf4_layers`, rejillas EASE2 y CMG.
- `scripts/etl_capa_global.py sample` muestrea los rásteres en el centro de cada ventana de `base_windows` y escribe `enrichment_global`, con una fila por `region_id` (~1,8 M filas, decenas de MB en parquet).
- Una tabla nueva `enrichment_global` en `specs/analysis/feature-store-etl-v1.json`, en la vista unificada y en la compactación.

## 4. Fase B: muestra de fondo estratificada

Se enriquece un conjunto aleatorio de ventanas exactamente igual que las candidatas, para que las vistas puente se ajusten sobre una población representativa.

- **Opción nueva** en `etl_superficie.py` y `etl_puentes.py`: `--background-sample N --seed S`.
- **Estratos:** familia GMM del motor × banda de latitud × régimen de entorno (aridez y nieve de la Fase A). Se excluye la cuenca reservada de Mojave.
- **Tamaño:** N ≈ 1 000, con un mínimo de 100 ventanas por vista medida, para superar `min_body_population`.
- **Trazabilidad:** cada fila enriquecida guarda `selection_reason` (`candidate`, `background`, `control` o `retrieval:<vista>`) e `inclusion_probability`.
- **Cambio en el motor:** las vistas puente se ajustan **solo** con las filas `background`, ponderadas por 1/`inclusion_probability`. Las candidatas se puntúan, pero no entran en el ajuste.

### Productos con cobertura parcial

- **EMIT** solo cubre las franjas áridas y **OPERA RTC-S1** solo Norteamérica. Para esas vistas, la muestra se estratifica **dentro** de su huella de cobertura. La huella se obtiene de los polígonos de los gránulos en CMR, solo con metadatos. Fuera de la huella, la vista queda `structurally_absent`, no «ausente por no medir».
- **ATI fina:** cuesta ~6 GB por tesela MODIS y año, así que 1 000 ventanas dispersas caerían en cientos de teselas, del orden de 1–2 TB. En la muestra de fondo se usa **muestreo por conglomerados**: unas 30–50 teselas al azar y varias ventanas por tesela, con su probabilidad de inclusión. Fuera de esas teselas, la ATI gruesa de la Fase A da la señal.

## 5. Fase C: listas cortas por vista

Cada vista propone sus propias candidatas con la señal barata de la Fase A. Se enriquece la **unión** de esas listas.

| Vista | Señal para proponer candidatas |
|---|---|
| Topográfica | `rank_similar` actual (relieve y pendientes) |
| Térmica | Distancia en rango de `ati_cmg_p50_per_k` al percentil de la referencia en su cuerpo |
| Espectral | `silicate_index_cmg` y aridez, dentro de la huella EMIT |
| Radar | Huella OPERA/RCM y elegibilidad; sin señal previa barata, solo cobertura |
| Entorno | Perfil de aridez, nieve, permafrost y humedad frente al escenario |

- `candidate_sites` pasa a aceptar `--retriever vista=K` (repetible). Por defecto, K se reparte en proporción a los pesos de la consulta: con topografía en 0, no se proponen candidatas topográficas.
- El motor ya fusiona con media ponderada o RRF, así que no hace falta cambiar la fusión.

## 6. Fase D: medir y mostrar el sesgo residual

- **Recall estimado.** En la muestra de fondo se calculan las puntuaciones con todas las vistas. Para cada vista, el recall es la fracción del q % superior de la muestra que las listas cortas habrían propuesto. Se guarda en la evidencia.
- **Cobertura en cada resultado.** Por vista: población ajustada (`n`), fracción de `base_windows` con la vista medida y composición de `selection_reason`.
- **Aviso.** Si la vista con más peso en una consulta cubre menos de un umbral de la base (propuesta: 1 %), la salida lo advierte en lugar de presentar un top-10 que parece global.

## 7. Orden y dependencias

| Paso | Depende de | Esfuerzo de código | Coste de ejecución |
|---|---|---|---|
| A. Capa global | Barrido mundial (centros de ventana) y autorización de GES DISC para IMERG | 1–2 días | ~30 GB, una VM Spot, horas |
| B. Muestra de fondo | A (estratos de entorno) y primer `fit` del motor (familias GMM) | ~1 día | 1 000 ventanas; ATI fina por conglomerados |
| C. Listas por vista | A | ~1 día | Según K por vista |
| D. Recall y avisos | B y C | ~0,5 días | Despreciable |

Secuencia de ejecución: barrido mundial → primer `fit` → A → B y C → segundo `fit` (vistas puente y de entorno) → D.

## 8. Decisiones abiertas

1. **Vista `entorno_superficial`.** Añadirla al spec del motor con las columnas `_cmg`. Falta decidir si actúa solo dentro de la Tierra (contexto y escenario) o si se compara con referencias planetarias, y en ese caso con qué valores de Marte y la Luna.
2. **ATI gruesa en la vista `termica`.** Usarla solo para proponer candidatas, o también como característica de respaldo cuando falta la fina.
3. **Tamaño de la muestra de fondo** y número de teselas para la ATI fina.
4. **Periodo climatológico.** 2019–2023 para todo, o adaptado a cada producto.

## 9. Criterios de verificación

- `enrichment_global` cubre ≥ 99 % de las ventanas de tierra, con columnas `_cmg` dentro de los rangos del contrato.
- Correlación de Spearman entre `ati_cmg` y la ATI fina, y entre `silicate_index_cmg` y la emisividad AG100, informada sobre las ventanas con ambas.
- Cada vista puente se ajusta con ≥ 100 filas `background`.
- Recall estimado por vista publicado en la evidencia, y aviso de cobertura comprobado en un test con una consulta de peso topográfico 0.
