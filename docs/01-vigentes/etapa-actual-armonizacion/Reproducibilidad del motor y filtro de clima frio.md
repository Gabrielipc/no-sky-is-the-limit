# Reproducibilidad del motor y filtro de clima frío

Revisión del 15 de noviembre de 2026 de la release `etl-30m-r2b`. Responde a dos preguntas: por qué dos ajustes del mismo motor dieron rankings distintos para Jezero, y si las dimensiones y filtros nuevos quitan rigor a las comparaciones.

**Conclusión.** El ajuste tenía dos fallos que sí afectaban a los rankings publicados, y están corregidos en el código. Los modelos `etl-30m-r1b`, `etl-30m-r2` y `etl-30m-r2b` se ajustaron con el código anterior; `etl-30m-r2c` es el primero con las correcciones y es reproducible con la misma semilla, pero sigue siendo sensible a la semilla (sección 4). Las dimensiones nuevas no entran en ningún ranking publicado. El filtro de clima frío no es sensible a sus umbrales, pero deja fuera todo el hemisferio sur y un cuarto de su población está a menos de 40° N.

## 1. Por qué Jezero cambió entre r2 y r2b

Entre r2 y r2b coincidieron 73 de los 100 primeros resultados de Jezero y 5 de los 10 primeros, con el mismo código, pool, pesos y semilla.

### 1.1 El muestreo dependía del orden de lectura

El ajuste tomaba la muestra de 200 000 ventanas con `USING SAMPLE reservoir(...) REPEATABLE (semilla)`. Esa cláusula fija la secuencia de números aleatorios, no las filas a las que se aplica. Medido sobre el almacén local (188 103 ventanas rankables, muestra de 26 000):

| Prueba | Resultado |
|---|---|
| Mismo orden, 1 u 8 hilos | Misma muestra |
| Mismo código y semilla, orden de entrada invertido | Coinciden 13,8 % de las filas, igual que el azar (13,8 %) |

En la nube el orden depende de cómo se listan y restauran los archivos del almacén, que cambia entre corridas. La muestra pasó a ser `ORDER BY hash(region_id, semilla) LIMIT n` (`similarity_ml.fit_sample_sql`): no depende del orden ni de los hilos. Un test lo comprueba con tres órdenes y hilos distintos.

### 1.2 La covarianza robusta degeneraba con variables llenas de ceros

La fracción de pendiente mayor de 15° y de 25° es exactamente cero en el 78 % y el 86 % de las ventanas del mundo. Tras la transformación a puntuaciones normales, todos esos ceros quedan en el mismo valor. `MinCovDet` puede entonces elegir un subconjunto donde una variable es constante, y devuelve una covarianza con una dirección de varianza cero.

- **Modelos publicados.** En `etl-30m-r1b` y `etl-30m-r2b` la covarianza de `slope_240m_gt25_fraction` es exactamente cero (varianza y covarianzas), y `slope_240m_gt15_fraction` se relaciona poco con el resto (correlación 0,35–0,38, frente a 0,72–0,78 en la covarianza clásica del almacén local). En `etl-30m-r2` la correlación entre ambas es −0,95, de signo contrario al de los datos. El motor invierte con pseudoinversa, así que la variable con varianza cero se descarta en silencio.
- **Reproducción local.** Con muestras de 26 000 ventanas, las semillas 1 y 2 dieron una covarianza singular (número de condición ≈ 10²⁸) y las semillas 3, 4 y 5 una bien condicionada.
- **Corrección.** Tras `MinCovDet` se compara con la covarianza clásica de las mismas filas. Si el resultado es singular (cociente de autovalores < 10⁻⁴) o su correlación se aleja más de 0,3 de la clásica, se sustituye por Ledoit‑Wolf y el modelo lo registra como `ledoit_wolf_after_degenerate_min_cov_det`.

### 1.3 Efecto medido

Jezero sobre el almacén local (2 474 ventanas elegibles), ajustes con muestra de 26 000 comparados con el ajuste sobre todo el pool. Coincidencias en el top 100:

| Vista o conjunto | Antes (semillas 1, 2, 3, 4, 5) | Después |
|---|---|---|
| Solo `escabrosidad` (semillas 1, 2, 3) | 51, 59, 97 | 93, 92, 97 (y 97, 96 en 4 y 5) |
| Pesos por defecto | 56, 79, 93, 93, 92 | 92, 94, 93, 93, 92 |

**Límites de esta medición.** Es un almacén local y pequeño (una zona del hemisferio norte), no el barrido mundial. La corrección no se ha probado todavía en la nube. La mejora a escala mundial es lo esperable por el mecanismo, no algo medido.

### 1.4 Lo que sigue inestable: el GMM de regímenes

Solo con `regimen_morfologico` (peso 0,15) las coincidencias siguen entre 37 y 72 de 100. En la fusión por defecto se diluyen (92–94). Hipótesis sin comprobar: muchas ventanas comparten posteriores casi idénticas, así que el top 100 de esa vista elige entre empates. Hasta comprobarlo, no se debe leer esa vista como un ranking fino.

## 2. ¿Quitan rigor las dimensiones nuevas?

**No entran en ningún ranking publicado.** En Jezero, Haworth y de Gerlache, `termica`, `entorno_superficial` y `emisividad_cmg` aparecen con peso 0 o `reference_missing`: son columnas terrestres y las referencias son de otro cuerpo. Solo intervendrían con una referencia terrestre (`--ref-region-id`).

Lo que sí limita las comparaciones:

- **Haworth y de Gerlache se ordenan solo por topografía.** El peso por defecto de la Luna da 0,2 a `radar`, sin datos terrestres, y se reparte entre las otras cuatro vistas (`weights_effective`). La condición «frío» la pone el filtro de elegibilidad, no la similitud.
- **`termica` descansa en 100 ventanas.** El modelo cuenta 2 000 filas (`n_complete`) porque remuestrea 100 ventanas medidas, de 40 teselas MODIS. El informe del modelo ahora incluye `fit_population` con el número real de ventanas medidas y de fondo.
- **Faltan datos lunares:** Tmin, amplitud térmica, rocas, H y S1 no existen en los polos, así que no hay vista térmica ni de regolito para la Luna.

## 3. Filtro de clima frío en `polar_cold_v1`

Análisis sobre las ventanas de r2 con cobertura de tipo polar (aproximadas con las columnas de la release; no incluyen musgo y líquenes). La sensibilidad se midió con una distancia topográfica simplificada a Haworth, no con el motor completo.

| Umbrales | Ventanas que pasan | Coincidencia del top 100 |
|---|---:|---:|
| Nieve ≥ 0,25 o permafrost ≥ 0,10 (actual) | 10 764 | 100 |
| Nieve ≥ 0,10 o permafrost ≥ 0,05 | 11 255 | 98 |
| Nieve ≥ 0,50 o permafrost ≥ 0,25 | 10 465 | 99 |
| Solo nieve ≥ 0,25 | 6 326 | 88 |
| Solo permafrost ≥ 0,10 | 10 196 | 34 |
| Sin filtro de clima | 198 828 | 54 |

- **Los umbrales no son críticos.** Entre 0,10 y 0,50 de nieve, y entre 0,05 y 0,25 de permafrost, el resultado casi no cambia.
- **Hace falta la combinación.** Solo permafrost pierde Islandia o Peary Land, donde la capa de permafrost no tiene valor. Solo nieve pierde la meseta tibetana.
- **El hemisferio sur no aporta nada.** De 8 277 ventanas del sur con cobertura de tipo polar, ninguna pasa. La Antártida no tiene cobertura de suelo (WorldCover) y las montañas del sur casi no llegan a 3 meses de nieve. Haworth está en el polo sur y sus análogos salen solo del hemisferio norte.
- **No es solo «polar».** El 25 % de las ventanas que pasan están al sur de 40° N, sobre todo en la meseta tibetana, donde pasan por permafrost. El filtro significa «terreno frío con nieve o permafrost», no latitud polar ni régimen de iluminación polar.
- **Mongolia en el top 6 de Haworth** pasa por permafrost (0,29 de la huella) y 0,17 de meses con nieve.

## 4. Medición en la nube de la release r2c

Con las dos correcciones, `etl-30m-r2c` se ajustó sobre el barrido mundial y se midió con `scripts/estabilidad_motor.py` ([resultado](../../evidencia-motor-similitud/estabilidad.json)): un ajuste de referencia, uno repetido con la misma semilla y tres con otras semillas. Coincidencias del top 100:

| Referencia | Misma semilla | Semilla 1 | Semilla 2 | Semilla 3 |
|---|---|---:|---:|---:|
| Jezero | ranking idéntico | 99 | 79 | 100 |
| Haworth | ranking idéntico | 99 | 79 | 100 |
| de Gerlache | ranking idéntico | 96 | 34 | 69 |

- **Primera corrección confirmada a escala mundial:** con la misma semilla el ranking es idéntico en las tres referencias.
- **Segunda corrección, solo parcial.** Entre semillas el ranking sigue cambiando: la media de coincidencia es 84 de 100 y la mínima 34. La semilla 2 fue la única en que `escabrosidad` conservó `MinCovDet`; las otras usaron el respaldo de Ledoit‑Wolf. Es coherente con que la guarda sea demasiado permisiva, pero no está aislado: una prueba local con Ledoit‑Wolf siempre dio coincidencias de 91–94, iguales a las de la guarda (92–95), así que no reproduce la diferencia.
- **de Gerlache es el caso débil.** Su referencia es extrema y queda lejos del pool, así que el orden entre candidatas cercanas es muy sensible.
- **Entre r2b y r2c** el top 100 coincide en 69 (Jezero), 50 (Haworth) y 39 (de Gerlache), como se espera al corregir un modelo degenerado.

**Decisión.** r2c se publica como activa con estos sesgos declarados en su README, y se corregirán en otra release.

## 5. Qué falta

1. **Estabilidad entre semillas.** Fijar un único estimador de covarianza para las vistas con variables llenas de ceros, o endurecer la guarda, publicar un ranking de consenso entre varios ajustes y medir de nuevo con `scripts/estabilidad_motor.py`.
2. **Decidir qué hacer con el sur:** una fuente de cobertura de suelo para la Antártida, o declarar en la interfaz que los análogos de Haworth son del hemisferio norte.
3. **Comprobar la hipótesis de empates del GMM** y, si se confirma, no presentar esa vista como ranking fino.
4. **Revisar la referencia de de Gerlache:** su ranking es el menos estable y su sitio queda fuera de su propia compuerta de pendiente.
