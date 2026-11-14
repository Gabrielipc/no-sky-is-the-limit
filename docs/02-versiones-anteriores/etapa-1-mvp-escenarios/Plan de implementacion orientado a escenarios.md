# Plan de implementación orientado a escenarios

**Estado:** plan de trabajo inicial, sujeto a la evidencia de las fuentes y a las reglas aplicables del evento.  
**Contexto:** reemplaza la secuencia operativa de [Plan de arranque desde cero](../../03-obsoletos-e-historico/Plan%20de%20arranque%20desde%20cero.md), que permanece como referencia técnica.  
**Objetivo:** ayudar a encontrar y explicar posibles análogos terrestres de áreas concretas de Marte o la Luna para un propósito de exploración definido.

## 1. Qué construiremos

Una persona selecciona un escenario y un área planetaria documentada. El sistema presenta candidatas terrestres, compara las características para las que existe evidencia compatible y explica tanto las semejanzas como las diferencias y los datos ausentes. Una candidata es una hipótesis para investigar; no una certificación de seguridad, acceso ni equivalencia ambiental.

La búsqueda tendrá dos niveles:

1. **Exploración regional:** capas de cobertura amplia ayudan a generar candidatas y dar contexto. La resolución y cobertura limitan los filtros que pueden aplicarse.
2. **Evaluación local:** imágenes, modelos de terreno y otras fuentes más detalladas permiten examinar características pertinentes para el escenario, solo donde existan datos comparables.

La búsqueda regional no debe descartar silenciosamente sitios por características que no estén justificadas para el escenario. Las candidatas sin detalle deben identificarse como pendientes de evaluación, no calificarse como malas coincidencias.

## 2. Principios y decisiones

- Una analogía responde a una pregunta: sitio, actividad, características y escala deben constar en el resultado.
- Cobertura global no implica detalle global. Una cuadrícula remuestreada no adquiere información nueva. El tamaño de ventana y la escala de medición se seleccionan por caso, sin imponer 10 km ni 500 m.
- Cada característica requiere unidades, método, resolución efectiva cuando se conozca, cobertura, procedencia y justificación de comparabilidad. Diferenciar observación, derivado e interpretación.
- Separar la similitud observada de la disponibilidad de evidencia. Ausente, insuficiente y no comparable no equivalen a cero ni deben ocultarse mediante promedios.
- Las magnitudes distintas, como temperatura e inercia térmica, no se comparan directamente. Las diferencias de instrumento, iluminación, referencia vertical y procesamiento requieren revisión.
- Preservar originales y registrar transformaciones. No asumir que una descarga, un hash local o una etiqueta garantiza calidad científica.
- Mantener un método interpretable como línea base. ML, infraestructura distribuida y procesamiento global masivo son opcionales y dependen de evidencia de necesidad.
- Los detalles de fuentes, usos y redistribución deben revisarse antes de publicar. Confirmar las reglas del evento; no asumir que se proporcionarán datos o sitios exclusivos.

## 3. Estado de partida

- El prototipo sirve tres regiones preparadas: Jezero, Atacama y Utah, en ventanas provisionales de 10 × 10 km. Usa MOLA y SRTM y calcula pendiente y relieve regionales; sus escalas de puntuación son ilustrativas, no validan movilidad.
- La API actual acepta solo referencias marcianas; LOLA está descargado pero no integrado en el recorrido de comparación.
- Hay archivos MOLA globales y polares, LOLA, dos teselas SRTM y GMTED2010 de 30 y 7,5 segundos de arco. El ZIP de 7,5 segundos permite listar su contenido; aún requiere comprobación de integridad, metadatos y cobertura efectiva. El manifiesto puede no reflejar el estado más reciente.
- ArcticDEM aparece como descarga parcial y REMA figura pendiente. No son requisitos automáticos del primer caso.
- La [auditoría local](../../03-obsoletos-e-historico/Auditoria%20de%20datos%20locales.md) describe una discrepancia entre cabeceras y etiquetas de recuentos MOLA; resolver la lectura conforme al producto antes de reutilizarla.
- El visor muestra capas de contexto y ventanas, no terreno 3D. Los colores por ventana no son directamente comparables sin una leyenda y escala apropiadas.

## 4. Fase 1: ficha de viabilidad del primer caso

**Hipótesis de trabajo, no selección definitiva:** navegación robótica en un área acotada de Jezero. Puede reemplazarse si las fuentes o el alcance del evento favorecen otro sitio. No afirmar que el área es una zona de operación validada sin una referencia independiente.

1. Formular una pregunta concreta y definir las características que serían relevantes, distinguiendo las esenciales de las opcionales.
2. Seleccionar un polígono planetario con ubicación y propósito documentados. Investigar imágenes y, si existe, un DTM de alta resolución que realmente lo cubran. Verificar huella, resolución, fecha, formato, metadatos y condiciones de uso; imagen y DTM son productos distintos.
3. Seleccionar inicialmente dos o tres candidatas terrestres, incluyendo los datos ya disponibles cuando sean pertinentes. Comprobar sus huellas y fuentes de detalle; no presumir que los sitios conocidos sean los mejores ni excluir otros.
4. Elaborar una matriz por sitio y variable: producto y enlace, cobertura del polígono, tamaño de muestra, unidades, método, calidad conocida, vacíos, restricciones y comparabilidad. Indicar si la información aún no se ha verificado.
5. Identificar una o dos métricas viables para un primer análisis. Definir qué se puede afirmar y qué no; por ejemplo, pendiente a una escala dada no prueba transitabilidad.

**Entregable:** `docs/Ficha de viabilidad - primer caso.md`, con enlaces directos a productos y una recomendación razonada de área, fuentes, variables y siguientes pasos. No descargar conjuntos masivos antes de confirmar que son necesarios.

**Criterio de salida:** existe un área planetaria documentada y al menos una candidata terrestre con datos verificables para una comparación concreta, o se documenta el bloqueo y se propone otro caso. No inventar cobertura ni atribuir resolución de imagen a un DTM.

## 5. Fase 2: primer análisis reproducible

1. Documentar para cada área el polígono, propósito, fuentes y condiciones de uso. Descargar solo los recortes o productos necesarios, conservar etiquetas y registrar identidad y origen.
2. Verificar lectura, coordenadas, unidades, nodata y resolución con metadatos y controles apropiados. Registrar incertidumbre y soporte de observación cuando sea posible.
3. Definir tamaño de ventana, método de armonización y escala de medición a partir de la evidencia. Evitar inferir detalle por interpolación; comparar únicamente características compatibles.
4. Implementar una línea base interpretable para una o dos variables defendibles. Guardar valores por sitio, unidades, cobertura, método y diferencias. No combinar variables incompatibles ni presentar un porcentaje como validación.
5. Contrastar los resultados con las fuentes e inspección visual; documentar sensibilidad básica a la escala o a la elección de ventana cuando sea relevante. Incluir al menos una candidata de referencia conocida cuando haya una pertinente, sin considerarla verdad absoluta.

**Entregable:** un análisis que pueda repetirse desde entradas y parámetros documentados, más una ficha que explique semejanzas, diferencias y límites.  
**Criterio de salida:** los resultados se reproducen, sus fuentes y transformaciones son trazables y una persona puede seguir el razonamiento sin depender de una puntuación opaca.

## 6. Fase 3: recorrido mínimo en la aplicación

**Estado:** implementada para el primer caso Jezero–Utah–Atacama. Ver [entrega y verificación de fase 3](Fase%203%20-%20recorrido%20minimo%20en%20la%20aplicacion.md). El recorrido consume la evidencia de fase 2, permite alternar 60/120 m y muestra métricas separadas, fuentes, cobertura y dimensiones pendientes. El soporte lunar continúa pendiente.

Adaptar la API y la interfaz existentes para seleccionar el escenario y el sitio de referencia, consultar candidatas y revisar el desglose por característica. Mostrar fuentes, escala, cobertura, datos ausentes y limitaciones; distinguir contexto regional de análisis local. Mantener la puntuación actual identificada como exploratoria o retirarla del recorrido nuevo si induce a conclusiones incorrectas.

Introducir soporte lunar cuando se implemente y pruebe explícitamente; no presentar LOLA descargado como funcionalidad ya integrada. El mapa contextual no debe sugerir que se visualiza un terreno 3D de alta resolución cuando no sea así.

**Criterio de salida:** alguien puede completar el recorrido del primer caso y entender para qué sirve cada candidata, qué evidencia la respalda y qué permanece desconocido.

## 7. Fase 4: ampliar la búsqueda terrestre

**Estado:** implementada para tres áreas acotadas, con 970 ventanas y tres controles. Se auditaron los dos GMTED, se generaron perfiles reproducibles a 300/600 m, se integró su consulta y exportación y se ejecutó una evaluación de detalle bajo demanda. Ver [entrega de fase 4](Fase%204%20-%20busqueda%20regional%20terrestre.md). El barrido global y el soporte polar permanecen fuera de este caso.

Verificar integridad y metadatos de GMTED2010, cobertura válida y limitaciones; reconciliar su manifiesto con los archivos. Usarlo, si resulta apropiado, para generar candidatas regionales en una extensión definida y medible. Registrar resolución y umbrales, y comprobar si el filtro excluye áreas relevantes.

Separar candidatas generadas de candidatas evaluadas localmente. Usar sitios conocidos como controles y buscar también ubicaciones menos conocidas. Añadir fuentes de detalle bajo demanda, incluidas fuentes polares cuando el escenario lo requiera. Evaluar coste y tiempo antes de un barrido global.

**Criterio de salida:** se puede reproducir la generación de candidatas fuera del catálogo inicial y explicar cómo influyen cobertura, filtros y ausencia de datos en los resultados.

## 8. Fase 5: expansión condicionada

**Estado:** implementada para un segundo escenario de reconocimiento topográfico, con diez ventanas de fase 4: siete evaluadas y tres pendientes. Se comparan productos a escala común y descriptores a cuatro escalas, con selección reproducible y sesgo de disponibilidad explícito. Ver [entrega de fase 5](Fase%205%20-%20expansion%20condicionada.md). ML, infraestructura distribuida y soporte lunar/polar se mantienen pospuestos por falta de evidencia suficiente para incorporarlos.

Incorporar escenarios, dimensiones o cuerpo adicional cuando exista una pregunta, fuentes utilizables y método de evaluación. Considerar ML solo si hay datos y evaluación suficientes para demostrar una mejora sobre la línea base; evaluar sesgos de sensor, escala y separación geográfica. Incorporar infraestructura adicional solo ante una necesidad medida de volumen, operación o colaboración.

## 9. Primer paquete de trabajo listo para iniciar

**Objetivo:** completar la ficha de viabilidad de la fase 1, sin cambiar todavía el motor de similitud.

1. Revisar el enunciado del challenge y el catálogo actual para acotar el escenario provisional y las coordenadas existentes.
2. Localizar en catálogos oficiales productos específicos de imagen y DTM para un área de Jezero; verificar que sus huellas cubren el área y registrar enlaces, resolución y restricciones. Si no se logra verificar, marcarlo como pendiente y proponer otro polígono.
3. Inventariar fuentes de detalle para dos o tres áreas terrestres, incluida al menos una fuera de los sitios actuales si hay datos adecuados. Registrar qué evidencia falta.
4. Construir la matriz de comparabilidad y seleccionar una o dos variables viables, con escala y limitaciones propuestas. Identificar controles y pruebas necesarios antes de calcularlas.
5. Escribir la ficha, enlazar productos concretos y decidir si procede la fase 2 o si debe ajustarse el caso.

**No incluye:** entrenamiento de ML, afirmaciones de seguridad de conducción, descarga global adicional, implementación de una plataforma distribuida ni selección definitiva de umbrales científicos.

## 10. Preguntas abiertas

- ¿Quién usará el primer resultado y para qué prueba específica?
- ¿Qué polígono planetario tiene los datos necesarios y es pertinente al escenario?
- ¿Qué fuentes terrestres permiten comparar las mismas variables y a qué escala?
- ¿Cómo se validarán los candidatos y cómo se identificarán sesgos de cobertura?
- ¿Qué reglas y recursos concretos proporciona el evento? Verificar el enunciado y sus condiciones vigentes.

El cronograma de dos semanas y el equipo supuesto en el plan anterior son hipótesis, no compromisos de este plan. Priorizamos entregables y criterios de salida sobre fechas hasta conocer recursos y disponibilidad.
