## Plataforma de búsqueda y exploración de análogos planetarios

**Estado:** Propuesta técnica inicial  
**Propósito:** Servir como base para la investigación, implementación y futuras iteraciones del proyecto.  
**Relación con el proyecto:** Este documento desarrolla técnicamente la visión de una plataforma para descubrir y explorar análogos terrestres de la Luna y Marte.

---

## 1. Resumen ejecutivo

El proyecto consistirá en una plataforma que permita descubrir, comparar y explorar lugares terrestres que puedan servir como análogos para misiones en la Luna y Marte.

La solución combinará:

- Datos de observación de la Tierra, la Luna y Marte.
    
- Procesamiento geoespacial y generación de variables científicas derivadas.
    
- Comparación multidimensional ajustada a una misión.
    
- Computer vision y machine learning para identificar patrones espaciales y recuperar candidatos.
    
- Visualización geoespacial y representaciones interactivas.
    
- Explicaciones sobre la evidencia, los límites y la incertidumbre de cada resultado.
    

La arquitectura propuesta utiliza **React y TypeScript** en el frontend, **CesiumJS** como motor geoespacial principal, **Three.js** para visualizaciones personalizadas y **Python con FastAPI** para la API y el procesamiento.

El motor de búsqueda será **híbrido**: combinará variables físicas interpretables con representaciones aprendidas mediante machine learning. La contribución de cada componente se evaluará experimentalmente.

Este documento fija una dirección técnica inicial. No implica que los conjuntos de datos, modelos o métodos de comparación ya hayan sido probados o validados para el proyecto.

## 2. Objetivo técnico

Construir un sistema capaz de ejecutar el siguiente recorrido:

> **Descripción de una misión → configuración de criterios → selección de una región planetaria → búsqueda de candidatos terrestres → comparación visual → explicación de la evidencia y sus límites.**

El sistema deberá permitir que una persona investigadora ajuste la importancia de las dimensiones según su misión y que una persona sin formación especializada explore los mismos resultados mediante una experiencia visual y guiada.

## 3. Decisiones técnicas iniciales

|Área|Propuesta inicial|Estado|
|---|---|---|
|Interfaz|React + TypeScript|Dirección recomendada.|
|Visualización geoespacial|CesiumJS|Motor principal recomendado; requiere pruebas con los productos planetarios elegidos.|
|Escenas personalizadas|Three.js|Uso selectivo donde CesiumJS no cubra la experiencia deseada.|
|API|Python + FastAPI|Dirección recomendada.|
|Procesamiento geoespacial|GDAL, Rasterio, GeoPandas y PyProj|Conjunto inicial de herramientas a validar según los formatos.|
|Análisis numérico|NumPy, SciPy y xarray|Propuesta inicial.|
|Machine learning|PyTorch y scikit-learn|Propuesta inicial para experimentación y evaluación.|
|Datos espaciales y metadatos|PostgreSQL + PostGIS|Opción recomendada para el catálogo y las consultas espaciales.|
|Búsqueda de embeddings|FAISS o pgvector|Pendiente de elegir según escala y necesidades.|
|Almacenamiento de archivos|Almacenamiento de objetos o archivos locales|Elección pendiente según despliegue y volumen.|
|Procesos prolongados|Procesos de trabajo separados; cola cuando sea necesaria|Dirección recomendada.|
|Modelo de ML|Enfoque híbrido con representaciones aprendidas|Pendiente de investigación y evaluación.|
|Proveedores de datos y terreno|NASA, USGS y otros; proveedores visuales por evaluar|Pendiente de selección por producto y región.|

Estas elecciones son puntos de partida y pueden cambiar si las pruebas revelan una alternativa mejor.

## 4. Principios de arquitectura

### 4.1. La misión configura la búsqueda

La similitud no será una propiedad universal de dos lugares. Dependerá del propósito de la misión, de las dimensiones seleccionadas y de la evidencia disponible.

### 4.2. El sistema combinará varias formas de evidencia

La búsqueda integrará tanto variables físicas interpretables como patrones espaciales aprendidos por modelos, cuando existan datos y validación suficientes.

### 4.3. El procesamiento pesado se separará de la interacción

La descarga, preparación de datos y generación de representaciones se realizarán principalmente por adelantado o mediante procesos independientes. La interacción del usuario consultará productos ya preparados siempre que sea posible.

### 4.4. Cada resultado tendrá procedencia

Será posible identificar qué productos, versiones y transformaciones contribuyeron a una comparación.

### 4.5. La falta de datos será explícita

La ausencia de información no se tratará como similitud ni como diferencia. El sistema mostrará qué dimensiones no pudieron evaluarse.

### 4.6. La visualización respetará los límites de los datos

Las representaciones deberán distinguir entre información observada, productos derivados y elementos visuales ilustrativos.

### 4.7. El sistema propondrá candidatos

Los resultados serán una ayuda para investigar y priorizar lugares. La plataforma no certificará por sí sola que un sitio es adecuado para una misión.

## 5. Arquitectura general

```
                     FUENTES DE DATOS
       Tierra                            Luna / Marte
 NASA Earthdata, USGS y otros       NASA PDS, USGS, ESA y otros
          │                                  │
          └────────────────┬─────────────────┘
                           ▼
              INGESTA Y CATÁLOGO DE DATOS
     productos · versiones · cobertura · calidad · acceso
                           │
                           ▼
             PROCESAMIENTO Y ARMONIZACIÓN
  coordenadas · escala · máscaras · variables · procedencia
                           │
                           ▼
                 CATÁLOGO DE REGIONES
  perfiles físicos · representaciones aprendidas · metadatos
                           │
                           ▼
               MOTOR DE BÚSQUEDA DE ANÁLOGOS
 filtros · similitud multidimensional · pesos · explicaciones
                           │
                           ▼
                        FASTAPI
               API y coordinación de procesos
                           │
                           ▼
                REACT + VISUALIZACIÓN 3D
  misión · ajustes · mapa · comparación · capas · narrativa
```

La arquitectura se organizará en dos flujos:

1. **Flujo de preparación:** incorporación de datos, procesamiento, cálculo de variables y generación de índices.
    
2. **Flujo interactivo:** interpretación de la misión, búsqueda en el catálogo, comparación y exploración de resultados.
    

## 6. Flujo de datos

### 6.1. Descubrimiento y selección

Cada producto candidato se evaluará por:

- Relevancia para una dimensión de comparación.
    
- Cobertura geográfica y temporal.
    
- Resolución y calidad.
    
- Formato y facilidad de acceso.
    
- Condiciones de uso.
    
- Compatibilidad con otros productos.
    
- Posibilidad de mantener trazabilidad hasta la fuente.
    

Se priorizará la integración de datos que aporten información útil y comparable. La cantidad de productos recopilados no será, por sí sola, una medida de progreso.

### 6.2. Ingesta y catálogo

El sistema registrará para cada producto, como mínimo:

```
Identificador y nombre
Fuente, misión e instrumento
Versión del producto
Variable física y unidades
Cobertura geográfica y temporal
Resolución y escala efectiva
Sistema de coordenadas
Referencia vertical
Formato y mecanismo de acceso
Máscaras, calidad y vacíos conocidos
Condiciones de uso y atribución
Fecha de incorporación
Transformaciones realizadas
```

Los datos originales y los derivados deberán poder distinguirse. Cada producto derivado conservará referencias a sus insumos y a los pasos de procesamiento.

### 6.3. Preparación y armonización

El procesamiento podrá incluir:

- Lectura y validación de archivos.
    
- Recorte de áreas de interés.
    
- Conversión y verificación de unidades.
    
- Tratamiento de máscaras y datos faltantes.
    
- Transformaciones de coordenadas apropiadas para cada cuerpo.
    
- Ajuste a escalas y resoluciones comparables.
    
- Cálculo de variables derivadas.
    
- Agregación espacial o temporal cuando corresponda.
    
- Registro de incertidumbre y limitaciones.
    

La armonización buscará hacer comparaciones justificables; no asumirá que todos los sensores observan exactamente la misma propiedad.

### 6.4. Generación de perfiles

Para cada región se construirá un perfil que podrá contener:

- Identificador, geometría y cuerpo planetario.
    
- Escala y resolución de análisis.
    
- Variables físicas y estadísticas derivadas.
    
- Cobertura y calidad por dimensión.
    
- Representaciones aprendidas, cuando estén disponibles.
    
- Fuentes y transformaciones.
    
- Referencias a productos visuales.
    

### 6.5. Indexación y consulta

Los perfiles terrestres se indexarán para permitir:

- Consultas espaciales.
    
- Filtrado por disponibilidad de variables.
    
- Filtrado por condiciones explícitas.
    
- Búsqueda por similitud física.
    
- Búsqueda mediante embeddings.
    
- Reordenamiento según los criterios de la misión.
    

## 7. Fuentes de datos iniciales

La siguiente tabla orienta la investigación. No garantiza que todos los productos sean compatibles, tengan cobertura suficiente o puedan integrarse en la primera versión.

|Dimensión|Tierra|Luna|Marte|
|---|---|---|---|
|**Topografía**|SRTM, ASTER GDEM y otras fuentes según región|LRO / LOLA y productos derivados|MOLA y productos topográficos combinados|
|**Imágenes y superficie**|HLS, Landsat y Sentinel-2|LRO / LROC|THEMIS, CTX y productos regionales disponibles|
|**Temperatura superficial**|Productos térmicos como MODIS o Landsat, según el caso|LRO / Diviner|Productos térmicos disponibles, incluidos los de THEMIS|
|**Geología y minerales**|Mapas geológicos y productos espectrales|Mapas y productos mineralógicos lunares|Mapas geológicos y productos de instrumentos como CRISM|
|**Agua y hielo**|Productos de nieve, hielo y superficie|Productos e indicadores disponibles para la región|Productos e indicadores disponibles para la región|

### 7.1. Tierra

**NASA Earthdata** será una puerta de entrada para buscar y acceder a datos terrestres de NASA.

**Harmonized Landsat and Sentinel-2 —HLS—** es un candidato para el análisis de reflectancia y superficie terrestre. Sus productos están distribuidos como Cloud Optimized GeoTIFF y requieren Earthdata Login para su acceso. Su armonización entre sensores terrestres no implica que sean directamente comparables con datos lunares o marcianos. [NASA HLS: acceso y herramientas](https://hls.gsfc.nasa.gov/data-access-and-tools/)

**SRTM y ASTER GDEM** son candidatos para elevación. La selección dependerá de cobertura y calidad. SRTM no cubre todas las latitudes polares, por lo que una búsqueda terrestre que incluya esas regiones necesitará fuentes complementarias. [USGS: datos globales de elevación](https://www.usgs.gov/faqs/where-can-i-get-global-elevation-data) · [USGS: cobertura de SRTM](https://pubs.usgs.gov/of/2011/1073/pdf/of2011-1073.pdf)

### 7.2. Luna

**NASA Planetary Data System —PDS—** será una fuente principal para datos de misiones planetarias.

**LOLA**, a bordo de Lunar Reconnaissance Orbiter, es una fuente inicial para topografía lunar. [PDS: productos LOLA](https://pds-geosciences.wustl.edu/missions/lro/lola.htm)

**Diviner** es un candidato para el análisis de temperatura superficial lunar. Será necesario especificar el producto, periodo, cobertura y resolución de cada comparación. [NASA/JPL: Diviner](https://www.jpl.nasa.gov/missions/diviner-lunar-radiometer-experiment-dlre/)

### 7.3. Marte

**MOLA y sus productos derivados** son una fuente inicial para topografía marciana. Se distinguirán los productos globales de los productos regionales de mayor detalle. [ASU: conjuntos globales de Marte](https://mars.asu.edu/data/)

**THEMIS y CRISM** son candidatos para investigar propiedades térmicas, imágenes o información mineralógica, según el producto seleccionado y la cobertura de la región. [PDS: datos de misiones marcianas](https://pds-geosciences.wustl.edu/missions/mep/datarecomm.pdf)

### 7.4. Acceso programático

Se investigarán los catálogos y servicios de acceso de cada proveedor. STAC puede ser útil donde esté disponible, pero no se asumirá que todos los productos terrestres y planetarios comparten una interfaz o estructura uniforme.

La ingesta deberá admitir adaptadores específicos por fuente.

## 8. Armonización científica

### 8.1. Unidades espaciales

Las superficies se dividirán en regiones o ventanas de análisis con un tamaño físico documentado.

La escala dependerá de la pregunta y de los datos disponibles. Una ventana amplia puede ser adecuada para comparar grandes formas del terreno, mientras que una ventana menor requiere datos capaces de resolver características locales.

El tamaño de la ventana no debe confundirse con la resolución del producto.

### 8.2. Sistemas de referencia

Los datos conservarán de forma explícita el cuerpo planetario y el sistema de referencia correspondiente.

Las operaciones de distancia, superficie y topografía utilizarán proyecciones apropiadas para cada región. Las elevaciones absolutas de cuerpos distintos no se compararán como si compartieran una misma referencia vertical.

Cuando tenga sentido, se priorizarán variables relativas, como:

- Pendientes.
    
- Diferencias de elevación dentro de una región.
    
- Variación del relieve.
    
- Distribución espacial de formas del terreno.
    

### 8.3. Resolución y escala efectiva

Las comparaciones se realizarán a una escala que ambos productos puedan respaldar.

Reducir el detalle de un conjunto puede ser necesario para una comparación justa. Interpolar un dato de baja resolución a una malla más fina no crea información nueva.

Como el remuestreo puede modificar pendientes y rugosidad, se registrará el método utilizado y se evaluará su efecto en los resultados.

### 8.4. Dimensión temporal

Las variables dinámicas se acompañarán de información temporal:

- Fecha o periodo.
    
- Valor puntual, promedio, rango o distribución.
    
- Condiciones de observación relevantes.
    
- Cantidad y calidad de observaciones.
    

No se considerarán directamente equivalentes productos con periodos o significados distintos sin una justificación específica.

### 8.5. Calidad, incertidumbre y ausencia de datos

Cada dimensión deberá conservar:

- Cobertura disponible.
    
- Máscaras y valores inválidos.
    
- Incertidumbre conocida o limitaciones del producto.
    
- Restricciones de escala.
    
- Grado de comparabilidad con la referencia.
    

Cuando falte una dimensión esencial, el sistema deberá indicarlo. No deberá generar una conclusión con apariencia de completitud que oculte ese vacío.

### 8.6. Observaciones e inferencias

El sistema distinguirá entre:

1. **Observación o producto de origen.**
    
2. **Variable derivada mediante una operación conocida.**
    
3. **Indicador indirecto.**
    
4. **Inferencia de un modelo.**
    
5. **Información no disponible.**
    

Por ejemplo, un indicador relacionado con hielo no se presentará automáticamente como confirmación de hielo local.

## 9. Variables y productos derivados

El proyecto buscará generar información útil a partir de los datos originales.

### 9.1. Relieve y movilidad

Según la resolución disponible:

- Distribución de pendientes.
    
- Variación de elevación.
    
- Rugosidad a distintas escalas.
    
- Proporción de terreno relativamente llano o inclinado.
    
- Relaciones espaciales entre zonas de diferentes pendientes.
    
- Formas generales del relieve.
    

Se evitará inferir obstáculos pequeños o transitabilidad de un rover específico cuando la resolución no permita observarlos.

### 9.2. Variables ambientales

Cuando los productos lo permitan:

- Rangos y distribuciones de temperatura superficial.
    
- Variación temporal o estacional.
    
- Persistencia de condiciones observables.
    
- Frecuencia y calidad de observaciones válidas.
    

### 9.3. Geología y materiales

Se investigarán variables o categorías relacionadas con:

- Unidades geológicas.
    
- Propiedades espectrales.
    
- Minerales o materiales identificados.
    
- Indicadores de procesos geológicos.
    

La comparación dependerá del significado y calidad de cada producto, no solamente de que ambos contengan imágenes o bandas espectrales.

### 9.4. Factibilidad terrestre

En una etapa posterior podrán incorporarse variables de contexto, como accesibilidad o protección ambiental.

Estas variables se mostrarán separadas de la similitud planetaria: influyen en la factibilidad de usar un lugar, pero no necesariamente en su parecido físico con otro mundo.

## 10. Motor de búsqueda: datos físicos, computer vision y ML

El proceso no estará basado exclusivamente en computer vision ni exclusivamente en tablas de mediciones. Combinará ambas aproximaciones.

### 10.1. Comparación física interpretable

Se construirá una primera búsqueda a partir de variables con significado explícito:

```
Similitud de pendientes
Similitud de variación del relieve
Similitud de materiales disponibles
Similitud de variables ambientales disponibles
```

Cada dimensión podrá ponderarse según la misión y examinarse por separado.

Esta búsqueda servirá como producto inicial y como referencia para evaluar la contribución del ML.

### 10.2. Computer vision y representaciones aprendidas

Los modelos podrán analizar datos con organización espacial, como:

- Imágenes.
    
- Modelos de elevación.
    
- Mapas de pendientes.
    
- Capas multiespectrales.
    
- Combinaciones de variables compatibles.
    

El objetivo será aprender patrones que puedan perderse en estadísticas agregadas, por ejemplo la disposición de zonas llanas e inclinadas o la organización de formas del relieve.

Un modelo podrá generar un **embedding** o representación numérica de cada región. La proximidad entre representaciones servirá para recuperar candidatos que luego se compararán con otras evidencias.

Los modelos de visión también pueden procesar matrices de mediciones de sensores; no se limitan a fotografías de color visible.

### 10.3. Riesgos del enfoque visual

Una semejanza visual o una proximidad entre embeddings no demuestra por sí sola:

- Composición mineral equivalente.
    
- Origen geológico compartido.
    
- Condiciones ambientales comparables.
    
- Utilidad para una misión concreta.
    

El modelo puede aprender diferencias debidas a sensores, iluminación, resolución o procesamiento. Estas posibilidades deberán investigarse durante la evaluación.

### 10.4. Combinación de componentes

El motor combinará, según el escenario:

1. Filtros y restricciones explícitas.
    
2. Disponibilidad y calidad de datos.
    
3. Similitud de variables físicas.
    
4. Señales provenientes de representaciones aprendidas.
    
5. Pesos o prioridades definidos para la misión.
    

La forma exacta de la combinación y sus coeficientes se determinarán experimentalmente. El sistema deberá conservar el desglose de sus componentes.

### 10.5. Falta de ejemplos etiquetados

Es posible que no exista un conjunto suficientemente grande de pares etiquetados como análogos adecuados para misiones específicas.

Se investigarán, entre otras opciones:

- Aprendizaje autosupervisado.
    
- Etiquetas débiles basadas en propiedades documentadas.
    
- Modelos preentrenados adaptados al dominio.
    
- Ejemplos revisados por el equipo.
    
- Recuperación de candidatos para revisión humana.
    
- Uso de análogos documentados y casos negativos.
    

Estas opciones son líneas de investigación, no decisiones cerradas.

### 10.6. Modelos candidatos

Se podrán evaluar modelos geoespaciales existentes para generar representaciones de datos terrestres. Por ejemplo, **Prithvi** es una familia de modelos geoespaciales que merece ser estudiada para datos de observación terrestre. Su aplicación a la comparación entre cuerpos planetarios requeriría validación específica. [NASA: Prithvi](https://science.nasa.gov/science-research/ai-foundation-model-in-orbit/)

La elección final del modelo dependerá de:

- Modalidades de entrada.
    
- Cobertura y resolución.
    
- Licencia y condiciones de uso.
    
- Recursos computacionales.
    
- Capacidad de adaptación.
    
- Calidad y explicabilidad de los resultados.
    

## 11. Evaluación científica y técnica

El motor se evaluará frente a un método interpretable de referencia y mediante la revisión de ejemplos concretos.

Las pruebas deberán investigar:

- Si recupera candidatos coherentes en casos documentados.
    
- Si distingue lugares visualmente parecidos pero físicamente diferentes.
    
- Si los resultados responden de forma razonable a cambios en las prioridades.
    
- Si son estables ante cambios moderados de escala o resolución.
    
- Si la falta de datos se comunica y gestiona correctamente.
    
- Si las representaciones aprendidas aportan resultados útiles frente a la comparación directa.
    
- Si la explicación refleja la evidencia que realmente influyó en el resultado.
    

Se procurará separar geográficamente las regiones de entrenamiento y evaluación para reducir el riesgo de que áreas cercanas produzcan resultados artificialmente optimistas.

Un análogo conocido puede servir como referencia de plausibilidad, pero su recuperación por el sistema no constituye una validación definitiva.

## 12. Interpretación de misiones

La persona usuaria podrá describir una misión o seleccionar un escenario preparado.

Ejemplo:

> «Quiero probar un rover que tendrá que desplazarse por terreno marciano volcánico, con pendientes variables y superficies rocosas».

El sistema propondrá una configuración inicial:

```
Destino: Marte
Actividad: movilidad robótica
Dimensiones propuestas: relieve, pendiente y superficie
Región de referencia: seleccionada o propuesta para revisión
Prioridades: configuración inicial modificable
```

La persona podrá revisar y corregir la interpretación antes de ejecutar la búsqueda.

Si se incorpora un modelo de lenguaje, su función será traducir la intención a una estructura controlada. No deberá inventar mediciones, fuentes o resultados científicos.

## 13. Backend y servicios

### 13.1. FastAPI

FastAPI actuará como interfaz entre el frontend y las capacidades del sistema:

- Validación de entradas.
    
- Interpretación estructurada de misiones.
    
- Consulta de regiones y productos.
    
- Ejecución de búsquedas.
    
- Recuperación de explicaciones.
    
- Entrega de referencias a capas visuales.
    
- Coordinación de tareas de procesamiento.
    

### 13.2. Operaciones conceptuales

```
POST /missions/interpret
    Propone criterios estructurados a partir de una misión.

POST /search
    Busca candidatos según referencia, dimensiones y pesos.

GET /regions/{id}
    Devuelve el perfil y los metadatos de una región.

GET /comparisons/{id}
    Devuelve el desglose de una comparación.

GET /layers/{id}
    Devuelve metadatos o referencias a capas visuales.
```

Estas rutas son ilustrativas y se definirán formalmente durante la implementación.

### 13.3. Procesamiento fuera de la API

Las tareas prolongadas —como incorporar datos, generar variables o calcular embeddings— se ejecutarán en procesos separados del ciclo inmediato de una petición.

En una primera versión se puede comenzar con procesos independientes y añadir una cola de tareas cuando el volumen o la necesidad operativa lo justifiquen.

### 13.4. Almacenamiento

**PostgreSQL + PostGIS** almacenará, como propuesta inicial:

- Geometrías de regiones.
    
- Metadatos.
    
- Perfiles.
    
- Resultados y relaciones entre productos.
    
- Configuraciones de misiones.
    
- Referencias a archivos.
    

Los rásteres, modelos y recursos visuales se almacenarán como archivos o en almacenamiento de objetos, según la etapa del proyecto.

Para embeddings se evaluarán **FAISS** y **pgvector**. La decisión dependerá del volumen, despliegue y tipo de consultas.

## 14. Frontend y visualización

### 14.1. React y TypeScript

El frontend gestionará:

- La descripción y configuración de misiones.
    
- La selección de destinos y regiones.
    
- Los controles de prioridades.
    
- El mapa y las vistas comparativas.
    
- Las fichas de candidatos.
    
- Los gráficos y explicaciones.
    
- Los modos de exploración guiada y avanzada.
    

### 14.2. CesiumJS

CesiumJS será el motor geoespacial principal para:

- Navegación sobre globos y regiones.
    
- Terreno e imágenes.
    
- Carga progresiva y niveles de detalle.
    
- Ubicación de candidatos.
    
- Capas geoespaciales y marcadores.
    
- Interacción con áreas de interés.
    

CesiumJS permite trabajar con representaciones de los cuerpos planetarios, pero los datos específicos de elevación e imágenes lunares o marcianas deberán seleccionarse y prepararse. [Cesium: terreno 3D](https://cesium.com/learn/cesiumjs-learn/cesiumjs-terrain/) · [Cesium: elipsoides planetarios](https://cesium.com/learn/cesiumjs/ref-doc/Ellipsoid.html)

### 14.3. Three.js

Three.js se utilizará de forma selectiva para:

- Escenas locales personalizadas.
    
- Animaciones o transiciones narrativas.
    
- Experiencias lúdicas.
    
- Visualizaciones que requieran un control especial de geometría o materiales.
    

La integración de ambos motores deberá justificarse por necesidades concretas para evitar duplicar complejidad sin beneficio.

### 14.4. Representación de la Tierra

Se evaluarán:

- Terreno e imágenes compatibles con Cesium.
    
- Productos abiertos preparados por el equipo.
    
- Otros proveedores visuales, sujetos a cobertura, coste y condiciones de uso.
    

**Google Photorealistic 3D Tiles** podrá investigarse como opción visual. Sus condiciones restringen usos como análisis de imágenes, interpretación automática y extracción de geodatos desde Map Tiles API; también exigen atribuciones. No se asumirá que puede utilizarse como insumo para el modelo. [Google: políticas de Map Tiles API](https://developers.google.com/maps/documentation/tile/policies?hl=en)

### 14.5. Representación de la Luna y Marte

La estrategia inicial podrá combinar:

- Mosaicos globales para orientación.
    
- Terrenos e imágenes regionales para las áreas de referencia.
    
- Vistas locales comparativas entre la región planetaria y el candidato terrestre.
    

No será necesario disponer desde el inicio de cobertura detallada y uniforme de toda la Luna o Marte.

### 14.6. Fidelidad y procedencia visual

La interfaz indicará:

- Fuente del terreno visualizado.
    
- Fuente de las imágenes.
    
- Fuente de las capas analíticas.
    
- Escala o resolución relevante.
    
- Exageración vertical, si se aplica.
    
- Elementos ilustrativos que no procedan de observaciones.
    

Los datos usados para mostrar un paisaje pueden diferir de los usados para calcular una comparación; esa diferencia deberá ser visible.

## 15. Contrato conceptual de un resultado

Cada candidato deberá poder presentarse mediante una ficha con esta estructura:

```
MISIÓN
  Objetivo
  Destino
  Dimensiones y prioridades

REFERENCIA PLANETARIA
  Cuerpo y región
  Extensión
  Escala
  Productos utilizados

CANDIDATO TERRESTRE
  Ubicación y geometría
  Área analizada
  Cobertura de datos

COMPARACIÓN POR DIMENSIÓN
  Resultado
  Evidencia
  Escala y periodo
  Datos faltantes

RESULTADO DEL MODELO
  Posición relativa
  Señales que contribuyeron
  Restricciones de interpretación

UTILIDAD PROPUESTA
  Actividad para la que podría ser relevante

LÍMITES
  Diferencias importantes
  Incertidumbre
  Características que no pueden evaluarse

VISUALIZACIÓN
  Fuentes de terreno, imágenes y capas

PROCEDENCIA
  Productos, versiones y transformaciones
```

Este contrato servirá como punto de encuentro entre procesamiento, ML, backend y frontend.

## 16. Plan de implementación

### Fase 1. Investigación y viabilidad

- Identificar regiones candidatas de la Luna y Marte.
    
- Seleccionar regiones terrestres iniciales.
    
- Probar acceso y lectura de datos topográficos.
    
- Registrar cobertura, resolución, coordenadas y calidad.
    
- Probar Cesium con la Tierra y una región planetaria.
    
- Elegir las primeras dimensiones comparables.
    

**Entregable:** inventario de fuentes, decisiones iniciales de datos y prueba visual básica.

### Fase 2. Primer flujo completo

- Preparar un conjunto delimitado de regiones.
    
- Calcular variables físicas documentadas.
    
- Construir un catálogo inicial.
    
- Implementar una búsqueda interpretable con pesos.
    
- Conectar FastAPI y frontend.
    
- Mostrar candidatos, evidencia y limitaciones.
    

**Entregable:** una misión puede producir candidatos reales y comparaciones explicables.

### Fase 3. Machine learning y computer vision

- Preparar entradas espaciales para modelos.
    
- Generar embeddings iniciales.
    
- Comparar recuperación con y sin ML.
    
- Revisar ejemplos positivos, negativos y resultados inesperados.
    
- Analizar sensibilidad a escala, sensores y prioridades.
    
- Integrar las señales útiles en el motor.
    

**Entregable:** evidencia de cómo contribuye el ML y bajo qué límites.

### Fase 4. Exploración visual y ampliación

- Desarrollar comparación 3D regional.
    
- Incorporar capas analíticas y procedencia.
    
- Añadir controles interactivos de prioridades.
    
- Desarrollar un recorrido guiado o lúdico.
    
- Incorporar un segundo escenario y nuevas dimensiones cuando estén listas.
    

**Entregable:** experiencia integrada para investigación y divulgación.

Las fases pueden solaparse si las personas responsables comparten los contratos de datos y los criterios de calidad.

## 17. Primer experimento recomendado

El primer experimento de extremo a extremo será:

1. Elegir una región lunar o marciana con un producto topográfico accesible.
    
2. Elegir varias regiones terrestres con datos de elevación adecuados.
    
3. Documentar sus diferencias de resolución, coordenadas y cobertura.
    
4. Prepararlas para una comparación a escala común.
    
5. Calcular variables topográficas interpretables.
    
6. Generar una primera representación aprendida o embedding.
    
7. Comparar los candidatos obtenidos por ambos métodos.
    
8. Visualizar una región planetaria y una terrestre.
    
9. Producir una ficha con evidencia y límites.
    
10. Documentar las decisiones y problemas encontrados.
    

El objetivo del experimento es aprender qué funciona con datos reales y orientar el diseño posterior. No se interpretará como validación completa de la plataforma.

## 18. Decisiones pendientes

Antes de cerrar la arquitectura detallada será necesario resolver:

- Regiones lunares y marcianas iniciales.
    
- Extensión de la búsqueda terrestre.
    
- Productos exactos y versiones.
    
- Dimensiones que pueden compararse con suficiente rigor.
    
- Tamaños de ventana y escalas de análisis.
    
- Estrategia de almacenamiento y despliegue.
    
- Método de búsqueda vectorial.
    
- Modelos candidatos y recursos de entrenamiento.
    
- Estrategia de evaluación con datos limitados.
    
- Proveedores visuales, costes y condiciones.
    
- Nivel de detalle viable para las representaciones 3D.
    
- Alcance permitido de preparación previa para el hackatón.
    

## 19. Criterio rector

La arquitectura debe permitir que la complejidad técnica produzca un resultado comprensible:

> **Un candidato debe poder explorarse visualmente, justificarse con datos, ajustarse a una misión y cuestionarse a partir de sus límites.**

El sistema deberá evolucionar hacia una búsqueda ambiciosa y multidimensional, manteniendo siempre la trazabilidad entre los datos originales, las inferencias del modelo y lo que se presenta a la persona usuaria.