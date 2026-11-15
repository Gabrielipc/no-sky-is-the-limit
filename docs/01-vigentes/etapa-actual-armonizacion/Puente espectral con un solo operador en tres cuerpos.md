# Puente espectral con un solo operador en tres cuerpos

Implementación del 14 de noviembre de 2026 para la prioridad 6 de la [auditoría de armonización](Auditoria%20de%20armonizacion%20y%20features%20frente%20a%20fuentes%20del%20challenge.md).

**Problema.** La [Tercera entrega](Tercera%20entrega%20-%20muestreo%20estratificado%20y%20puentes%20entre%20cuerpos.md) comparaba parámetros de resumen continuos de CRISM en Jezero (sobre toda la huella con `IN = 0`) contra profundidades del mejor ajuste Tetracorder de EMIT L2B (solo sobre muestras identificadas en cada grupo). Magnitud física, umbral de detección y denominador eran distintos.

**Solución.** Aplicar un **único operador continuo** ([`pipelines/spectral_params.py`](../../../pipelines/spectral_params.py)) sobre cubos de reflectancia de los tres cuerpos —**CRISM MTRDR** en Marte, **EMIT L2A v002** en la Tierra y **Chandrayaan‑1 M³ L2** en la Luna— usando en todos los casos la misma huella cuadrada en proyección azimutal equidistante local (`1,8 × 1,8 km` y `3,0 × 3,0 km`), el mismo umbral fijo por indicador y el mismo denominador (celdas válidas dentro de la huella, con soporte mínimo `≥ 80 %` y `≥ 30` celdas).

> **Modo de ejecución local y migración a GCP.** Por restricción de ancho de banda y latencia local, la validación y la generación de [`docs/evidencia-puente-espectral/resultados.json`](../../evidencia-puente-espectral/resultados.json) en este entorno corrieron en modo `--offline` sobre la caché local (CRISM `FRT000047A3`, glóbulos `LOC` locales de M³ y geometría GLT local de EMIT L2B), dejando tipadas como `on_demand_fetchable` las lecturas remotas completas hacia una VM Spot en GCP. Se reportan además las mediciones parciales obtenidas en las primeras lecturas remotas (Utah y tiras polares de Haworth y de Gerlache) distinguiéndolas explícitamente del estado sincronizado en JSON offline.

---

## 1. Operador espectral común y validación frente a CRISM

[`pipelines/spectral_params.py`](../../../pipelines/spectral_params.py) transcribe la formulación hiperespectral oficial del nodo PDS (*CRISM Summary Parameter Calculation Reference*, J. Christian, julio de 2026), más `BD920_2`:

- Para cada término $T(\lambda, k)$, $R_\lambda$ toma la mediana espectral ignorando `NaN` de una ventana centrada en la banda más cercana a $\lambda$.
- El continuo $RC_\lambda$ se interpola linealmente entre anclas $T(\lambda_L, k_L)$ y $T(\lambda_H, k_H)$ usando las longitudes de onda reales de cada sensor (extrapolando cuando procede, como en `OLINDEX3`).
- El ancho de ventana $k$ se evalúa literalmente en canales para CRISM (`kernel_mode="channels"`, muestreo `~6,55 nm/canal`) y con el mismo ancho físico en nanómetros ($\pm k \cdot 6,55 / 2\text{ nm}$) para EMIT L2A y M³ (`kernel_mode="nm"`).

### Contraste con el producto oficial SR de 2017 (`FRT000047A3`)

Se aplicó el operador sobre la reflectancia `IF` (`FRT000047A3_07_IF166J_MTR3`) en la franja cacheada (`filas 552:752`, $n = 137.924$ píxeles válidos) y en la huella de `1,8 km` sobre el abanico de Jezero ($n = 8.897$), comparando contra `frt000047a3_07_sr166j_mtr3.img`:

| Parámetro | Complejo / rol | $r$ franja (`552:752`) | $\text{med}|\Delta|$ franja | $r$ huella `1,8 km` | Estado en puente |
|---|---|---:|---:|---:|---|
| `BD1900R2` | Hidratados `1,9–2,26 µm` (rango 1) | **1,00000** | `4,9 × 10⁻⁸` | **1,00000** | Validado exacto |
| `LCPINDEX2` | Máficos Fe²⁺ `1,0 µm` (rango 2) | 0,9928 | 0,00061 | 0,9918 | Validado |
| `BD530_2` | Óxidos Fe³⁺ `0,53 µm` (rango 1) | 0,9878 | 0,00107 | 0,9904 | Validado |
| `HCPINDEX2` | Piroxeno alto Ca (diagnóstico) | 0,9848 | 0,00100 | 0,9742 | Validado |
| `BD2290` | Fe/Mg‑OH `2,30 µm` (rango 2) | 0,9822 | 0,00021 | 0,9852 | Validado |
| `OLINDEX3` | Máficos Fe²⁺ `1,0 µm` (rango 1) | 0,9789 | 0,00220 | 0,9627 | Validado |
| `BD860_2` | Óxidos Fe³⁺ `0,86 µm` | 0,9669 | 0,00074 | 0,9154 | Validado |
| `BD2210_2` | Al‑OH `2,20 µm` (rango 2) | 0,9616 | 0,00023 | 0,9573 | Validado |
| `MIN2295_2480` | Carbonatos `2,30–2,50 µm` (rango 1) | 0,9502 | 0,00053 | 0,9584 | Validado |
| `BD2500_2` | Carbonatos `2,50 µm` | 0,9478 | 0,00053 | 0,9563 | Validado |
| `D2300` | Fe/Mg‑OH `2,30 µm` (rango 1) | 0,9431 | 0,00041 | 0,9692 | Validado |
| `D2200` | Al‑OH `2,20 µm` (rango 1) | 0,9274 | 0,00036 | 0,9698 | Validado |
| `BD1900_2` | Hidratados `1,9 µm` (diagnóstico) | 0,6897 | 0,00146 | 0,6865 | Diferencia entre versiones CAT |
| `BD2265` | Hidratados `1,9–2,26 µm` (rango 2) | 0,6628 | 0,00159 | 0,8188 | Anclas 2014 vs. 2026 (`r = 0,940` con 2014) |
| `BD920_2` | Máficos Fe²⁺ `0,92 µm` (rango 3) | — | — | — | 11 bandas VNIR de `IF` diferidas a GCP; SR oficial `p50 = -0,0144` |

**Por qué difieren `BD2265` y `BD1900_2`.** El producto SR público de 2017 fue generado con una versión anterior de CAT. Al sustituir en `BD2265` las anclas de la referencia de julio de 2026 (`2120–2340 nm`) por las de Viviano‑Beck et al. (2014) (`2210–2340 nm`), la correlación sube de `r = 0,6628` a **`r = 0,9370`** en la franja (y de `0,8188` a **`0,9401`** en la huella de `1,8 km`). Para evitar mezclar definiciones de distintas versiones de CAT entre planetas, **el puente aplica [`pipelines/spectral_params.py`](../../../pipelines/spectral_params.py) a los tres instrumentos** en lugar de reutilizar el raster SR precalculado en Marte.

---

## 2. Lectores por rangos, regla de emparejamiento y umbrales

### Lectura por rangos HTTP ([`pipelines/spectral_readers.py`](../../../pipelines/spectral_readers.py))

Cada lector descarga exclusivamente los bytes de bandas y filas que cubren la huella:

- **CRISM MTRDR (`crism_footprint`, `EnviBsqRemote`):** lee por HTTP `Range` solo las bandas y filas `BSQ float32` necesarias sobre `FRT000047A3_07_IF166J_MTR3`, aplicando la máscara `IN` (`band 9 == 0`). En modo `--offline` reutiliza el recorte cacheado (`552:752`) de `data/raw/crism/frt000047a3/if_cache`.
- **EMIT L2A v002 (`emit_footprint`, `RangeFile` + `h5py`):** lee sobre HTTP `Range` la reflectancia ortorrectificada en la rejilla `GLT` (`~60 m`) y la máscara agregada `EMIT_L2A_MASK_002` (`Aggregate Flag == 0`), pasando `EARTHDATA_TOKEN` por entorno sin persistirlo en disco. Marca como `NaN` las bandas con `good_wavelengths == 0`.
- **Chandrayaan‑1 M³ L2 (`m3_footprint`):** consulta las tiras `CH1M3_0004` (`RFL` `float32 BIL`) y sus geometrías `CH1M3_0003` (`LOC` `float64` + `OBS`), leyendo únicamente las líneas dentro de la huella con backoff exponencial ante respuestas `429/5xx` del nodo PDS. Excluye píxeles con incidencia solar facetaria `≥ 85°` (`max_incidence_deg = 85.0`) o valor inválido (`-999`).

### Regla de emparejamiento y umbrales ([`specs/analysis/puente-espectral-v1.json`](../../../specs/analysis/puente-espectral-v1.json), [`pipelines/spectral_bridge.py`](../../../pipelines/spectral_bridge.py))

Cada complejo mineral define una lista ordenada de indicadores con un único umbral fijo (`floor`):

| Complejo | Rango 1 (umbral · origen) | Rango 2 (umbral · origen) | Rango 3 (umbral · origen) |
|---|---|---|---|
| `abs_fe3_oxide_0p53_0p90um` | `BD530_2` (`0,05` · contrato) | — | — |
| `abs_al_oh_2p20um` | `D2200` (`0,005` · contrato) | `BD2210_2` (`0,005` · **inicial**) | — |
| `abs_fe_mg_oh_2p30um` | `D2300` (`0,008` · contrato) | `BD2290` (`0,005` · **inicial**) | — |
| `abs_carbonate_2p30_2p50um` | `MIN2295_2480` (`0,0` · contrato) | — | — |
| `abs_hydrated_sioh_so4_1p9_2p26um` | `BD1900R2` (`0,005` · contrato) | `BD2265` (`0,005` · **inicial**) | — |
| `abs_mafic_fe2_1p0um` | `OLINDEX3` (`0,13` · contrato) | `LCPINDEX2` (`0,0` · **inicial**) | `BD920_2` (`0,01` · **inicial**) |

`pair_comparison` compara cualquier par de sitios tomando, para cada complejo, **el primer indicador de la lista que ambos instrumentos cubren y miden** (`measured` o `measured_absent`). Si un instrumento queda sin cobertura espectral (`unobserved_by_product`) o por debajo del soporte espacial (`insufficient_coverage`), no sustituye el indicador por otra métrica ajena.

> [!IMPORTANT]
> **Umbrales iniciales pendientes de validación.** Los cinco umbrales marcados como **`inicial`** en [`specs/analysis/puente-espectral-v1.json`](../../../specs/analysis/puente-espectral-v1.json) (`BD2210_2 = 0,005`, `BD2290 = 0,005`, `BD2265 = 0,005`, `LCPINDEX2 = 0,0` y `BD920_2 = 0,01`) son elecciones de partida y deben validarse con controles minerales antes de usar las fracciones activas en ningún ranking. Además, aunque operador, huella, umbral y denominador son comunes, el soporte del píxel sigue siendo distinto (`CRISM ~18 m`, `EMIT ~60 m`, `M³ ~148–196 m` en las tiras polares revisadas).

---

## 3. Resultados por cuerpo

### Marte — Abanico de Jezero (`mars-jezero-fan`, `FRT000047A3`)

- **Huella de `1,8 km` (`8.897 / 10.200` celdas válidas = `87,23 % ≥ 80 %`):** mide los 6 complejos en modo local sin descargas remotas (salvo `BD920_2` sobre `IF`, cuyas 11 bandas VNIR quedan en `on_demand_fetchable` para GCP; el SR oficial de 2017 da `0,0 %` activo):

  | Complejo | Indicador (rango) | Umbral | P50 | P95 | Fracción activa | Estado |
  |---|---|---:|---:|---:|---:|---|
  | Fe³⁺ | `BD530_2` (1) | `0,05` | 0,1439 | 0,1557 | **100,0 %** | `measured` |
  | Al‑OH | `D2200` (1) · *`BD2210_2` (2)* | `0,005` | 0,00357 · *0,00054* | 0,00846 · *0,00300* | **29,22 %** · *0,47 %* | `measured` |
  | Fe/Mg‑OH | `D2300` (1) · *`BD2290` (2)* | `0,008` · *`0,005`* | 0,00579 · *0,00252* | 0,01231 · *0,00669* | **27,55 %** · *14,98 %* | `measured` |
  | Carbonato | `MIN2295_2480` (1) | `0,0` | −0,00615 | 0,00098 | **7,05 %** | `measured` |
  | Hidratados | `BD1900R2` (1) · *`BD2265` (2)* | `0,005` | 0,00236 · *0,00236* | 0,00744 · *0,00640* | **18,46 %** · *12,88 %* | `measured` |
  | Máficos Fe²⁺ | `OLINDEX3` (1) · *`LCPINDEX2` (2)* | `0,13` · *`0,0`* | 0,12004 · *−0,03588* | 0,13903 · *−0,02388* | **19,24 %** · *0,0 %* | `measured` (`LCPINDEX2` `measured_absent`) |

- **Huella de `3,0 km` (`20.514 / 28.390` celdas válidas = `72,26 % < 80 %`):** incumple el mínimo de cobertura espacial de la huella y los 6 complejos quedan en `insufficient_coverage`. Para emparejar con Jezero debe usarse la huella de `1,8 km` (aunque frente a M³ o EMIT esto introduce un contraste de escala con las huellas terrestres/lunares de `3,0 km`).

### Tierra — Utah y Atacama (`EMIT_L2A` v002)

- **Restricción atmosférica y de rango en EMIT (`381–2493 nm`):** las ventanas de vapor de agua atmosférico en la Tierra (`1327–1432 nm` y `1804–1960 nm`) y el límite superior del espectrómetro (`2493 nm`) anulan `D2300`, `BD1900R2`, `BD1900_2`, `MIN2295_2480`, `BD2500_2`, `OLINDEX3`, `LCPINDEX2` y `HCPINDEX2` (`unobserved_by_product`). En consecuencia:
  - El puente Tierra–Marte selecciona **`BD530_2`** (Fe³⁺), **`D2200`** (Al‑OH; su ancla baja en `1815 ± 22,9 nm` alcanza `~1792 nm`, cayendo al respaldo **`BD2210_2`** cuando la máscara de bandas malas de una escena se extiende por debajo de `1792 nm`), **`BD2290`** (Fe/Mg‑OH), **`BD2265`** (hidratados) y **`BD920_2`** (máficos Fe²⁺ a `0,92 µm`).
  - El complejo **`abs_carbonate_2p30_2p50um`** (`MIN2295_2480`, ancla alta en `2570 nm`) queda **`unbridged_unobserved`** en los pares con Tierra.
- **Estado de escenas:**
  - `earth-utah` (`EMIT_L2A_RFL_002_20230609T171110`): comprobación previa remota confirmó medición de óxidos férricos (`BD530_2`) y `Al-OH` con el operador común; los archivos L2B locales confirman `1.140 / 1.140` (`1,8 km`) y `3.200 / 3.200` (`3,0 km`) celdas GLT válidas en grupo 1.
  - `earth-atacama` (`EMIT_L2A_RFL_002_20220909T131332`) y `earth-atacama-2023` (`EMIT_L2A_RFL_002_20230130T135427`): ambas cubren la rejilla GLT al `100 %` (`990` celdas a `1,8 km` y `2.750` a `3,0 km`); en L2B local la escena de septiembre de 2022 tiene `990/990` y `2.750/2.750` celdas de relleno `-9999` en grupo 1, mientras la de enero de 2023 es válida en el `100 %` de la huella. La lectura L2A v002 remota completa de las tres escenas queda diferida a la VM Spot en GCP (`pending_gcp_l2a_fetch`).

### Luna — Polos sur y control iluminado Apollo 15 (`M3_L2`)

- **Fondo de Haworth (`moon-haworth-fondo`, `-87,45° S, -5,0° E`):** las dos tiras cacheadas localmente (`M3G20090416T195741` a `48,0 m` con `141` / `393` px a `1,8` / `3,0 km`, y `M3G20090417T193320` a `51,8 m` con `134` / `357` px; píxel `~151 m`) cubren geométricamente la huella, pero la lectura M³ mostró **`0` píxeles válidos** con el Sol bajo el horizonte local (incidencia solar `93–95°`), coherente con su clasificación de `100 %` sombra permanente (`volatile_target_psr`).
- **Cresta de de Gerlache (`moon-de-gerlache-cresta`, `-88,71° S, -68,7° E`):** el cribado `LOC` local confirma cobertura geométrica en `M3G20090426T155845` (`61,5 m`, `147` / `408` px a `~148 m`) y `M3G20090623T135841` (`37,0 m`, `87` / `238` px a `~196 m`). La primera tira medida de las 12 más cercanas arrojó solo **`48 %` de píxeles válidos a `~85°` de incidencia**, por debajo del umbral de `80 %` (`insufficient_coverage`). El cribado completo de las 12 tiras se mantiene en la especificación para GCP, pero los sitios polares lunares **no sostienen el puente espectral pasivo con M³** por iluminación rasante o sombra permanente.
- **Control iluminado Apollo 15 (`moon-apollo-15`, `26,13° N, 3,63° E`, basalto de mare en Hadley‑Apennine):** confirmado en coordenadas NSSDC e incorporado con cuatro tiras candidatas en OP1B/OP2A (`M3G20090206T124851_V01_RFL`, `M3G20090206T143952_V01_RFL`, `M3G20090610T104352_V01_RFL` y `M3G20090610T122814_V01_RFL`), diferidas a la VM Spot en GCP (`on_demand_fetchable`). En latitudes iluminadas sin vapor de agua atmosférico, M³ permite evaluar todos los indicadores SWIR/máficos sin las bandas ciegas de EMIT.

---

## 4. Pruebas y ejecución (local vs. GCP)

- **Pruebas automatizadas ([`tests/test_puente_espectral.py`](../../../tests/test_puente_espectral.py)):** 8 pruebas deterministas (`SyntheticSpectraTest`, `CoverageAndPairingRuleTest` y `LocalCacheIntegrationTest`) verifican cero sesgo sobre continuo lineal en los 15 parámetros, recuperación analítica de profundidades sintéticas (`10 %`), equivalencia entre `kernel_mode="channels"` y `"nm"` al muestreo de CRISM (`6,55 nm`) más su escalado en rejilla gruesa (`15 nm`), exclusión por bandas atmosféricas de EMIT y caída al rango 2/3, el corte del `80 %` y `≥ 30` celdas, la regla de emparejamiento en los tres cuerpos y la integración sobre las cachés locales de CRISM y M³ `LOC`.
- **Ejecución local offline (sin red):**
  ```bash
  bash scripts/ejecutar_minerales.sh -m pytest tests/test_puente_espectral.py tests/test_contrato_comun_entrega3.py -v
  bash scripts/ejecutar_minerales.sh scripts/puente_espectral.py --offline
  ```
- **Ejecución remota completa en GCP Spot VM (`us-west1-a`, con `EARTHDATA_TOKEN`):**
  ```bash
  bash scripts/ejecutar_minerales.sh scripts/puente_espectral.py --skip-measured
  ```
  (El flag `--skip-measured` conserva las huellas ya medidas en [`docs/evidencia-puente-espectral/resultados.json`](../../evidencia-puente-espectral/resultados.json) y completa en GCP las lecturas `pending_gcp_l2a_fetch`, `pending_gcp_m3_fetch` y las 11 bandas VNIR de `BD920_2` en `CRISM IF`.)
