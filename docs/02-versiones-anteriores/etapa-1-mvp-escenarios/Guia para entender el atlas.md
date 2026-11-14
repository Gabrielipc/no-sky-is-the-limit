# Guía para entender el atlas

Fecha: 7 de noviembre de 2026. Basada en el código y las entregas locales de las fases 1–5. No necesitas conocimientos de geografía, estadística ni programación para empezar.

Alcance: esta guía explica esas cinco fases. Las ampliaciones incorporadas después, como el escenario de dimensiones de superficie, tienen sus propias fichas. El recorrido visual fue reorganizado en el [refactor del frontend](Refactor%20frontend%20-%20entrega.md); la sección sobre la interfaz anterior explica el punto de partida.

## 1. La idea en un minuto

Queremos encontrar lugares de la Tierra que compartan **ciertas características medibles** con una zona de Marte. Esos lugares podrían servir para investigar preguntas de exploración. La utilidad depende de qué quieras estudiar: parecerse en inclinación no implica parecerse en materiales, temperatura o dificultad de conducción.

El atlas actual compara dos características: **pendientes** y **relieve**. Luego busca más zonas y comprueba cuánto cambia el resultado al usar otros datos o tamaños de celda.

La pregunta que sí podemos responder hoy es: «¿Cómo se comparan estas zonas en esas dos características, con estas fuentes y a esta escala?». Para decidir dónde probar un rover todavía faltan mediciones y evaluación especializada.

Piensa en buscar una pista terrestre para ensayar una actividad marciana. Primero necesitas saber qué quieres ensayar. Después miras terrenos parecidos en lo relevante y revisas qué información falta antes de elegir.

## 2. Qué hizo cada fase y por qué sirve

| Fase | En palabras corrientes | Resultado concreto | Por qué importa |
|---|---|---|---|
| 1 · Viabilidad | Averiguar si había datos utilizables de las zonas elegidas | Áreas, productos, muestras y una matriz de datos disponibles y faltantes | Evita comparar lugares con datos que no los cubren o que miden cosas diferentes |
| 2 · Análisis reproducible | Medir terreno de Jezero, Utah y Atacama con una receta explícita | Ventanas de 1,8 × 1,8 km, celdas de 60/120 m, pendientes y relieve | Permite entender de dónde salen las cifras y volver a obtenerlas |
| 3 · Aplicación | Llevar ese análisis al navegador | Comparación, figuras, fuentes, cobertura y cambio de escala | Hace consultables los resultados sin ejecutar scripts |
| 4 · Búsqueda regional | Mirar más lugares dentro de tres áreas terrestres | 970 ventanas nuevas de 3 × 3 km y tres controles; filtros a 300/600 m | Amplía la exploración más allá de los dos ejemplos iniciales |
| 5 · Fuente y escala | Ver si las decisiones cambian al usar otro producto de elevación | Diez ventanas seleccionadas; siete evaluadas y tres pendientes | Permite observar sensibilidad antes de extender la evaluación |

**«Fases terminadas» significa que se entregó ese alcance.** Quedan abiertos la validación física independiente, otras características, Luna, polos y búsqueda global. Los números de fase organizan el trabajo; no indican un nivel de certeza científica.

En fase 4 se muestrearon huellas que ocupan aproximadamente 8,3–8,5 % de cada área delimitada: hay espacios entre las ventanas. Las 970 ventanas no representan un examen de cada metro de esas regiones.

## 3. Un resultado real, traducido

En el primer caso, con ventana de 1,8 km y celda de 60 m:

| Qué se observa | Jezero | Utah | Atacama |
|---|---:|---:|---:|
| Inclinación mediana | 2,88° | 1,81° | 7,97° |
| Relieve relativo | 54,63 m | 27,38 m | 200,11 m |
| Distancia de pendientes a Jezero; menor = distribuciones más cercanas | Referencia | 1,456° | 5,033° |

**Lectura:** entre estas dos candidatas, la ventana de Utah se acerca más a Jezero en distribución de pendientes. Sus inclinaciones suelen ser menores y su relieve es aproximadamente la mitad. La ventana de Atacama tiene inclinaciones y relieve mayores. Esto describe los polígonos elegidos, no todo Utah ni todo Atacama.

Al cambiar a 120 m, Utah sigue siendo la más cercana en pendientes entre las dos. Las cifras cambian porque se promedia el terreno en bloques mayores.

En fase 4, a 300 m y perfil base, pasan 99 de 272 ventanas de Utah, 128 de 278 de Mojave y 136 de 420 de Atacama. Son **363 ventanas que cumplen esas dos condiciones**, no 363 sitios certificados.

En fase 5, las siete ventanas con datos suficientes conservaron su decisión de filtro al sustituir GMTED por SRTM a 300/600 m en los tres perfiles. Sus métricas sí cambiaron. Las otras tres quedaron pendientes. Esto describe una muestra pequeña elegida en parte por los archivos disponibles; no demuestra que el método acierte siempre.

### Tres números que no debes confundir

- **Distancia entre pendientes: 1,456°** resume una diferencia entre distribuciones. No significa que todas las laderas difieran 1,456°, ni que Utah tenga esa inclinación.
- **Diferencia de relieve: −27,247 m** significa que el relieve de Utah es menor que el de Jezero por esa cantidad. El signo negativo no expresa una mala nota.
- **Cobertura: 100 %** significa que todas las celdas requeridas tuvieron valores válidos según el método. No expresa 100 % de certeza ni observación directa en cada punto.

## 4. El vocabulario que aparece en la experiencia

### La pregunta y los lugares

| Término | Significado y ejemplo |
|---|---|
| Análogo planetario | Lugar terrestre útil para estudiar algún aspecto de otro cuerpo. La analogía siempre es parcial y depende de la pregunta |
| Escenario | Pregunta que organiza la comparación. Aquí hay comparación topográfica y reconocimiento de sensibilidad a fuente/escala |
| Referencia | Zona con la que se comparan las demás; en este caso, un sector de Jezero |
| Candidata | Zona terrestre que vale la pena examinar. No implica aprobación |
| Jezero / abanico sedimentario | Cráter marciano y sector donde se acumularon sedimentos en forma de abanico; es la referencia del caso |
| Ventana / polígono / huella | Ventana: porción delimitada que se mide. Polígono: su contorno. Huella: superficie cubierta por una ventana o producto |
| Bbox | Rectángulo envolvente expresado como oeste, sur, este y norte. Ayuda a delimitar una búsqueda |
| Barrido / muestreo / stride | Examinar ventanas distribuidas en un área. Stride es la separación de sus centros: aquí, 10 km para ventanas de 3 km |
| Control contextual | Sitio conocido que se incluye para observar el comportamiento del método. No se supone que sea una respuesta correcta |
| Ancla | Caso que se conserva para conectar dos análisis; `utah-010-007` vincula fases 4 y 5 |
| Dimensión / variable / feature | Aspecto medido, como pendiente. Feature suele significar un descriptor calculado, como la mediana de pendiente |
| Regional / local / detalle | Niveles relativos de observación. «Detalle» con celdas de 60 m sigue sin mostrar rocas de tamaño de rover |
| Transitabilidad / movilidad / idoneidad | Poder desplazarse o servir para una actividad. Requiere más información que las dos variables actuales |

### Terreno y escala

| Término | Significado y cómo leerlo |
|---|---|
| Elevación / altitud | Altura respecto a una referencia vertical. No comparamos directamente la altitud absoluta terrestre con la marciana |
| Pendiente | Inclinación respecto a la horizontal, en grados: 0° es plano; 90° es vertical |
| Relieve relativo p95−p5 | Diferencia entre una elevación alta y una baja dentro de la ventana, dejando fuera el 5 % de cada extremo. No es la altitud ni el máximo menos el mínimo |
| Rugosidad | Variación o irregularidad del terreno a una escala definida. No es sinónimo automático de pendiente y no aparece como tercera métrica integrada |
| Ráster / cuadrícula / celda / píxel | Una tabla espacial de valores. Cada celda representa una porción de superficie; un píxel de imagen también puede guardar brillo o color |
| Tamaño de ventana | Cuánta superficie entra en la medición: por ejemplo, 1,8 × 1,8 km |
| Tamaño de celda / agregación | Tamaño de los bloques usados para calcular: por ejemplo, 60 × 60 m. Aquí se promedian elevaciones |
| Base de pendiente | Separación entre posiciones usadas para estimar la inclinación. Con este método es dos veces la celda: 60 m → 120 m |
| Paso nativo | Separación de las muestras en el producto original. No garantiza cuánto detalle real distingue |
| Resolución efectiva | Detalle que los datos realmente permiten distinguir tras sensor y procesamiento. No está cuantificado localmente en este caso |
| Remuestreo / interpolación | Crear valores en otra cuadrícula. Puede suavizar o estimar entre muestras; no crea observaciones nuevas |
| Armonización | Preparar datos con unidades, geometrías y procedimientos compatibles para una comparación definida |
| Sombreado / hillshade | Iluminación simulada a partir del relieve para ver formas. Depende de la luz elegida |
| Textura / capa de contexto | Imagen que cubre un mapa o globo para orientarse. Puede tener mucho menos detalle que el área analizada |
| Terreno 3D / malla | Geometría con alturas. El globo actual usa una superficie de referencia y texturas; no representa el terreno analizado en 3D |
| Segundos de arco, 7,5″ / 30″ | Unidad angular de separación de muestras. Su tamaño físico depende de la latitud y la dirección |

**Ejemplo de escala:** una ventana de 1800 m con celdas de 60 m contiene 30 × 30 = 900 celdas; a 120 m contiene 15 × 15 = 225. El lugar no cambió. Cambió el tamaño de los bloques con los que lo describimos. Tampoco aumentó la precisión por tener más cifras decimales.

### Estadística sin fórmulas obligatorias

| Término | Traducción práctica |
|---|---|
| Distribución | Cómo se reparten los valores: cuánto terreno tiene poca, media o mucha inclinación |
| Histograma | Agrupa valores por intervalos y cuenta cuántos hay. Si los intervalos tienen distinto ancho, sus barras requieren cuidado al interpretarlas |
| Distribución acumulada / CDF | Para cada inclinación, indica qué fracción de celdas tiene ese valor o menos. Es distinta de una barra por intervalo |
| Percentil p10 / p50 / p90 | Umbral por debajo del cual queda aproximadamente el 10/50/90 % de los valores. p50 es la mediana |
| Distancia de Wasserstein | Resume cuánto difieren dos distribuciones. Aquí usa pendientes y se expresa en grados; menor significa más cercanas en esa métrica |
| Delta / diferencia firmada | Resta con dirección. En relieve: candidata − Jezero. En el contraste de fuente de fase 5: SRTM − GMTED |
| Sensibilidad / estabilidad | Cuánto cambia un resultado al cambiar una decisión de análisis, como celda o producto. No son una garantía de verdad |
| Perfil / umbral / filtro | Condiciones para incluir resultados. Base: distancia de pendientes ≤ 2° y diferencia absoluta de relieve ≤ 60 m, con cobertura suficiente, solo a 300/600 m |
| Estricto / base / amplio | Tres conjuntos predefinidos de condiciones. Son elecciones exploratorias, no categorías de seguridad |
| Peso / normalización | Peso: importancia asignada a una variable. Normalización: convertir magnitudes a una escala común antes de combinarlas. Su elección afecta el resultado |
| Score / índice / ranking | Score: puntuación calculada; ranking: orden. Ordenar por pendientes no evalúa automáticamente relieve ni otras dimensiones |
| Línea base / baseline | Método sencillo y explícito contra el que se puede comparar uno más complejo. «Perfil base» es otro uso de la palabra: un filtro específico |
| Muestra de conveniencia estratificada | Elegir ejemplos de grupos distintos, favoreciendo los datos disponibles. Así se eligió parte de fase 5; no representa estadísticamente las 970 ventanas |
| Sesgo | Preferencia sistemática introducida por datos, selección o método. Aquí hay más detalle donde ya había archivos locales |
| Correlación espacial | Celdas cercanas comparten estructura e información. 900 celdas no equivalen a 900 mediciones independientes |
| Incertidumbre / precisión / exactitud | Incertidumbre: cuánto desconocemos; precisión: consistencia o nivel de detalle de una medición; exactitud: cercanía al valor real. Decimales y repetición no demuestran exactitud |
| Falso positivo / falso negativo | Decisión equivocada frente a una respuesta conocida. Sin etiquetas independientes de analogía no podemos calcular esas tasas |

Dos lugares pueden tener distribuciones de pendiente parecidas y organizar las laderas de manera diferente. Wasserstein no compara por sí sola la posición de canales, rutas o rocas.

### Evidencia y calidad

| Término | Qué acredita y qué debes recordar |
|---|---|
| Cobertura válida | Proporción de celdas que cumplen los requisitos numéricos del cálculo. Se informa por elevación y pendiente |
| Soporte | Datos válidos que contribuyen a una celda o cálculo. Para pendiente también hacen falta vecinos válidos |
| Nodata / NaN / null | Ausencia o invalidez explícita. Aquí cero puede ser una elevación o una distancia válida; nunca sustituye a un dato faltante |
| Observación / derivado / interpretación | Observación: registro de un instrumento. Derivado: transformación calculada. Interpretación: significado que atribuimos al resultado |
| Producto / fuente / procedencia | Archivo concreto de un proveedor; su origen y transformaciones. Dos productos pueden compartir observaciones |
| QA / control de calidad | Comprobaciones para detectar problemas concretos: huecos, lectura incorrecta, geometrías o artefactos |
| Metadatos / etiqueta PDS | Descripción de un archivo: dimensiones, unidades, coordenadas, valores inválidos, etc. PDS es un sistema de archivo de datos planetarios |
| Reproducibilidad | Poder repetir el procedimiento documentado con las mismas entradas y parámetros y obtener los resultados previstos |
| Trazabilidad | Poder seguir un número hasta sus archivos y transformaciones |
| Validación independiente | Contrastar con una referencia externa adecuada, por ejemplo mediciones o evaluación experta. Sigue pendiente para las afirmaciones de analogía |
| Hash / checksum / SHA-256 | Huella digital de bytes para comprobar identidad local. Una coincidencia no certifica que el terreno esté bien medido |
| CRC | Comprobación de integridad usada aquí dentro de los ZIP; detecta determinados problemas de archivo |
| Manifiesto / manifest | Lista de archivos y sus identidades. Permite detectar ausencias o cambios |
| Test / verificación | Comprobación de un comportamiento concreto del software o método. Pasar tests no convierte una candidata en análogo validado |
| Evidencia exploratoria | Resultado útil para investigar bajo las condiciones declaradas, con cuestiones todavía abiertas |

## 5. Los nombres de las fuentes

| Nombre | Qué es | Papel actual |
|---|---|---|
| DEM / DTM / DSM | Modelos digitales de elevación, terreno o superficie. DSM puede incluir elementos sobre el suelo; el nombre del archivo no elimina sus limitaciones | El análisis usa modelos de elevación para calcular terreno |
| HiRISE | Instrumento de imágenes de Marte; mediante imágenes estéreo se genera el DTM usado aquí | DTM de Jezero y ortoimagen para inspección |
| Ortoimagen | Imagen corregida geométricamente para ubicar sus píxeles sobre el terreno | Apoya inspección; no mide rocas automáticamente |
| SRTM | Shuttle Radar Topography Mission, fuente terrestre de elevación por radar | Utah y Atacama; evaluación local y contraste de fase 5 |
| GMTED2010 | Global Multi-resolution Terrain Elevation Data, producto terrestre compuesto de varias fuentes | Genera ventanas regionales; se contrasta con SRTM a escala común |
| MOLA | Mars Orbiter Laser Altimeter, altimetría de Marte | Catálogo histórico y textura contextual; fuera de las métricas del recorrido nuevo |
| LOLA | Lunar Orbiter Laser Altimeter | Datos descargados/reservados; Luna sigue sin integrarse al recorrido |
| 3DEP | Programa estadounidense de elevación, con productos de detalle | Productos localizados en fase 1; no incorporados a estas métricas |
| CTX / HLS | Imágenes marcianas de contexto / productos armonizados Landsat-Sentinel terrestres | No integrados a la comparación actual |
| THEMIS / inercia térmica | Instrumento marciano / propiedad relacionada con cómo responde un material al calentamiento | No evaluados aquí; temperatura e inercia térmica son magnitudes distintas |
| ArcticDEM / REMA | Modelos de elevación del Ártico / Antártida | Fuera del escenario actual |
| USGS / NGA / NASA / JPL | Organizaciones proveedoras o vinculadas a los datos | Atribuir datos no implica que respalden las conclusiones de la aplicación |

## 6. Coordenadas: solo lo necesario

| Término | Significado |
|---|---|
| Latitud / longitud | Ubicación angular. Las convenciones de signo y rango deben ser explícitas |
| CRS / proyección | Reglas para convertir coordenadas en ubicaciones. Una proyección local permite trabajar en metros |
| WGS84 | Referencia terrestre usada para ubicaciones y cálculos de la Tierra |
| Datum / referencia vertical / EGM96 | Convención desde la que se mide la altura. EGM96 se documenta para SRTM; Marte usa su propia referencia |
| AEQD | Proyección azimutal equidistante centrada en cada área, utilizada en los cálculos locales |
| Esfera / elipsoide / IAU | Modelos de forma y convenciones de referencia de cada cuerpo. No se coloca Marte sobre un sistema terrestre por conveniencia |
| Corregistro | Alinear espacialmente productos. Que dos etiquetas coincidan no equivale a comprobar exactitud contra el terreno |
| GeoJSON / GeoTIFF | Formatos de geometrías / rásteres con información geográfica. El GeoJSON exportado de candidatas corresponde a la Tierra |

## 7. Por qué cambiaron Cesium y los sliders

**Cesium sigue en `frontend/src/ContextGlobe.tsx`.** Los globos se abren dentro de «Ubicación en el globo» o «Ver ubicación y polígono». Cargan texturas globales, un marcador y un contorno. Su función es orientar; no enseñan el relieve medido como terreno 3D. En el primer caso quedan después de varias tablas y explicaciones, por lo que se pierde la comparación inmediata.

Los **pesos históricos** siguen en `/api/search`, una ruta marcada como obsoleta. El prototipo convertía diferencias a una similitud usando escalas fijas de 10° y 300 m, y promediaba según los pesos. Era una fórmula ilustrativa. El recorrido nuevo calcula otras métricas y deja de combinarlas en un porcentaje.

La razón metodológica del cambio está documentada: una cifra única podía esconder que un sitio se parece en pendientes y difiere en relieve. **La interacción sigue siendo valiosa.** Podemos recuperar comparación simultánea, capas y control de escala; también filtros y preferencias explícitos. Lo importante es que el control explique qué modifica y no atribuya a las cifras una certeza que no tienen.

## 8. Tecnología que funciona hoy

No necesitas memorizar estos nombres para usar el atlas.

| Palabra | Traducción y papel |
|---|---|
| Frontend / React / TypeScript / CSS | Pantallas interactivas, componentes, lenguaje con tipos y estilos |
| Vite / build | Herramienta de desarrollo y preparación del frontend para ejecutarlo |
| Cesium / WebGL | Biblioteca de globos y mapas 3D / capacidad gráfica del navegador |
| Backend / API / endpoint / FastAPI | Servicio que entrega datos a la pantalla; API es el contrato; endpoint es una dirección concreta; FastAPI implementa el servicio |
| JSON / spec | Formato de datos / configuración explícita de una pregunta, fuentes y parámetros |
| Python / script / pipeline | Lenguaje / programa ejecutable / secuencia de pasos de procesamiento |
| GDAL / Rasterio / PROJ / pyproj | Herramientas para leer rásteres, operar sus valores y transformar coordenadas |
| NumPy / Pillow | Cálculo con matrices / lectura y tratamiento de imágenes; aquí Pillow decodifica la ortoimagen |
| Pixi / entorno / lockfile | Instalador y entorno de herramientas; el lockfile fija versiones resueltas para repetir la instalación |
| Git / repositorio | Historial de cambios / carpeta versionada del proyecto |
| Caché / precalculado | Resultado conservado para no repetir trabajo. La API actual consulta evidencia guardada, no vuelve a analizar terreno al mover controles |
| Lazy loading | Cargar algo cuando se necesita; por ejemplo, abrir un globo de contexto |
| Refactorización / componente / estado | Reorganizar código conservando comportamientos / pieza de interfaz / selección y datos activos de una pantalla |
| UX / UI / divulgación progresiva | Experiencia de uso / presentación e interacción / mostrar el detalle técnico cuando hace falta |
| URL / deep link / accesibilidad / responsive | Dirección / enlace que restaura una vista / uso con distintas capacidades y dispositivos / adaptación al ancho de pantalla |

## 9. Buzzwords de la arquitectura futura

La [arquitectura objetivo](../../03-obsoletos-e-historico/Arquitectura%20objetivo%20y%20plataforma%20de%20datos.md) contiene propuestas de largo plazo. Su existencia en un documento no significa que estén operando. `packages/analogos_core`, `ml` y `releases` contienen espacios reservados; los pipelines actuales son scripts y registros locales. La fase 5 pospone ML, soporte lunar/polar e infraestructura distribuida.

| Familia de términos | Traducción | Estado respecto al recorrido actual |
|---|---|---|
| Lago de datos, raw / normalized / features / visual | Archivos originales, preparados, descriptores y capas de presentación organizados por propósito | Hay archivos y derivados locales; la plataforma completa está propuesta |
| Asset / run_id / release / versionado | Producto de datos / identificador de ejecución / conjunto publicado / conservar versiones | Hay manifiestos de entregas; la publicación transaccional completa sigue pendiente |
| Atomicidad / transacción / inmutable | Sustituir un archivo completo / activar varios cambios como unidad / conservar sin sobrescribir | Escritura atómica por archivo; sin transacción conjunta de entregas |
| AnalysisSpec / DimensionSpec / body_reference / ADR | Fichas de análisis, variable y cuerpo / registro de una decisión arquitectónica | Hay configuraciones concretas de los casos; contratos generales todavía incompletos |
| Dagster / Prefect / Airflow / orquestador / DAG | Herramientas que coordinan tareas y dependencias; DAG es un grafo sin ciclos | Propuestas; los scripts actuales no requieren estos servicios |
| Dask / distribuido / backfill | Cálculo por bloques o varios trabajadores / reparto del trabajo / recalcular datos históricos | No se ha demostrado necesidad de infraestructura distribuida |
| Docker / Compose / self-hosted / nube / spot / GPU | Entornos empaquetados / servicios coordinados / alojamiento propio / remoto / capacidad interrumpible / procesador paralelo | Opciones arquitectónicas; la ejecución documentada actual usa Pixi local |
| S3 / bucket / Garage / SeaweedFS / GCS / R2 | Interfaz y servicios para almacenar objetos; bucket es un contenedor de archivos | Opciones de almacenamiento futuro |
| COG / Zarr / Parquet / GeoParquet | Ráster preparado para lectura parcial / matrices por bloques / tablas columnares / tablas con geometrías | Formatos propuestos para una plataforma mayor |
| STAC / pgSTAC / stac-fastapi | Catálogo estandarizado de productos espaciales y herramientas para alojarlo | Catálogo futuro; no confundir con el JSON actual de candidatas |
| PostgreSQL / PostGIS / SQL / DuckDB | Base de datos / extensión espacial / lenguaje de consulta / motor analítico | Opciones propuestas; la API actual sirve registros de archivos |
| PMTiles / TiTiler / planetcantile / TMS / quantized-mesh | Distribución de teselas, reglas de cuadrícula y mallas de alturas para visores | Pendientes; no hay servicio actual de terreno de detalle |
| HEALPix / nside / H3 / S2 | Formas de dividir superficies en celdas; nside controla el nivel de subdivisión de HEALPix | Malla planetaria propuesta; el barrido actual usa centros locales cada 10 km |
| ML / entrenamiento / inferencia / etiquetas | Aprendizaje automático / ajuste de modelo / aplicación del modelo / respuestas de referencia para evaluar | ML pospuesto por falta de evidencia y etiquetas independientes |
| Embedding / vector / modelo fundacional | Representación numérica aprendida / lista de números / modelo preentrenado amplio | No forman parte de la búsqueda actual |
| kNN / ANN / HNSW / pgvector / FAISS / Qdrant | Búsqueda de vecinos exacta o aproximada y herramientas de índices vectoriales | Propuestos para experimentos o servicio futuros |
| MLflow / partición geográfica / leakage | Registro de experimentos / separar zonas para evaluar / filtración de información de entrenamiento a evaluación | Requisitos de una eventual evaluación de ML |
| Recall / top-k / Kendall / benchmark | Cuánto recupera una búsqueda / primeros k resultados / concordancia de órdenes / medición comparativa | Vocabulario de evaluación futura; no son métricas de calidad publicadas hoy |
| CI / fixture / test de humo / digest | Comprobaciones automáticas / datos de prueba conocidos / comprobación básica / identidad de una imagen de software | Prácticas técnicas; hay tests locales, sin inferir que toda la plataforma CI esté desplegada |

## 10. Cómo leer la aplicación sin perderte

1. Identifica la pregunta y el tamaño de ventana: 1,8 km y 3 km son experimentos distintos.
2. Mira qué candidata y qué fuente están activas.
3. Compara pendientes y relieve por separado, con unidades.
4. Cambia solo una condición a la vez: candidata, celda o producto.
5. Distingue «pasa este filtro», «evaluada» y «pendiente»: son hechos diferentes.
6. Abre fuentes y método cuando necesites comprobar la procedencia de un resultado.

El avance útil es disponer de comparaciones revisables, una búsqueda acotada y controles para observar sus límites. La siguiente mejora de producto consiste en hacer que esa explicación aparezca mediante imágenes y cambios visibles al interactuar.

## Fuentes locales para profundizar

- [Plan que organiza las cinco fases](Plan%20de%20implementacion%20orientado%20a%20escenarios.md).
- [Resultados, cifras y método del primer caso](Primer%20analisis%20reproducible%20-%20Jezero%20y%20candidatas%20terrestres.md).
- [Búsqueda regional: conteos, filtros y cobertura](Fase%204%20-%20busqueda%20regional%20terrestre.md).
- [Fuente y escala: muestra, resultados y pendientes](Fase%205%20-%20expansion%20condicionada.md).
- Código de la experiencia: [App](../../../frontend/src/App.tsx), [búsqueda](../../../frontend/src/features/explore/ExploreWorkspace.tsx), [sensibilidad](../../../frontend/src/features/sensitivity/SensitivityWorkspace.tsx), [globo](../../../frontend/src/ContextGlobe.tsx).
- [Fórmula histórica y ruta obsoleta](../../../backend/app/main.py).
- [Plan propuesto de refactorización](Plan%20de%20refactorizacion%20visual%20del%20frontend.md).

Las verificaciones de las fases se consultaron como evidencia existente. Esta guía no declara haber repetido el procesamiento ni sus pruebas científicas.
