# Fase 4 — búsqueda regional terrestre

**Estado:** implementada para el primer escenario, el 7 de noviembre de 2026.  
**Resultado:** 970 ventanas terrestres fuera del catálogo inicial, tres centros de control, dos escalas, tres perfiles de filtro y una evaluación local exploratoria ejecutada. No se afirma que estas ventanas sean análogos validados.

## 1. Auditoría y decisión sobre GMTED

Se comprobaron los SHA-256 y los CRC de **todos los miembros** de `mn75_grd.zip` y `mn30_grd.zip`, sin modificar ni extraer los rásteres globales. Se verificaron tamaño, formato, dimensiones, CRS horizontal, paso angular, nodata y muestras de lectura. Las identidades coinciden con las entradas del manifiesto local de adquisición.

| Archivo | Bytes comprimidos | Cuadrícula leída | Paso | Uso en esta fase |
|---|---:|---|---|---|
| `mn75_grd.zip` | 2 919 537 239 | ArcGrid/AIG, Int16, 67 200 × 172 800 | 7,5″ | Preselección regional |
| `mn30_grd.zip` | 277 229 566 | ArcGrid/AIG, Int16, 20 880 × 43 200 | 30″ | Contexto y auditoría; no participa en los filtros |

Ambos declaran WGS84 horizontal y nodata −32768. Sus bandas no declaran unidad vertical; se documentan metros según [los metadatos FGDC de USGS](https://topotools.cr.usgs.gov/gmted_viewer/gmted2010_fgdc_metadata.html), que advierten que el datum vertical depende de la fuente. No se asigna un datum único por píxel ni se compara elevación absoluta con Marte.

La distribución oficial identifica estos archivos como **media** en [ArcGrid global](https://topotools.cr.usgs.gov/gmted_viewer/gmted2010_global_grids.php). La [ficha USGS EROS](https://www.usgs.gov/centers/eros/science/usgs-eros-archive-digital-elevation-global-multi-resolution-terrain-elevation) documenta fuentes heterogéneas y lagunas a 7,5″, en particular polares. Se atribuye GMTED2010 a USGS/NGA y a Danielson y Gesch (2011); los derivados de esta entrega agregan, recortan, reproyectan y calculan descriptores. No se atribuye aprobación del USGS a estos cambios.

La auditoría confirma que 7,5″ termina aproximadamente en 56° S y 84° N; 30″ alcanza aproximadamente 90° S. **La extensión y los valores numéricos no son una máscara de observaciones ni de tierra:** en las muestras de 5 × 5 píxeles, 7,5″ devuelve 25 valores cero en el Pacífico y también en un punto de Groenlandia, mientras que 30″ devuelve elevación de 3103 m en este último punto. No se deduce de esas muestras un porcentaje global de cobertura. Cero sigue siendo un valor numéricamente válido; este caso se limita a tres áreas interiores no polares y conserva la falta de máscara de tierra/agua como limitación.

Se reconciliaron únicamente las dos entradas GMTED de `data/manifests/plan.json`: tamaños y hashes coincidían; 7,5″ figuraba como `downloaded`, y ambos quedan `verified_local` con `zip_crc=passed_all_members`. El estado previo se conserva en [la auditoría](../../evidencia-fase-4/auditoria-gmted.json) y el subconjunto conciliado en [manifiesto GMTED](../../evidencia-fase-4/manifiesto-gmted.json). No se alteraron entradas de otras fuentes. Estos son controles de identidad e integridad local, no autenticidad externa ni exactitud científica.

## 2. Dominio y método reproducible

La configuración es [busqueda-regional-v1.json](../../../specs/search/busqueda-regional-v1.json). Se generan centros cada **10 km** en una proyección AEQD por área y se conservan solo ventanas cuyos bordes densificados caben dentro del rectángulo geográfico. El paso evita solapamiento de las huellas medidas; deja espacios sin muestrear. No es una búsqueda exhaustiva ni global.

| Área | Bbox [oeste, sur, este, norte] | Ventanas nuevas | Huellas muestreadas | Área del rectángulo, aprox. |
|---|---|---:|---:|---:|
| Utah interior | [−111,5; 38; −109,5; 39,5] | 272 | 2448 km² · 8,46 % | 28 949 km² |
| Mojave interior | [−117,5; 34,5; −115,5; 36] | 278 | 2502 km² · 8,26 % | 30 290 km² |
| Atacama interior | [−69; −25; −67; −23] | 420 | 3780 km² · 8,39 % | 45 079 km² |

Las áreas se calculan con Geod/WGS84; el área del bbox usa sus vértices geodésicos como aproximación. Los tres controles se añaden en sus centros exactos, fuera de estos conteos: Utah y Atacama de fase 2 y Silver Lake de [la ficha de viabilidad](Ficha%20de%20viabilidad%20-%20primer%20caso.md). El punto Silver Lake es una referencia contextual de ensayos, sin comprobar equivalencia con una huella exacta ni considerarlo verdad de referencia.

Se usa una ventana de **3000 × 3000 m**, con agregaciones de **300 y 600 m** y base de pendiente de **600 y 1200 m**. El tamaño nativo nominal de GMTED 7,5″ es angular y varía físicamente con la latitud; aquí la celda métrica es mayor que ese paso nominal, sin atribuirle resolución efectiva. GMTED 30″ no se interpola para aparentar detalle de 300 m.

La referencia de Jezero se vuelve a calcular a estas escalas desde el DTM preservado. Antes de fijar la ventana se probaron 1800, 2400, 3000, 3600, 4200 y 4800 m. La ventana de 3000 m es la mayor probada con cobertura completa de elevación y pendiente a ambas escalas; a 3600 m la pendiente a 600 m baja a 94,44 %, por debajo del mínimo de 95 %. El [registro de selección](../../evidencia-fase-4/seleccion-de-ventana.json) conserva los resultados. Es una decisión medida para este experimento, no un tamaño universal óptimo.

El cálculo reutiliza las funciones de terreno de fase 2: promedio espacial de elevación, máscara 0/1 independiente que conserva nodata, aceptación solo con soporte completo (tolerancia 10⁻⁶) y diferencias centrales con centro y vecinos válidos. El margen de 600 m proporciona vecinos en el borde. Se guardan conteos, cobertura por variable, percentiles y relieve p95−p5. Las pendientes se comparan mediante Wasserstein en grados; la diferencia de relieve es candidata−Jezero en metros. No hay índice combinado ni porcentaje de similitud.

La referencia tiene 100/100 celdas válidas por variable a 300 m y 25/25 a 600 m; relieve de **111,303 m** y **97,284 m**, respectivamente. Estas celdas están correlacionadas. **No son las métricas del área de 1,8 km de fase 2**, que permanece intacta y accesible en otro recorrido.

## 3. Filtros, controles y hallazgos

Se requiere al menos 95 % de cobertura válida de elevación y pendiente en la ventana. Si no hay cobertura o métricas suficientes, la ventana se marca como insuficiente; no se presenta como una mala semejanza. Los tres perfiles son decisiones operativas exploratorias:

| Perfil | Distancia de pendientes máxima | Diferencia absoluta de relieve máxima |
|---|---:|---:|
| Estricto | 1° | 30 m |
| Base | 2° | 60 m |
| Amplio | 4° | 120 m |

Las dos condiciones se aplican por separado y de forma inclusiva. No fueron calibradas con pares de análogos revisados por expertos. La interfaz permite incluir ventanas que quedan fuera del filtro, con sus motivos, y cambiar de perfil sin recalcular rásteres.

| Área | Celda | Estricto | Base | Amplio | Total generado |
|---|---:|---:|---:|---:|---:|
| Utah | 300 m | 30 | 99 | 168 | 272 |
| Utah | 600 m | 52 | 126 | 191 | 272 |
| Mojave | 300 m | 50 | 128 | 217 | 278 |
| Mojave | 600 m | 67 | 149 | 227 | 278 |
| Atacama | 300 m | 47 | 136 | 277 | 420 |
| Atacama | 600 m | 70 | 149 | 282 | 420 |

No se encontraron celdas insuficientes en las ventanas de este barrido; eso describe disponibilidad numérica en este dominio, no precisión, observación directa ni cobertura de los espacios entre ventanas. Los IDs y decisiones completas se conservan en [candidatas.json](../../evidencia-fase-4/candidatas.json).

**Los tres controles quedan fuera del perfil base a ambas escalas.** Utah excede la diferencia de relieve, aunque era la candidata más cercana en pendientes dentro del experimento de fase 2. Silver Lake también queda fuera y entra con el perfil amplio; Utah entra en ese perfil y Atacama sigue fuera por relieve. Esto demuestra que el filtro puede omitir sitios de interés contextual. No demuestra falsos negativos científicos: los centros, preguntas y ventanas no son etiquetas verdaderas de analogía, y fase 2 empleaba otra extensión y escala. Se muestran los controles incluso cuando no pasan.

### Evaluación de detalle bajo demanda

La ventana nueva **`utah-010-007`**, aproximadamente 38,914° N y −110,688° E, se evaluó con la tesela SRTM `N38W111.tif` ya disponible. Conserva una ventana de 3 km; la referencia y la candidata se calcularon de nuevo a 60 y 120 m. Su [registro de detalle](../../evidencia-fase-4/detalle/utah-010-007.json) incluye hashes, conteos y límites.

| Celda | Distancia de pendientes | Diferencia de relieve |
|---|---:|---:|
| 300 m · GMTED | 0,328° | −7,473 m |
| 600 m · GMTED | 0,411° | −10,052 m |
| 60 m · SRTM | 1,015° | −4,102 m |
| 120 m · SRTM | 0,742° | −4,193 m |

El detalle tiene 2500/2500 y 625/625 celdas válidas de pendiente y se identifica como **evaluación local exploratoria**. No hereda una validación de movilidad ni prueba que sea mejor análogo. Las demás ventanas conservan el estado de detalle pendiente; no se les asigna cero.

El plan de detalle calcula las teselas SRTM que cubren cada ventana y su margen. El comando usa originales locales, comprueba identidad de las copias conocidas de fase 2, y verifica CRS, dimensiones, paso, nodata y cobertura antes de generar métricas. Solo con `--download` obtiene archivos ausentes de las URLs propuestas de OpenTopography: máximo cuatro teselas y 50 MB por archivo, con descarga temporal y apertura antes de adoptarlo. Los nuevos hashes son identidad local, sin una firma remota. SRTM tiene límites de superficie radar, rellenos y datum documental ya descritos en fase 2. Las fuentes polares continúan fuera de este escenario no polar.

## 4. Uso, API y reproducción

Abrir [la aplicación](http://localhost:5173) y elegir **«Ampliar búsqueda · ventanas de 3 km»**. Se puede cambiar área, celda y perfil, incluir ventanas fuera del filtro, paginar, abrir una ventana o control y exportar el resultado como GeoJSON. Las fichas separan métricas regionales, detalle disponible, planes de adquisición y contexto geográfico. Al cambiar filtros se descarta la selección anterior; durante carga o error no se muestran resultados de otra consulta.

| Ruta | Contenido |
|---|---|
| `GET /api/regional-search` | Configuración, referencia, sensibilidad, controles, áreas muestreadas y evaluaciones locales disponibles. |
| `GET /api/regional-search/candidates` | Parámetros `area_id`, `cell_m`, `profile`, `include_excluded`, `offset`, `limit`; conteos y página de ventanas. |
| `GET /api/regional-search/candidates/{id}` | Geometría, ambas escalas, motivos por perfil y evaluación o plan de detalle. Incluye los tres controles. |
| `GET /api/regional-search/export` | GeoJSON de la selección; usa los mismos filtros. |
| `GET /api/regional-search/evidence/{filename}` | Lista cerrada de registros y manifiestos; sin originales ni acceso arbitrario a carpetas. |

La API lee la entrega revisada y verifica los hashes de configuración y catálogo. Los detalles se verifican contra su manifiesto y el hash del catálogo al que pertenecen. No procesa rásteres ni descarga datos en las consultas. Los filtros fuera del dominio se rechazan y una evidencia ausente o modificada genera 503. La escritura atómica es por archivo; todavía no hay publicación transaccional de todos los archivos ni manifiestos firmados.

Desde la raíz y con el entorno Pixi instalado:

```sh
# Verificar originales completos y reconciliar sus entradas de adquisición.
./.pixi/envs/default/bin/python scripts/buscar_candidatas.py audit

# Generar las ventanas y decisiones reproducibles; requiere auditoría previa.
./.pixi/envs/default/bin/python scripts/buscar_candidatas.py search

# Evaluar una ventana con el SRTM disponible.
./.pixi/envs/default/bin/python scripts/buscar_candidatas.py detail utah-010-007

# Para otra ventana sin teselas locales: añadir --download explícitamente.
# No se requiere ni se hizo ninguna descarga para la evaluación incluida.

make check
./.pixi/envs/default/bin/python -m unittest discover -s tests -v
```

`audit` debe ejecutarse cuando faltan sus registros o cambian las entradas. `search` vuelve a verificar los hashes completos de los ZIP y conserva los originales. Los recortes regionales y de detalle se guardan en `data/normalized/fase4/`, excluido de Git; los resultados legibles por la aplicación están en `docs/evidencia-fase-4/`. Repetir `search` con parámetros idénticos conserva el catálogo; un cambio exige revisar también los detalles asociados.

## 5. Verificación, coste y límites de salida

Se aprobaron **39 pruebas**: 17 de backend y 22 de análisis/adquisición. Incluyen límites de filtro y cobertura, cero válido y exterior sin dato, CRC/archivo truncado, geometrías y áreas de ventanas, ausencia de descarga implícita, concordancia con el catálogo, controles excluidos, detalle pendiente/evaluado, paginación, GeoJSON, parámetros inválidos, aislamiento de archivos y evidencia alterada. TypeScript/Vite y los CRS del entorno se comprobaron correctamente.

Una repetición final produjo el mismo SHA-256 para `candidatas.json`: **`3786f3de7b69b5813f70bcad6b13e01f6d8a27675af8e5c28c9d426b820a0d21`**. Esto incluye valores, geometrías, decisiones, controles y configuración. El tiempo de ejecución en `procesamiento.json` es variable. Véase [repetición](../../evidencia-fase-4/repeticion.json).

La última generación medida tardó aproximadamente **9,3 s**, incluyendo comprobación de hashes, referencia, recortes y métricas; excluye la auditoría CRC inicial y la evaluación de detalle. Los dos ZIP suman **3 196 766 805 bytes**; los tres recortes regionales ocupan **4 182 134 bytes**. No hubo peticiones de red ni extracción global en esa ejecución. Son medidas locales de este dominio, no un benchmark de memoria ni una estimación fiable de un barrido global. La configuración limita el lote a 1500 ventanas y el programa impone un techo de 5000; antes de ampliar el dominio se necesitan otro presupuesto y una revisión del muestreo y de las fuentes.

Se cumple el criterio de salida para una búsqueda **acotada** fuera del catálogo inicial, con cobertura, sensibilidad, controles y pendientes explícitos. La escala efectiva, la procedencia por píxel, las máscaras de agua/interpolación, la exactitud física local y la validación experta siguen pendientes. Tampoco se integró soporte lunar, fuentes polares, ML ni procesamiento global. Los originales y los 47 archivos del manifiesto de fase 2 permanecen preservados.

La revisión interactiva y la captura de la aplicación se registran en [evidencia de fase 4](../../evidencia-fase-4/README.md).
