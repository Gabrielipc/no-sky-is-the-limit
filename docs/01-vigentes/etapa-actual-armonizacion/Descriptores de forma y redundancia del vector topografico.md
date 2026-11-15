# Descriptores de forma y redundancia del vector topográfico

**Pregunta científica.** ¿Qué información añaden descriptores de forma y organización de la huella al vector de ranking actual (relieve P95–P5, pendiente P50 y P90 a base de 240 m), y en qué se distingue Jezero de las ventanas áridas terrestres?

**Conclusión.** En las 716 ventanas de desarrollo, el vector de ranking y la rugosidad describen un solo eje de escabrosidad (61 % de la varianza). La **integral hipsométrica** aporta un eje independiente (~80 % de su orden no lo explica el ranking, estable en las tres cuencas) y es justo donde Jezero es atípico: su huella queda en el percentil 98 de la muestra terrestre, mientras en relieve y pendiente queda cerca de la mediana. La concentración de orientación aporta un tercer eje más débil. Las fracciones de pendiente fuerte y la rugosidad no añaden información para ordenar terreno árido. Ninguna feature nueva entra al ranking del barrido; la integral entra, con el relieve, en el [ranking densificado](#ranking-densificado-relieve-e-integral-en-el-mejor-encuadre). La [prueba de desplazamiento](#sensibilidad-al-encuadre-de-la-huella) muestra además que la integral depende del encuadre: conserva su orden con desplazamientos de hasta 300 m, pero no con desplazamientos de 750 m o más ni con huellas de 1,8 km. Por eso solo sirve en la etapa densificada sobre candidatas, no en el barrido de reconocimiento de 10 km.

Responde a la prioridad 3 de la [auditoría frente a las fuentes del challenge](Auditoria%20de%20armonizacion%20y%20features%20frente%20a%20fuentes%20del%20challenge.md#11-redundancia-del-vector-topográfico).

## Método

- **Descriptores.** `pipelines/etl_extractors.py` calcula cinco descriptores nuevos con la misma huella de 3 km, celdas de 30 m, halo de 720 m y derivada a base de 240 m que el ranking. La tabla `base_windows` los guarda en columnas propias:

  | Columna | Definición | Sin valor cuando |
  |---|---|---|
  | `hypsometric_integral` | `(media − P5) / (P95 − P5)` de la elevación | `P95 − P5 < 2 m` |
  | `elevation_skew_p95_p05` | `(P95 + P5 − 2·P50) / (P95 − P5)`, en [−1, 1] | `P95 − P5 < 2 m` |
  | `aspect_240m_resultant_length` | Longitud resultante media de los vectores descendentes unitarios en celdas con pendiente > 1°. 1 = una orientación dominante; 0 = isótropo | < 10 % de celdas con pendiente > 1° |
  | `slope_240m_gt15_fraction`, `slope_240m_gt25_fraction` | Fracción de celdas con pendiente > 15° y > 25° | — |

- **Muestra.** Se usaron las 716 ventanas de los 11 bloques de desarrollo de la [Tercera entrega](Tercera%20entrega%20-%20muestreo%20estratificado%20y%20puentes%20entre%20cuerpos.md#31-partición-determinista-en-bloques-de-desarrollo-y-reserva-holdout) (Utah, Mojave y Atacama), recalculadas con GLO‑30 a 30 m. Los bloques reservados no se leyeron. Las 716 tienen QA `rankable`; 653 tienen los nueve descriptores (los faltantes son ventanas casi planas).
- **Referencia.** Jezero se calculó con la misma función sobre el DTM HiRISE agregado a la misma rejilla. Reproduce los valores de referencia del ETL (120,27 m; 3,07°; 9,24°).
- **Aporte de información.** Para cada descriptor se calculó `1 − R²` de su rango regresado sobre los rangos de relieve, pendiente P50 y P90. Es la parte de su orden que el ranking actual no explica. Se repitió por cuenca, y se calculó además un análisis de componentes principales sobre rangos estandarizados. La regla es aportar al menos 50 % en cada cuenca con cobertura ≥ 90 %.

## Resultados

| Descriptor | Cobertura | ρ con relieve | Aporte frente al ranking (total · Atacama / Mojave / Utah) | Jezero (percentil en la muestra) | Lectura |
|---|---:|---:|---|---:|---|
| `hypsometric_integral` | 95,1 % | 0,03 | **0,80** · 0,79 / 0,72 / 0,85 | 0,613 (**p98**) | Eje independiente y estable. |
| `elevation_skew_p95_p05` | 95,1 % | −0,03 | 0,80 · 0,79 / 0,73 / 0,84 | −0,305 (**p3**) | Redundante con la integral (ρ = −0,98). |
| `aspect_240m_resultant_length` | 91,2 % | −0,08 | 0,36 · 0,37 / 0,38 / 0,55 | 0,452 (p40) | Aporte parcial; no cumple la regla en Atacama ni Mojave. |
| `slope_240m_gt25_fraction` | 100 % | 0,77 | 0,23 · 0,28 / 0,27 / 0,13 | 0,000 | Redundante. |
| `slope_240m_gt15_fraction` | 100 % | 0,86 | 0,08 · 0,08 / 0,08 / 0,07 | 0,027 (p51) | Redundante (ρ = 0,96 con P90). |
| `roughness_360m_p50_m` | 100 % | 0,78 | 0,06 · 0,07 / 0,09 / 0,03 | 7,57 | Redundante con la pendiente en terreno árido. |

Dentro del vector actual, la pendiente P50 solo aporta un 17 % de orden que el relieve no explica, y la P90 un 16 % sobre relieve y P50. En la muestra, Jezero queda en los percentiles 44, 46 y 49 de relieve, P50 y P90.

| Componente | Varianza explicada | Cargas dominantes |
|---|---:|---|
| 1 · escabrosidad | 61,2 % | Relieve, P50, P90, rugosidad y fracciones de pendiente fuerte (cargas de 0,38 a 0,42) |
| 2 · forma hipsométrica | 22,7 % | Integral hipsométrica (+0,68) y asimetría (−0,68) |
| 3 · organización | 10,4 % | Concentración de orientación (−0,88) |

## Sensibilidad al encuadre de la huella

**Pregunta.** ¿El valor atípico de Jezero y el orden entre ventanas terrestres se mantienen si la huella se desplaza o se reduce?

**Método.** Para las 716 ventanas de desarrollo y para Jezero se recalculó el contrato con la huella de 3 km desplazada 120, 300, 750 y 1.500 m en ocho direcciones (las diagonales conservan la distancia euclídea), y con una huella de 1,8 km en el mismo centro. Se compara el cambio de cada descriptor con su dispersión entre ventanas (IQR) y se mide si el orden entre ventanas se conserva (Spearman entre la huella original y la desplazada). Los bloques reservados no se leyeron. El DTM de Jezero mide ~7 km de ancho, así que dos desplazamientos de 1.500 m al este no tienen soporte suficiente.

| Descriptor | ρ de orden, mediana por dirección (120 / 300 / 750 / 1.500 m · huella 1,8 km) | IQR entre ventanas / cambio mediano (120 / 300 / 750 m) |
|---|---|---|
| Relieve P95–P5 | 0,999 / 0,993 / 0,963 / 0,901 · 0,969 | 73 / 31 / 12 |
| Pendiente P50 | 0,999 / 0,995 / 0,974 / 0,923 · 0,987 | 113 / 46 / 18 |
| Pendiente P90 | 0,999 / 0,993 / 0,965 / 0,905 · 0,972 | 113 / 47 / 19 |
| Concentración de orientación | 0,997 / 0,983 / 0,903 / 0,734 · 0,903 | 39 / 17 / 7 |
| **Integral hipsométrica** | 0,987 / 0,937 / **0,733** / **0,458** · **0,766** | 17 / 7,2 / **3,1** |

| Encuadre de Jezero | Integral hipsométrica | Percentil en las 716 ventanas |
|---|---:|---:|
| Huella original de 3 km | 0,613 | 98 |
| Desplazada 120 m (8 direcciones) | 0,594–0,615 | 97–98 |
| Desplazada 300 m | 0,529–0,615 | 87–98 |
| Desplazada 750 m | 0,509–0,614 | 78–98 |
| Desplazada 1.500 m (6 con soporte) | 0,406–0,607 | 25–98 |
| Huella de 1,8 km | 0,493 | 70 |

**Lectura.**
- **La integral es unas cuatro veces más sensible al encuadre que el relieve y la pendiente.** A 300 m su orden se conserva (ρ = 0,94) y la dispersión entre ventanas supera siete veces el cambio por desplazamiento. A 750 m el cambio típico ya es un tercio del IQR, y el orden cae a ρ = 0,73.
- **Lo atípico de Jezero resiste errores de registro, no cambios de encuadre.** Con 120 m sigue en el percentil 97–98. Al desplazar 300–750 m hacia el oeste o el este, o al reducir la huella a 1,8 km, baja a los percentiles 70–87, porque el abanico deja de ocupar la parte alta de la huella. La integral describe la relación entre el depósito y su entorno dentro de un encuadre concreto, no el depósito por sí solo.
- **En el barrido de reconocimiento el encuadre es arbitrario.** Con centros cada 10 km y huellas de 3 km, un abanico terrestre casi nunca queda centrado como el de Jezero, y su integral sería la de un encuadre cualquiera.

**Uso propuesto.** La integral hipsométrica no debe entrar en el ranking del barrido de 10 km. En la etapa densificada sobre candidatas preseleccionadas por escabrosidad, calcularla sobre una retícula local con paso ≤ 300 m alrededor del centro, comparar el **mejor encuadre** con el de Jezero y publicar el rango observado. Para la referencia conviene declarar el encuadre que se compara: la huella actual de Jezero está centrada en el abanico, y con 1,8 km el valor cambia. La concentración de orientación aguanta mejor (ρ = 0,90 a 750 m) y puede calcularse en ambas etapas.

## Etapa densificada: mejor encuadre

Implementado en [`pipelines/etl_framing.py`](../../../pipelines/etl_framing.py) y en el comando `etl_pipeline.py refine`.

- **Qué hace.** Toma las `--limit` mejores candidatas del ranking topográfico bajo el perfil de elegibilidad elegido. Para cada una, lee GLO‑30 una sola vez sobre una rejilla ampliada y recalcula el contrato en una retícula de 5 × 5 encuadres (paso de 300 m, hasta 600 m por eje). Elige el encuadre más cercano a Jezero en relieve e integral a la vez (criterio `joint_relief_hi_v2`, ver la sección siguiente). Hasta el 14 de noviembre lo elegía solo por la integral (`hi_only_v1`), que es el criterio del ensayo de esta sección.
- **Qué guarda.** La tabla `enrichment_framing` registra:
  - la integral en el centro, en el mejor encuadre y su rango (mínimo y máximo);
  - el desplazamiento elegido;
  - `best_at_lattice_edge`, que indica que el mejor encuadre cayó en el borde de la retícula y que podría mejorar más lejos;
  - el relieve, las pendientes y la orientación en ese encuadre.
  Sin DEM, el estado es `insufficient_coverage`.
- **Cómo se consulta.** `rank` muestra esas columnas y `hi_best_abs_delta` (diferencia con la referencia) sin cambiar la distancia del barrido. `rank --stage densified` ordena por relieve e integral en el mejor encuadre (siguiente sección).
- **Sesgo conocido.** Elegir el mejor de 25 encuadres acerca a todas las candidatas hacia la referencia por igual. Los valores son comparables entre candidatas encuadradas con la misma retícula, no con una medición de encuadre fijo.

**Ensayo del 14 de noviembre.** Se cargaron en un almacén temporal las 10 ventanas de desarrollo más cercanas a Jezero en relieve y pendiente, y se ejecutó `refine` con GLO‑30 (26,6 s).

| Ventana | Integral en el centro | Mejor encuadre (desplazamiento E, N) | ¿En el borde? | Relieve centro → mejor encuadre (m) |
|---|---:|---|:-:|---|
| `utah-002-007` | 0,500 | 0,578 (600, 300) | sí | 98,8 → 93,0 |
| `mojave-010-013` | 0,559 | 0,578 (300, 600) | sí | 135,1 → 120,1 |
| `mojave-002-002` | 0,544 | 0,576 (0, −300) | no | 114,6 → 100,5 |
| `utah-010-008` | 0,500 | 0,565 (−600, −300) | sí | 104,1 → 91,8 |
| `atacama-016-003` | 0,408 | 0,545 (600, 600) | sí | 130,5 → 133,9 |
| `utah-005-002` | 0,435 | 0,515 (600, 600) | sí | 116,0 → 142,8 |
| `mojave-004-002` | 0,463 | 0,497 (600, 600) | sí | 108,7 → 117,3 |
| `mojave-011-006` | 0,449 | 0,487 (600, −600) | sí | 117,2 → 104,4 |
| `utah-005-012` | 0,432 | 0,481 (−600, 600) | sí | 144,5 → 132,1 |
| `utah-011-004` | 0,422 | 0,454 (600, −600) | sí | 110,0 → 97,2 |

- Las integrales en el centro coinciden con las del experimento de redundancia, lo que confirma que se mide lo mismo.
- Ninguna candidata alcanza el 0,613 de Jezero, ni siquiera en el mejor encuadre. Entre las 10 con su misma escabrosidad, ninguna tiene un depósito tan elevado respecto de su entorno.
- En 9 de 10, el mejor encuadre cae en el borde de la retícula. Conviene repetir con `--max-offset 900` o más antes de concluir.
- El mejor encuadre puede alejar el relieve de la referencia: `utah-005-002` pasa de 116 a 143 m. Por eso el relieve se guarda en ese mismo encuadre, para valorar el compromiso.

```sh
bash scripts/ejecutar_minerales.sh scripts/etl_pipeline.py refine --limit 25 --profile arid_mars_surface_v2
bash scripts/ejecutar_minerales.sh scripts/etl_pipeline.py rank --limit 25
```

## Ranking densificado: relieve e integral en el mejor encuadre

Implementado el 14 de noviembre de 2026 en `FeatureStore.rank_densified` (`pipelines/etl_store.py`) y en `etl_pipeline.py rank --stage densified`. El ranking del barrido (`--stage recon`, por defecto) no cambia.

- **Vector** `densified_relief_hi_v2`. Usa una feature por eje del análisis de componentes: el relieve P95–P5 (escabrosidad) y la integral hipsométrica (forma), ambas medidas en el mismo encuadre. Las pendientes se siguen mostrando, pero no entran en la distancia porque repiten el eje del relieve.
- **Distancia** `0,5·|relieve − 120,27 m|/5,82 m + 0,5·|HI − 0,613|/0,0130`. Cada escala es el cambio absoluto mediano que produce un paso de retícula (300 m) en las 716 ventanas de desarrollo ([sensibilidad](../../evidencia-descriptores-forma/sensibilidad-huella.json)). Así ambos términos se cuentan en «pasos de encuadre», y la escala no depende de qué candidatas se comparen. Los pesos iguales son un punto de partida, no una calibración. Cada fila lleva `ranking_vector_status = pending_blind_validation`.
- **La misma distancia elige el encuadre y ordena** (`framing.densified_distance`). `refine` evalúa todos los encuadres de la retícula y se queda con el de menor distancia. Por eso un encuadre que alcanza la integral de Jezero a costa de alejarse en relieve queda penalizado, y la selección no puede contradecir al ranking. `enrichment_framing` guarda el criterio (`framing_criterion`), el relieve de referencia y la distancia en el centro y en el mejor encuadre.
- **Qué candidatas se comparan.** Solo las encuadradas con el criterio conjunto, con la misma referencia de relieve e integral y con la misma retícula (`--step`, `--max-offset`). Las filas antiguas, sin criterio, se leen como `hi_only_v1` y quedan fuera. `enrichment_framing` guarda solo la última medición por ventana: reencuadrar con otra retícula sustituye la anterior.

**Ensayo del 14 de noviembre.** El almacén tenía 8 ventanas elegibles con cobertura bajo `arid_mars_surface_v2`, todas del barrido mundial. Se ejecutó `refine` sobre copias temporales del almacén, con paso de 300 m y retículas de 600 m (25 encuadres, 60 s) y de 900 m (49 encuadres, 52 s).

| Ventana (lat, lon) | Puesto en el barrido | Puesto densificado (600 / 900 m) | HI centro → mejor (900 m) | Relieve centro → mejor (900 m; solo integral) | Distancia centro → mejor (900 m) | ¿Borde? |
|---|---:|---:|---|---|---|:-:|
| `…32637-306-73` (27,64, 41,33) | 1 | **1 / 1** | 0,612 → 0,612 | 121 → 121 m (121) | 0,13 → 0,10 | no |
| `…32718-841-39` (−14,38, −76,02) | 6 | **2 / 2** | 0,560 → 0,611 | 114 → 116 m (116) | 2,54 → 0,44 | no |
| `…32719-747-39` (−22,87, −70,07) | 7 | 3 / 3 | 0,409 → 0,491 | 125 → 122 m (128) | 8,24 → 4,89 | sí |
| `…32631-323-71` (29,18, 5,16) | 2 | 7 / 4 | 0,354 → 0,518 | 118 → 143 m (150) | 10,15 → 5,68 | sí |
| `…32733-690-75` (−28,00, 17,54) | 8 | 4 / 5 | 0,362 → 0,475 | 129 → 116 m (83) | 10,44 → 5,72 | sí |
| `…32719-723-61` (−25,04, −67,91) | 4 | 5 / 6 | 0,432 → 0,476 | 117 → 109 m (79) | 7,25 → 6,23 | sí |
| `…32632-251-74` (22,68, 11,34) | 5 | 8 / 7 | 0,322 → 0,458 | 124 → 116 m (76) | 11,57 → 6,35 | sí |
| `…32642-358-70` (32,34, 71,13) | 3 | 6 / 8 | 0,418 → 0,439 | 123 → 116 m (78) | 7,72 → 7,03 | no |

- **La forma reordena candidatas con la misma escabrosidad.** Las ocho tienen un relieve de 114–129 m en el centro. La ventana de la costa de Ica (Perú) pasa del puesto 6 al 2: con 300 m de desplazamiento alcanza la integral de Jezero sin cambiar su relieve, y su distancia cae de 2,54 a 0,44. La segunda del barrido (Argelia) baja al 4–7, porque ni a 900 m pasa de 0,52 y para acercarse tiene que subir a 143 m de relieve.
- **La selección conjunta mantiene el relieve.** Con el criterio anterior, elegir solo por la integral llevaba el relieve de cuatro candidatas a 76–83 m. Con el conjunto se queda en 109–116 m, y la integral solo pierde 0,02–0,05. El orden apenas cambia frente al criterio anterior: los tres primeros puestos son los mismos, y del cuarto en adelante el orden se mueve tanto entre criterios como entre retículas.
- **Las dos primeras son las únicas con una distancia baja** (< 0,5 frente a ≥ 4,9) y con un mejor encuadre que no depende de la retícula. Las demás no tienen cerca un encuadre con la integral de Jezero: su mejor encuadre suele caer en el borde, y su orden relativo no es estable.

```sh
bash scripts/ejecutar_minerales.sh scripts/etl_pipeline.py refine --limit 25 --max-offset 900
bash scripts/ejecutar_minerales.sh scripts/etl_pipeline.py rank --stage densified --max-offset 900 --limit 25
```

[Resultados del ensayo, con los del criterio anterior para comparar](../../evidencia-descriptores-forma/ranking-densificado.json)

## Interpretación

- **El ranking actual ordena por un solo eje.** Relieve, P50 y P90 entran con pesos 0,40/0,35/0,25 en `rank_similar`, pero a 30 m sus correlaciones de rangos entre sí van de 0,89 a 0,91. El ranking premia ventanas tan escabrosas como Jezero sin mirar su forma.
- **La integral hipsométrica separa Jezero de la mayoría de las candidatas de escabrosidad parecida.** Una integral de 0,61 indica elevación concentrada en la parte alta de la huella: el abanico es un depósito elevado sobre el fondo del cráter. La mediana terrestre (0,46) y su asimetría positiva describen huellas cóncavas, como cuencas, piedemontes y valles en relleno. La integral depende de dónde cae la huella: una ventana desplazada hacia el fondo del cráter daría otro valor. Antes de usarla para ordenar hay que medir su sensibilidad a desplazamientos de la huella, como se hizo con THEMIS.
- **La asimetría no aporta frente a la integral.** Se conserva en la base como diagnóstico, pero solo una de las dos debería entrar al ranking.
- **La orientación es un tercer eje débil.** Aporta 36–55 % según la cuenca. Puede servir para distinguir abanicos y escarpes de lomas dispersas, pero necesita la revisión ciega de formas para saber si esa distinción corresponde a la forma buscada.
- **Las fracciones de pendiente fuerte son útiles como umbral, no como medida de parecido.** Son interpretables para transitabilidad en una base lunar (> 15°) y para escarpes (> 25°), pero repiten la información de la P90.

## Decisiones

| Feature | Decisión | Condición para revisarla |
|---|---|---|
| `hypsometric_integral` | `densified_stage_ranking`: fuera del ranking del barrido; entra con el relieve en el ranking densificado (`densified_relief_hi_v2`, pesos 0,5/0,5 en pasos de encuadre), con el encuadre elegido por la misma distancia | Pesos y vector `pending_blind_validation`: compararlo con el ranking del barrido en los bloques reservados (Paso 7) antes de usarlo como orden final |
| `aspect_240m_resultant_length` | `candidate_conditional` | Revisión ciega de formas que muestre que separa abanicos de relieve disperso |
| `elevation_skew_p95_p05` | `diagnostic_only` | Redundante con la integral (ρ = −0,98) |
| `slope_240m_gt15_fraction`, `slope_240m_gt25_fraction` | `threshold_only` | Umbrales del escenario lunar; no como distancia |
| `roughness_360m_p50_m` | Se mantiene `approved_conditional`, sin peso en el ranking árido | Aporta 6 % frente al ranking en las 716 ventanas |

El vector menos redundante (relieve e integral hipsométrica) ya existe como ranking densificado. La concentración de orientación se añadiría como tercer eje si la revisión ciega la valida. El ranking del barrido (`rank_similar`) sigue igual porque la integral no es estable con su encuadre fijo, y el densificado sigue pendiente de compararse en los bloques reservados. Las ventanas guardadas antes de este cambio no tienen las columnas nuevas y deben re-extraerse para obtenerlas.

## Alcance, partición sin fuga espacial y replicación multi-dominio (polar y paleolago)

La repetición del análisis en particiones sin bloques adyacentes ni descongelación de reservas previas y en los dominios `polar_cold_v1` y `paleolake_margin_v1` sobre teselas GLO-30 en caché local (`mode='cache'`, con `0` pares adyacentes desarrollo–*holdout* y bloques *holdout* no leídos) confirma el comportamiento del vector de forma:

| Dominio y subconjunto (`GLO-30`, `30 m`) | Cuenca reservada (*holdout*, no leída) | Ventanas desarrollo (completas) | Cobertura `hypsometric_integral` | Aporte `unique_share_vs_ranking` (mín. por cuenca) | `adds_information` | Observación principal |
|---|---|---:|---:|---:|:-:|---|
| `arid_mars_surface_v2` (cuenca completa sin *holdout* previo) | `mojave` (`279`) | `457` (`utah` + `atacama`) | `93,49 %` | `0,8475` (`0,7884`) | sí | Estable frente a eliminación de contigüidad; `skew` redundante ($\rho = -0,98$). |
| `arid_mars_surface_v2` (búfer de 1 bloque de Chebyshev) | `5` bloques originales (`257`) | `122` (`utah:-112` + `mojave:-118`) | `95,31 %` | `0,7389` (`0,5112`) | sí | Mantiene la regla en ambas cuencas con $\ge 1$ bloque completo de separación. |
| `polar_cold_v1` (desarrollo en Ártico) | `antartida` (`290` en 4 bloques) | `409` (`416` rankable en `taimyr` + `groenlandia_can`) | `98,32 %` | `0,9012` (`0,7887`) | sí | `roughness_360m_p50_m` queda redundante (`0,0371`); con búfer de 1 bloque `HI = 0,8992` (`n = 310`). |
| `paleolake_margin_v1` (márgenes con relieve $\ge 2\text{ m}$) | `amadeus` (`110` en 2 bloques) | `538` (`makgadikgadi` + `sistan` + `balkhash`) | `88,20 %` global / `100 %` si relieve $\ge 2\text{ m}$ | `0,8430` (`0,6628`) | sí (en relieve $\ge 2\text{ m}$) | `11,8 %` de fondos planos de salar tienen `relieve < 2 m` (`HI = None`); en márgenes con relieve $\ge 2\text{ m}$ y con búfer de 1 bloque (`n = 272`, `HI = 0,8017`) conserva su eje independiente. |

- En los tres dominios `aspect_240m_resultant_length` pierde cobertura sobre terrenos planos (< 1° de pendiente: `90,14 %` árido estricta, `78,37 %` polar, `33,77 %` paleolago) y no alcanza el criterio multi-cuenca; las fracciones `slope_240m_gt15/25_fraction` tienen varianza nula (`0,0`) en cuencas llanas como Taimyr, Makgadikgadi o Balkhash y siguen siendo solo umbrales interpretables.
- Los descriptores se calcularon sobre GLO-30, que es un modelo de superficie. En terreno árido el efecto del dosel es pequeño, como mostró la [validación topográfica](Validacion%20de%20armonizacion%20topografica%20en%20desierto%20bosque%20y%20costa.md).

## Evidencia y reproducción

[Resultados por ventana, particiones sin fuga y replicación polar/paleolago](../../evidencia-descriptores-forma/resultados.json) · [Manifiesto con hashes y activos GLO-30](../../evidencia-descriptores-forma/manifest.json) · [Script](../../../scripts/evaluar_descriptores_forma.py) · [Pruebas sintéticas](../../../tests/test_etl_shape.py)

```sh
bash scripts/ejecutar_minerales.sh scripts/evaluar_descriptores_forma.py --reuse-arid-cache
bash scripts/ejecutar_minerales.sh -m unittest tests.test_etl_shape tests.test_contrato_comun_entrega3 -v
```

Sensibilidad al encuadre: [resultados](../../evidencia-descriptores-forma/sensibilidad-huella.json) · [manifiesto](../../evidencia-descriptores-forma/manifest-sensibilidad.json) · [script](../../../scripts/sensibilidad_integral_hipsometrica.py) (204 s).

```sh
bash scripts/ejecutar_minerales.sh scripts/sensibilidad_integral_hipsometrica.py --mode auto
```
