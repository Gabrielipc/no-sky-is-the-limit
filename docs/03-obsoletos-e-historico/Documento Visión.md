## Exploración inteligente de análogos planetarios

**Estado:** Visión inicial de producto  
**Nombre del proyecto:** Por definir  
**Propósito del documento:** Servir como referencia para las decisiones de investigación, diseño y desarrollo del proyecto. La arquitectura, los modelos concretos y la selección definitiva de datos se definirán posteriormente.

---

## 1. Visión

Crear una plataforma que permita descubrir, comparar y explorar lugares de la Tierra que puedan servir como análogos para la exploración de la Luna y Marte.

La plataforma combinará datos de observación, machine learning y visualización interactiva para responder una pregunta central:

> **¿Qué lugares de la Tierra podrían ayudarnos a preparar una misión concreta en la Luna o Marte, por qué serían útiles y cuáles son los límites de esa comparación?**

El proyecto se concibe tanto como una herramienta para investigadores y equipos de misión como una experiencia accesible para personas que quieran explorar, aprender y descubrir conexiones entre nuestro planeta y otros mundos.

Su propuesta une dos capacidades inseparables: un **motor de descubrimiento científico** y una **experiencia visual de exploración**.

## 2. Contexto y oportunidad

La Tierra es un laboratorio natural para preparar la exploración espacial. Sus desiertos, regiones polares, paisajes volcánicos, cráteres, montañas y otros entornos pueden ayudar a estudiar procesos planetarios y ensayar tecnologías, instrumentos y operaciones.

Sin embargo, encontrar un buen análogo no consiste en localizar un paisaje que se vea parecido a otro planeta. Un lugar puede ser útil para estudiar determinados materiales y poco adecuado para probar movilidad; otro puede ofrecer un relieve comparable, pero diferir mucho en temperatura o composición.

Además, ningún lugar de la Tierra reproduce por completo las condiciones de la Luna o Marte. Por eso, una comparación útil debe explicar tanto sus fortalezas como sus límites.

La oportunidad del proyecto está en utilizar datos abiertos de la Tierra, la Luna y Marte para buscar estas relaciones de manera más sistemática, descubrir candidatos potencialmente inesperados y comunicar los resultados de una forma que invite a explorarlos.

## 3. Problema

Una persona que necesita preparar una misión o estudiar un proceso planetario enfrenta varias dificultades:

- Las semejanzas relevantes dependen del objetivo: movilidad, geología, recursos, instrumentos u operaciones pueden requerir criterios diferentes.
    
- La información está distribuida entre múltiples conjuntos de datos, con escalas, coberturas y resoluciones distintas.
    
- Los sitios análogos conocidos son valiosos, pero una búsqueda limitada a ellos puede dejar fuera otras ubicaciones prometedoras.
    
- Una puntuación única de «parecido» puede ocultar diferencias importantes y dar una impresión de precisión que los datos no justifican.
    
- Los resultados científicos pueden ser difíciles de interpretar para personas sin conocimientos especializados.
    

El proyecto abordará estas dificultades mediante una búsqueda multidimensional y explicable, acompañada de herramientas visuales que permitan comprender los hallazgos.

## 4. Propuesta de valor

La plataforma permitirá pasar de una necesidad de misión a una selección razonada de lugares candidatos.

Una persona podrá describir qué desea investigar o probar, seleccionar un destino y ajustar la importancia de distintas características. El sistema buscará áreas terrestres que presenten relaciones relevantes con una región lunar o marciana de referencia y mostrará:

- Por qué cada lugar aparece como candidato.
    
- Qué dimensiones presentan similitudes.
    
- Qué diferencias son importantes.
    
- Qué datos respaldan la comparación y cuáles faltan.
    
- Para qué actividades podría ser útil el lugar.
    
- Qué aspectos requieren una investigación o validación adicional.
    

La plataforma no presentará un lugar como «el equivalente terrestre» de otro mundo. Presentará **candidatos para propósitos concretos**, con evidencia y limitaciones visibles.

## 5. Principios del proyecto

### 5.1. La misión guía la búsqueda

La relevancia de un análogo depende de lo que se quiera hacer. La plataforma partirá del propósito de la misión y permitirá traducirlo en criterios de búsqueda.

Un lugar puede ser adecuado para ensayar navegación robótica y no serlo para investigar hielo o composición mineral. Ambas conclusiones pueden ser válidas al mismo tiempo.

### 5.2. La comparación es multidimensional

Los lugares se caracterizarán mediante un conjunto de dimensiones, según los datos disponibles. Entre ellas podrían incluirse:

- Relieve, pendiente y rugosidad.
    
- Geología, mineralogía y materiales superficiales.
    
- Temperatura y otros extremos ambientales.
    
- Agua, hielo o características relacionadas.
    
- Polvo, erosión y otros procesos superficiales.
    
- Condiciones relevantes para operaciones robóticas o humanas.
    

Las dimensiones concretas de la primera versión se seleccionarán tras estudiar la disponibilidad y comparabilidad de los datos.

### 5.3. El machine learning es parte central del descubrimiento

El proyecto tendrá un enfoque fuerte en machine learning o deep learning para representar lugares, identificar patrones multidimensionales y recuperar candidatos relevantes.

La elección de modelos y métodos se definirá durante la fase de arquitectura e investigación. Su utilidad se evaluará frente a métodos de referencia y mediante el análisis de resultados concretos.

### 5.4. La evidencia debe ser comprensible

Cada recomendación debe poder explorarse y cuestionarse. La plataforma distinguirá entre características medidas, indicadores indirectos, inferencias del modelo y datos no disponibles.

Si se utiliza una puntuación para ordenar candidatos, su significado, los criterios que la componen y sus límites deben ser comprensibles.

### 5.5. Los límites de la analogía son parte del hallazgo

El proyecto hará visibles las diferencias relevantes entre un lugar terrestre y su referencia planetaria. Entre ellas pueden estar la gravedad, la atmósfera o el vacío, la radiación, la iluminación y condiciones superficiales que los datos no permitan comparar.

La plataforma identificará candidatos para investigar y evaluar; no certificará por sí sola la idoneidad de un sitio para una misión.

### 5.6. La presentación es parte esencial del producto

La visualización no será una capa decorativa. Permitirá descubrir patrones, interpretar comparaciones y comunicar resultados a personas con distintos niveles de conocimiento.

La experiencia deberá ser atractiva, clara y científicamente honesta.

## 6. Personas usuarias

### Investigadores y equipos de misión

Personas que necesitan identificar o comparar entornos terrestres para preparar actividades relacionadas con la exploración espacial.

Sus necesidades incluyen:

- Traducir una misión en criterios de búsqueda.
    
- Seleccionar una región planetaria de referencia.
    
- Ajustar la importancia de distintas dimensiones.
    
- Comparar candidatos y examinar la evidencia.
    
- Conocer fuentes, escalas, limitaciones y datos faltantes.
    
- Conservar o compartir resultados para una evaluación posterior.
    

### Estudiantes, educadores y público general

Personas que desean aprender sobre la Tierra, la Luna y Marte mediante la exploración.

Sus necesidades incluyen:

- Comenzar sin conocimientos científicos avanzados.
    
- Descubrir lugares y relaciones sorprendentes.
    
- Explorar visualmente paisajes planetarios y terrestres.
    
- Entender, mediante explicaciones claras, por qué dos lugares pueden compararse y en qué difieren.
    
- Participar en experiencias lúdicas basadas en preguntas científicas.
    

## 7. Experiencia central

La experiencia principal se organizará como un recorrido:

> **Describir una misión → configurar la búsqueda → descubrir candidatos → explorar y comparar → comprender la evidencia y los límites.**

### 7.1. Describir una misión

La persona podrá comenzar explicando qué desea hacer en lenguaje natural o seleccionando un escenario preparado.

Por ejemplo:

> «Quiero probar un rover que tendrá que desplazarse por terreno marciano volcánico, con pendientes variables y superficies rocosas».

El sistema propondrá una interpretación inicial de la misión: destino, actividad y dimensiones relevantes. La persona podrá revisar y corregir esa interpretación antes de buscar.

La descripción de la misión ayudará a configurar el análisis, pero la comparación deberá estar vinculada a una región planetaria identificable y a datos concretos.

### 7.2. Configurar prioridades

La persona podrá ajustar la importancia de las dimensiones según sus necesidades. Por ejemplo:

- Dar mayor peso a la pendiente y el relieve para una prueba de movilidad.
    
- Priorizar materiales para una investigación geológica.
    
- Priorizar condiciones frías o presencia de hielo para otro tipo de operación.
    

La herramienta mostrará cómo estos ajustes afectan los resultados. Los criterios disponibles dependerán de la cobertura y calidad de los datos.

### 7.3. Descubrir candidatos

El sistema presentará áreas terrestres candidatas mediante un mapa y una lista comparativa. La búsqueda podrá abarcar tanto lugares conocidos como áreas menos estudiadas dentro de la cobertura procesada.

La plataforma comunicará de manera explícita qué regiones fueron analizadas. Un posible hallazgo se presentará como candidato hasta revisar la evidencia y los estudios previos pertinentes.

### 7.4. Explorar y comparar

Cada candidato tendrá una ficha que permita responder:

- ¿Dónde está y qué área se ha analizado?
    
- ¿Con qué región lunar o marciana se compara?
    
- ¿En qué dimensiones muestra similitud?
    
- ¿Qué diferencias o vacíos de información existen?
    
- ¿Qué actividad podría ensayarse o investigarse allí?
    
- ¿Qué fuentes y métodos sustentan el resultado?
    

Cuando sea posible, la persona podrá explorar ambos lugares mediante vistas interactivas y capas de información.

### 7.5. Refinar la búsqueda

La persona podrá cambiar las prioridades de la misión y observar cómo se reorganizan los candidatos. El sistema explicará qué dimensiones contribuyeron a ese cambio.

Este proceso permitirá experimentar con distintas definiciones de utilidad y entender los compromisos entre ellas.

## 8. Capacidades del motor de descubrimiento

El motor deberá evolucionar hacia las siguientes capacidades:

### Representación de lugares

Construir perfiles de áreas terrestres y planetarias a partir de varias fuentes de información. Estos perfiles podrán combinar características físicas y representaciones aprendidas por modelos.

### Búsqueda multidimensional

Identificar áreas terrestres que presenten patrones relevantes para una región planetaria y una misión específicas.

### Personalización por misión

Adaptar la clasificación de candidatos a las dimensiones y prioridades elegidas por la persona usuaria.

### Explicabilidad

Mostrar las principales razones de cada resultado y permitir inspeccionar las dimensiones por separado.

### Gestión de incertidumbre y datos faltantes

Comunicar qué datos existen, qué datos faltan y cómo estas condiciones afectan la comparación. La ausencia de información no debe presentarse como evidencia de similitud.

### Evaluación del modelo

Contrastar los resultados con métodos de referencia, casos conocidos y revisión de ejemplos concretos. El proyecto deberá investigar si el enfoque de machine learning aporta valor a la búsqueda y bajo qué condiciones.

## 9. Experiencia visual e inmersiva

La plataforma buscará que cada resultado pueda experimentarse como una exploración.

La visión incluye:

- Un mapa o globo para descubrir ubicaciones terrestres.
    
- Representaciones interactivas de regiones de la Tierra, la Luna y Marte.
    
- Vistas comparativas de dos lugares a escalas coherentes.
    
- Capas visuales para explorar las dimensiones disponibles.
    
- Marcadores y explicaciones que conecten lo observado con la misión.
    
- Transiciones narrativas que permitan viajar entre el destino planetario y sus candidatos terrestres.
    

La fidelidad de cada representación dependerá de los datos disponibles. La interfaz deberá distinguir entre información respaldada por datos y elementos visuales utilizados para facilitar la comprensión.

La experiencia puede ser visualmente rica sin presentar como hechos detalles que no se conocen.

## 10. Accesibilidad y dimensión lúdica

La plataforma debe poder disfrutarse sin conocimientos científicos previos, sin perder profundidad para quienes sí los tienen.

Se propone una experiencia adaptable:

**Exploración guiada:** preguntas sencillas, misiones preparadas, explicaciones breves y recorridos visuales.

**Exploración avanzada:** controles sobre las dimensiones, consulta de datos, detalles metodológicos y comparación entre candidatos.

La dimensión lúdica podrá tomar la forma de desafíos, recorridos o preguntas como:

> «¿Qué lugar elegirías para probar un rover que debe recorrer un terreno con pendientes variables?»

Después de la elección, la plataforma explicará qué evidencia favorece o limita esa decisión. El objetivo es que jugar y aprender formen parte del mismo proceso de exploración.

## 11. Alcance de la primera demostración

La primera demostración deberá probar el recorrido completo con datos reales:

1. Presentar una misión o seleccionar un escenario.
    
2. Identificar una región planetaria de referencia.
    
3. Configurar las dimensiones relevantes.
    
4. Buscar y ordenar candidatos terrestres.
    
5. Explorar visualmente al menos un candidato y su referencia.
    
6. Explicar similitudes, diferencias, fuentes y límites.
    
7. Mostrar cómo cambia el resultado al modificar una prioridad.
    

La ambición es que la plataforma evolucione para trabajar con la Luna y Marte, múltiples dimensiones y varios escenarios de misión. La cobertura exacta de la primera demostración dependerá de la investigación de datos, la validación de los métodos y el tiempo disponible.

El proyecto priorizará completar una experiencia integrada y defendible mientras amplía progresivamente destinos, variables y alcance geográfico.

## 12. Criterios para evaluar el éxito

El proyecto tendrá éxito en la medida en que pueda demostrar que:

- **Responde a una necesidad de misión:** los resultados cambian de forma comprensible cuando cambian las prioridades.
    
- **Encuentra candidatos fundamentados:** los lugares presentados cuentan con evidencia y una justificación verificable.
    
- **Aprovecha el aprendizaje automático con propósito:** su contribución se evalúa y se puede explicar frente a alternativas de referencia.
    
- **Comunica la incertidumbre:** no confunde ausencia de datos con similitud ni presenta resultados como certezas que no son.
    
- **Permite explorar visualmente:** las representaciones ayudan a entender la comparación.
    
- **Resulta accesible:** una persona sin formación especializada puede seguir la historia y aprender de ella.
    
- **Conserva profundidad científica:** una persona investigadora puede examinar criterios, fuentes y limitaciones.
    
- **Puede ampliarse:** la propuesta admite nuevos datos, destinos y escenarios sin perder sus principios centrales.
    

## 13. Preguntas abiertas para la siguiente fase

Las siguientes decisiones se desarrollarán en la etapa de investigación y arquitectura:

1. ¿Qué dimensiones ofrecen la mejor combinación de relevancia científica, cobertura y comparabilidad entre cuerpos planetarios?
    
2. ¿Qué regiones de la Luna y Marte servirán como primeras referencias y por qué?
    
3. ¿Qué áreas terrestres podrán procesarse y con qué cobertura?
    
4. ¿Cómo se representarán los lugares para permitir una búsqueda multidimensional?
    
5. ¿Qué enfoque de machine learning es más adecuado y cómo se entrenará o adaptará?
    
6. ¿Cómo se evaluará la calidad de los candidatos cuando no existan etiquetas completas de análogos?
    
7. ¿Cómo se incorporarán las prioridades de una misión en la búsqueda?
    
8. ¿Qué explicaciones y señales de incertidumbre podrá ofrecer el sistema?
    
9. ¿Qué nivel de reconstrucción visual permiten los datos disponibles?
    
10. ¿Cómo se articularán las experiencias guiada y avanzada?
    
11. ¿Qué preparación previa y qué trabajo durante el evento permiten las reglas aplicables al reto?
    

## 14. Norte del proyecto

El proyecto aspira a convertir los datos de nuestro planeta y de otros mundos en una herramienta para descubrir posibilidades de exploración.

Su valor está en conectar una necesidad concreta con una búsqueda inteligente, hacer visibles las razones detrás de cada candidato y permitir que tanto especialistas como público general recorran y comprendan esos lugares.

**Queremos que una persona pueda imaginar una misión, descubrir dónde empezar a prepararla en la Tierra y entender tanto las conexiones como las diferencias entre ambos mundos.**