# Revisión metodológica del Atlas de 30 m

El Atlas compara ventanas terrestres de 3 × 3 km con un sector de Jezero, en Marte, mediante tres métricas: pendiente, relieve relativo y rugosidad. El principal riesgo es que la posición de un sitio refleje diferencias entre los modelos de elevación o las reglas de procesamiento. Para saber cuánto influyen esos factores, hay que medir cómo cambia el ranking al variar cada uno.

## 1. Comparabilidad de los modelos de elevación

El Atlas agrega el modelo HiRISE de Jezero desde una rejilla de aproximadamente 1 m y usa GLO-30 para las ventanas terrestres. Aunque ambos se analicen en celdas de 30 m, GLO-30 puede incorporar vegetación y estructuras. En una ventana boscosa, parte de la rugosidad medida podría venir de la vegetación y afectar la posición del sitio.

**Prueba propuesta.** Recalcular las mismas ventanas con un modelo terrestre que represente el terreno, como 3DEP donde haya cobertura. Usar la misma huella y celda de análisis, y comparar cuánto cambian las métricas y la puntuación de cada ventana al sustituir la fuente.

## 2. Escala de cálculo de la rugosidad

A 30 m, la rugosidad se calcula con una vecindad de 25 × 25 centros y un radio de 360 m. Si se mantiene ese número de centros a 120 m, el radio sube a 1.440 m. En ese caso, un cambio en la puntuación podría deberse tanto al tamaño de celda como a que la rugosidad se mide sobre un entorno más amplio.

**Prueba propuesta.** Mantener un radio de 360 m para evaluar el efecto del tamaño de celda. Eso equivale a usar 13 × 13 centros a 60 m y 7 × 7 a 120 m. Documentar también la distancia sobre la que se calcula la pendiente en cada escala.

## 3. Superficie que aporta datos a cada métrica

El control de cobertura usa como denominador la superficie de tierra. Una ventana costera de 9 km² con 0,9 km² de tierra puede registrar un 100 % de datos válidos sobre tierra, aunque esa tierra ocupe solo el 10 % de la huella. Además, cerca de la costa o de un hueco, una celda con elevación válida puede carecer de vecinos suficientes para calcular la rugosidad.

**Prueba propuesta.** Registrar por ventana la fracción de la huella ocupada por tierra, la fracción de esa tierra con elevación válida y la superficie que efectivamente contribuyó a cada métrica. Evaluar cuánto cambia el ranking al exigir una superficie válida comparable entre candidatos.

## 4. Validación del parecido entre formas

Si la puntuación se basa en estadísticas resumidas, un escarpe continuo y un conjunto de lomas dispersas podrían obtener resultados similares. Si el objetivo es encontrar análogos de una forma específica de Jezero, hace falta comprobar que los candidatos comparten rasgos observables de esa forma.

**Prueba propuesta.** Revisar mapas e imágenes de candidatos de distintas posiciones con los mismos criterios, sin que quien evalúe conozca su puesto. Comparar después la evaluación visual con las puntuaciones para comprobar si el ranking distingue las formas buscadas.

## Criterio para presentar los resultados

La prioridad es comprobar si los primeros puestos se mantienen al cambiar la fuente de elevación, variar el tamaño de celda con el radio fijo y exigir una superficie válida comparable. Si cambios pequeños en el procesamiento alteran el primer puesto, conviene presentar un grupo de candidatos con resultados similares. La revisión de formas aporta la evidencia adicional necesaria para describir un sitio como análogo geomorfológico.

*Referencia: documento técnico del Atlas, secciones 1 «Escalas y ventanas» y 2 «Topografía, geometría y máscaras».*
