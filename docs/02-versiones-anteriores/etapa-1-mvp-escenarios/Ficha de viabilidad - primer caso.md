# Ficha de viabilidad — primer caso

**Fecha de evaluación:** 6 de noviembre de 2026, America/Managua. Las consultas realizadas después de las 00:00 UTC del día 7 corresponden todavía al día 6 local.  
**Decisión:** avanzar a la fase 2 para verificar y analizar **Jezero–Utah** a escala regional. No se ha demostrado similitud entre estos sitios.  
**Audiencia:** equipo del proyecto que seleccionará datos y preparará el primer análisis reproducible.  
**Antecedente:** [plan orientado a escenarios](Plan%20de%20implementacion%20orientado%20a%20escenarios.md). La selección siguiente sustituye únicamente la ventana provisional para el nuevo experimento; no modifica el catálogo de la aplicación.

## 1. Pregunta, propósito y dimensiones

**¿Qué áreas terrestres presentan características de terreno comparables con un sector documentado de Jezero, a una escala respaldada por los datos?**

El propósito inmediato es caracterizar diferencias de pendiente y relieve para orientar investigaciones relacionadas con navegación robótica. No se modela un vehículo, una ruta ni sus límites mecánicos. La meta del producto continúa siendo encontrar análogos multidimensionales según el escenario: la disponibilidad inicial de topografía no convierte las demás dimensiones en irrelevantes.

| Dimensión | Papel en este caso | Evidencia necesaria | Viabilidad encontrada |
|---|---|---|---|
| Pendiente y relieve relativo | Esencial para la primera comparación | Elevación, geometría, máscara válida y método a escala física común | Viable para un experimento regional Jezero–Utah; calidad y cobertura completas se comprobarán antes del cálculo. |
| Geología y materiales superficiales | Complementaria ahora; esencial si se quiere interpretar comportamiento del suelo | Cartografía y/o mediciones de composición con ubicación y escala | Hay una referencia geológica marciana; no se verificó una correspondencia de materiales con los polígonos terrestres. Pendiente. |
| Propiedades térmicas | Complementaria para futuras pruebas de instrumentos u operaciones | Misma magnitud física, unidades, hora local, estación y calidad | Se localizaron colecciones candidatas; no productos locales comparables. Temperatura e inercia térmica permanecen separadas. |
| Rocas y textura superficial | Necesaria para estudiar obstáculos, fuera de las métricas regionales elegidas | Imágenes de detalle, escala efectiva, sombras y un método validado de detección | Ortoimágenes específicas en Jezero; falta verificar imágenes terrestres de detalle. No hay estimación de obstáculos. |
| Polvo y procesos eólicos | Complementaria; puede afectar sensores y superficie | Observaciones temporales, indicadores y su interpretación física | Sin productos locales seleccionados. No inferir polvo de un color o de un DEM. |
| Agua o hielo | No es filtro esencial en esta pregunta | Evidencia específica y temporal de agua/hielo si otro escenario lo exige | Sin comparación seleccionada. Un antiguo ambiente lacustre no demuestra agua actual ni equivalencia ambiental. |

Las decisiones de viabilidad son inferencias de este proyecto. La evidencia y sus límites se detallan abajo; ninguna ausencia se interpreta como similitud ni como valor cero.

## 2. Áreas seleccionadas y fundamento

### Jezero: sector del abanico sedimentario

El centro del prototipo, 18,44° N, 77,45° E, era provisional. Se desplaza el nuevo experimento a **18,49° N, 77,41° E** para trabajar dentro del rectángulo de un DTM y sus ortoimágenes identificados. La selección está motivada por datos y contexto, no por una validación operativa del terreno.

El producto [DTEEC_002387_1985_003798_1985_A01](https://www.uahirise.org/dtm/PSP_002387_1985) identifica un abanico sedimentario en Jezero. Como referencia independiente del proveedor de ese DTM, [Bell et al. (2022)](https://pmc.ncbi.nlm.nih.gov/articles/PMC9683734/) documentan el contexto geológico y las observaciones de Perseverance en Jezero. Ese trabajo respalda el interés de la región, **no certifica el polígono definido aquí como área de pruebas**.

Se define una ventana nominal de **1,8 × 1,8 km**, aproximadamente 3,24 km². Sus vértices, en orden longitud este/latitud planetocéntrica, son:

```text
(77.3939850559, 18.4748097438)
(77.4260149441, 18.4748097438)
(77.4260177838, 18.5051889096)
(77.3939822162, 18.5051889096)
(77.3939850559, 18.4748097438)
```

La geometría completa está en [areas-marte.json](../../evidencia-fase-1/areas-marte.json). Usa la esfera local del producto, radio 3 394 839,8133163 m, latitud planetocéntrica y longitud positiva al este. **No es una geometría terrestre EPSG:4326**. El análisis deberá conservar esa distinción.

El rectángulo declarado por el DTM y la ortoimagen C comprende longitudes 77,34394372–77,466254° E y latitudes 18,392143429723–18,588734996352° N. Los cuatro vértices quedan dentro de la extensión ráster comprobada por GDAL. Esto acredita contención geométrica; no acredita una máscara válida completa ni ausencia de artefactos internos.

### Candidatas terrestres

Los tres polígonos, también nominalmente de 1,8 km de lado, se conservan en [areas-tierra.geojson](../../evidencia-fase-1/areas-tierra.geojson), en WGS84, orden longitud/latitud. Sus esquinas se construyeron mediante destinos geodésicos a 900√2 m del centro, con rumbos 225°, 135°, 45° y 315°. Se propone un tamaño común pequeño para la prueba; no se afirma que sea el tamaño óptimo de una misión.

| Sitio y centro | Evidencia y pertinencia | Decisión |
|---|---|---|
| Atacama: −23,8°, −67,9° | SRTM local contiene todo el polígono y 3717/3717 centros de píxel examinados tienen elevación válida. NASA documenta [pruebas ARADS en Atacama](https://www.nasa.gov/image-article/tire-tracks-mars-atacama-rover-astrobiology-drilling-studies/), pero no se verificó que este polígono corresponda a esas pruebas. No se seleccionó un DTM local de mayor detalle. | Candidata secundaria y contraste regional; no etiquetarla como sitio ARADS. |
| Utah: 38,6°, −110,6° | SRTM local contiene el polígono y 4425/4425 centros de píxel examinados son válidos. Además, se verificaron catálogo, XML y georreferencia de una tesela 3DEP de 1 m que lo contiene. No se verificó un ensayo de rover en este polígono. | Primera candidata por disponibilidad verificable y posibilidad de ampliar el detalle, no por ser la más parecida. |
| Mojave/Silver Lake: 35,35°, −116,10° | La [referencia NASA NTRS 20110011444](https://ntrs.nasa.gov/citations/20110011444) documenta ensayos astronauta–rover en Silver Lake. Se seleccionó una tesela 3DEP que contiene el polígono. La [descripción del equipo FIDO](https://wufs.wustl.edu/fido/d_silverlake.htm) proporciona contexto lacustre y de materiales. No se ha demostrado que este cuadrado coincida con la huella exacta de los ensayos. | Tercera candidata, fuera del catálogo actual; referencia contextual para una ampliación con 3DEP. |

Los conteos SRTM describen valores disponibles del modelo, incluidos posibles rellenos; no son conteos de observaciones radar independientes. No se ha ordenado científicamente a las candidatas.

## 3. Productos identificados

Todos los registros siguientes fueron consultados el 6 de noviembre local. Enlaces, respuestas HTTP y hashes se encuentran en el [registro de evidencia](../../evidencia-fase-1/README.md). Las cabeceras parciales no son rásteres completos utilizables para el análisis.

### J-DTM: elevación HiRISE de Jezero

- **Identidad:** `DTEEC_002387_1985_003798_1985_A01`, versión de producto 1.0; conjunto `MRO-M-HIRISE-5-DTM-V1.0`; productor University of Arizona. [Archivo IMG](https://www.uahirise.org/PDS/DTM/PSP/ORB_002300_002399/PSP_002387_1985_PSP_003798_1985/DTEEC_002387_1985_003798_1985_A01.IMG), [etiqueta extraída](../../evidencia-fase-1/jezero-dtm-etiqueta.txt).
- **Magnitud y lectura:** elevación derivada por estéreo, metros sobre la superficie equipotencial Mars 2000 según la etiqueta; Float32 little-endian, factor 1 y desplazamiento 0. `MISSING_CONSTANT=16#FF7FFFFB#`, leído por GDAL como aproximadamente −3,402822655×10³⁸.
- **Geometría:** 6934 columnas × 11538 filas; equirectangular, paralelo estándar 15°, meridiano central 77,41°. `MAP_SCALE=1.0096476466229 m/píxel`. El paso de la cuadrícula no establece la resolución efectiva ni la precisión vertical local.
- **Tiempo:** imágenes fuente [PSP_002387_1985](https://www.uahirise.org/PSP_002387_1985), 29/01/2007, y [PSP_003798_1985](https://www.uahirise.org/PSP_003798_1985), 19/05/2007. La etiqueta inspeccionada no indica fecha de creación del DTM.
- **Verificación:** 17 franjas sistemáticas suman 30 872 muestras, todas finitas, distintas de nodata y dentro del intervalo válido declarado. Se descargaron 123 488 bytes para ese muestreo, además del prefijo de 65 536 bytes. Las franjas incluyen píxeles de borde del rectángulo envolvente: **no representan una medición de cobertura válida total del polígono**. Véase [jezero-muestreo.json](../../evidencia-fase-1/jezero-muestreo.json).
- **Calidad y uso:** falta revisar completamente costuras, interpolaciones y otros artefactos, y cuantificar incertidumbre local. La [documentación del productor](https://www.uahirise.org/dtm/about.php) advierte que esos defectos pueden existir; no se afirma que estén presentes aquí. La [política HiRISE](https://www.uahirise.org/media/usage.php) permite uso de imágenes y solicita atribución. Conservar además los metadatos del DTM y revisar su documentación de distribución antes de redistribuirlo; no se encontró una licencia independiente en su etiqueta.

### J-IMG: ortoimágenes específicas, separadas del DTM

`PSP_002387_1985_RED_C_01_ORTHO`, versión 1.0, es una ortoimagen RED JPEG2000 con [etiqueta](../../evidencia-fase-1/PSP_002387_1985_RED_C_01_ORTHO.LBL) y [archivo JP2](https://www.uahirise.org/PDS/DTM/PSP/ORB_002300_002399/PSP_002387_1985_PSP_003798_1985/PSP_002387_1985_RED_C_01_ORTHO.JP2). Su etiqueta declara la misma extensión y paso de 1,0096476466229 m que el DTM; contiene 6934 × 11538 muestras. Su magnitud es intensidad/flujo, no elevación: `I/F = DN × 0.0002616083304924 + 0.0598125686258066`. Nulo 0 y códigos de saturación requieren tratamiento específico. Solo se descargó la etiqueta; la fracción válida de imagen está pendiente.

La variante `PSP_002387_1985_RED_A_01_ORTHO`, versión 1.0, tiene [etiqueta propia](../../evidencia-fase-1/PSP_002387_1985_RED_A_01_ORTHO.LBL) y [JP2 propio](https://www.uahirise.org/PDS/DTM/PSP/ORB_002300_002399/PSP_002387_1985_PSP_003798_1985/PSP_002387_1985_RED_A_01_ORTHO.JP2); declara 0,25241191165571 m/píxel y 27733 × 46148 muestras. Esta escala de imagen **no pertenece al DTM**. No se descargó la imagen ni se verificó su máscara válida. Ambas variantes derivan de la observación del 29/01/2007 y sirven inicialmente para inspección contextual; no se derivan rocas ni composición a partir de ellas en esta fase.

### A-SRTM y U-SRTM: elevación terrestre disponible

| Registro | Producto específico | Geometría y muestra examinada |
|---|---|---|
| A-SRTM | [`S24W068.tif`](https://opentopography.s3.sdsc.edu/raster/SRTM_GL1/SRTM_GL1_srtm/S24W068.tif) | 3601 × 3601; centros extremos −68 a −67° y −24 a −23°; 3717 centros dentro del polígono, todos válidos. |
| U-SRTM | [`N38W111.tif`](https://opentopography.s3.sdsc.edu/raster/SRTM_GL1/SRTM_GL1_srtm/N38W111.tif) | 3601 × 3601; centros extremos −111 a −110° y 38 a 39°; 4425 centros dentro del polígono, todos válidos. |

Son GeoTIFF Int16, EPSG:4326 horizontal, paso 1/3600°, `AREA_OR_POINT=Point`, nodata −32768. La conversión de segundos de arco a metros depende de la latitud; no se asume un píxel cuadrado de 30 m en ambos sitios. Los bordes completos, CRS y máscaras examinadas constan en [auditoria-local.json](../../evidencia-fase-1/auditoria-local.json).

La [colección del distribuidor](https://portal.opentopography.org/raster?jobId=rt1674642591184) describe SRTM GL1, versión 3 con rellenos, y adquisición del 11–22/02/2000. La versión concreta no está inscrita en las etiquetas TIFF locales: la asociación a esa colección procede del registro de descarga del proyecto. La referencia vertical EGM96 y las unidades en metros deben corroborarse con documentación del producto original; el TIFF no declara un CRS vertical. Es un derivado radar de superficie, no un DTM de suelo desnudo validado localmente.

No se midió exactitud ni se identificaron píxeles rellenados. El distribuidor exige reconocer la fuente y OpenTopography y muestra licencia no proporcionada; no se infiere una licencia de redistribución para estas copias. La [auditoría previa](../../03-obsoletos-e-historico/Auditoria%20de%20datos%20locales.md) conserva identidad y riesgos de los archivos.

### U-3DEP y M-3DEP: fuentes de detalle verificadas en metadatos

| Registro | Identificador de producto y enlace directo | Tiempo y referencia |
|---|---|---|
| U-3DEP | [`USGS_1M_12_x53y428_UT_FEMA_FS_FlamingGorge_2020_B20.tif`](https://prd-tnm.s3.amazonaws.com/StagedProducts/Elevation/1m/Projects/UT_FEMA_FS_FlamingGorge_2020_B20/TIFF/USGS_1M_12_x53y428_UT_FEMA_FS_FlamingGorge_2020_B20.tif); registro `65b9e4b5d34e18c6baf2ca59` | XML: adquisición 08/08–20/11/2020; publicación 05/01/2024. NAD83/UTM 12N, EPSG:26912; NAVD88 vertical según XML. |
| M-3DEP | [`USGS_1M_11_x58y392_CA_FEMALevee_D23.tif`](https://prd-tnm.s3.amazonaws.com/StagedProducts/Elevation/1m/Projects/CA_FEMALevee_D23/TIFF/USGS_1M_11_x58y392_CA_FEMALevee_D23.tif); registro `675905a7d34edfeb87103aa1` | XML: adquisición 25/05–15/06/2023; publicación 25/11/2024. NAD83/UTM 11N, EPSG:26911; NAVD88 vertical según XML. |

Ambos son modelos derivados de suelo desnudo por lidar, GeoTIFF Float32, 10012 × 10012, paso 1 m, nodata −999999. La escala publicada no equivale a exactitud de 1 m. No se encontró un número de versión independiente: se conservan nombre de proyecto, registro y fecha de publicación como identidad, sin inventarlo.

Las cuatro esquinas de cada polígono están dentro del rectángulo real de su TIFF, verificado mediante su geotransformación, no solo mediante el bbox del catálogo. Se conservaron XML, respuestas TNM y los primeros 65 536 bytes de cada TIFF. **No se leyó su máscara de píxeles ni se verificó cobertura válida**; la muestra de elevación examinada es cero, aunque el tamaño nominal del polígono permitiría aproximadamente 3,24 millones de celdas de 1 m. Eso no indica observaciones independientes.

El catálogo describe estos productos como dominio público. Los XML piden reconocer la fuente, documentar modificaciones y no atribuir aprobación del USGS. La exactitud horizontal/vertical remite a metadatos del proyecto original: sigue pendiente su revisión. Los detalles están en [auditoria-3dep.json](../../evidencia-fase-1/auditoria-3dep.json), [XML Utah](../../evidencia-fase-1/utah-1m.xml) y [XML Mojave](../../evidencia-fase-1/mojave-1m.xml). El nombre del proyecto de Utah no sustituye la comprobación geométrica realizada.

## 4. Matriz por sitio, variable y producto

Las filas heredan identidad, tiempo, formato, calidad y uso del registro de producto citado en la sección 3. Así se evita ocultar metadatos bajo una calificación única. La [matriz detallada en JSON](../../evidencia-fase-1/matriz-evidencia.json) conserva una entrada por sitio, variable y producto, además de entradas explícitas sin producto para las dimensiones pendientes. **Verificación** describe qué se inspeccionó; **comparabilidad** describe lo que permite proponer esa evidencia.

| Sitio | Variable | Producto | Cobertura y muestra | Método propuesto; unidad | Verificación / comparabilidad |
|---|---|---|---|---|---|
| Jezero | Pendiente | J-DTM | Contención geométrica; 30 872 muestras válidas en franjas; máscara total pendiente | Agregar elevación y después diferencias centrales; grados | Etiqueta y muestra verificadas / propuesta a 60 m, pendiente de QA completa. |
| Jezero | Relieve relativo | J-DTM | Igual evidencia, no conteo de celdas independientes | p95−p5 de elevación agregada; m | Etiqueta y muestra verificadas / propuesta a 60 m. |
| Atacama | Pendiente | A-SRTM | 3717/3717 centros válidos en el polígono nativo | Mismo procedimiento a 60 m; grados | Archivo y disponibilidad verificados / condicionada a referencia vertical, soporte y artefactos. |
| Atacama | Relieve relativo | A-SRTM | Igual cobertura | p95−p5; m | Archivo verificado / contraste secundario a 60 m. |
| Utah | Pendiente | U-SRTM | 4425/4425 centros válidos en el polígono nativo | Mismo procedimiento a 60 m; grados | Archivo verificado / primera comparación propuesta. |
| Utah | Relieve relativo | U-SRTM | Igual cobertura | p95−p5; m | Archivo verificado / primera comparación propuesta. |
| Utah | Pendiente | U-3DEP | Contención geométrica; valores válidos no inspeccionados | Posible análisis a 10 m tras verificar soporte; grados | Solo metadatos / aún no habilitada. |
| Utah | Relieve relativo | U-3DEP | Igual evidencia | p95−p5; m | Solo metadatos / aún no habilitada. |
| Mojave | Pendiente | M-3DEP | Contención geométrica; valores válidos no inspeccionados | Posible análisis a 10 m; grados | Solo metadatos / aún no habilitada. |
| Mojave | Relieve relativo | M-3DEP | Igual evidencia | p95−p5; m | Solo metadatos / aún no habilitada. |
| Jezero | Textura/rocas | J-IMG C | Extensión etiquetada; sin máscara válida ni detecciones | Inspección visual inicial; I/F, sin métrica de obstáculos | Etiqueta verificada / no comparable todavía con imágenes terrestres. |
| Jezero | Textura/rocas | J-IMG A | Extensión etiquetada; sin máscara válida ni detecciones | Inspección visual de mayor detalle; I/F, sin métrica de obstáculos | Etiqueta verificada / no atribuir su paso de imagen al DTM. |
| Jezero | Unidades geológicas | USGS SIM 3464, [registro específico](https://www.usgs.gov/maps/geologic-map-jezero-crater-and-nili-planum-region-mars) | Registro localizado; descarga directa devolvió 403; no se superpuso el GIS al polígono | Cartografía interpretada; categorías, no magnitud continua | Verificación local incompleta / sin correspondencia terrestre. |

### Matriz de vacíos para dimensiones complementarias

| Sitio(s) | Variable | Producto exacto y cobertura local | Fuente siguiente y condición para incorporar |
|---|---|---|---|
| Atacama, Utah, Mojave; pendiente por separado en cada sitio | Geología/materiales | Ninguno seleccionado; unidades, muestra y restricciones sin verificar | Localizar mapas o mediciones oficiales para cada polígono; justificar correspondencias por materiales/procesos. No usar el nombre del desierto como etiqueta de composición. |
| Atacama, Utah, Mojave; pendiente en los tres | Rocas/textura | Ninguna imagen terrestre específica verificada | Buscar ortoimágenes oficiales de detalle; verificar huellas, fecha, resolución efectiva y sombras antes de comparar con J-IMG. |
| Jezero | Temperatura e inercia térmica | Ningún producto local seleccionado; no hay muestra | [Productos THEMIS](https://viewer.mars.asu.edu/glossary/themis/dcs): identificar primero la magnitud y después escena, hora local, estación y QA. |
| Atacama, Utah, Mojave; pendiente en los tres | Temperatura superficial | Ninguna escena seleccionada; no se presume cobertura válida | [Landsat Collection 2 Surface Temperature](https://www.usgs.gov/landsat-missions/landsat-collection-2-surface-temperature): seleccionar escenas y revisar máscaras, emisividad y soporte térmico. |
| Los cuatro sitios | Polvo/procesos eólicos | Ningún producto seleccionado | Definir indicador y temporalidad; imágenes visualmente similares no bastan. |
| Los cuatro sitios | Agua/hielo | Ningún producto seleccionado | Investigar solo si el escenario lo requiere; mantener separado ambiente antiguo, agua actual e indicadores indirectos. |

La definición de producto térmico y las condiciones de observación impiden habilitar esta dimensión todavía. No se compara temperatura superficial terrestre con inercia térmica marciana. Los mapas geológicos se tratarán como interpretaciones; los DEM como derivados y las imágenes como observaciones procesadas.

## 5. Primer análisis recomendado para la fase 2

**Pareja inicial:** Jezero J-DTM y Utah U-SRTM. **Contraste adicional:** Atacama A-SRTM. Mojave y U-3DEP quedan como ampliaciones con inspección pendiente. La selección prioriza una prueba realizable, no una declaración de mejor análogo.

1. **Adquisición acotada y QA.** Obtener el recorte marciano con su etiqueta y margen de 240 m por lado, o conservar el archivo específico si el servicio obliga a descargarlo completo. El producto pesa aproximadamente 320 MB; no descargar otros DTM sin necesidad. Verificar identidad, lectura, máscara completa, límites y artefactos. Leer SRTM local con el mismo margen. Conservar originales y parámetros. No reutilizar recuentos MOLA para esta ruta.
2. **Escala y geometría.** Usar proyecciones métricas locales por cuerpo, explicitando su radio/elipsoide; definir una ventana cuadrada exacta de 1800 m centrada en cada área y conservar su geometría final. Las geometrías geodésicas de esta ficha son la selección de investigación. Agregar elevación a una cuadrícula de **60 m**, 30 × 30 celdas interiores. Es una hipótesis regional conservadora frente al paso angular de SRTM, no una resolución efectiva igualada ni un estándar de movilidad. No interpolar SRTM a 1 m.
3. **Máscaras.** Preservar nodata y códigos especiales; no rellenar huecos automáticamente. Documentar para cada celda objetivo la fracción de soporte válido. Para esta primera prueba utilizar solo celdas cuyo soporte de agregación sea completamente válido; una pendiente requiere centro y sus cuatro vecinos válidos. Informar pérdidas y conteos. Si el soporte resulta insuficiente, reformular área o escala antes de interpretar resultados, sin asignar similitud cero.
4. **Métricas.** Calcular pendiente después de agregar la elevación: `atan(hypot(dz/dx, dz/dy))`, diferencias centrales en metros y resultado en grados. Mostrar su distribución y percentiles 10, 50 y 90. Calcular relieve relativo `p95(z)−p5(z)` en metros, con percentiles lineales sobre celdas válidas. No comparar elevaciones absolutas entre Marte y Tierra ni combinar ambas métricas en un porcentaje de analogía.
5. **Comprobaciones previas y sensibilidad.** Verificar decodificación con valores de control y límites del producto; inspeccionar imagen/relieve sombreado, costuras y bordes. Ensayar pendiente sobre una superficie plana y un plano inclinado de pendiente conocida; verificar invariancia del relieve ante un desplazamiento vertical constante. Repetir a **120 m** sobre la misma ventana y explicar cambios. Informar cantidad de celdas válidas de elevación y de pendiente, además de la extensión física.
6. **Ampliación posterior.** Si se confirma calidad de U-3DEP/M-3DEP y soporte compatible con J-DTM, estudiar una comparación separada a 10 m y sensibilidad a 20 m. No mezclar sus resultados con los de 60 m. Antes de habilitar materiales, térmica u obstáculos, completar las filas pendientes de la matriz.

La discrepancia `.hdr`/PDS de MOLA documentada en la [auditoría local](../../03-obsoletos-e-historico/Auditoria%20de%20datos%20locales.md) continúa abierta. Los recuentos no deben reutilizarse hasta resolver tipo de dato y significado de cero. La lectura explícita que pueda hacer el script actual no corrige por sí sola las cabeceras ni valida la interpretación científica del soporte. Esta fase no alteró esos archivos ni regeneró el catálogo.

## 6. Cierre y condiciones para avanzar

**Avanzar a fase 2**, comenzando por QA completa del recorte Jezero–Utah antes de calcular métricas. Se cumple la viabilidad inicial: hay área marciana delimitada, producto específico con geometría y muestras verificadas y al menos una candidata terrestre con elevación verificable para la misma comparación regional. La cobertura válida marciana completa y la calidad científica aún no se dan por comprobadas.

| Control de salida | Resultado |
|---|---|
| Pregunta, audiencia y dimensiones | Definidas; dimensiones adicionales permanecen visibles. |
| Polígonos explícitos por cuerpo | Guardados con convenciones y tamaño físico. |
| Productos exactos y enlaces | DTM, dos ortoimágenes, dos SRTM y dos 3DEP identificados; fuentes aún no seleccionadas marcadas como tales. |
| Geometría frente a cobertura válida | Separadas; se conserva el tamaño y alcance de cada muestra. |
| Imagen frente a DTM | Paso de imagen de 0,2524 m separado del DTM de 1,00965 m. |
| Magnitudes compatibles | Pendiente con pendiente y relieve relativo con relieve relativo; comparabilidad propuesta, sujeta a QA. |
| Incertidumbre y límites | No se demuestra movilidad, seguridad, permisos de acceso, equivalencia ambiental ni similitud efectiva. |
| Trazabilidad | Etiquetas, respuestas de catálogo, prefijos, franjas, auditorías y manifiesto local disponibles. Los hashes acreditan identidad local, no exactitud científica. |
| Reglas del evento | Pendientes: no se proporcionó edición/reto específico. No bloquean esta investigación documental; revisar antes de presentar o redistribuir. |

Si la QA de fase 2 invalida el DTM o encuentra artefactos dominantes, se reformulará el polígono dentro de productos verificados y se repetirá la comprobación; no se sustituirá silenciosamente por MOLA ni se supondrá detalle ausente. El siguiente trabajo autorizado por esta ficha es el análisis reproducible acotado, sin cambios todavía en API, interfaz ni puntuación del prototipo.
