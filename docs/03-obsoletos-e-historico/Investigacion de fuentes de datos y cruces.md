# Investigación de fuentes de datos y cruces para análogos planetarios

**Proyecto:** plataforma de búsqueda y exploración de análogos terrestres de la Luna y Marte  
**Fecha de consulta:** 4 de noviembre de 2026  
**Estado:** investigación y propuesta inicial; los productos concretos, su cobertura local y sus condiciones deben comprobarse antes de integrarlos.  
**Documento relacionado:** «Arquitectura y estrategia de implementacion.md».

## 1. Alcance y conclusiones

La vía más sólida para una primera versión es comparar **relieve a una escala común**, complementado por imágenes y mapas geológicos para contextualizar los resultados. Las variables térmicas y mineralógicas pueden enriquecer una segunda iteración, siempre que se documenten sus métodos de obtención. El agua, el hielo y la factibilidad terrestre son relevantes para determinadas misiones, pero no constituyen un criterio universal.

La comparación debe responder a una actividad: un sitio puede ser útil para probar navegación sobre pendientes y no ser un buen análogo mineralógico o térmico. Las fuentes de abajo son candidatas para construir perfiles, entrenar modelos o evaluarlos; su inclusión no demuestra que ya sean compatibles ni que una región concreta tenga datos suficientes.

**Clases de evidencia:** O = observación o producto calibrado; D = derivado físico; I = indicador indirecto o interpretación; R = referencia de campo o etiqueta. Estas clases describen el uso propuesto y no reemplazan la documentación de cada producto. **Prioridad:** P1 = primer prototipo; P2 = ampliación; P3 = investigación especializada.

## 2. Inventario por dimensión

### 2.1 Relieve, morfología y movilidad

| Fuente y producto | Cuerpo; clase; prioridad | Cobertura / resolución y acceso | Uso y límites |
|---|---|---|---|
| [SRTM 1 arc-second](https://www.usgs.gov/faqs/where-can-i-get-global-elevation-data) | Tierra; D; P1 | Aproximadamente 30 m en el ecuador; no cubre toda la zona polar. EarthExplorer, registro gratuito. | Pendiente, rango de elevación y rugosidad. Es una representación de superficie derivada de radar y puede reflejar vegetación o estructuras; revisar vacíos y rellenos. |
| [ASTER GDEM v3](https://www.usgs.gov/faqs/where-can-i-get-global-elevation-data) | Tierra; D; P1 | 1 segundo de arco; AppEEARS o EarthExplorer. | Alternativa o contraste de SRTM; no mezclar ambos sin controlar artefactos, sesgos y calidad local. |
| [3DEP](https://www.usgs.gov/faqs/what-types-elevation-datasets-are-available-what-formats-do-they-come-and-where-can-i-download) | Tierra; D/O; P2 | Estados Unidos y territorios; modelos de 1–30 m según disponibilidad, además de fuentes lidar; descarga gratuita. | Evaluación local detallada y degradación controlada a escala planetaria. Su cobertura no es global y el detalle fino no debe filtrarse a una comparación de resolución gruesa. |
| [LOLA GDR / SLDEM2015](https://pds-geosciences.wustl.edu/missions/lro/lola.htm) | Luna; D; P1 | Productos PDS de varias resoluciones; SLDEM2015 combina LOLA y Kaguya entre 60° S y 60° N. | Pendientes y relieve regional. Elegir tesela y versión; leer etiquetas PDS, referencia y escala. GDR y SLDEM tienen construcción y cobertura distintas. |
| [MOLA MEGDR](https://pds-geosciences.wustl.edu/missions/mgs/megdr.html) | Marte; D; P1 | Global, 4–128 píxeles por grado y productos polares; PDS4. | Comparación de relieve regional. A 128 píxeles/grado el tamaño este-oeste cambia con la latitud y, cerca del ecuador, es de unos 463 m/píxel; no resuelve rocas ni obstáculos pequeños. La capa de recuentos ayuda a evaluar soporte. |
| [Mars Express HRSC](https://pds-geosciences.wustl.edu/tools/default.htm) | Marte; D/O; P2 | Productos regionales y archivo de la misión; consultar cobertura, proyección y resolución del modelo elegido. | Modelos de elevación de mayor detalle para sitios específicos y validación multiescala. No asumir que todas las escenas tienen un DEM estéreo utilizable. |

Una pendiente calculada con un DEM de centenares de metros representa inclinación a esa escala: no caracteriza directamente la seguridad de un rover ni el tamaño de los obstáculos. La resolución de salida de una rejilla no equivale necesariamente a la resolución efectiva de sus observaciones.

### 2.2 Imágenes y propiedades de superficie

| Fuente y producto | Cuerpo; clase; prioridad | Cobertura / acceso | Uso y límites |
|---|---|---|---|
| [HLS HLSL30 y HLSS30](https://hls.gsfc.nasa.gov/data-access-and-tools/) | Tierra; O/D; P1 | Reflectancia de Landsat y Sentinel-2 armonizada en rejilla de 30 m; COG; Earthdata Login. [Ficha técnica](https://www.earthdata.nasa.gov/s3fs-public/2022-05/SNWG_HLSFactSheet_0.pdf). | Contexto de superficie, máscaras y parches para modelos terrestres. Filtrar nubes, sombras, nieve o vegetación según objetivo. HLS no convierte bandas terrestres en equivalentes de sensores lunares o marcianos. |
| [Landsat Collection 2 Level-2](https://www.usgs.gov/landsat-missions/landsat-collection-2-level-2-science-products) | Tierra; D; P2 | Reflectancia y temperatura superficial, según escena, en EarthExplorer. | Complemento temporal y térmico. Aplicar factores de escala y QA del producto, y verificar disponibilidad. |
| [LROC](https://pds-geosciences.wustl.edu/missions/lro/) | Luna; O/D; P1 | Imágenes y mosaicos; búsqueda mediante Planetary Image Atlas; resolución y cobertura dependen del producto. | Contexto morfológico y datos para visión; documentar iluminación y geometría. Imágenes aisladas no son modelos de elevación. |
| [CTX y HiRISE](https://pds-geosciences.wustl.edu/missions/mro/) | Marte; O/D; P1/P2 | Imágenes regionales, búsqueda en Mars ODE; HiRISE ofrece gran detalle pero cobertura localizada. | CTX para contexto y parches; HiRISE para inspección detallada y etiquetas donde exista cobertura. Comparar texturas únicamente tras controlar escala e iluminación. |
| [THEMIS](https://pds-geosciences.wustl.edu/missions/odyssey/themis.html) | Marte; O/D; P2 | Imágenes visibles y térmicas; consulta por Mars Image Explorer; la escala depende del modo y producto. | Morfología y contexto térmico. No confundir radiancia, temperatura derivada e inercia térmica. |

### 2.3 Geología y minerales

| Fuente | Cuerpo; clase; prioridad | Cobertura / acceso | Uso y límites |
|---|---|---|---|
| [OneGeology](https://portal.onegeology.org/) y servicios geológicos nacionales, por ejemplo [USGS Geologic Map of North America](https://www.usgs.gov/centers/geology-energy-and-minerals-science-center/science/geologic-map-north-america) | Tierra; I; P2 | Catálogos y mapas según país; escalas, licencias y leyendas variables. | Identificar unidades volcánicas, sedimentarias o de impacto. Usar la leyenda y escala de cada fuente; ausencia de unidad no equivale a ausencia de material. |
| [Unified Geologic Map of the Moon v2](https://astrogeology.usgs.gov/search/map/Moon/Geology/Unified_Geologic_Map_of_the_Moon_GIS_v2/) | Luna; I; P2 | Global; escala 1:5 000 000; GIS; CC0 con cita solicitada. | Contexto regional y proporción de unidades dentro de una ventana. No identificar afloramientos pequeños a partir de un mapa global. |
| [Mapa geológico global de Marte, USGS SIM 3292](https://www.usgs.gov/maps/geologic-map-mars) | Marte; I; P2 | Global; mapas y descripción de unidades. | Contexto geológico y etiquetas débiles con control de escala; no se debe equiparar literalmente una unidad marciana a una unidad terrestre. |
| [Moon Mineralogy Mapper —M³—](https://pds-geosciences.wustl.edu/missions/chandrayaan1/) | Luna; O/D/I; P2 | Datos espectrales Chandrayaan-1 en PDS; cobertura y resolución dependen del modo y escena. | Indicadores espectrales y clasificación mineralógica con validación. Verificar correcciones, iluminación y calidad; una absorción no equivale por sí sola a una abundancia precisa. |
| [CRISM](https://pds-geosciences.wustl.edu/missions/mro/crism.htm) | Marte; O/D/I; P2 | Espectrometría visible-infrarroja; productos y modos diversos; PDS. | Minerales y alteración a partir de índices o productos interpretados; revisar cobertura, atmósfera y polvo. Los datos de cada modo no son homogéneos. |
| [USGS Spectral Library v7](https://data.usgs.gov/datacatalog/data/USGS%3A5807a2a2e4b0841e59e3a18d) | Laboratorio; R; P2 | Espectros de minerales, rocas y mezclas con metadatos y versiones remuestreadas. | Referencias para clasificación e investigación de respuesta espectral; no son etiquetas georreferenciadas ni reproducen automáticamente mezclas, iluminación y condiciones orbitales. |

### 2.4 Temperatura y propiedades termofísicas

| Fuente | Cuerpo; clase; prioridad | Cobertura / acceso | Uso y límites |
|---|---|---|---|
| [MOD11A2 MODIS](https://www.earthdata.nasa.gov/s3fs-public/2025-04/MOD11_User_Guide_V4.pdf) | Tierra; D; P2 | Temperatura superficial día/noche; compuestos de 8 días y rejilla de 1 km. Seleccionar colección vigente y QA. | Distribuciones estacionales y contexto; el compuesto de cielos despejados y la hora de paso no representan un ciclo diario completo. |
| [Landsat Collection 2 Level-2](https://www.usgs.gov/landsat-missions/landsat-collection-2-level-2-science-products) | Tierra; D; P2 | Temperatura superficial por escena; consultar resolución efectiva térmica y disponibilidad. | Contexto más localizado, con menos frecuencia; no equiparar el espaciado de la rejilla a la resolución del sensor. |
| [LRO Diviner GDR](https://pds-geosciences.wustl.edu/missions/lro/) | Luna; D; P2 | Productos de temperatura por observación o rejilla; revisar periodo, hora local y cobertura de cada producto. | Rangos térmicos y condiciones de sombra; no comparar una observación puntual con promedios terrestres sin armonizar condiciones. |
| [MGS TES Thermal Inertia Maps](https://pds-geosciences.wustl.edu/missions/mgs/tes-timap.html) | Marte; D/I; P2 | Mapas derivados de observaciones de 1999–2004; consultar versión y condiciones. | Indicador termofísico útil para investigar materiales. La inercia térmica es una propiedad inferida con supuestos de modelo, no una medición directa del tamaño de grano. |
| [THEMIS infrarrojo](https://pds-geosciences.wustl.edu/missions/odyssey/themis.html) | Marte; O/D; P2 | Imágenes térmicas por escena; selección por fecha y geometría. | Temperaturas o productos termofísicos cuando corresponda; distinguir las variables y evitar deducir composición de temperatura únicamente. |

**Advertencia:** temperatura superficial, temperatura del aire e inercia térmica son variables distintas. La Tierra, la Luna y Marte difieren en atmósfera, gravedad, insolación y duración del día; una coincidencia numérica puede ser irrelevante para el objetivo de la misión.

### 2.5 Agua, hielo y ambientes fríos

| Fuente | Cuerpo; clase; prioridad | Cobertura / acceso | Uso y límites |
|---|---|---|---|
| [MOD10A1 v6.1](https://nsidc.org/data/data-access-tool/MOD10A1/versions/61) | Tierra; D; P2 | Nieve diaria en rejilla de 500 m; NSIDC/Earthdata. | Persistencia de nieve y selección de ambientes fríos. Nieve superficial terrestre no representa automáticamente hielo enterrado planetario. Tratar nubes y QA. |
| [GLIMS / NSIDC](https://nsidc.org/data/explore-data) | Tierra; I/D; P2 | Inventarios de glaciares; fechas y completitud variables. | Contexto de hielo terrestre y clasificación de regiones; no asumir que el polígono refleja condiciones actuales. |
| [LRO LEND](https://pds-geosciences.wustl.edu/missions/lro/lend.htm) | Luna; O/I; P3 | Flujos de neutrones y productos derivados; PDS. | Evidencia indirecta relacionada con hidrógeno; depende de huella, profundidad de sensibilidad y modelo. No es un mapa de depósitos confirmados de hielo local. |
| [Mars Odyssey GRS / NS / HEND](https://pds-geosciences.wustl.edu/missions/odyssey/index.htm) | Marte; O/I; P3 | Productos de espectrometría y neutrones en PDS; huellas regionales grandes y variables. | Contexto de hidrógeno y posible hielo cercano a superficie bajo supuestos. Mantener soporte espacial original; no inferir hielo en una ventana menor que la huella. |
| [SHARAD y MARSIS](https://pds-geosciences.wustl.edu/tools/default.htm) | Marte; O/I; P3 | Sondeo radar por trayectorias; PDS/ESA, según instrumento. | Estructuras subsuperficiales e hipótesis de hielo; interpretación geofísica especializada, cobertura irregular y ambigüedad material. |

### 2.6 Factibilidad, observaciones de campo y referencias

| Fuente | Cuerpo; clase; prioridad | Uso y límites |
|---|---|---|
| [World Database on Protected Areas / Protected Planet](https://www.protectedplanet.net/en/thematic-areas/wdpa) | Tierra; I; P2 | Contexto de áreas protegidas y restricciones potenciales. Comprobar cobertura, fecha y condiciones de uso y redistribución; no sustituye permisos ni regulación local. Mantener separado de similitud física. |
| [OpenStreetMap](https://www.openstreetmap.org/copyright) | Tierra; O/I; P2 | Proximidad a caminos y asentamientos, como indicador de logística. Cobertura y calidad variables; ODbL y atribución según uso. Un camino cartografiado no garantiza acceso. |
| [USGS Terrestrial Analogs Data Portal](https://tadp.astrogeology.usgs.gov/) | Tierra; R; P1/P2 | Investigaciones de campo financiadas por NASA relevantes para ciencia planetaria. Localizar campañas con coordenadas, documentación y licencias adecuadas; un registro de campo no es por sí mismo un par etiquetado. [Directorio NASA](https://planetary.data.nasa.gov/find-data?combine=&field_data_repositories_target_id=All&order=title&sort=desc). |
| [NASA Planetary Analog Explorer](https://science.nasa.gov/solar-system/analog-explorer/) | Tierra y referencias planetarias; R; P1 | Ejemplos documentados de ambientes análogos para revisión humana y formulación de casos; no es un benchmark exhaustivo ni prueba de equivalencia para toda misión. |
| [Planetary Pits and Caves Analog Dataset](https://ti.arc.nasa.gov/dataset/caves/) | Tierra; O/R; P3 | Nubes lidar e imágenes de sitios análogos; útil para evaluar geometría local y visión 3D. Su página exige consentimiento escrito de autores para uso comercial o incorporación a una base mayor distribuida públicamente. |
| [NASA AI Astrobiology Training Sets](https://www.nasa.gov/ai-astrobiology/training-sets/) | Principalmente Tierra; R; P3 | Referencias para misiones astrobiológicas específicas; evaluar variables, permisos y curación. No asumir compatibilidad directa con imágenes orbitales. |

Los portales Earthdata y PDS son **catálogos y mecanismos de acceso**, no un dataset único. Para un producto concreto deben conservarse identificador, versión, archivo, licencia o condiciones de uso y fecha de consulta. Comprobar términos por colección, incluidos costos de cómputo, autenticación y derechos de redistribución; la procedencia gubernamental no implica por sí sola ausencia de condiciones.

## 3. Cruces prometedores y transformaciones

| Pregunta / cruce | Operación propuesta y resultado | Limitaciones y controles |
|---|---|---|
| **Movilidad regional:** SRTM o ASTER + LOLA o MOLA | Construir ventanas del mismo tamaño físico; agregar el DEM más detallado hasta una escala soportada por ambos, calcular pendiente, percentiles y relieve relativo; comparar distribuciones. | Comparar en cada cuerpo con su propio sistema de referencia; probar sensibilidad al método de agregación. El resultado describe pendientes regionales, no transitabilidad de un vehículo. |
| **Morfoestructura:** DEM + LROC/CTX/HLS | Corregistrar dentro de cada cuerpo; cruzar pendiente con textura o patrones de imagen para distinguir, por ejemplo, planicies y bordes de cráter. | Controlar nubes, sombras, ángulo solar y resolución. Fotografías de sensores distintos no son pares positivos por parecerse; probar si el modelo reconoce el sensor. |
| **Terreno volcánico:** mapa geológico + DEM + CRISM/M³ + biblioteca USGS | Cruzar unidad regional con relieve e indicadores espectrales. Construir etiquetas separadas de material, morfología y confianza. | Los polígonos geológicos pueden ser demasiado generales; usar espectros de biblioteca ajustados a respuesta de cada instrumento y validar mezclas. Mismo mineral no implica misma historia ni textura. |
| **Comportamiento térmico:** MODIS/Landsat + Diviner/THEMIS/TES | Extraer perfiles por hora local, estación, tipo de superficie y QA; comparar solo variables físicas equivalentes o perfiles explícitamente definidos. | No comparar MOD11A2 de 8 días con una escena individual como si midieran lo mismo; documentar atmósfera, muestreo y supuestos. No tratar inercia térmica como temperatura. |
| **Ambientes fríos:** MOD10A1/GLIMS + Diviner/LEND o GRS/radar | Determinar persistencia de nieve terrestre y superponer indicadores planetarios con temperatura y topografía a su propia escala; registrar cada indicador por separado. | La nieve visible, neutrones y radar miden cosas distintas. Hidrógeno no confirma hielo local; no remuestrear una huella de kilómetros a precisión ficticia. |
| **Entrenamiento y verificación:** TADP + DEM + imágenes + mapa geológico | Vincular registros de campo georreferenciados a ventanas satelitales y describir actividad, fecha, método y calidad de etiqueta. | Evaluar error de ubicación, diferencia temporal y representatividad; una muestra puntual no describe automáticamente toda la ventana. |
| **Selección operativa:** candidatos físicos + OSM + WDPA | Superponer geometrías terrestres y mostrar accesibilidad y protección como filtros o atributos independientes. | Comprobar fecha, cobertura y permisos de uso; no confundir factibilidad con similitud. |

### 3.1 Procedimiento de armonización

1. **Definir la pregunta y la unidad espacial.** Escoger región, tamaño físico y escala de características de interés. Mantener geometría y cuerpo; no realizar una unión espacial entre coordenadas terrestres y planetarias como si fueran el mismo territorio.
2. **Interpretar el producto.** Leer etiquetas y aplicar factores de escala, desplazamiento, unidades, valores inválidos y QA. Conservar la observación original. Por ejemplo, la [FAQ de LOLA](https://pds-geosciences.wustl.edu/missions/lro/lola_faq.htm) explica el factor y desplazamiento para sus GDR; se debe verificar la etiqueta del archivo específico antes de aplicarlos.
3. **Geometría.** Usar para cada cuerpo su radio/elipsoide, convención planetocéntrica o planetográfica, longitud este/oeste, dominio y referencia vertical. Reproyectar localmente en metros y corregistrar capas del mismo cuerpo; revisar polos y antimeridiano. Registrar error de alineación. No comparar elevaciones absolutas de cuerpos distintos sin modelo físico y referencia justificados.
4. **Soporte efectivo.** Elegir una escala objetivo que respete la resolución efectiva, huella y precisión del producto más grueso. Aplicar filtrado previo y agregación apropiada a variables continuas; para categorías usar proporciones de área o una regla documentada. Los indicadores de huella gruesa permanecen a esa escala. Calcular pendientes después de armonizar el DEM y, si es útil, conservar también resultados nativos por separado.
5. **Tiempo y condiciones.** Guardar fecha, estación, hora local, geometría y número de observaciones válidas; seleccionar comparaciones con soporte compatible. En Marte, cuando corresponda, registrar año marciano y longitud solar. No asumir que un sol equivale a un día terrestre.
6. **Calidad y cobertura.** Aplicar máscaras de nubes, sombras, errores y vacíos específicos. Conservar fracción válida y límites; «sin dato» es distinto de cero o de ausencia. Establecer umbrales por dimensión antes de evaluar resultados.
7. **Características y escalado.** Producir distribuciones y métricas con unidades; si se normalizan para ML, ajustar parámetros exclusivamente con entrenamiento y aplicarlos sin reajuste a validación y prueba. Documentar un esquema fijo, incluidas máscaras de datos faltantes.
8. **Trazabilidad y sensibilidad.** Guardar origen, versión, parámetros, código, escala, fecha y calidad de cada derivado. Repetir con alternativas razonables de remuestreo, ventana e incertidumbre para medir estabilidad.

## 4. Uso de los datos en entrenamiento y evaluación de modelos

### 4.1 Conjuntos propuestos

- **Entrada base:** ventanas topográficas de SRTM/ASTER y LOLA o MOLA, con elevación relativa y capas de pendiente a escala común, máscara de validez, escala y metadatos. Empezar con un solo destino y una sola escala.
- **Entrada visual opcional:** imágenes HLS y LROC o CTX recortadas por región y procesadas por separado; la compatibilidad geométrica dentro de cada cuerpo no garantiza compatibilidad espectral entre cuerpos.
- **Supervisión débil:** unidades geológicas e indicadores mineralógicos con fuente, confianza y límites. Mantener etiquetas geológicas planetarias y terrestres distintas hasta justificar una correspondencia por proceso o material.
- **Referencia humana:** construir una tabla propia con región terrestre, región planetaria cuando esté identificada, propósito de misión, dimensión que motiva el análogo, fuente, extensión, confianza y evaluador. TADP y Analog Explorer sirven para localizar candidatos; no todos sus registros constituyen pares precisos y balanceados.
- **Pruebas difíciles:** regiones visualmente parecidas pero geológicamente distintas, o geológicamente parecidas con relieve diferente. Estos son negativos condicionados a la misión, no «no análogos» universales. Incluir casos sin evidencia suficiente como desconocidos, no como negativos.

### 4.2 Estrategia experimental

1. Implementar primero una **línea base interpretable** con distancia entre distribuciones de pendiente, rugosidad y relieve relativo; registrar pesos, datos disponibles y escala.
2. Probar un modelo autosupervisado sobre parches topográficos enmascarados o representaciones terrestres preentrenadas; evaluar si el modelo acepta efectivamente las bandas y resolución disponibles. Un modelo terrestre como Prithvi no tiene validez planetaria garantizada.
3. Generar variantes de un mismo parche con perturbaciones físicamente justificadas para entrenamiento; no introducir cambios que alteren la variable que se desea preservar. La similitud de aumentos dentro de un cuerpo no proporciona por sí sola pares Tierra–Marte o Tierra–Luna.
4. Entrenar o adaptar una representación multimodal solo si existen suficientes registros alineados; incluir máscaras y calidad. Probar comparaciones con y sin imagen y con y sin cada dimensión.
5. Separar entrenamiento, validación y prueba **antes de cortar ventanas**, por regiones geográficas y con zonas de exclusión para impedir solapamiento y proximidad; mantener campañas, teselas relacionadas y datos aumentados en una sola partición. Reservar regiones y, de ser viable, sensores o provincias geológicas completos para evaluar generalización. No elegir regiones de prueba después de inspeccionar resultados.
6. Con revisión experta y pares pertinentes a la misión, medir recuperación top-k, precisión o recall cuando proceda, además de cobertura y métricas por dimensión. Reportar tamaño de muestra e incertidumbre; sin un conjunto de relevancia suficiente, reportar exploración cualitativa y no presentar cifras como validación definitiva.
7. Comparar la línea base, el embedding y la combinación híbrida en los mismos casos. Probar sensibilidad a escala, iluminación y producto; entrenar una prueba que intente predecir sensor o cuerpo desde el embedding para detectar atajos, interpretando su resultado junto con otras evidencias. Registrar casos fallidos y datos ausentes.

La similitud de un embedding es una señal de recuperación. No acredita mineralogía, transitabilidad ni adecuación a una misión. No usar imágenes comerciales o visuales como datos de entrenamiento sin verificar los derechos específicos; [Google Map Tiles API](https://developers.google.com/maps/documentation/tile/policies) impone restricciones que deben revisarse antes de cualquier uso analítico.

## 5. Primer experimento recomendado

**Escenario:** búsqueda de regiones terrestres para explorar morfología y pendientes regionales de una zona marciana; no pretende certificar un sitio para un rover.

1. Elegir una región de Marte con cobertura MOLA MEGDR y CTX, y al menos varias regiones terrestres con SRTM, cobertura HLS y algún caso documentado en TADP o Analog Explorer. Las regiones exactas quedan pendientes de comprobación; evitar elegir únicamente sitios famosos.
2. Descargar el producto MOLA de 128 píxeles/grado, sus etiquetas y recuentos; seleccionar y guardar teselas SRTM y metadatos. Registrar fecha, identificadores y cobertura real. Consultar si un DEM regional más detallado es necesario para una pregunta distinta.
3. Crear ventanas candidatas **de 10 × 10 km** como hipótesis inicial, no como escala validada. A 128 píxeles/grado MOLA equivale cerca del ecuador a unos 463 m por píxel: en 10 km habría aproximadamente 22 celdas por lado allí; el soporte efectivo y la longitud de celda cambian según ubicación. Revisar si la cantidad y calidad de observaciones sustentan las métricas antes de aceptar la ventana.
4. Reproyectar cada zona en un sistema local del cuerpo respectivo; filtrar y agregar SRTM hasta una resolución comparable, guardar máscara y fracción válida. Calcular pendiente y percentiles de relieve relativo después de la agregación, usando el mismo procedimiento y unidades.
5. Clasificar candidatos mediante la línea base física; conservar el desglose y presentar CTX/HLS solo como contexto. Revisar fuentes de error y probar tamaños de ventana y rejilla alternativos.
6. Separar regiones completas para prueba, elaborar un pequeño conjunto de relevancia por misión con expertos y comparar recuperación física con una representación aprendida cuando existan datos suficientes. Con pocas etiquetas, limitar la conclusión a casos exploratorios.
7. Entregar fichas con fuentes, mapas, escala, métricas, datos faltantes, sensibilidad y limitaciones. Una coincidencia de relieve regional no permite inferir rocas individuales ni movilidad real.

**Criterios de avance:** lectura reproducible y correcta de productos; cobertura suficiente documentada; comparación físicamente interpretable; resultados estables ante variantes razonables; revisión humana de ejemplos y ausencia de afirmaciones que excedan la resolución. Los umbrales concretos se acordarán tras explorar calidad y disponibilidad, antes de comparar modelos.

## 6. Esquema mínimo del catálogo

```text
region_id, cuerpo, geometria, sistema_referencia, referencia_vertical
producto_id, proveedor, instrumento, version, enlace, fecha_acceso
observacion_inicio, observacion_fin, hora_local, condiciones_observacion
variable, unidad, clase_evidencia, resolucion_nominal, soporte_efectivo
cobertura_valida, mascara_calidad, incertidumbre, restricciones_uso
transformaciones, parametros, version_codigo, fuentes_derivacion
ventana_metros, escala_analisis, estadisticas, limitaciones
```

Para asociaciones y etiquetas añadir `region_referencia`, `region_candidata`, `mision`, `dimension`, `tipo_relacion`, `fuente`, `confianza` y `revisor`. Mantener por separado fuentes observadas, productos derivados y resultados de modelos. Las resoluciones, fechas y licencias deben estar en el registro del producto exacto, no inferirse solo de esta lista.

## 7. Decisiones pendientes y próximos pasos

- Seleccionar destino, región de referencia, actividad y escala de misión; verificar cobertura real en los catálogos antes de descargar.
- Elegir si el primer experimento requiere más detalle que el producto MOLA global; de ser así, localizar un DEM estéreo regional y verificar su cobertura y precisión.
- Determinar qué expertos pueden revisar pares y negativos, y qué evidencia basta para una evaluación inicial.
- Confirmar identificadores, versiones, formato, condiciones de uso y costos para cada colección seleccionada; probar acceso y lectura con un área pequeña.
- Documentar los umbrales de calidad y cobertura y las reglas para dimensiones ausentes antes de producir una clasificación.

Esta investigación se apoya en las páginas oficiales enlazadas junto a cada producto. Las propuestas de combinación, prioridades y experimentos son inferencias de diseño para este proyecto, sujetas a prueba con datos reales.
