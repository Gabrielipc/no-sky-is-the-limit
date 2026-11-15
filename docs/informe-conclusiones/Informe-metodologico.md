# Conclusiones metodológicas y hoja de ruta del Atlas de análogos planetarios

Informe de síntesis | Corte de evidencia: 15 de noviembre de 2026

## Resumen ejecutivo

El proyecto construyó un sistema exploratorio para localizar ventanas terrestres cuyas propiedades de superficie se parecen a las de una referencia planetaria. La contribución principal es una cadena reproducible que transforma observaciones heterogéneas en descriptores comparables, controla su calidad, filtra por contexto y ordena candidatas. El caso más desarrollado es el abanico de Jezero, en Marte. El sistema ayuda a priorizar lugares para estudio; no demuestra que un lugar sea un análogo geológico integral ni que sea seguro o apropiado para una misión.

La release identificada como etl-30m-r1b registra 1.793.175 ventanas terrestres en 22.308 lotes, de ellas 1.459.470 con calidad topográfica rankable y 174.595 elegibles para el perfil árido publicado. Son ventanas de 3 km con centros separados 10 km, procesadas a una celda de 30 m: se trata de reconocimiento mundial muestreado, no de cobertura continua de 30 m. En una cuadrícula ideal, las huellas representan alrededor del 9 % de la superficie antes de considerar bordes, mar y huecos. [I1, I2]

El modelo no supervisado asociado se ajustó con una muestra de 200.000 de 1.459.164 ventanas rankables fuera de la cuenca reservada de Mojave. Aprende la distribución de los descriptores terrestres, no la verdad de qué constituye un análogo. Cuatro vistas topográficas figuran ajustadas; las vistas espectral, térmica, radar y ambientales no están ajustadas en esa versión. La validación ciega independiente sigue pendiente. [I3]

La experiencia demuestra viabilidad técnica para procesar y resumir una muestra de escala global con procesamiento por lotes, acceso parcial a datos y recursos moderados. No demuestra que cualquier análisis global pueda ejecutarse en una computadora pequeña, ni acredita un costo total o un requisito máximo de memoria: parte del ajuste final se hizo en una VM de GCP y los experimentos tienen alcances diferentes. El principal cuello de botella medido en un ensayo fue la red. [I3, I4]

## 1. Pregunta científica y alcance

La pregunta operativa es: ¿qué ventanas de la Tierra merecen una revisión más profunda por compartir características medibles con una ventana de Marte o, posteriormente, de la Luna? «Parecido» depende de la pregunta: relieve semejante no implica misma mineralogía, historia geológica, clima, procesos, accesibilidad o movilidad. Por ello el atlas separa medición, comparabilidad, elegibilidad y ordenamiento. La resolución espacial, el producto original, la fecha y el soporte condicionan cada conclusión. [I5, I6]

Hay dos rutas de ordenamiento que conviene distinguir. La release del atlas declara etl-quantiles-v1, una distancia basada en resúmenes topográficos y normalización de la población elegible. El modelo motor-similitud-ml-v1 es otra implementación, no supervisada, que usa vistas y covarianzas aprendidas; acompaña a la misma release, pero no debe confundirse automáticamente con el método declarado por el manifiesto del mapa. Las métricas y pesos no son intercambiables entre ambas rutas. [I1, I3, I7]

## 2. Del problema al diseño metodológico

### 2.1 Evolución del análisis

El proyecto partió de un caso acotado Jezero–Tierra: un DTM HiRISE y candidatas terrestres, comparadas en ventanas de 1,8 km y celdas de 60 y 120 m. Se examinaron por separado la distribución de pendientes mediante distancia de Wasserstein y el relieve relativo P95–P5. La búsqueda regional amplió después el reconocimiento a 970 ventanas nuevas de 3 km en Utah, Mojave y Atacama con GMTED2010 a 300/600 m. Un análisis posterior contrastó fuentes y escalas antes de extender la cobertura. Estas etapas son experimentos históricos y sus cifras no deben sumarse al inventario de la release mundial. [I8]

La revisión metodológica identificó cuatro riesgos: modelos de elevación con distinta física, operadores cuyo tamaño físico cambiaba con la celda, denominadores de cobertura engañosos y descriptores estadísticos incapaces de reconocer por sí solos la forma espacial. La respuesta fue fijar huella y distancias físicas, evaluar el soporte por variable, comparar sensores y agregar descriptores de forma y organización como hipótesis a validar. [I5]

### 2.2 Fuentes y preparación

Para la referencia de Jezero se empleó el DTM HiRISE DTEEC_002387_1985_003798_1985_A01. Para el barrido terrestre se seleccionó Copernicus DEM GLO-30 por su inventario casi global y acceso por teselas; Natural Earth define tierra, WorldCover 2021 y JRC Global Surface Water aportan contexto de cobertura y agua. GLO-30 es un modelo de superficie: árboles y estructuras pueden influir en sus elevaciones, a diferencia de un DTM de terreno. La selección de estos datos favorece cobertura y acceso, no garantiza igualdad de calidad entre regiones. [I1, R1–R5]

Las ventanas usan 3 × 3 km, celdas de 30 m, base física de pendiente de 240 m y radio de rugosidad de 360 m. El relieve es P95 menos P5; las pendientes se resumen por P50 y P90. La referencia Jezero de la release tiene relieve 120,27 m, pendiente P50 3,07°, P90 9,24° y rugosidad 7,57 m. Esos valores describen esa huella y ese procedimiento, no todo el cráter. El manifiesto exige 80 % de tierra y 95 % de elevación válida para sus reglas de calidad. [I1]

El procesamiento proyecta y muestrea las fuentes por ventanas, calcula variables y soporte, conserva estados de calidad y escribe resúmenes tabulares. Los controles separan ausencia de cobertura, soporte insuficiente y errores de acceso. La reanudación identifica lotes completos por parámetros y permite reintentar los incompletos. El enriquecimiento de cobertura puede realizarse sin recalcular la topografía. Los manifiestos identifican versión, fuentes, parámetros y recuentos; las entradas científicas originales no se almacenan en Git. [I1, I4, I9]

### 2.3 Elegibilidad antes de interpretar el ranking

Una ventana topográficamente parecida puede estar cubierta por bosque, agua o construcciones. WorldCover y JRC permiten aplicar un perfil de superficie árida expuesta antes de interpretar el resultado. El perfil es una decisión vinculada al objetivo, no una verdad universal: un escenario costero o polar requiere otras reglas. El agua se evalúa con las fuentes disponibles y sus periodos; una clase ausente o una lectura fallida no equivale a ausencia física. [I4, I10]

La release contabiliza 1.336.276 ventanas con cobertura medida y 122.949 sin tesela de cobertura; 123.194 quedan pendientes de verificación de elegibilidad. También registra 331.371 con tierra insuficiente, 1.915 sin DEM y 419 con soporte DEM insuficiente. «Complete» en el manifiesto se refiere al estado operativo de la publicación; no elimina los huecos ni significa que todas las ubicaciones o dimensiones estén medidas. Los conteos de QA, cobertura y elegibilidad responden a categorías diferentes y no deben sumarse entre sí. [I1]

## 3. Desarrollo del modelo que alimenta la búsqueda

No existían suficientes etiquetas independientes de análogos para entrenar un predictor supervisado fiable. Se optó por aprendizaje no supervisado sobre la población terrestre, dejando explícitas las decisiones de pesos y escenarios. El modelo final usa una muestra reproducible de 200.000 ventanas con semilla 20261114 y reserva Mojave fuera del ajuste. Su informe identifica el código 08f92fd y el artefacto model.joblib mediante SHA-256; la verificación de la release reporta cero errores y avisos por referencias lunares ausentes. [I3]

Primero, cada característica se transforma mediante cuantiles empíricos terrestres a una escala normal, para reducir el efecto de unidades y colas diferentes. Después, dentro de cada vista, se estima covarianza robusta con Minimum Covariance Determinant y contracción diagonal del 5 %; la distancia de Mahalanobis tiene en cuenta la correlación entre características. Esto importa porque relieve, pendientes y rugosidad no son pruebas independientes: en un análisis regional, relieve y pendiente P90 tuvieron correlaciones de rango cercanas a 0,95. La distancia se expresa con una transformación basada en χ²; ello facilita la comparación operativa entre vistas, pero no convierte el resultado en una probabilidad de analogía validada. [I7, I11; R12–R14]

Una mezcla gaussiana agrupa regímenes morfológicos y compara las probabilidades de pertenencia con el coeficiente de Bhattacharyya. El número de componentes se selecciona mediante BIC dentro del rango configurado. Las vistas se fusionan con pesos declarados o fusión de rankings; si falta una dimensión, la política explícita puede tratarla como neutral, renormalizar o exigirla. El intervalo reportado refleja la política para información ausente; no debe presentarse como un intervalo de confianza estadístico validado. La reserva espacial evita entrenar sobre Mojave, pero por sí sola no prueba que las candidatas sean correctas: queda por realizar y evaluar la revisión ciega. [I7, R15–R17]

En etl-30m-r1b figuran ajustadas escabrosidad, forma hipsométrica, organización y régimen morfológico. Espectral y radar no tenían mediciones suficientes; térmica contaba con solo 39 ventanas de fondo; entorno superficial y emisividad global aún no se habían muestreado para el ajuste. Las vistas no ajustadas se excluyen de la fusión con aviso. Jezero funciona como referencia; Haworth y De Gerlache requieren ventanas lunares en el almacén. Una búsqueda calculada en consulta necesita el feature store; los resultados precalculados pueden servirse desde la release. [I3]

## 4. Validación realizada y resultados

### 4.1 Armonización topográfica

Se compararon mediciones pareadas de GLO-30 y SRTM frente a 3DEP en controles de desierto, dos bosques y costa. Al pasar de una base de pendiente de 60 m a 240 m, la discrepancia absoluta mediana por celda frente a 3DEP bajó aproximadamente 74 % en Utah y entre 51 % y 55 % en los otros tres controles. En Utah la discrepancia de GLO-30 a 240 m fue aproximadamente 0,05°, frente a 0,32° para SRTM. La costa exhibió diferencias más grandes de relieve y soporte limitado de rugosidad. Estos ensayos justifican una base física fija, pero cuatro controles no establecen precisión mundial ni eliminan sesgos por dosel, costa o fuente. [I11, I12; R6, R7]

La redundancia de variables motivó el tratamiento de covarianza y la búsqueda de rasgos de forma. Un escarpe continuo y lomas dispersas pueden compartir cuantiles, por lo que un ranking topográfico exige inspección de imágenes y evaluación ciega de morfología. En experimentos de selección regional se usaron 973 ventanas en 16 bloques; Mojave completo se reservó como alternativa espacial. Los documentos históricos sobre partición contienen revisiones y esquemas distintos: debe consultarse el manifiesto y el esquema exacto de cada ensayo antes de atribuirle independencia espacial. [I5, I11]

### 4.2 Minerales y puente entre instrumentos

CRISM, en Marte, y EMIT L2B, en Tierra, producen magnitudes y denominadores distintos. Sus mapas permiten contexto mineralógico, pero no corresponde restar sus porcentajes como si midieran lo mismo. Se desarrolló un operador sobre reflectancias CRISM, EMIT L2A y M³ para acercar definiciones, umbrales y denominadores. En una franja CRISM de 137.924 píxeles válidos, BD1900R2 reprodujo el producto oficial con correlación cercana a 1 y diferencia absoluta mediana 4,9 × 10⁻⁸; otros parámetros variaron y algunos discreparon por versiones. Esto valida una parte de la implementación frente a ese producto, no demuestra equivalencia integral entre sensores o identificación mineral de campo. [I13; R8–R11]

En Jezero la huella espectral de 1,8 km tuvo 87,23 % de soporte y la de 3 km 72,26 %, inferior al umbral del 80 %. Restricciones de bandas atmosféricas y resolución impiden algunos cruces; varios umbrales son iniciales. La evidencia local incluyó ejecución offline y lecturas remotas parciales. En la release del modelo el espectro no participa en el ranking ajustado; debe tratarse como contexto o investigación pendiente, no como similitud mineral validada. [I13, I3]

### 4.3 Evidencia operacional de escala

Un benchmark de cinco bloques de 100 km con cuatro workers midió 500 ventanas topográficas en 780 s y 730 MB de transferencia, con 491 rankables. La fase de cobertura duró 829 s y transfirió 816 MB; hubo 391 ventanas medidas y 100 sin tesela polar. El ritmo observado fue cercano a 1 MB/s y, con teselas locales, se midieron 0,03 s por ventana para cobertura. Son mediciones de un entorno y cinco estratos, no un benchmark universal. [I4]

El documento operacional estimó alrededor de 140 GB de transferencia para completar el enriquecimiento de cobertura por teselas: 124 GB publicados para WorldCover más una estimación de ~16 GB para JRC. Estimó ~39 horas a la velocidad observada, o ~3 horas a 100 Mb/s, más ~3 horas de CPU con cuatro workers. Es una extrapolación, no una factura ni una medición integral de la ejecución. La estimación de GLO-30 de ~0,67 TB se basa en extrapolar una muestra geográficamente sesgada y tampoco equivale a la descarga efectiva. El resultado útil es que no hace falta guardar todos los originales a la vez para generar descriptores de una muestra mundial: el costo depende de red, lectura, caché, resolución, densidad, almacenamiento temporal y producto. [I4, I14]

## 5. Capacidad actual y límites de interpretación

El sistema puede explorar un catálogo mundial muestreado, mostrar calidad y elegibilidad, comparar una referencia Jezero con ventanas terrestres, ordenar candidatas por descriptores disponibles y reproducir resultados versionados. Puede explicar algunas contribuciones por vista y mostrar faltantes; también existen análisis experimentales para controles topográficos y puentes espectrales. La presencia de código o de una fuente en el catálogo no prueba que esa capa haya sido medida globalmente ni que forme parte del ajuste publicado. [I1, I3, I7]

No puede afirmar equivalencia geológica completa, identificar la composición real sin contraste, inferir directamente condiciones pasadas de Marte, evaluar seguridad de navegación o certificar accesibilidad de una zona. Tampoco proporciona un ranking mundial exhaustivo: la separación de 10 km omite áreas entre ventanas y favorece lo que la malla y los filtros observan. El GLO-30 representa superficie y las clases de cobertura corresponden a productos y épocas concretas. Los parámetros, los pesos y la población de normalización pueden cambiar el orden; fuentes, escala, soporte y selección introducen incertidumbre. Un número alto no es una probabilidad científica de éxito. [I1, I5, I10]

## 6. Roadmap propuesto

Las fases siguientes son recomendaciones, no trabajo ya completado. Los criterios son puertas de decisión propuestas y requieren fijar responsables, presupuesto y umbrales antes de ejecutarlas.

### Fase 1  Consolidar la evidencia y la reproducibilidad

Congelar release, código, contratos, entorno, hash del modelo y manifiestos; publicar por separado cobertura, elegibilidad y errores. Documentar en la interfaz qué algoritmo produce cada ranking, qué dimensiones están activas y qué significa cada puntuación. Reejecutar verificación y documentar hardware, tiempo, RAM, disco, red y costo. Criterio de salida: otra persona puede reconstruir una muestra y reconciliar los recuentos con los manifiestos sin acceso a credenciales ni originales en Git.

### Fase 2  Validar la utilidad científica del ranking

Definir antes del análisis una pregunta geológica, criterios observables, controles positivos y negativos, métricas top-k y protocolo de revisión ciega por especialistas. Mantener cuencas independientes como reserva; separar selección de variables, calibración y evaluación final. Medir acuerdo entre revisores, precisión o utilidad por posición, recuperación de sitios conocidos y desempeño frente a una línea base simple. Criterio de salida: resultados por cuenca y límites publicados, sin usar el conjunto reservado para ajustar decisiones.

### Fase 3  Robustez y reducción del sesgo

Recalcular una muestra estratificada con DEM alternativos y variar escala, huella, soporte y pesos. Medir estabilidad de top-k y reportar grupos de candidatas prácticamente empatadas. Incorporar descriptores de forma solo si añaden información fuera de muestra. Densificar a paso de 3 km en regiones prometedoras; la densidad ideal crece aproximadamente 11 veces y requiere un presupuesto nuevo. Incorporar perfiles árido, costero y polar con fuentes y máscaras adecuadas; WorldCover no cubre la Antártida en el ensayo. [I4, I5, I14]

### Fase 4  Incorporar dimensiones con comparabilidad demostrada

Validar el operador espectral con muestras de referencia, espectros y controles independientes, propagando QA y resolución efectiva; resolver huecos de bandas y calibrar umbrales. Para térmica y radar comparar propiedades realmente equivalentes, geometrías y condiciones temporales; no equiparar temperatura instantánea con inercia térmica. Incorporar una vista al ranking únicamente si existe soporte suficiente, mejora medible frente a la línea base y comportamiento robusto en reserva espacial. Mantener el resto como contexto. [I6, I13]

### Fase 5  Escalar producto y operaciones

Procesar por tesela, reutilizar caché, aplicar enriquecimiento selectivo y medir bytes, memoria, latencia, almacenamiento y costo por ventana útil. Automatizar controles de integridad, reintentos, versiones y observabilidad. Priorizar revisión humana, acceso y permisos, y validación de campo de un subconjunto. Para Luna, completar el almacén y validar fuentes LOLA, iluminación, temperatura y cobertura apropiadas antes de presentar búsquedas polares como operativas. Definir un presupuesto y umbrales de disponibilidad con base en mediciones reales.

## 7. Referencias y créditos

Las referencias I identifican evidencia interna del repositorio; R identifica proveedores y metodología externa. Las URL son enlaces a fuentes originales o documentación oficial. La inclusión en el catálogo no implica uso efectivo en cada análisis. Deben conservarse atribuciones y licencias de cada producto al redistribuir derivados.

### Evidencia interna del proyecto

I1. Release etl-30m-r1b, manifiesto: ml/modelos/etl-30m-r1b/release-manifest.json. Define conteos, perfil, malla, fuentes y ranking del atlas.
I2. Elección de fuentes y costo de cobertura mundial: docs/01-vigentes/etapa-actual-armonizacion/Eleccion de fuentes y costo de cobertura mundial.md. Estimaciones de volumen y malla.
I3. Modelo de release: ml/modelos/etl-30m-r1b/README.md y model.json. Población, muestra, hash, vistas y estado.
I4. Barrido mundial: robustez, cobertura, costo y publicación: docs/01-vigentes/operacion-y-datos/Barrido mundial - robustez cobertura costo y publicacion.md; evidencia en docs/evidencia-barrido/benchmark.json.
I5. Revisión metodológica del Atlas de 30 m: docs/01-vigentes/arquitectura-y-vision/revision-metodologica-atlas-30-m.md.
I6. Auditoría de armonización y features frente a fuentes del challenge: docs/01-vigentes/etapa-actual-armonizacion/Auditoria de armonizacion y features frente a fuentes del challenge.md.
I7. Motor de similitud ML no supervisado: docs/01-vigentes/etapa-actual-armonizacion/Motor de similitud ML no supervisado.md; implementación pipelines/similarity_ml.py y especificación specs/analysis/motor-similitud-ml-v1.json. Sus cifras históricas de ajuste no sustituyen I3.
I8. README.md y entregas de fases 1 a 5 en docs/02-versiones-anteriores/etapa-1-mvp-escenarios/; evidencia en docs/evidencia-fase-1/ a evidencia-fase-5/.
I9. Código pipelines/etl_stream.py, pipelines/etl_store.py y scripts/etl_pipeline.py; contratos en specs/ y manifiestos de la release.
I10. Código de elegibilidad pipelines/etl_eligibility.py; perfil declarado en I1.
I11. Tercera entrega, muestreo estratificado y puentes entre cuerpos: docs/01-vigentes/etapa-actual-armonizacion/Tercera entrega - muestreo estratificado y puentes entre cuerpos.md; evidencia docs/evidencia-entrega-3/.
I12. Validación de armonización topográfica en desierto bosque y costa: docs/01-vigentes/etapa-actual-armonizacion/Validacion de armonizacion topografica en desierto bosque y costa.md; evidencia docs/evidencia-validacion-topografica/.
I13. Puente espectral con un solo operador en tres cuerpos: docs/01-vigentes/etapa-actual-armonizacion/Puente espectral con un solo operador en tres cuerpos.md; resultados docs/evidencia-puente-espectral/resultados.json.
I14. Atlas de 30 m, operación: docs/01-vigentes/operacion-y-datos/Atlas de 30 m - operacion.md; estimaciones adicionales en I2.

### Datos y metodología externos

R1. ESA y Copernicus. Copernicus DEM GLO-30, modelo digital de superficie. DOI: https://doi.org/10.5270/ESA-c5d3d65 ; acceso público COG: https://copernicus-dem-30m.s3.amazonaws.com/readme.html
R2. McEwen, A. y equipo HiRISE. MRO HiRISE Digital Terrain Model, MRO-M-HIRISE-5-DTM-V1.0. NASA Planetary Data System: https://pds.nasa.gov/ds-view/pds/viewDataset.jsp?dsid=MRO-M-HIRISE-5-DTM-V1.0
R3. ESA WorldCover 10 m 2021 v200. DOI: https://doi.org/10.5281/zenodo.7254221 ; documentación y atribución: https://esa-worldcover.org/en/data-access
R4. Comisión Europea JRC y Google. Global Surface Water, producto Occurrence: https://global-surface-water.appspot.com/download . La versión y periodo usados constan en I1.
R5. Natural Earth. Land, escala 1:10 millones, versión 5.1.1: https://www.naturalearthdata.com/downloads/10m-physical-vectors/10m-land/
R6. USGS. 3D Elevation Program, productos de elevación: https://www.usgs.gov/3d-elevation-program
R7. NASA. SRTM y NASADEM: https://data.nasa.gov/dataset/nasadem-merged-dem-global-1-arc-second-v001
R8. NASA LP DAAC. EMIT L2B Mineral Identification y Band Depth, guía de usuario: https://lpdaac.usgs.gov/documents/1660/EMITL2BMIN_User_Guide_V1.pdf
R9. NASA PDS Geosciences Node. CRISM, datos y documentación: https://pds-geosciences.wustl.edu/missions/mro/crism.htm
R10. NASA PDS Geosciences Node. Chandrayaan-1 Moon Mineralogy Mapper M³: https://pds-geosciences.wustl.edu/missions/chandrayaan1/m3.htm
R11. NASA PDS Geosciences Node. THEMIS y Diviner: https://pds-geosciences.wustl.edu/missions/odyssey/themis.html y https://pds-geosciences.wustl.edu/missions/lro/diviner.htm . Usados como contexto o investigación de dimensiones, no como vistas ajustadas de I3.
R12. Rousseeuw, P. J. y Van Driessen, K. (1999). A Fast Algorithm for the Minimum Covariance Determinant Estimator. Technometrics 41, 212–223. https://doi.org/10.1080/00401706.1999.10485670
R13. Mahalanobis, P. C. (1936). On the Generalised Distance in Statistics. Proceedings of the National Institute of Sciences of India 2, 49–55. Referencia histórica de la distancia; implementación concreta en I7.
R14. scikit-learn. QuantileTransformer y robust covariance, documentación de implementación: https://scikit-learn.org/stable/modules/generated/sklearn.preprocessing.QuantileTransformer.html y https://scikit-learn.org/stable/modules/covariance.html
R15. Schwarz, G. (1978). Estimating the Dimension of a Model. Annals of Statistics 6, 461–464. https://doi.org/10.1214/aos/1176344136
R16. Bhattacharyya, A. (1943). On a Measure of Divergence between Two Statistical Populations Defined by Their Probability Distributions. Bulletin of the Calcutta Mathematical Society 35, 99–109.
R17. Cormack, G. V., Clarke, C. L. A. y Buettcher, S. (2009). Reciprocal Rank Fusion outperforms Condorcet and individual Rank Learning Methods. https://doi.org/10.1145/1571941.1572114 . La variante ponderada y sus opciones son decisiones de implementación del proyecto.

## Nota de lectura

Este informe sintetiza la evidencia disponible en el repositorio al corte indicado; las cifras de experimentos, costos y estado operativo pueden cambiar con nuevas corridas. Las fuentes externas se citan para atribuir datos y métodos, no como aval institucional del proyecto. Los derechos, condiciones de uso y citas exigidas por cada proveedor deben revisarse para cualquier publicación o redistribución.
