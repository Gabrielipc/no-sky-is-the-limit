# Plan de implementación: prototipo de análogos planetarios

## Resumen

Construir una prueba de concepto que permita seleccionar una región de Marte, buscar regiones terrestres con un relieve regional comparable y explorar los resultados con sus fuentes y limitaciones.

El prototipo validará el recorrido completo con **React, TypeScript, CesiumJS y FastAPI**. Usará una búsqueda física interpretable como referencia y probará, en paralelo, si una representación aprendida aporta resultados útiles.

El diseño del ETL y de la armonización queda pendiente. Para desarrollar y probar el sistema se utilizará un conjunto pequeño de datos y perfiles preparados previamente, con procedencia y limitaciones documentadas.

## Datos para la primera prueba

| Datos | Fuente propuesta | Uso en el prototipo |
|---|---|---|
| Elevación de una región de Marte | [MOLA MEGDR](https://pds-geosciences.wustl.edu/missions/mgs/megdr.html), producto de 128 píxeles por grado, con sus etiquetas y recuentos | Referencia para comparar relieve regional. |
| Elevación de varias regiones terrestres | [SRTM 1 arc-second](https://www.usgs.gov/faqs/where-can-i-get-global-elevation-data) | Perfiles de regiones candidatas. |
| Imagen de la región marciana | [CTX](https://pds-geosciences.wustl.edu/missions/mro/) | Contexto visual de la región de referencia. |
| Imágenes de las regiones terrestres | [HLS](https://hls.gsfc.nasa.gov/data-access-and-tools/) | Contexto visual de los candidatos; requiere Earthdata Login. |
| Referencias de análogos existentes | [NASA Planetary Analog Explorer](https://science.nasa.gov/solar-system/analog-explorer/) y [USGS Terrestrial Analogs Data Portal](https://tadp.astrogeology.usgs.gov/) | Selección y revisión humana de algunos casos, sin tratarlos automáticamente como pares validados. |

- Seleccionar **una región marciana y varias terrestres** tras comprobar cobertura y acceso; incluir al menos un sitio documentado y otros candidatos con características diferentes.
- Usar ventanas iniciales de **10 × 10 km** como hipótesis de trabajo. Su utilidad depende de la cobertura y el soporte real de MOLA.
- El contrato de entrada al prototipo contendrá geometría y cuerpo, escala, perfiles de pendiente y relieve relativo, cobertura válida, referencias visuales, fuente y limitaciones. Los valores ausentes se identificarán explícitamente.
- CTX y HLS se usarán como contexto visual, no como evidencia directa de equivalencia entre sensores. Temperatura, minerales, agua, hielo y factibilidad logística quedan para iteraciones posteriores.

## Implementación

### 1. Viabilidad y entorno

- Comprobar acceso a muestras reales, lectura de los productos y visualización básica de una región de la Tierra y otra de Marte en CesiumJS.
- Crear una aplicación local con frontend React/TypeScript y API FastAPI. Utilizar archivos locales para el catálogo pequeño y las imágenes; evaluar PostGIS cuando las consultas espaciales o el volumen lo justifiquen.
- Registrar identificadores, versiones, cobertura, condiciones de uso y límites de los productos seleccionados.

**Entregable:** entorno ejecutable, inventario de muestras y demostración visual básica de ambos cuerpos.

### 2. Búsqueda y experiencia integrada

- Implementar un escenario de misión predefinido, selección de la región marciana y ajuste de prioridades para las métricas disponibles de pendiente y relieve relativo.
- Crear una búsqueda que ordene candidatos terrestres mediante las métricas físicas disponibles y muestre el aporte de cada dimensión. No comparar elevaciones absolutas entre planetas.
- Exponer desde FastAPI operaciones para listar regiones, consultar sus detalles y ejecutar una búsqueda con los pesos elegidos. Cada resultado incluirá puntuación y desglose, cobertura, fuentes, escala y datos faltantes.
- En el frontend, mostrar la referencia y los candidatos en Cesium, una lista ordenada y una vista comparativa con imágenes, métricas y limitaciones. Al modificar un peso, volver a consultar y actualizar los resultados.
- Presentar los resultados como **candidatos para investigación**, no como certificación de movilidad o idoneidad para una misión.

**Entregable:** recorrido completo desde el escenario de misión hasta la comparación explicable de al menos un candidato.

### 3. Experimento de aprendizaje automático

- Probar fuera del flujo principal una representación aprendida sobre los parches topográficos disponibles y recuperar candidatos por cercanía entre representaciones.
- Ejecutar el método físico y el experimental sobre los mismos casos; registrar coincidencias, diferencias y ejemplos inesperados. Mantener separadas las regiones usadas para desarrollo y revisión.
- Si no hay suficientes datos o referencias revisadas, presentar los resultados como exploración cualitativa. Integrar ML en la búsqueda principal solo en una iteración posterior respaldada por la evaluación.

**Entregable:** informe breve con resultados comparados, limitaciones y recomendación para la siguiente iteración.

## Pruebas y criterios de aceptación

- **Recorrido funcional:** seleccionar el escenario, ejecutar la búsqueda, cambiar prioridades y abrir la comparación de un candidato con sus fuentes.
- **Comportamiento del motor:** comprobar que los pesos afectan el orden cuando corresponde, que el desglose explica la puntuación y que los datos faltantes no se interpretan como cero ni como coincidencia.
- **Visualización:** verificar que Tierra y Marte se representan en el cuerpo correcto y que se distingue la imagen contextual de los datos utilizados en la comparación.
- **Calidad y límites:** mostrar cobertura, escala y procedencia; comprobar que la interfaz no afirma detectar obstáculos pequeños ni determinar transitabilidad a partir de MOLA.
- **Evaluación exploratoria:** revisar resultados esperados e inesperados con las referencias disponibles y documentar los casos en los que la evidencia sea insuficiente.
- **Reproducibilidad:** entregar instrucciones para iniciar frontend y API, cargar el conjunto de prueba y repetir la demostración y el experimento de ML.

## Supuestos

- El primer destino será **Marte** y la dimensión inicial será el **relieve regional**, siguiendo el primer experimento recomendado en la investigación.
- Se dispondrá de perfiles preparados para las pruebas; su proceso de obtención y armonización se definirá por separado.
- La primera versión será una demostración local con un catálogo acotado, sin autenticación de usuarios ni despliegue público.
- Los umbrales de cobertura y calidad se fijarán después de inspeccionar las muestras y antes de evaluar los resultados; no se asumirán validados de antemano.
