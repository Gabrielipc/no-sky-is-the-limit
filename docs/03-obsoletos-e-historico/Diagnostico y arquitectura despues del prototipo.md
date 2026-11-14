# Del prototipo a una plataforma de análogos planetarios

**Fecha:** 5 de noviembre de 2026  
**Estado:** diagnóstico de la prueba de concepto y propuesta de trabajo; no es una validación científica ni un diseño definitivo.  
**Alcance:** primera búsqueda Tierra–Marte basada en relieve, evolución hacia otras dimensiones y visualización geoespacial. Complementa, y cuando corresponda actualiza, la propuesta de `Arquitectura y estrategia de implementacion.md`.

## 1. Conclusión principal

La prueba demuestra que es posible recorrer un flujo completo con datos reales: descargar elevación, preparar tres ventanas, calcular dos métricas, clasificarlas mediante una API y representarlas sobre dos globos. **No demuestra todavía que la clasificación identifique análogos útiles para una misión**, que los datos estén científicamente armonizados ni que el sistema pueda operar a escala global.

El riesgo más importante no es elegir un motor 3D o procesar muchos archivos: es producir comparaciones que parezcan precisas aunque las observaciones tengan distinta resolución, cobertura, procedencia o significado. La arquitectura debe permitir inspeccionar esas diferencias y limitar las conclusiones antes de optimizar o añadir ML.

### Recomendación

Construir primero un producto vertical acotado: **un caso de uso de relieve Tierra–Marte**, con un catálogo regional más amplio, procesamiento reproducible, medidas de calidad y una comparación revisable por expertos. Una vez comprobada esa base, ampliar dimensiones y cuerpos de manera incremental. Mantener el procesamiento científico separado de los productos visuales y de la API interactiva.

## 2. Qué se comprobó y qué no

| Aspecto | Evidencia de la prueba | Conclusión y límite |
|---|---|---|
| Ingesta | Se descargaron una tesela MOLA de topografía, recuentos y metadatos; dos teselas SRTM para Atacama y Utah. | Hay una ruta viable para un conjunto pequeño. No se probó ingesta masiva, actualización, cobertura global ni todos los productos. |
| Preparación | Tres ventanas de 10 × 10 km, cuadrícula de 500 m; pendiente media y diferencia P95−P5; SHA-256 de entradas. | La ejecución es repetible en el entorno probado, pero aún no hay validación científica independiente ni análisis de sensibilidad. |
| Dato delicado | La primera lectura MOLA interpretó mal el orden de bytes y produjo valores absurdos; se corrigió antes de publicar el catálogo. | La lectura de formatos y metadatos necesita controles automáticos y pruebas contra valores de referencia; que un archivo abra no garantiza que sus números sean correctos. |
| Consulta | FastAPI devuelve el catálogo y ordena candidatos con ponderaciones y desglose. | Funciona para tres registros; no valida las escalas 10°/300 m, la relevancia de los resultados ni el rendimiento con un catálogo real. |
| Visualización | Dos globos, fondos globales, controles y cuadrículas generadas a partir de elevación. En las capturas del usuario se aprecia la cuadrícula de Utah y un fondo verde uniforme en el visor de Marte. | La capa terrestre se observó en la captura. La cuadrícula de Marte no se ve en esa captura; su causa no está confirmada y requiere una prueba interactiva. No debe tratarse como verificada de extremo a extremo. |
| Calidad de observación | Para Jezero el prototipo muestra 100 % de celdas de elevación disponibles, pero aproximadamente 44 % con recuento MOLA > 0 tras remuestreo por vecino más cercano. | Son dos indicadores diferentes. El 44 % es una aproximación en la cuadrícula de salida, no un porcentaje validado de observaciones independientes ni una medida completa de calidad. |
| Validación visual | Se verificaron compilación, archivos HTTP y consistencia numérica, pero no se completó la inspección visual automatizada de ambos globos. | Las capturas aportan evidencia parcial; faltan pruebas de navegación, alineación y renderizado en equipos reales. |

**No confundir:** datos reales de entrada ≠ métricas científicamente validadas ≠ candidatos recomendados para una misión.

## 3. Inventario de cuellos de botella

| Prioridad | Problema | Evidencia / riesgo actual | Primera respuesta |
|---|---|---|---|
| Crítica | Comparabilidad y resolución efectiva | MOLA se interpola a 500 m y SRTM se agrega; compartir malla no implica tener el mismo soporte ni precisión. | Caracterizar productos, definir escala y filtros por caso de uso y medir sensibilidad. |
| Crítica | Ausencia de validación de relevancia | Hay una región marciana, dos candidatas terrestres, centros provisionales y escalas de puntuación arbitrarias. | Acordar preguntas de misión, criterios de relevancia y un conjunto de revisión independiente. |
| Alta | Cobertura frente a observaciones directas | El DEM puede contener valores interpolados aun con `coverage=1`. | Registrar calidad y cobertura por variable, junto con soporte de medición y método de cálculo. |
| Alta | Significado de la puntuación | Los valores 10° y 300 m saturan diferencias y el porcentaje puede sugerir una probabilidad o certeza que no existe. | Documentar/calibrar escalas y publicar desglose, cobertura y sensibilidad; evitar presentar la cifra como probabilidad. |
| Alta | Referencias y geometría planetaria | Se mezclan proyecciones locales, esferas planetarias, referencias verticales e imágenes de contexto. | Adoptar contratos de CRS/cuerpo/datum por producto y pruebas de puntos de control y conversión vertical. |
| Alta | Visualización y comunicación | Se normalizan colores por ventana; Marte no muestra la cuadrícula en una captura; no hay relieve real 3D. | Diagnosticar el caso, indicar estados de capa y ofrecer escalas y leyendas claras; probar alineación y cámara. |
| Alta | Fragilidad del procesamiento | Un script central tiene sitios, rutas y formatos codificados; sobrescribe salidas; no gestiona versiones de publicación transaccionales. | Separar adaptadores, especificaciones y etapas; validar antes de publicar archivos versionados. |
| Media-alta | Escala operativa | Se cargan regiones desde JSON y se dibuja una entidad por celda: 400 polígonos por ventana, además de dos visores. | Medir costo real y migrar a productos ráster y teselados, consultas e índices según necesidad. |
| Media-alta | Múltiples dimensiones | Temperatura, minerales y agua tienen unidades, soporte y significado distintos según instrumento. | Incorporar una dimensión por escenario, con contrato propio y control de calidad. |
| Media | Dependencias externas | Disponibilidad, autenticación, costos, condiciones de uso y cambios de productos varían por fuente. | Registro de fuentes, caché, atribución, límites de acceso y política de actualización. |

Las prioridades indican orden de mitigación, no una clasificación medida de rendimiento. La descarga inicial de MOLA fue lenta y Earthdata respondió con autenticación en una ruta; eso demuestra posibles fricciones de acceso, no permite estimar costos o velocidades de una infraestructura productiva.

## 4. Lo que significa la resolución para el producto

### 4.1. Tamaño de píxel no es tamaño de detalle garantizado

- **MOLA MEGDR 128 píxeles/grado:** cerca del ecuador, el espaciamiento nominal es de unos 463 m en dirección norte–sur; la separación este–oeste cambia con la latitud. En una ventana de 10 km hay solo unas pocas decenas de muestras nominales por lado. El modelo contiene interpolación en celdas sin observación directa. [PDS: MOLA MEGDR](https://pds-geosciences.wustl.edu/missions/mgs/megdr.html).
- **SRTM 1 segundo de arco:** espaciado nominal cercano a 30 m en el ecuador, no resolución efectiva uniforme. El manual de la colección estima la resolución espacial real generalmente en el rango de 50–80 m; depende del producto y sus condiciones. La cobertura original está principalmente entre 60° N y 56° S; la ubicación provisional de Islandia queda fuera. [Guía SRTM](https://lpdaac.usgs.gov/documents/179/SRTM_User_Guide_V3.pdf), [USGS](https://www.usgs.gov/centers/eros/science/usgs-eros-archive-digital-elevation-shuttle-radar-topography-mission-srtm-1).
- **Cuadrícula actual de 500 m:** es un intervalo de salida elegido para la prueba, no la resolución real de ambos instrumentos. El promedio terrestre y la interpolación marciana no garantizan funciones de respuesta espacial equivalentes; el producto marciano puede tener menos soporte independiente que celdas disponibles.
- **Ventana de 10 km:** es una hipótesis, no una escala validada. Según el fenómeno podría ser demasiado grande o demasiado pequeña; los bordes y la posición del centro pueden cambiar el resultado.

### 4.2. Consecuencias para la interpretación

La pendiente media y P95−P5 resumen formas regionales, pero no preservan distribución completa ni organización espacial: dos terrenos distintos pueden compartir los mismos valores. Una media tampoco identifica pendientes extremas o tramos transitables.

No se pueden inferir rocas, zanjas pequeñas, selección de una ruta o seguridad de un rover desde MOLA global. Si una misión requiere estudiar obstáculos de metros o centímetros, debe incorporarse **otro DEM y evidencia apropiados para esa escala**, verificar cobertura local y replantear la pregunta; ni el zoom ni la interpolación generan nuevas mediciones.

### 4.3. Decisiones pendientes y pruebas

1. Fijar para cada pregunta la extensión, la resolución de análisis, un mínimo de soporte útil y las fuentes candidatas. No adoptar umbrales sin examinar datos y acordarlos antes de evaluar resultados.
2. Comparar métodos de filtrado y remuestreo físicamente justificados. Evaluar incertidumbre vertical/horizontal y resolución efectiva, no solo el número de columnas.
3. Recalcular con ventanas y desplazamientos alternativos, por ejemplo 5/10/20 km **solo cuando el soporte del producto lo permita**, y varios tamaños de malla. Medir cambios de métricas y de orden del top-k.
4. Calcular estadísticas con máscaras e informar cuántas celdas válidas soportan cada variable; para pendientes, exigir también vecinos válidos.
5. Comparar elevación relativa, pendientes y distribuciones; no restar elevaciones absolutas entre planetas con diferentes referencias verticales.

## 5. Hasta dónde puede llegar la visualización 3D

### 5.1. Cuatro niveles que deben presentarse por separado

| Nivel | Qué permite | Estado / esfuerzo | Límite de interpretación |
|---|---|---|---|
| Globo + mapa global | Ubicar regiones y comprender el contexto planetario. | Existe una imagen global por cuerpo; permite un primer recorrido. | La textura marciana es MOLA coloreado, no fotografía en color natural; al ampliar se pixela. |
| Capa analítica 2D sobre el globo | Superponer ventana, elevación, pendiente, calidad y límites con leyenda. | Existe la primera capa de elevación con polígonos. Hay que revisar el caso marciano de las capturas. | Los colores actuales se ajustan por ventana; el mismo color no significa la misma altura en dos ventanas. Es una representación plana. |
| Terreno 3D regional | Orbitar una superficie derivada de un DEM y superponer imagen o capas. | No implementado. Es viable como prueba regional si se prepara una malla o un proveedor de terreno apropiado. | Solo reproduce el detalle respaldado por el DEM. MOLA global produce formas gruesas; no crea rocas ni garantiza alturas/pendientes precisas a pequeña escala. |
| Escena detallada por sitio | Mostrar superficie de mayor resolución cuando existan DEM/imágenes o datos de campo compatibles. | Trabajo posterior, limitado por cobertura, derechos, alineación y capacidad del dispositivo. | Una imagen detallada no equivale a un modelo 3D; si no existe un DEM equivalente, no se debe inventar geometría ni presentar rellenos como observación. |

Una textura de mayor resolución mejora apariencia; un DEM más detallado puede mejorar geometría si es confiable y cubre la zona. **Son dos fuentes y dos resoluciones distintas.** La exageración vertical puede ayudar a leer relieve suave, pero debe ser opcional, indicar el factor y no usarse para medir pendientes o distancias sin corregir.

### 5.2. Formatos y decisiones para Cesium

CesiumJS soporta proveedores de terreno como `CesiumTerrainProvider` con teselas *quantized-mesh* y niveles de detalle; una superficie de elipsoide, como la del prototipo, no contiene por sí sola terreno observado. [Cesium: terreno](https://cesium.com/learn/cesiumjs-learn/cesiumjs-terrain/). Para una prueba pequeña también puede ser suficiente una malla regional propia, siempre documentando su CRS, datum y calidad.

**No asumir que una herramienta terrestre de teselado funciona automáticamente en Marte.** Por ejemplo, la documentación del servicio Terrain Tiler de Cesium indica que reproyecta las entradas a WGS84; debe verificarse el soporte real del cuerpo y del flujo antes de enviarle un DEM marciano. [Cesium Terrain Tiler](https://cesium.com/platform/cesium-ion/3d-tiling-pipeline/terrain/). En quantized-mesh las alturas se expresan respecto al elipsoide del proveedor; transformar topografía MOLA referida al areoide a la superficie de visualización requiere una conversión vertical justificada, no cambiar solamente el radio. [Cesium: datos quantized-mesh](https://cesium.com/learn/cesiumjs/ref-doc/QuantizedMeshTerrainData.html).

Probar primero una sola región en cada cuerpo con puntos de control conocidos y comparar mapa, contorno y alturas en varias vistas. No mezclar fuentes de terreno con referencias diferentes sin registrar cómo se alinearon; validar bordes, polos, antimeridiano y orientación.

### 5.3. Rendimiento: hipótesis que hay que medir

Hoy cada ventana genera hasta **400 entidades poligonales**, con dos `Viewer` y dos contextos de visualización. No hay mediciones de cuadros por segundo, memoria ni tiempo de primera imagen. Más celdas o regiones podrían hacer que la geometría, el tiempo de construcción, la memoria GPU y el costo de dos visores dominen el rendimiento; es un riesgo razonable, no un límite ya medido.

Antes de elegir tecnología o fijar un techo:

- Definir equipos representativos: móvil, portátil integrada y escritorio; tamaños de pantalla y navegadores objetivo.
- Medir tiempo hasta primera imagen y ventana útil, memoria, cuadros por segundo durante navegación, tamaño descargado, número de peticiones y errores con una/dos escenas.
- Probar una ventana, varias regiones y capas; comparar polígonos individuales con una imagen ráster georreferenciada/teselada, geometría agrupada y/o un único visor con cambio de cuerpo. Medir, no suponer el ganador.
- Utilizar niveles de detalle y teselas para fondos y terreno; cargar solo lo visible, limitar cachés y liberar recursos al cerrar escenas. Establecer presupuestos de rendimiento después de la línea base.
- Separar fallo de textura, fallo de capa, descarga pendiente y ausencia real de datos. Las capturas de Marte hacen prioritario verificar el estado de carga y el encuadre de la ventana.

El número de polígonos, el tamaño de textura y la velocidad dependen de hardware, navegador, complejidad de geometría, red y configuración; no hay una cifra universal sustentada por esta prueba.

## 6. Arquitectura propuesta

```text
FUENTES EXTERNAS
  NASA PDS / USGS / Earthdata / otros
         │ adaptadores, autenticación y licencias
         ▼
REGISTRO DE PRODUCTOS + ARCHIVOS ORIGINALES INMUTABLES
         │ etiquetas, versión, huellas, cobertura, calidad
         ▼
TRABAJOS DE PREPARACIÓN VERSIONADOS
  lectura → validación → reproyección/armonización → métricas
         │                              │
         ▼                              ▼
PERFILES Y CALIDAD                ACTIVOS DE VISUALIZACIÓN
catálogo + índice espacial        rásteres/teselas/mallas + leyendas
         └──────────────┬───────────────┘
                        ▼
       MOTOR DE BÚSQUEDA Y EXPLICACIÓN
   filtros → métricas comparables → ranking → desglose
                        │
                        ▼
                API DE APLICACIÓN
                        │
                        ▼
             INTERFAZ + VISUALIZADOR
 misión · catálogo · selección · comparación · procedencia
```

### 6.1. Componentes y responsabilidades

1. **Adaptadores de fuentes:** localizar, descargar y verificar productos concretos; conservar etiquetas y responder a límites de acceso. Separar descarga de procesamiento. Una fuente puede requerir autenticación, otra no.
2. **Registro de productos y artefactos:** almacenar identificadores, checksum, origen, versión, cobertura, licencia y estado de calidad. Conservar originales sin modificar y guardar derivados con una relación explícita a sus entradas.
3. **Procesamiento:** trabajos reproducibles para validar formato, convertir unidades y coordenadas, aplicar máscaras, armonizar escala y producir variables. Controlar fallas por etapa; publicar resultados solo tras validación, sin sobrescribir un catálogo operativo a medias.
4. **Catálogo geoespacial:** representar regiones, geometrías, productos disponibles y perfiles versionados. El JSON actual sirve para desarrollo; pasar a PostgreSQL/PostGIS cuando haya consultas espaciales, concurrencia o volumen que lo justifiquen. No guardar rásteres voluminosos dentro de una fila de base de datos por defecto: usar archivos u objetos con URI y metadatos en el catálogo.
5. **Motor de búsqueda:** recibir una referencia, escenario, filtros, versión de características y pesos; recuperar candidatos elegibles y explicar resultados. Mantenerlo separado del acceso HTTP para poder probarlo y evaluarlo sin la interfaz.
6. **API:** exponer consulta de regiones, capacidades de datos, perfiles, búsqueda y estado de trabajos. Respuestas versionadas, con datos faltantes, calidad, método y enlaces a activos; paginar resultados. Trabajos largos fuera del ciclo de petición/respuesta y cola cuando la carga lo requiera.
7. **Frontend:** manejar estados de carga y error, controles y accesibilidad; visualizar escalas, referencias y limitaciones. No recalcular el método científico en el cliente ni tratar la textura como evidencia de similitud.
8. **Almacenamiento y entrega visual:** guardar derivados raster/mesh en formatos adecuados para lectura por ventanas o teselas, servirlos por HTTP con caché; COG para análisis y teselas de imagen/terreno para visualización cuando corresponda. COG no es automáticamente un proveedor de terreno Cesium.

Para una primera instalación, un proceso de preparación por lotes, almacenamiento local, FastAPI y un pequeño catálogo pueden ser suficientes. Colas, servicios distribuidos, nube y un índice vectorial deben responder a necesidades medidas; no son prerrequisitos del primer producto útil.

### 6.2. Modelo de datos mínimo recomendado

Separar entidades y versiones evita que una cifra pierda su contexto:

| Entidad | Contenido esencial |
|---|---|
| `body_reference` | Cuerpo, sistema de coordenadas, forma de referencia, convención de latitud/longitud y referencia vertical. |
| `source_product` | Proveedor, colección, instrumento, versión, identificador, fecha, unidades, resolución nominal y efectiva cuando se conozca, cobertura, licencia y calidad. |
| `region` | ID, nombre, cuerpo, geometría exacta, centro, escala y sistema de referencia. Una región es distinta de un píxel o una tesela de descarga. |
| `processing_run` | ID inmutable, entradas y hashes, versión de código/entorno, parámetros, máscaras, fecha, estado y advertencias. |
| `feature` | Región, dimensión, variable, valor o distribución, unidad, método, escala, cobertura, soporte, incertidumbre y procedencia. |
| `visual_asset` | Área, cuerpo, tipo de imagen/terreno/capa, CRS, datum, extensión, resolución, leyenda, método, fuente y URL. |
| `search_run` | Referencia, escenario, versiones de perfiles y método, pesos, filtros, fecha y resultados reproducibles. |
| `review` | Par o sitio, misión, evaluador, evidencia, etiqueta de relevancia y confianza; conservar desacuerdos y desconocidos. |

Cada dimensión debe poder tener un estado como **disponible, insuficiente, ausente o no comparable**, sin convertir nulos en ceros. El registro debe distinguir observación, producto interpolado, derivado e inferencia.

## 7. Búsqueda y similitud

### 7.1. Problemas del motor actual

El motor aplica `máx(0, 1 − |a−b| / escala)` con escalas fijas de 10° y 300 m y hace una media ponderada. Por ejemplo, una diferencia de relieve mayor o igual a 300 m recibe cero en esa dimensión, independientemente de cuánto mayor sea. Esto es transparente y útil como línea base, pero **esas escalas se escogieron para la demostración**, no mediante un estudio de relevancia. Mostrar `80 %` puede hacer pensar en una probabilidad, precisión o certeza que el método no calcula.

El orden actual coloca comparaciones completas antes de incompletas; la media de dimensiones disponibles y la fracción de pesos disponible se calculan por separado. Esa regla necesita validación por misión: una dimensión faltante puede ser obligatoria para un escenario y opcional para otro.

### 7.2. Evolución propuesta

1. Definir cada escenario con variables obligatorias/opcionales, filtros y escala de análisis.
2. Mantener línea base interpretable; añadir distribuciones de pendientes, percentiles y rugosidad multiescala cuando sean estables y comparables. Evitar sumar variables redundantes sin comprobar su efecto.
3. Determinar escalas, transformaciones y pesos con criterios de dominio y datos de desarrollo; congelarlos antes de evaluar el conjunto reservado. Mostrar en interfaz cómo se obtuvo cada componente.
4. Reportar **similitud relativa a una configuración**, rango o puntuación con desglose; no llamarla probabilidad de ser análogo sin calibración apropiada.
5. Investigar estabilidad ante producto, ventana, posición, resolución y error. Si el orden cambia mucho, explicitarlo en vez de ocultarlo bajo un decimal.
6. Fijar antes de evaluar cómo se excluyen o muestran candidatos con datos insuficientes. Un cero válido, un dato ausente y una variable no comparable son casos distintos.

### 7.3. ML: después de la línea base

Una representación aprendida podría ayudar a comparar patrones espaciales que se pierden en promedios. Es una hipótesis, no un requisito para la primera versión productiva. Exige muestras suficientes, separación geográfica antes de cortar ventanas, exclusión de parches solapados y evaluación contra la misma línea base. Comprobar si el modelo aprende el sensor, la resolución o el cuerpo en vez del patrón de interés. No entrenar con las texturas globales de contexto como si fueran etiquetas científicas.

## 8. Dimensiones adicionales: qué implica cada una

La misión determina qué dimensiones importan. No conviene convertir todas las capas en una sola cifra sin justificar su significado ni su soporte.

| Dimensión | Posible valor | Lo necesario para integrarla | Dificultad principal / salida inicial |
|---|---|---|---|
| Relieve y morfología | Pendientes, formas y variación del terreno. | DEM, CRS y datum, máscaras, resolución efectiva, derivadas y escala. | Diferentes sensores y soporte. **Primera dimensión**, con distribuciones y sensibilidad. |
| Imágenes de contexto | Inspeccionar paisaje y orientar interpretación humana. | Producto con cobertura, proyección, fecha, iluminación y derechos; registrar alineación. | La apariencia depende de sensor e iluminación. **No entra al score automáticamente**. HLS es terrestre; CTX es marciano. |
| Geología y minerales | Buscar materiales o procesos pertinentes a una misión. | Productos o mapas interpretados, leyendas, resolución, confianza, cobertura y correspondencias justificadas. | Una banda o color entre sensores no significa el mismo mineral; productos derivados no son siempre identificación concluyente. CRISM es una fuente candidata, su modo y producto deben escogerse. [PDS CRISM](https://pds-geosciences.wustl.edu/missions/mro/crism.htm). |
| Temperatura | Comparar condiciones o ciclos relevantes. | Variable física, hora local, estación, fecha, cobertura, incertidumbre y producto comparable. | Una medición instantánea no equivale a un ciclo ni a temperatura del aire; diferencias de atmósfera y sensor. Empezar como comparación contextual si no hay condiciones compatibles. |
| Agua / hielo | Investigar indicadores pertinentes a un escenario. | Tipo de producto, observación directa o indicador, profundidad/huella, fecha y confianza. | Un proxy de hidrógeno u otra señal no confirma agua local ni aporta la misma resolución que un DEM. Presentar por separado y como evidencia condicionada. |
| Factibilidad terrestre | Ayudar a planificar trabajo de campo. | Acceso, permisos, áreas protegidas, logística y fechas de actualización, según disponibilidad. | Cambia con el tiempo y no es similitud planetaria. Aplicar como filtro contextual separado y verificar con autoridades/fuentes pertinentes. |
| Luna | Extender el destino de referencia. | Datos y CRS lunares, referencia vertical, escala, ventanas y casos de uso. | No es sustituir el nombre del planeta: necesita adaptadores, geometría, productos, pruebas y evaluación propios. |

Para incorporar una dimensión, exigir una ficha mínima: pregunta, definición y unidades, productos concretos, cobertura real, escala, calibración y máscaras, método de armonización, calidad, ausencia de datos, fuente y ejemplo validado de extremo a extremo. Tener datos disponibles no implica que la dimensión sea comparable entre cuerpos.

## 9. Experiencia de usuario y comunicación de evidencia

El prototipo ya sugiere varias mejoras prioritarias:

- Hacer visible **qué área se compara** en ambos globos; añadir indicadores de carga, fallo y falta de cobertura. Investigar la cuadrícula marciana que no aparece en la captura antes de afirmar que funciona.
- Distinguir vista global, imagen contextual, datos analíticos y terreno 3D. Mantener controles de centrar y regresar, con ayuda breve y accesibilidad de teclado.
- Mostrar unidades y leyendas por capa. Para comparar relieve usar, cuando proceda, una escala común de **elevación relativa** o leyendas independientes muy claras; nunca insinuar que los datums verticales absolutos son equivalentes.
- Etiquetar textura marciana global como topografía coloreada; mostrar fuente, fecha, escala y límites de cada activo visual.
- Reemplazar el protagonismo de un porcentaje aislado por ranking, diferencias, cobertura por dimensión y explicación del escenario. Informar que una puntuación es una función de similitud, no una probabilidad ni una certificación.
- Separar «no hay información», «no se puede comparar», «dato interpolado» y «baja cobertura» de un resultado con valor cero.
- Permitir inspeccionar cada variable, método y producto original; exportar la configuración de búsqueda y sus versiones para repetir el resultado.

## 10. Hoja de ruta y criterios de salida

Las fases son dependencias propuestas, no estimaciones de duración. Una fase puede reducirse o detenerse si la evidencia no sustenta continuar.

### Fase 0 — Cerrar y auditar la prueba existente

- Reproducir y diagnosticar la ventana de Marte que no se observa en la captura: cámara, carga de JSON, geometría, renderizado y consola; probar ambos cuerpos y cambios de candidato.
- Añadir pruebas de lectura con valores de referencia MOLA, CRS, orientación y endianidad; cobertura, datos faltantes y regeneración reproducible. Validar estructura de entrada, rangos, tamaños y errores.
- Documentar y revisar la lectura de SRTM/MOLA, el remuestreo y el significado de 44 % de soporte aproximado. Comprobar fuentes y geometría de las ventanas originales.
- Evitar escrituras parciales o sobrescrituras accidentales; registrar resultados por versión y validar antes de activar.

**Salida:** los resultados numéricos y visuales se repiten en un entorno documentado, con errores identificables. Sigue siendo una prueba exploratoria.

### Fase 1 — Producto mínimo de relieve

- Definir con usuarios una misión concreta y criterios de revisión. Aumentar diversidad de regiones marcianas y terrestres, incluyendo ejemplos de contraste y cobertura insuficiente, sin escoger todos por fama o por resultado esperado.
- Crear catálogo de fuentes, contrato de región y procesamiento por etapas. Aplicar controles de calidad y reporte por dimensión.
- Mejorar línea base con distribuciones y pruebas de sensibilidad; evaluar que los resultados respondan al escenario y mostrar desglose.
- Habilitar exploración 2D sobre el globo, navegación y estados de datos; probar geometría en ambas superficies.

**Salida:** conjunto pequeño pero trazable, búsqueda y explicación revisadas por usuarios, con limitaciones y casos que no se pueden responder.

### Fase 2 — Evaluación y terreno 3D regional

- Construir un conjunto independiente de relevancia con evaluadores y criterios por misión; separar regiones y evitar contaminación espacial.
- Medir recuperación top-k cuando haya suficientes juicios, cobertura, estabilidad y ejemplos de error. Reportar número de casos e incertidumbre, sin convertir una muestra pequeña en validación general.
- Crear una demostración de terreno en una región por cuerpo con productos que soporten la escala, puntos de control y datum documentado; comparar alternativas de formato y medir rendimiento.

**Salida:** evidencia de utilidad para la misión seleccionada y decisión fundamentada sobre 3D; no se promete resolución detallada global.

### Fase 3 — Más dimensiones y escala operativa

- Elegir una dimensión adicional y demostrar su contrato, calidad, armonización y evaluación en un escenario concreto.
- Incorporar catálogo espacial, almacenamiento de objetos, trabajos y caché conforme a volumen observado. Instrumentar costos, tiempos y fallas.
- Añadir Luna o nuevos productos solo con referencias y validación específicas. Investigar ML si hay datos y etiquetas suficientes.

**Salida:** comparación multidimensional explícita y operable, sin ocultar diferencias de cobertura ni depender de un único puntaje opaco.

## 11. Decisiones abiertas y próximos experimentos

1. **Misión y audiencia:** ¿qué decisión quiere apoyar la primera versión y quién revisa su utilidad? Definir antes de seleccionar variables y criterios de éxito.
2. **Cobertura inicial:** ¿qué regiones y qué resolución son realmente necesarias? Levantar un inventario de productos disponibles antes de prometer cobertura global.
3. **Indicadores de calidad:** elegir criterios mínimos por variable tras examinar muestras y antes de evaluar ranking; no equiparar celdas válidas con observaciones directas.
4. **Vista regional:** ¿basta una capa analítica 2D o el 3D cambia una decisión de usuarios? Probar ambas con la misma evidencia y registrar costo/beneficio.
5. **Infraestructura:** medir número de regiones, tráfico, tamaño de activos, tiempos y presupuesto. Seleccionar entre local, servicios alojados o nube cuando existan cargas y restricciones concretas.
6. **Propiedad y actualización:** definir responsables de fuentes, control de cambios, derechos y atribución, revisión de errores y actualización del catálogo.

### Primeros experimentos recomendados

- **E1 — confiabilidad geoespacial:** comparar coordenadas y valores de varias celdas con una herramienta de referencia, en Marte y Tierra; verificar la cuadrícula en pantalla y sus límites. Registrar errores y tolerancias antes de declararla correcta.
- **E2 — sensibilidad del ranking:** recalcular las mismas zonas con variantes justificadas de ventana, remuestreo y productos; registrar cambios de métricas y orden, junto a cobertura. No variar simultáneamente todo sin poder atribuir causas.
- **E3 — comprensión:** pedir a usuarios que expliquen qué significan colores, porcentajes, datos interpolados y ausencia de información, y detectar interpretaciones erróneas.
- **E4 — visualización y rendimiento:** comparar un mapa 2D con una malla 3D local; medir calidad, latencia y memoria en dispositivos representativos. Incluir el caso del visor marciano de las capturas.
- **E5 — revisión por misión:** hacer que especialistas comparen candidatos esperados, inesperados e insuficientes sin depender del orden del motor; registrar criterios y desacuerdos.

## 12. Fuentes y material del proyecto

- [Código de preparación y generación de cuadrículas](../../scripts/preparar_datos.py), [API y motor actuales](../../backend/app/main.py), [visualizadores y controles](../../frontend/src/main.tsx).
- [Extracción y preparación de datos reales](../../data/README-datos-reales.md), [arquitectura anterior](Arquitectura%20y%20estrategia%20de%20implementacion.md), [investigación de fuentes](Investigacion%20de%20fuentes%20de%20datos%20y%20cruces.md), [plan de prototipo](Plan%20Prototipo.md).
- [MOLA MEGDR — PDS](https://pds-geosciences.wustl.edu/missions/mgs/megdr.html); [guía SRTM — NASA/USGS](https://lpdaac.usgs.gov/documents/179/SRTM_User_Guide_V3.pdf); [CRISM — PDS](https://pds-geosciences.wustl.edu/missions/mro/crism.htm).
- [CesiumJS: terreno](https://cesium.com/learn/cesiumjs-learn/cesiumjs-terrain/); [formato quantized-mesh](https://cesium.com/learn/cesiumjs/ref-doc/QuantizedMeshTerrainData.html); [Terrain Tiler y su reproyección](https://cesium.com/platform/cesium-ion/3d-tiling-pipeline/terrain/).

Las secciones de diagnóstico describen el código, los datos y las capturas disponibles. Las propuestas de arquitectura, priorización y experimentos son recomendaciones que deberán contrastarse con las necesidades y resultados del proyecto.
