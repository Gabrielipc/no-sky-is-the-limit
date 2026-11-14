# Atlas de Análogos Planetarios
## Estado actual (AS IS), visión objetivo (TO BE) y estrategia de datos para una búsqueda global

**Documento de visión y propuesta técnica · Versión 1.0 · 9 de noviembre de 2026**  
**Proyecto:** NASA Space Apps — *Identify Earth Locations that Analog the Permanent Moon Base Locations and Mars*  
**Estado:** Propuesta para discusión; no equivale a una implementación completada ni a una validación científica de análogos.

> **Tesis del proyecto.** Evolucionar desde comparaciones topográficas reproducibles entre unas pocas regiones hacia un atlas mundial de características terrestres, capaz de **buscar sistemáticamente candidatos** a análogos de Marte o la Luna y después **profundizar únicamente en los lugares más prometedores**. La búsqueda se basará primero en métricas explícitas y explicables; el aprendizaje automático será opcional y deberá demostrar valor adicional.

---

# 1. Resumen ejecutivo

El atlas actual constituye una prueba de concepto valiosa: dispone de comparaciones locales de pendiente y relieve, una búsqueda regional acotada y pruebas de sensibilidad a fuente y escala. La documentación suministrada no acredita aún un índice mundial de features, una búsqueda global ejecutada ni una validación independiente de que los candidatos sean análogos útiles [I1].

El objetivo TO BE es construir dos capacidades complementarias:

1. **Descubrimiento global (breadth):** recorrer las tierras emergidas mediante ventanas espaciales sistemáticas, describir cada ventana con un conjunto compacto de *features* y buscar candidatos desde un perfil de referencia planetario. Se conservará un catálogo tabular consultable (Parquet/DuckDB), no necesariamente todos los rásteres crudos en disco.
2. **Caracterización selectiva (depth):** abrir un expediente detallado de las regiones mejor clasificadas, releer productos originales a mayor detalle cuando existan, contrastar fuentes y escalas, estudiar materiales, contexto y procesos, y explicar tanto las semejanzas como las diferencias.

La referencia inicial será el sector estudiado de **Jezero, Marte**; la infraestructura deberá permitir después otras regiones marcianas y, mediante contratos de datos específicos, casos lunares. Ningún sitio terrestre se considerará un análogo universal: cada comparación debe estar vinculada a una **pregunta de exploración**.

**Decisión arquitectónica propuesta:** 30 m como resolución objetivo para el primer índice topográfico global (Copernicus DEM GLO-30), con otras capas a sus resoluciones efectivas; una malla de ventanas nominales de 3 × 3 km; procesamiento por teselas; catálogo de features compacto; y refinamiento de candidatos con fuentes de 1–10 m u observaciones hiperespectrales **solo donde estén disponibles**. La cobertura mundial y el costo total del pipeline deberán demostrarse mediante un benchmark antes de comprometerse con un procesamiento exhaustivo.

# 2. Alcance, evidencia y definiciones

## 2.1 Qué está documentado y qué es propuesta

- **AS IS confirmado por la guía:** hechos atribuidos a *Guía para entender el atlas* (7 de noviembre de 2026), que resume entregas locales de las fases 1–5 [I1]. No se ha auditado aquí el repositorio completo ni se han ejecutado sus pipelines.
- **Fuentes externas verificadas:** características nominales de productos NASA, ESA, USGS, Copernicus, DLR y otros organismos según referencias [S1–S14]. Acceso nominal no implica que cada área, fecha y banda tenga observaciones válidas.
- **TO BE:** arquitectura, fases de entrega, columnas de la base de datos, prioridades, capacidades y umbrales **propuestos**. No forman parte del sistema actual por el solo hecho de aparecer en este documento.
- **Supuestos de capacidad:** cálculos de volumen basados en superficies y tamaños de datos teóricos; no son métricas medidas en el equipo del proyecto.

## 2.2 Vocabulario operativo

| Concepto | Interpretación en el atlas |
|---|---|
| **Dato raw / fuente** | Imagen, DEM, ráster, producto hiperespectral o reanálisis en su formato y resolución de origen; fuente para calcular o recalcular características. |
| **Feature** | Descriptor de una región: p. ej., mediana de pendiente, relieve p95−p5, fracción de suelo desnudo o frecuencia de presencia de agua. |
| **Ventana** | Polígono de medición, inicialmente de 3 × 3 km. La separación entre centros (*stride*) puede ser diferente del tamaño de ventana. |
| **Índice global** | Catálogo de ventanas y features, con procedencia, calidad, época, escala y cobertura. No equivale a conservar todos los píxeles. |
| **Referencia planetaria** | Región delimitada de Marte o la Luna con variables comparables y una pregunta científica. |
| **Candidato** | Región terrestre priorizada para revisión; no «análogo validado». |
| **Resolución nativa / efectiva / de análisis** | Separación de muestras del producto / detalle físicamente distinguible / tamaño de celdas empleado en el cálculo; deben registrarse por separado. |
| **Análogo orientado a tarea** | Sitio útil para estudiar una característica o proceso concretos; puede ser un mal análogo para otras dimensiones. |

# 3. Estado actual — AS IS

## 3.1 Capacidades completadas según la guía

| Fase | Entrega documentada | Alcance y limitación |
|---|---|---|
| **1. Viabilidad** | Inventario de productos, áreas, muestras y disponibilidad de datos. | Se estableció viabilidad en regiones elegidas; no una cobertura terrestre mundial. |
| **2. Análisis reproducible** | Comparación Jezero–Utah–Atacama con ventanas de 1,8 × 1,8 km y celdas de 60/120 m. | Descriptores de pendiente y relieve para polígonos concretos. |
| **3. Aplicación** | Frontend para mostrar comparaciones, figuras, fuentes, cobertura y escala. | Consulta resultados precomputados; no recalcula al mover controles. |
| **4. Búsqueda regional** | 970 ventanas nuevas de 3 × 3 km entre Utah, Mojave y Atacama; tres controles; filtros a 300/600 m. | Barrido disperso con separación de centros de 10 km: las huellas cubrieron aprox. 8,3–8,5 % de cada área definida. |
| **5. Fuente y escala** | Contraste GMTED2010 frente a SRTM en diez ventanas seleccionadas. | Siete evaluadas con datos suficientes, tres pendientes; resultados exploratorios, no validación independiente. |

El atlas actual compara **pendiente y relieve relativo**. En el caso local de Jezero, la pendiente mediana fue 2,88° y el relieve relativo 54,63 m; la ventana de Utah tuvo pendiente mediana 1,81° y relieve 27,38 m, mientras Atacama registró 7,97° y 200,11 m. La distancia Wasserstein de pendientes entre Utah y Jezero fue 1,456° frente a 5,033° entre Atacama y Jezero. Esos números describen las ventanas escogidas, no las regiones completas [I1].

En la fase 4, con el perfil base y celdas de 300 m, **363 ventanas** superaron los filtros topográficos predefinidos: 99 en Utah, 128 en Mojave y 136 en Atacama. Son ventanas que cumplen condiciones exploratorias, **no** 363 análogos certificados [I1].

## 3.2 Fuentes, software y arquitectura documentados

- **Marte:** DTM estéreo de HiRISE en Jezero; ortoimagen para inspección. MOLA se menciona como contexto, no como métrica del recorrido nuevo.
- **Tierra:** SRTM para comparaciones detalladas; GMTED2010 para muestreo regional y sensibilidad. Se identificaron 3DEP y otras fuentes, pero no estaban integradas en las métricas descritas.
- **Luna y polos:** LOLA descargado/reservado y otras fuentes consideradas; **no** integrados al recorrido descrito.
- **Procesamiento:** Python, Rasterio/GDAL, NumPy, pyproj/PROJ y scripts locales; entornos Pixi y manifiestos de evidencia.
- **Aplicación:** React/TypeScript, FastAPI y Cesium como globo de contexto; los globos actuales no muestran como geometría 3D el relieve medido.
- **Resultados:** registros/archivos locales precalculados. No se documenta una base global de features operativa, una plataforma distribuida, STAC/PostGIS desplegados ni ML entrenado.

La propia guía advierte que existen propuestas y carpetas reservadas de arquitectura futura; su presencia **no demuestra implementación**. También señala que ampliaciones posteriores —como dimensiones de superficie— tienen fichas separadas y **no están cubiertas por la guía**. Por ello este AS IS no debe leerse como una auditoría exhaustiva del estado del código a la fecha de hoy [I1].

## 3.3 Brecha hacia la visión objetivo

| Dimensión | AS IS documentado | TO BE deseado |
|---|---|---|
| Cobertura | Tres regiones terrestres seleccionadas. | Búsqueda sistemática mundial sobre tierra emergida, con cobertura y vacíos explícitos. |
| Referencia | Sector de Jezero. | Biblioteca de perfiles marcianos y, más tarde, lunares. |
| Variables | Pendiente y relieve; sensibilidad a escala/fuente. | Topografía, cobertura, reflectancia, temperatura, agua/hielo y capas especializadas. |
| Persistencia | Evidencia local y resultados precomputados. | Feature store particionado, versionado y rastreable en Parquet. |
| Búsqueda | Filtros y comparación regional. | Recuperación global + reordenamiento multivariable + análisis local. |
| Certidumbre | Exploratoria, sin validación física independiente. | Evidencia por dimensión, calidad, limitaciones y verificaciones externas. |
| Experiencia de usuario | Comparaciones y globos de contexto. | Flujo «referencia → mapa mundial → candidatos → expediente detallado». |

# 4. Visión futura — TO BE

## 4.1 Propuesta de producto

**Pregunta principal:** «Dada una región concreta de Marte o la Luna y una tarea de exploración, ¿qué lugares de la Tierra comparten las características relevantes, cuáles difieren y dónde merece la pena investigar con mayor detalle?».

El producto deseado tendría cinco funciones:

1. **Elegir un escenario:** referencia planetaria, objetivo científico (p. ej., procesos sedimentarios frente a movilidad robótica), escala y dimensiones relevantes.
2. **Buscar en todo el planeta:** evaluar un índice terrestre ya calculado, aplicar requisitos de cobertura y mostrar regiones candidatas.
3. **Explicar el resultado:** visualizar diferencias por variable, fuentes, período, escala, pesos y ausencias de datos; evitar porcentajes de «parecido a Marte» sin definición.
4. **Refinar candidatos:** lanzar comparaciones y consultas de productos de mayor resolución para un conjunto pequeño, conservando trazabilidad.
5. **Comunicar utilidad y límites:** describir para qué experimento podría servir un lugar y qué factores terrestres no reproducen condiciones marcianas o lunares.

## 4.2 Arquitectura de dos niveles

**Nivel A — Descubrimiento global:** catálogo de ventanas con features compactas, cobertura extensa y ranking rápido. Su cometido es reducir millones de posibilidades a decenas o cientos de candidatos. Se sugiere Copernicus DEM GLO-30 como fuente topográfica principal a evaluar, no como obligación irrevocable [S1].

**Nivel B — Investigación focalizada:** análisis de las mejores regiones: distribuciones completas, textura y formas del terreno, datos hiperespectrales, series temporales, fuentes detalladas como USGS 3DEP allí donde existan, imágenes y revisión de literatura/uso científico. Puede usar cuadrículas de 1–10 m, pero no asumir tal cobertura global [S13].

**Secuencia operativa de extremo a extremo:**

```text
FUENTES TERRESTRES REMOTAS                 REFERENCIA PLANETARIA
DEM / óptico / térmico / hielo / clima     Jezero (inicialmente)
                  │                                  │
       lectura por teselas                 perfil comparable + tarea
                  │                                  │
    QA + cálculo de descriptores                       │
                  │                                  │
     FEATURE STORE GLOBAL (Parquet) ─────────► BÚSQUEDA GLOBAL
                  │                                  │
                  └────────────────────────► ranking explicable
                                                     │
                                          candidatos seleccionados
                                                     │
                                         REFINAMIENTO LOCAL
                                                     │
                                     expediente + visualización
```

**Regla de operación:** el buscador usa principalmente features precomputadas. Los rásteres originales se vuelven a leer al incorporar features nuevas, cambiar escala/fuente o caracterizar candidatos; pueden residir remotamente y no permanecer completos en el almacenamiento local.

## 4.3 Decisiones espaciales abiertas

- **Unidad de análisis propuesta:** ventana de 3 × 3 km, para aprovechar experiencia previa. No debe confundirse con tamaño de celda.
- **Muestreo inicial rápido:** centros cada 10 km, útil para probar el flujo; **no exhaustivo** (9 km² por cada 100 km² en una cuadrícula ideal = ~9 % de ocupación nominal).
- **Cobertura nominal continua:** centros cada 3 km en una teselación apropiada, evitando huecos y registrando bordes/costas. La implementación real requerirá definir una malla planetaria reproducible y manejo polar.
- **Escalas múltiples:** permitir ventanas adicionales y comparaciones por escala solo cuando existan productos adecuados. Un único score no debe mezclar métricas calculadas con soportes espaciales incompatibles.

# 5. Nuevas fuentes de datos candidatas y dimensiones

Las fuentes se ordenan por utilidad para un catálogo global inicial y para un segundo nivel especializado. **«Global» describe el alcance nominal de la colección, no que cada ventana tenga imágenes válidas en toda fecha**. HLS excluye la Antártida y los productos ópticos tienen limitaciones de nubes, iluminación y nieve [S2].

## 5.1 Núcleo del atlas global: fuentes prioritarias

| Dimensión | Fuente candidata | Resolución del producto | Qué observaríamos / features | Advertencia principal |
|---|---|---|---|---|
| **Topografía** | Copernicus DEM **GLO-30** [S1] | ~30 m | Pendiente, relieve p95−p5, rugosidad, orientación, distribución de pendientes. | Es un **modelo digital de superficie** (puede incluir vegetación/edificaciones), no un modelo puro de terreno. Acceso GLO-30 con registro/condiciones del servicio. |
| **Cobertura / vegetación** | ESA **WorldCover 2021** [S3] | 10 m | Fracciones de suelo desnudo, vegetación, nieve/hielo, agua, urbano y clases dominantes. | Clasificación imperfecta; años 2020/2021 no equivalen a una serie temporal homogénea por cambio de algoritmo. |
| **Reflectancia / superficie** | NASA **HLS L30 + S30** [S2] | 30 m | Medianas y percentiles de reflectancia; índices NDVI, NDMI, NDSI y variabilidad temporal. | Series multiescena potencialmente voluminosas; no mide mineralogía específica ni humedad de suelo directamente. |
| **Agua superficial** | JRC **Global Surface Water** [S5] | 30 m | Ocurrencia, recurrencia, estacionalidad, cambios observados de agua. | Histórico 1984–2021; agua superficial, no subsuperficial. |
| **Temperatura superficial** | USGS **Landsat Collection 2 ST** [S4] | Sensor térmico 100 m en L8/9; producto remuestreado a 30 m | Medianas, extremos, distribución térmica de observaciones disponibles. | El producto de 30 m **no** aporta 30 m de detalle térmico independiente; nubosidad, horario y huecos. |

**Alternativa o extensión para topografía:** ALOS AW3D30 (JAXA), de clase ~30 m, para contrastes en regiones seleccionadas. La elección final debe atender acceso, cobertura efectiva, artefactos, referencia vertical y continuidad. Su incorporación no se presupone ya realizada.

## 5.2 Capas especializadas y ambientales complementarias

| Dimensión | Dataset | Resolución / alcance | Uso propuesto | Rol recomendado |
|---|---|---|---|---|
| **Mineralogía** | NASA **EMIT L2B** [S6] | 60 m; adquisiciones discontinuas, regiones áridas entre ~52°S y 52°N | Firmas minerales estimadas, profundidades de banda e incertidumbre. | Refinamiento donde haya datos; no cobertura global homogénea. |
| **Composición espectral** | DLR **EnMAP** [S7] | 30 m; adquisiciones por franjas / archivo creciente | Identificación/contraste de materiales mediante espectros hiperespectrales. | Refinamiento especializado; cobertura no exhaustiva. |
| **Litología contextual** | **GLiM** [S8] | Mapa de polígonos, escala media aprox. 1:3.750.000 | Clase geológica y contexto regional. | Contexto grueso; rasterizar a 30 m no agrega detalle real. |
| **Procesos eólicos: formas** | Sentinel-2 / HLS [S2] | 10–30 m según producto | Textura de dunas, orientación aparente, cambios multitemporales. | Descriptores morfológicos; no equivalen directamente a tasas de erosión. |
| **Procesos eólicos: aerosoles** | NASA **MAIAC MCD19A2** [S9] | 1 km; observaciones diarias | Profundidad óptica de aerosoles (AOD), variabilidad, episodios. | Contexto atmosférico; AOD no es exclusivamente polvo mineral. |
| **Viento y ambiente** | **ERA5-Land** [S10] | ~9 km; reanálisis horario | Viento modelado, temperatura y humedad atmosféricas, extremos. | Contexto regional; no tratarlo como medición local a 30 m. |
| **Nieve / hielo superficial** | **MODIS MOD10A1** [S11] | 500 m; diario | Persistencia, estacionalidad y frecuencia de nieve. | Complemento temporal; no detecta hielo enterrado. |
| **Humedad del suelo** | NASA **SMAP** [S12] | 36 km; cuadrícula mejorada de 9 km | Humedad superficial regional y evolución temporal. | Contexto grueso, no feature «medida a 30 m». |
| **Topografía local de alta resolución** | USGS **3DEP** [S13] | ~10 m y productos lidar de 1 m según cobertura | Reconocimiento detallado de formas, pendiente y rugosidad. | Solo candidatos estadounidenses con datos disponibles. |

## 5.3 Qué dimensiones pueden describirse realmente a ~30 m

- **Con buen encaje espacial:** topografía, reflectancia óptica, cobertura terrestre, agua superficial observada, ciertas formas eólicas y nieve/hielo visibles.
- **Con encaje parcial:** temperatura superficial (producto a 30 m pero información térmica nativa de ~100 m en Landsat 8/9); minerales con EMIT 60 m y EnMAP 30 m, pero sin mosaico global completo.
- **Principalmente contextuales/gruesas:** viento, transporte atmosférico, humedad real del suelo, permafrost/hielo enterrado, geología de mapas globales. Se pueden asociar a ventanas de 3 km, **sin convertirlos en evidencia de 30 m**.

## 5.4 Features sugeridas por dimensión

| Dimensión | Descriptores candidatos | Interpretación correcta |
|---|---|---|
| Topografía | `slope_p10/p50/p90`, `slope_wasserstein_ref`, `relief_p95_p5_m`, `roughness_multiscale`, `aspect_histogram`. | Forma estadística del relieve; no garantiza transitabilidad de rovers. |
| Superficie / vegetación | `bare_fraction`, `veg_fraction`, `ndvi_p50`, `ndvi_seasonality`, `urban_fraction`. | Estado/uso de superficie e indicadores ópticos; no analogía geológica por sí sola. |
| Reflectancia / materiales | `red_swir_ratio`, `band_percentiles`, `spectral_variability`, `lithology_context`. | Indicadores de propiedades ópticas y contexto; no «abundancia mineral» salvo producto validado para ello. |
| Temperatura | `lst_day_p50`, `lst_p90`, `lst_obs_count`, `lst_valid_fraction`, `lst_monthly_range`. | Condiciones de la superficie en horarios observados; no temperatura del aire continua. |
| Agua / hielo | `water_occurrence`, `water_seasonality`, `snow_frequency`, `snow_valid_fraction`. | Presencia superficial detectable; no agua/hielo en subsuelo. |
| Eólico / atmósfera | `dune_orientation`, `aod_p90`, `wind_speed_p90`, `dry_days_proxy`. | Mezcla de formas, aerosoles y reanálisis; no tasa real de erosión sin validación. |
| Humedad | `smap_surface_soil_moisture`, `soil_moisture_period`, `ndmi_p50` (separado). | SMAP y NDMI miden/proxyan fenómenos distintos; no fusionarlos sin aclaración. |

# 6. Datos raw, feature store y pipeline por streaming

## 6.1 Por qué siguen importando los rásteres originales

La búsqueda cotidiana se realizará sobre Parquet, **no** escaneando un GeoTIFF por cada solicitud. Sin embargo, los datos originales siguen siendo necesarios para: (a) calcular features por primera vez, (b) corregir un error, (c) generar una métrica no prevista, (d) cambiar escala/fuente, (e) producir visualizaciones de detalle y (f) auditar resultados.

**Estrategia de persistencia:** guardar permanentemente features, metadatos, manifiestos, código/configuración y una caché pequeña de productos frecuentes. Conservar el identificador y la ubicación de cada fuente externa. No asumir que una URL remota permanecerá inmutable: incluir versión, fecha de acceso y, si se dispone, identificador estable o checksum.

## 6.2 Pipeline propuesto (procesamiento fuera de línea)

1. **Inventario de cobertura y derechos:** producto, versión, resolución efectiva, fechas, licencia y método de acceso. No iniciar un barrido global sin esta tabla.
2. **Definición reproducible de ventanas:** IDs estables, polígonos, proyección apropiada y reglas para costas/polos; conservar tamaño de ventana y stride.
3. **Lectura remota por teselas:** acceder a COG cuando el proveedor lo soporte, o descargar temporalmente bloques de archivos/gránulos. COG facilita lectura parcial, pero no garantiza que todo producto remoto soporte acceso eficiente.
4. **Máscaras y control de calidad:** nodata, nubes, QA del sensor, calidad geométrica, soporte de cálculo y área válida por dimensión.
5. **Extracción de features:** cargar una tesela con halo de vecindad, computar varias ventanas juntas, registrar unidades y procesamiento aplicado.
6. **Escritura incremental:** Parquet por lote/región/fuente/versión; evitar mantener todos los datos en RAM.
7. **Validación técnica y publicación:** comprobar conteos, cobertura, rangos, checksums y resultados de una muestra; publicar una versión coherente del índice.

No almacenar datos raw localmente **no significa no leerlos**. La lectura/transferencia total puede ser de cientos de GB o TB, y el costo de calcular productos multitemporales depende mucho más del número de escenas que del tamaño final del Parquet.

## 6.3 Modelo lógico mínimo de datos

**Tabla `regions` (una fila por ventana):** `region_id`, `geometry/bbox`, `center_lat/lon`, `window_size_m`, `stride_m`, `grid_version`, `land_fraction`, `region_status`.

**Tabla `features` (fila por región × feature × producto/escala/época, o partición ancha equivalente):** `region_id`, `feature_name`, `value`, `unit`, `dimension`, `source_id`, `source_version`, `period_start/end`, `native_resolution_m`, `analysis_cell_m`, `valid_fraction`, `qa_status`, `run_id`.

**Tabla `sources`:** `source_id`, `provider`, `product`, `version`, `url/DOI`, `license`, `spatial_extent`, `temporal_extent`, `reference_system`, `access_notes`.

**Tabla `planetary_profiles`:** `profile_id`, `body`, `site`, `geometry`, `scenario`, `feature_spec`, `source_versions`, `limitations`.

**Tabla `search_runs`:** `query_id`, `profile_id`, `filter_spec`, `dimension_weights`, `normalization_version`, `index_release`, `candidate_ids`, `timestamp`.

Para un catálogo de consultas rápidas es razonable materializar tablas **anchas** por dimensión (columnas de características) y conservar una descripción normalizada de cada feature en un diccionario o manifiesto. Los faltantes deben representarse como `null` con causa, nunca como cero.

# 7. Escalabilidad y almacenamiento: hipótesis verificables

## 7.1 Orden de magnitud de la malla

Tomando como supuesto ~149 millones de km² de tierras emergidas:

- **Ventanas de 3 × 3 km con stride 10 km:** ~1,49 millones de centros por proporción de área; muestreo nominal del ~9 %, **no** cobertura territorial exhaustiva.
- **Ventanas de 3 × 3 km con stride 3 km:** ~16,6 millones de ventanas por proporción de área; cobertura nominal contigua antes de ajustes de costas, proyección y polos.
- **Detalle topográfico dentro de una ventana:** a 30 m, aproximadamente 100 × 100 = 10.000 celdas; a 250 m, aproximadamente 12 × 12 = 144 celdas.
- **Píxeles teóricos de todas las tierras emergidas a 30 m:** 149 × 10⁶ km² / 0,0009 km² ≈ 165,6 mil millones de celdas; una sola capa float32 ocuparía ≈ 662 GB **sin compresión**. Este volumen de entrada no es el volumen del índice final.

## 7.2 Cuánto podría ocupar el catálogo Parquet

Ejemplo de planificación, **no benchmark**: 16,6 millones de regiones × (50 features numéricas × 4 bytes + 40–80 bytes de campos compactos) ≈ **4,0–4,7 GB** de contenido tabular antes de estructura, índices externos, geometrías extensas y compresión. Varias escalas, series temporales completas o distribuciones muy detalladas aumentarían considerablemente la huella.

**Implicación:** un presupuesto de 100 GB de SSD puede ser razonable para el índice, cachés y lotes pequeños, pero **no** garantiza que quepan simultáneamente todos los rásteres ni que el procesamiento global de 30 m sea rápido. Los límites probables son transferencia, I/O, tiempo de cómputo, cobertura de servicios y QA.

## 7.3 Estrategia técnica local sugerida

- Python + Rasterio/GDAL + NumPy para rasters, por bloques y con halos; Parquet (Arrow) para persistencia; DuckDB para consulta y ranking.
- Iniciar con equipo convencional y **medir** si 16 GB de RAM bastan; 32 GB aporta margen. No plantear GPU como requisito del baseline.
- Hacer un **benchmark de 100 × 100 km**: tiempo, RAM máxima, bytes transferidos, SSD temporal, costo de cada feature y porcentaje de región válida.
- Extrapolar con rangos, no con un único tiempo. Repetir en costa, montaña, desierto y región nublada/polar; observar diferencias de costo.
- Construir primero un índice topográfico; incorporar capas estáticas (WorldCover, JRC) antes que series HLS/Landsat de todos los años.

# 8. Cómo funcionaría la búsqueda de similitud

## 8.1 Baseline explicable sin entrenamiento

La búsqueda global puede funcionar inicialmente sin ML:

1. Aplicar filtros por **requisitos no negociables**: dimensión disponible, cobertura válida, tipo de terreno o restricciones geográficas si son relevantes.
2. Calcular distancias **por dimensión**, con normalización coherente y unidades documentadas.
3. Ordenar el subconjunto con pesos ligados a la tarea de exploración; mostrar también cada distancia individual.
4. Ejecutar un **reranking detallado** solo sobre los mejores N candidatos, usando histogramas, distribuciones completas o productos nuevos.
5. Generar un expediente con evidencia, fuentes, incertidumbres, dimensiones sin datos y límites de la analogía.

**Ejemplo de familias de métricas:** Wasserstein para distribuciones de pendiente; diferencia normalizada para relieve; distancias entre distribuciones de coberturas; contrastes espectrales solo si se han armonizado; similitud de series temporales cuando sean comparables. No hay una «similitud física universal» derivable de una suma arbitraria de scores.

## 8.2 Dónde encajaría ML

- **Opcional y posterior:** clustering y detección de anomalías para explorar grupos de paisajes inusuales.
- **No como requisito del MVP:** aprendizaje supervisado de «análogo/no análogo» sin etiquetas independientes y validadas.
- **Condición de adopción:** superar a un baseline transparente en recuperación, estabilidad y utilidad de los candidatos; de lo contrario, la complejidad no está justificada.

## 8.3 Tierra ≠ Marte/Luna: reglas mínimas de comparabilidad

Un valor con la misma unidad no es necesariamente la misma magnitud física. Por ejemplo: NDVI terrestre no tiene un análogo marciano directo, un índice óptico no identifica por sí solo minerales, la temperatura superficial depende del régimen de observación y las condiciones atmosféricas de ERA5-Land no reproducen el ambiente marciano o lunar.

Para cada dimensión se debe elaborar una ficha con: **pregunta científica; observación terrestre; contraparte planetaria; transformación propuesta; escala común; qué semejanza es interpretable; dónde falla la analogía; fuentes; calidad y confianza**. Si no existe contraparte planetaria comparable, la variable puede funcionar como **filtro o contexto**, pero no debe incorporarse silenciosamente al score de similitud.

# 9. Experiencia del usuario y narrativa del proyecto

La interfaz propuesta se organizaría en cuatro pantallas o momentos:

1. **Seleccionar referencia:** Jezero y pregunta de exploración. Mostrar el polígono, instrumentos, resolución y dimensiones disponibles.
2. **Explorar el mundo:** mapa de candidatas y filtros. Indicar cobertura analizada y zonas sin datos. Permitir elegir «topografía», «materiales» u otras vistas y comparar criterios sin ocultar los pesos.
3. **Comparar candidatos:** tabla/mapa con fortalezas, debilidades, escalas y fuente. Distinguir «alto ranking», «evaluado en detalle» y «validado externamente».
4. **Abrir expediente:** evidencia multifuente del candidato, mapas de relieve, material/espectro cuando exista, contraste de escala, diferencias respecto a la referencia y posible uso científico.

**Storytelling central:** «No buscamos el paisaje que se vea más marciano; usamos datos terrestres para descubrir ambientes que reproducen procesos o características útiles para preparar la exploración, y explicamos dónde dejan de ser comparables».

# 10. Hoja de ruta de implementación propuesta

| Etapa | Entrega concreta | Criterio de salida / puerta de decisión |
|---|---|---|
| **0. Inventario y contratos** | Lista de fuentes y licencias, esquema de features, especificación de ventanas y perfiles. | Cada feature tiene unidad, escala, procedencia y tratamiento de nodata. |
| **1. Benchmark técnico** | Ensayo 100 × 100 km con GLO-30 y 3 km de ventana; Parquet de salida. | RAM, tiempo, transferencia, precisión de lectura y cobertura medidos. |
| **2. Índice topográfico ampliado** | Barrido progresivo: primero disperso (stride 10 km), después contiguo (3 km) si el costo es asumible. | Consultas locales reproducibles y mapa que distingue áreas cubiertas y no cubiertas. |
| **3. Núcleo multivariable** | WorldCover + JRC; HLS compuesto y Landsat ST en una muestra/piloto antes de escalar temporalmente. | Aporte de cada dimensión demostrado; calidad temporal/espacial registrada. |
| **4. Buscador mundial** | Filtros, pesos, explicación por dimensión y reranking de top-N. | Recupera candidatos diversos; ranking estable bajo pruebas razonables de fuente/escala. |
| **5. Expedientes de descubrimiento** | 3–5 candidatos con refinamiento y contraste de fuentes, incluidos lugares inesperados cuando haya evidencia. | Cada expediente muestra semejanzas, diferencias, datos faltantes y tarea de exploración. |
| **6. Extensiones** | EMIT/EnMAP, eólico, clima, SMAP, Luna y ML exploratorio si hay tiempo y validación. | No sacrificar la búsqueda explicable ni la integridad del núcleo. |

**Prioridad del hackathon:** cumplir de manera demostrable las etapas 0–4 y presentar al menos un expediente de la etapa 5. La cobertura global exhaustiva y todas las dimensiones no son prerrequisitos para demostrar el método; sí deben declararse los huecos.

# 11. Validación, riesgos y criterios de éxito

## 11.1 Validación técnica y científica

- **Trazabilidad:** reconstruir una feature a partir de su producto, versión y parámetros.
- **Cobertura:** porcentaje de ventanas procesadas; porcentaje de píxeles válidos por producto y fecha; regiones con ausencias explícitas.
- **Estabilidad:** variar fuentes DEM, tamaño de celda, ventana, pesos y umbrales; registrar cambios de clasificación/ranking.
- **Baseline:** comparar búsqueda multivariable contra pendiente+relieve y contra una selección regional arbitraria.
- **Controles contextuales:** verificar comportamiento en sitios bien estudiados, sin tratarlos automáticamente como verdad de terreno para todas las dimensiones.
- **Validación externa:** revisar candidatos sorprendentes con geología, trabajos científicos, imágenes de detalle o expertos; no declarar tasas de falsos positivos sin etiquetas independientes.

## 11.2 Principales riesgos y mitigaciones

| Riesgo | Consecuencia | Mitigación |
|---|---|---|
| Cobertura temporal/sensorial incompleta | Regiones con datos desiguales o rankings sesgados. | Indicadores de cobertura y perfiles comparables; no rellenar faltantes con 0. |
| Confundir 30 m de píxel con 30 m efectivos | Puntuaciones aparentemente precisas pero inválidas. | Metadatos `native_resolution`, `effective_resolution` si se conoce y `analysis_cell`. |
| Coste global de procesamiento | Escalado inviable durante el hackathon. | Benchmark, streaming por teselas, procesar por prioridad, caché limitada y parada/reanudación. |
| Confundir reflectancia, mineralogía y geología | Conclusiones científicas no justificadas. | Fichas por feature y lenguaje prudente; EMIT/EnMAP como evidencia especializada. |
| Sesgo del índice topográfico | Lugares geométricamente parecidos pero geológicamente irrelevantes. | Evaluación multivariable por objetivo + inspección independiente. |
| Score único engañoso | Oculta incompatibilidades importantes. | Distancias por dimensión, filtros y explicaciones de diferencias. |
| Dependencia de acceso remoto | Cuotas, autenticación, cambios de API o enlaces. | Inventario de accesos/licencias, pruebas de lectura parcial, fallback, manifiestos y reintentos. |
| Alcance excesivo | Pipeline incompleto y demo frágil. | Núcleo demostrable primero; especializaciones y ML después. |

## 11.3 Indicadores de éxito propuestos

- Índice publicado con número de ventanas, porcentaje de área nominal cubierta y porcentaje de features válidas.
- Búsqueda reproducible desde Jezero; filtros y score definidos, no caja negra.
- Capacidad de localizar y explicar **candidatos no elegidos manualmente**.
- Al menos tres expedientes con visualizaciones, trazabilidad, fortalezas, limitaciones y uso científico propuesto.
- Evaluación de sensibilidad a escala/fuente en una muestra independiente de las regiones usadas para ajustar parámetros.
- Métrica real de tiempo, RAM, bytes leídos y espacio temporal del pipeline piloto.

# 12. Decisiones pendientes para el equipo

1. **Primer escenario científico:** ¿analogía topográfica general, sedimentos/alteración de Jezero o movilidad robótica? Esta elección define qué features importan.
2. **Cobertura inicial:** ¿índice mundial topográfico disperso primero o densificar desde el comienzo zonas áridas? La primera opción comunica mejor la búsqueda global; la segunda reduce costo.
3. **Especificación espacial:** tamaño de ventana, stride, proyección, tratamiento de costa y latitudes altas.
4. **Primer conjunto de capas:** recomendación: GLO-30 + WorldCover + JRC; sumar HLS/Landsat en un piloto por período definido.
5. **Contraparte planetaria:** para cada dimensión terrestre, ¿qué producto marciano/lunar se comparará y a qué escala común?
6. **Capacidad real del equipo:** RAM/CPU/SSD/red, autenticación a servicios, y autorización para guardar derivados.
7. **Condición de «candidato prometedor»:** calidad de datos, estabilidad, valor científico y narrativa, no solo mínima distancia estadística.

# 13. Recomendación final

**No construir todavía un lago planetario completo ni entrenar un modelo supervisado.** Construir un **índice global de features verificable y pequeño**, utilizando fuentes públicas de alta utilidad y procesamiento por teselas, seguido de un **refinamiento profundo de pocos candidatos**. Esto separa dos preguntas difíciles: «¿dónde buscar?» y «¿qué evidencia hace que el lugar sea útil para una misión?».

El hallazgo valioso para NASA Space Apps no sería demostrar una semejanza visual universal con Marte o la Luna, sino presentar **un procedimiento reproducible para encontrar, explicar y priorizar ambientes terrestres como laboratorios de exploración planetaria**.

---

# Referencias y fuentes consultadas

**Base interna del proyecto**

- **[I1]** *Guía para entender el atlas*, documento local suministrado por el equipo, fechado el 7 de noviembre de 2026. Resume las fases 1–5; menciona extensiones posteriores no incluidas en su alcance. No se ha auditado el código ni ejecutado el pipeline para elaborar esta propuesta.

**Fuentes públicas oficiales y técnicas** (consultadas para esta propuesta el 9 de noviembre de 2026)

- **[S1]** Copernicus Data Space Ecosystem. *Copernicus DEM — Global and European Digital Elevation Model* y aviso de acceso GLO-30 (agosto de 2026). https://dataspace.copernicus.eu/explore-data/data-collections/copernicus-contributing-missions/collections-description/COP-DEM ; https://dataspace.copernicus.eu/news/2026-8-25-copernicus-dem-30m-view-service-update
- **[S2]** NASA. *Harmonized Landsat Sentinel-2 (HLS)* y catálogo HLSL30 v2.0. https://hls.gsfc.nasa.gov/ ; https://data.nasa.gov/dataset/hls-landsat-operational-land-imager-surface-reflectance-and-toa-brightness-daily-global-30-b4633
- **[S3]** ESA. *WorldCover — About / Data Access*. https://esa-worldcover.org/en/about/about ; https://esa-worldcover.org/en/data-access
- **[S4]** USGS. *Landsat Collection 2 Surface Temperature*. https://www.usgs.gov/landsat-missions/landsat-collection-2-surface-temperature
- **[S5]** EC JRC / Google. *Global Surface Water, v1.4*. https://developers.google.com/earth-engine/datasets/catalog/JRC_GSW1_4_GlobalSurfaceWater
- **[S6]** NASA Earthdata. *EMIT L2B Mineral Identification, 60 m V001*. https://doi.org/10.5067/EMIT/EMITL2BMIN.001
- **[S7]** EnMAP / DLR. *Mission; Data & Access*. https://www.enmap.org/mission/ ; https://www.enmap.org/data_access/
- **[S8]** Universidad de Hamburgo. *GLiM — Global Lithological Map*. https://www.geo.uni-hamburg.de/en/geologie/forschung/aquatische-geochemie/glim.html
- **[S9]** NASA. *MCD19A2.061 — MAIAC Land Aerosol Optical Depth, daily 1 km*. https://data.nasa.gov/dataset/modis-terraaqua-land-aerosol-optical-depth-daily-l2g-global-1km-sin-grid-v061-c3a26
- **[S10]** ECMWF. *ERA5-Land*, resolución ~9 km. https://www.ecmwf.int/en/era5-land
- **[S11]** NSIDC. *MODIS Snow Products*. https://nsidc.org/data/modis/data
- **[S12]** NSIDC. *SMAP data products and subsetting*. https://nsidc.org/data/user-resources/help-center/what-data-subsetting-reformatting-and-reprojection-services-are-available-smap-data
- **[S13]** USGS. *About 3DEP Products & Services*. https://www.usgs.gov/3d-elevation-program/about-3dep-products-services
- **[S14]** ESA. *WorldCover 2020/2021 data access and quality*. https://esa-worldcover.org/en/data-access

> **Nota de uso:** los productos y condiciones de acceso pueden cambiar. Antes de ejecutar un pipeline mundial, confirmar producto exacto, cobertura, formato disponible, términos de uso, límites de acceso, QA y fecha/versión. Este documento es una propuesta de arquitectura informada por fuentes, no un certificado de viabilidad computacional o de analogía científica.
