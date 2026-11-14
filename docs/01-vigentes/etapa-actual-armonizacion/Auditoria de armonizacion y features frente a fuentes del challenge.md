# Auditoría de armonización y selección de características frente a las fuentes del challenge

Revisión del 14 de noviembre de 2026. Contrasta el contrato `contrato-comun-superficie-v1`, el ETL (`pipelines/etl_*.py`) y la evidencia de las entregas con los recursos oficiales del challenge (Earthdata Search, Worldview, PDS, LRO/Diviner, RCM, RADARSAT‑1, tutorial SAR de CSA, CDSE, ESA Open Science Catalog y JAXA G‑Portal). Complementa el [contraste de fuentes](Contraste%20de%20fuentes%20del%20challenge%202026.md), que inventarió qué aporta cada portal, y la [elección de fuentes y costo](Eleccion%20de%20fuentes%20y%20costo%20de%20cobertura%20mundial.md). Aquí el foco son los **vacíos de método**: dónde el vector de características o su armonización no sostiene lo que el reto pide, y qué features concretas lo cerrarían.

**Conclusión.** La armonización topográfica está bien fundamentada (base de 240 m, huella fija, controles con 3DEP). Los vacíos principales son: (1) las tres features del ranking están muy correlacionadas dentro del dominio árido y miden casi lo mismo; (2) el puente espectral Tierra–Marte compara magnitudes y denominadores distintos y aun así figura como `approved_for_ranking`; (3) el contrato no contempla la Luna, aunque el reto es *Permanent Moon base locations and Mars*; (4) la compuerta de elegibilidad es exclusivamente árida y tiene errores de etiquetado; y (5) varias dimensiones marcadas como “pendientes” ya tienen productos oficiales en los portales del challenge, algunos con puentes físicos directos entre cuerpos.

Esta revisión contrastó código, evidencia y documentación. No se descargaron granulos nuevos; la disponibilidad y cobertura de los productos propuestos debe confirmarse antes de medir.

## 1. Vacíos en las features aprobadas

### 1.1 Redundancia del vector topográfico

La Tercera entrega justifica la complementariedad de relieve y pendiente con `r = 0,7628` (Pearson, n = 11 sitios a 30 m). La propia evidencia muestra otra cosa:

| Par (fuente: `seleccion-y-redundancia.json`) | Spearman ρ | Pearson r | n |
|---|---:|---:|---:|
| relieve vs. pendiente P50 (ventanas de desarrollo, 300 m) | 0,954 | 0,925 | 716 |
| relieve vs. pendiente P90 (ventanas de desarrollo, 300 m) | 0,946 | 0,908 | 716 |
| pendiente P50 vs. P90 (ventanas de desarrollo, 300 m) | 0,925 | 0,908 | 716 |
| relieve vs. pendiente P50 (sitios, 30 m) | **0,946** | 0,763 | 11 |
| pendiente P50 vs. rugosidad 360 m (sitios, 30 m) | 0,964 | **0,986** | 11 |

- Dentro del dominio árido, `relief_p95_p05_m`, `slope_240m_p50_deg` y `slope_240m_p90_deg` comparten ~85–91 % de su orden. La distancia ponderada 0,40/0,35/0,25 de `rank_similar` (`pipelines/etl_store.py`) cuenta en la práctica un solo eje de “escabrosidad” tres veces.
- El `r = 0,76` citado es el valor más bajo disponible, con 11 sitios de estratos muy distintos (bosque, polo, desierto). Con esa muestra el Spearman es 0,95.
- `roughness_360m_p50_m` es casi una función lineal de la pendiente P50 (r = 0,986). Su aprobación condicional no añade información en los sitios medidos.

**Refinamiento.** Sustituir los cuantiles redundantes por descriptores de **forma y organización**, que separan un abanico con canales de unas lomas dispersas con los mismos cuantiles (el riesgo 4 de la [revisión metodológica](../arquitectura-y-vision/revision-metodologica-atlas-30-m.md)). Todos se calculan con el mismo DEM y la misma huella, sin coste de adquisición:

| Feature propuesta | Qué separa | Nota de armonización |
|---|---|---|
| Integral hipsométrica `(media − min)/(max − min)` | Abanicos y cuencas en relleno (cóncavo) frente a mesetas o domos (convexo) | Adimensional; robusta a datum vertical. Usar P5/P95 en lugar de min/max. |
| Concentración de orientación (varianza circular del aspecto ponderada por pendiente) | Abanico o escarpe con orientación dominante frente a relieve isótropo | Calcular con la base de 240 m y excluir celdas con pendiente < 1°. |
| Convergencia/divergencia del flujo (fracción de celdas con acumulación > umbral, o curvatura plana a base fija) | Red de canales distributarios (divergente en abanico) frente a red tributaria | Reemplaza a `laplacian_curvature` (descartada por usar 4 vecinos): usar base física fija, igual que la pendiente. |
| Fracción de huella con pendiente > 15° y > 25° | Cola de escarpes; umbrales de transitabilidad y aterrizaje relevantes para una base lunar | Interpretables en ambos cuerpos; el soporte se reporta igual que el P90. |
| Asimetría (skewness) de la elevación relativa | Fondo plano con bordes elevados (cráter, playa) frente a pendiente regional | Útil para la referencia lunar, donde los cráteres dominan el relieve. |

Para seleccionar entre ellas, repetir el análisis de redundancia con **correlación parcial** controlando por relieve, o con un análisis de componentes principales en las 716 ventanas de desarrollo, y retener una feature por componente.

### 1.2 Puente espectral Tierra–Marte

La tabla 2.2 de la Tercera entrega compara, por complejo, la **fracción espacial de píxeles CRISM** sobre un umbral con la **fracción de muestras EMIT minerales** identificadas en un grupo Tetracorder. Son magnitudes distintas:

| Aspecto | CRISM (Jezero) | EMIT L2B (Tierra) | Consecuencia |
|---|---|---|---|
| Magnitud | Parámetro de banda continuo (`D2200`, `BD1900R2`…) según su formulación | Profundidad de banda del mejor ajuste de biblioteca | Los `p50`/`p95` no tienen la misma unidad física. |
| Denominador | Toda la huella con `IN = 0` | Solo muestras con identificación válida en el grupo, después de excluir orgánicos | “30,0 % vs. 29,8 %” en Al‑OH es una coincidencia numérica entre cocientes distintos. |
| Umbral de “activo” | Fijo por parámetro (`> 0,005`, `> 0,008`…) | `2 × fit ≥ 0,8` y `profundidad > 2σ` | La fracción depende de umbrales sin calibración cruzada. |

Además, el [plan de armonización](Plan%20de%20armonizacion%20de%20las%20dimensiones%20de%20superficie.md) dice que “la correspondencia entre instrumentos requiere calibración espectral”, mientras la Tercera entrega marca cinco complejos como `approved_for_ranking`. El código tampoco los usa: `rank_similar` solo ordena por topografía.

**Refinamiento.**
1. Reclasificar los cinco complejos como `functional_contract_bridge` con decisión `approved_as_context_only` hasta que exista una magnitud común.
2. Crear esa magnitud con **EMIT L2A (reflectancia)**: remuestrear a las longitudes de onda de CRISM y aplicar las mismas fórmulas de parámetros de resumen (Viviano‑Beck et al., 2014) que usa MTRDR. Así ambos cuerpos tienen el mismo operador, el mismo umbral y el mismo denominador (fracción de huella sobre umbral). EMIT L2A está en Earthdata Search (LP DAAC).
3. Esto también resuelve `abs_mafic_fe2_1p0um` (hoy `unobserved_by_product` en Tierra), porque L2A incluye la absorción de 1 µm.
4. Para la Luna, el análogo es **Chandrayaan‑1 M³** (PDS Imaging Node): bandas de 1 y 2 µm de piroxeno/olivino. Con L2A y M³, el complejo máfico sería el único puente espectral en los tres cuerpos.

### 1.3 Compuerta de elegibilidad

`classify_eligibility` (`pipelines/etl_extractors.py:48`) tiene tres problemas:

- **Etiqueta errónea por defecto.** Si `bare_or_sparse < 0,85` y `trees ≤ 0,05` (pastizal, cultivo, musgo/líquenes, humedal), la función devuelve `excluded_dense_canopy`. Una tundra o estepa queda registrada como bosque. Hace falta un estado propio (p. ej. `excluded_vegetated_non_tree`).
- **Hielo agrupado con urbano.** `ice > 0,05` y `built > 0,02` comparten `excluded_urban_or_ice`. Para un escenario polar, el hielo es una condición buscada, no un motivo de exclusión, y hoy no se puede separar en el almacén.
- **Agua permanente con tolerancia cero.** `permanent_water > 0,0` excluye cualquier ventana con un solo píxel de agua de WorldCover. Los análogos de Jezero (paleolago y delta) incluyen márgenes de playas, salares y lagos efímeros, que suelen tener algún píxel de agua. JRC (`water_occurrence_mean_pct`) ya se lee pero no participa: un umbral sobre ocurrencia ≥ 50 % y una tolerancia (p. ej. ≤ 2 % del área) serían más coherentes con la [validación costera](Plan%20de%20armonizacion%20de%20las%20dimensiones%20de%20superficie.md#cobertura-y-agua).

**Refinamiento.** Versionar la compuerta **por escenario** (`arid_mars_surface_v1`, `polar_lunar_cold_v1`, `paleolake_margin_v1`) con sus propios umbrales y guardar el motivo de exclusión con una sola causa por estado.

## 2. Vacíos de armonización entre cuerpos

### 2.1 La Luna no existe en el contrato

`BODY_ENUM = ('Earth', 'Mars')` (`pipelines/etl_contract.py`) y el esquema de procedencia no guarda CRS ni marco planetario. El enunciado del challenge pide sitios para una base lunar permanente y Marte, y cuatro de los recursos oficiales son lunares (PDS, LRO, Diviner). Las features necesarias para la referencia lunar son:

| Feature lunar | Producto oficial | Contraparte terrestre para la analogía |
|---|---|---|
| Relieve, pendiente P50/P90 y forma con la misma huella y base | LOLA de sitio (5 m, Haworth y otros) o mosaico polar de 20 m, con recuentos | GLO‑30 / ArcticDEM en la misma huella (ya en el pipeline) |
| Fracción de iluminación promedio y regiones permanentemente sombreadas (PSR) | Productos de iluminación LOLA (PGDA) | Sin equivalente directo: usar solo como compuerta del sitio lunar |
| Temperatura máxima, mínima y amplitud | Diviner polar a 240 m | Climatología MODIS LST día/noche (MOD11A1/MYD11A1) |
| Abundancia de rocas y parámetro H (termofísica del regolito) | Productos derivados de Diviner (verificar versión en PDS Geosciences) | Inercia térmica aparente (ver 2.2) |
| Retrodispersión y CPR (rugosidad decimétrica, posibles volátiles) | Mini‑RF (S‑band, polarimetría híbrida) | RCM en modo de polarimetría compacta (ver 3) |

Acciones: añadir `Moon` al enum, `crs_wkt` y `planetary_frame` (`MOON_ME`/DE421, `IAU_MARS`, EPSG terrestre) al esquema de procedencia, y una partición por proyección estereográfica polar para la Luna.

### 2.2 Térmica: falta el puente físico

THEMIS mide inercia térmica; Landsat ST mide temperatura de una escena. El propio piloto documentó que la LST de una escena varía 38,1 K en Utah entre enero y agosto (estado meteorológico). La Tercera entrega propone ATI pero no la especifica.

**Feature propuesta: inercia térmica aparente (ATI) climatológica**
`ATI = (1 − albedo) / (T_día − T_noche)`, con:
- `T_día`, `T_noche`: medianas estacionales de MOD11A1/MYD11A1 (Earthdata, 1 km, QA ≤ 2 K) sobre ≥ 20 observaciones despejadas por estación, guardando `n_obs` y el periodo.
- Albedo: MCD43A3 (albedo de onda corta, 500 m), mismo periodo.
- ECOSTRESS (70 m, día y noche a horas variables) como refinamiento donde haya pares cercanos.

La ATI no es la inercia de THEMIS (depende de la hora de paso y de la atmósfera), así que el nivel correcto es `functional_contract_bridge` comparando **rangos ordenados** (p. ej. percentil dentro de su cuerpo), no valores absolutos. Con Diviner (amplitud y parámetro H), la propiedad termofísica sería la segunda dimensión comparable en los tres cuerpos.

Escala: MODIS a 1 km da ~9 píxeles por huella de 3 km. Hay que publicar el soporte y no mezclarlo con la rejilla de 30 m.

### 2.3 Selección validada solo en dominio árido y con fuga espacial

- La redundancia y la estabilidad se midieron en Utah, Mojave y Atacama. Para un escenario polar o de paleolago, la selección debe repetirse con ventanas de ese dominio.
- Los bloques reservados son **adyacentes** a bloques de desarrollo de la misma cuenca (p. ej. `utah:-110_+38` limita con `utah:-111_+38`, y `atacama:-068_-24` con `atacama:-069_-24` y `atacama:-068_-25`). La distancia entre cuencas (≥ 662 km) no evita la autocorrelación entre bloques vecinos. Para una validación ciega, reservar **cuencas completas** (p. ej. Mojave entera) o añadir un búfer ≥ 1 bloque entre desarrollo y reserva.
- El documento de la Tercera entrega dice 13 bloques (10/3) y cita otros IDs, mientras `seleccion-y-redundancia.json` registra 16 bloques (11 de desarrollo y 5 reservados). Hay que regenerar el texto desde la evidencia.

## 3. Dimensiones “pendientes” que ya tienen fuente oficial

El plan de armonización marca humedad de suelo, nieve persistente y clima como pendientes de observación física. Los portales del challenge tienen productos para todas:

| Dimensión | Producto oficial (portal) | Feature propuesta | Nivel de comparabilidad |
|---|---|---|---|
| **Aridez** | GPM IMERG (Earthdata, 0,1°) · GSMaP (G‑Portal) | Precipitación media anual y fracción de meses secos, 2001–2025 | `planet_specific_constraint`: la hiperaridez es el criterio clásico de análogo marciano (Atacama). |
| **Humedad de suelo** | SMAP L3 (Earthdata, 9 km) · AMSR2 (G‑Portal, ~10 km) | Mediana y P90 de humedad volumétrica superficial por estación | Contexto regional; soporte mucho mayor que la huella, debe declararse. |
| **Nieve y hielo persistentes** | MOD10A1 (Earthdata, 500 m) · GCOM‑C/SGLI SICE (G‑Portal, 250 m) | Días/año con nieve observada sobre días válidos | Compuerta positiva en el escenario polar. |
| **Permafrost** | ESA CCI Permafrost v5 (Open Science Catalog, 1 km) | Probabilidad de permafrost y profundidad de capa activa | Contexto terrestre del escenario frío. |
| **Composición silicatada (infrarrojo térmico)** | ASTER GED v3 (Earthdata, 100 m) · ECOSTRESS emisividad | Posición del rasgo de Christiansen / índice máfico‑félsico de emisividad | Puente con Diviner (rasgo de Christiansen lunar) y THEMIS IR: los basaltos de la Luna y Marte se distinguirían de los sedimentos félsicos terrestres. |
| **Rugosidad decimétrica** | Sentinel‑1 RTC (CDSE) · OPERA RTC‑S1 (Earthdata) · RCM (CSA) | σ⁰ VV/VH mediana y CPR | Escala distinta (cm–dm) de la rugosidad DEM (360 m); no es redundante con ella. |
| **Altimetría láser** | ICESat‑2 ATL06/ATL08 (Earthdata) | Pendiente y rugosidad diferencial a lo largo de traza en bases de 20–100 m | Mismo principio de medición que LOLA y MOLA: puente `direct_metric` de perfil en los tres cuerpos, independiente del DEM. |

Tres puentes merecen prioridad por usar la misma física en varios cuerpos:

1. **Láser: ICESat‑2 ↔ LOLA ↔ MOLA.** Las pendientes y rugosidades diferenciales calculadas sobre perfiles de altimetría láser no dependen de la interpolación de un DEM ni del dosel cuando se usan los fotones de terreno de ATL08. ICESat‑2 cubre hasta 88° de latitud, incluido el Ártico canadiense.
2. **Radar polarimétrico: RCM compacto ↔ Mini‑RF.** Ambos permiten calcular la razón de polarización circular (CPR). La cobertura pública de RCM sobre tierra se limita a Canadá, donde está justamente el control lunar propuesto (Haughton, isla Devon). La diferencia de longitud de onda (C‑band 5,6 cm vs. S‑band 12,6 cm) obliga a comparar por rangos o a normalizar por escala.
3. **Térmico: ATI MODIS ↔ THEMIS TI ↔ Diviner (amplitud y parámetro H)** (sección 2.2).

## 4. Uso de herramientas del challenge sin coste de features

- **Worldview/GIBS para la revisión ciega de formas.** La revisión metodológica pide evaluar candidatas visualmente sin conocer su puesto. Worldview permite generar vistas con la misma fecha, capa y escala para cada ventana, y el enlace puede guardarse en el expediente.
- **Tutorial SAR de CSA** como guía para la primera escena RCM de Devon: calibración a σ⁰, corrección del terreno y máscaras de sombra antes de extraer features.
- **ESA Open Science Catalog** para fijar DOI y versión de los productos regionales (permafrost) en el manifiesto.

## 5. Prioridades

| Prioridad | Acción | Esfuerzo | Desbloquea |
|---|---|---|---|
| 1 | Corregir `classify_eligibility` (etiqueta por defecto, hielo separado, tolerancia de agua con JRC) y versionar la compuerta por escenario | Bajo | Escenarios polar y de paleolago sin reprocesar la topografía |
| 2 | Reclasificar los complejos espectrales a contexto y regenerar el texto de la Tercera entrega desde la evidencia (bloques, correlaciones) | Bajo | Coherencia entre documentación, evidencia y código |
| 3 | Añadir integral hipsométrica, concentración de orientación, fracción > 15°/25° y asimetría; repetir la redundancia con correlación parcial | Medio | Un ranking que distinga formas, no solo escabrosidad |
| 4 | Añadir `Moon`, CRS y marco planetario al contrato; extraer LOLA de Haworth con las mismas features | Medio | La mitad lunar del enunciado |
| 5 | ATI climatológica MODIS (MOD11A1/MYD11A1 + MCD43A3) y Diviner en las referencias | Medio | Dimensión termofísica comparable en tres cuerpos |
| 6 | EMIT L2A → parámetros CRISM; M³ para la Luna | Alto | Puente espectral defendible y complejo máfico |
| 7 | ICESat‑2 sobre candidatas y RCM compacto en Devon | Alto | Validación independiente del DEM y del CPR |

Antes de cada adición: fijar colección y versión, comprobar cobertura real en las ventanas de referencia y control, y registrar resolución efectiva, unidad, máscara, denominador y periodo, igual que en las entregas anteriores.
