# Puentes de altimetría láser (`ICESat‑2 ATL08`) y radar polarimétrico compacto (`RCM`)

> **Estado:** Contrato, extractores, controles polarimétricos y preparación para ejecución remota completados (14 de noviembre de 2026) · Corresponde a la **Prioridad 7** de la [Auditoría de armonización y features](Auditoria%20de%20armonizacion%20y%20features%20frente%20a%20fuentes%20del%20challenge.md).
> **Evidencia:** [`docs/evidencia-puentes-laser-radar/resultados.json`](../../evidencia-puentes-laser-radar/resultados.json) · **Especificación:** [`specs/sources/puentes-laser-radar-v1.json`](../../../specs/sources/puentes-laser-radar-v1.json).

---

## 1. Propósito y alcance en tres cuerpos

La comparación topográfica base descansa sobre `Copernicus GLO‑30` en Tierra frente a `MOLA`/`HiRISE` en Marte y `LOLA` en la Luna, pero un modelo digital de elevaciones o de superficie construido con radar interferométrico en banda X (`TanDEM-X` / `GLO‑30`) necesita una verificación independiente en dos ejes identificados en la auditoría:

1. **Verificación altimétrica independiente del DEM (`ICESat‑2/ATLAS ATL08` v007, `C3565574177-NSIDC_CPRD`):** perfiles láser directos de fotones sobre el núcleo de `3 km` de cada ventana, con dos escalas de pendiente a lo largo de la traza (`20 m` y `100 m`) y la pendiente diferencial multibanda de Kreslavsky & Head (2000) a `200 m` y `600 m` (esta última resoluble directamente por `MOLA` y `LOLA`), evaluando exactamente las mismas métricas sobre `GLO‑30` en los mismos pares de puntos y midiendo el sesgo vertical `DEM − láser` (`dem_minus_laser_median_m` y `dem_minus_laser_nmad_m`).
2. **Puente de polarimetría circular compacta (`RCM SAR‑C`, `NRCan rcm-ard`, `CEOS-ARD NRB-POL`):** la razón de polarización circular ($\mathrm{CPR} = \mathrm{RR}/\mathrm{RL}$), potencia total $S_1$ y grado de polarización $\mathrm{DoP}$ en banda C (`5,405 GHz`), homólogos físicos directos del $\mathrm{CPR}$ de `Mini‑RF` en banda S/X para la Luna.

| Dimensión | Sensor terrestre y colección | Producto / modo | Cobertura medida hasta hoy | Homólogo planetario |
|---|---|---|---|---|
| **Altimetría láser** | `ICESat‑2 / ATLAS` (`ATL08` v007, `C3565574177-NSIDC_CPRD`) | Segmentos de terreno a `20 m` / `100 m`, `h_te_best_fit` | Manicouagan completo (`measured`); Devon piloto parcial (`6/120`); piloto Atacama pre-corte (`35` gránulos); barrido completo de `12` candidatas + `3` controles pendiente en GCP Spot | `MOLA` (Marte) y `LOLA` (Luna) en líneas de base de `600 m` |
| **Radar polarimétrico** | `RADARSAT Constellation Mission` (`NRCan rcm-ard` MLC, `s3://rcm-ceos-ard`) | Polarimetría compacta circular-transmisión ($\gamma^0$), julio–septiembre | Manicouagan completo (`measured`, `12/60` escenas); Devon y Mistastin confirmados sin cobertura (`no_swath_coverage`) | `Mini‑RF` (Luna, $\mathrm{CPR} = \mathrm{RR}/\mathrm{RL}$ y $\mathrm{DoP}$) |

---

## 2. Esquema e integración en el Feature Store

Ambas dimensiones están formalizadas en [`pipelines/etl_bridges_schema.py`](../../../pipelines/etl_bridges_schema.py), registradas en la validación contractual de [`pipelines/etl_contract.py`](../../../pipelines/etl_contract.py), declaradas en [`specs/analysis/feature-store-etl-v1.json`](../../../specs/analysis/feature-store-etl-v1.json) y servidas por la vista unificada `features_unified` a través de `unified_bridge_columns_sql`:

- **`enrichment_altimetry`** (vista `enrichment_altimetry_latest`): agrupa `ALTIMETRY_COUNTS` (`granules_found`, `granules_with_data`, `n_tracks`, `n_segments`, `n_pairs_20m`, `n_pairs_100m`, `n_diff_200m`, `n_diff_600m`), `ALTIMETRY_METRICS` (`laser_slope_20m_p50_deg`, `laser_slope_20m_p90_deg`, `laser_slope_100m_p50_deg`, `laser_slope_100m_p90_deg`, `laser_diff_slope_200m_p50_deg`, `laser_diff_slope_600m_p50_deg`, `dem_slope_100m_p50_deg`, `dem_slope_100m_p90_deg`, `dem_diff_slope_200m_p50_deg`, `dem_diff_slope_600m_p50_deg`, `dem_minus_laser_median_m`, `dem_minus_laser_nmad_m`, `snow_flag_fraction`), `altimetry_status`, `source_manifest_id` y `updated_at`.
- **`enrichment_radar`** (vista `enrichment_radar_latest`): agrupa `RADAR_COUNTS` (`scenes_found`, `n_scenes`), `RADAR_METRICS` (`rcm_cpr_p50`, `rcm_cpr_p90`, `rcm_s1_p50_db`, `rcm_dop_p50`, `rcm_local_incidence_p50_deg`, `rcm_valid_fraction`), `radar_status`, `source_manifest_id` y `updated_at`.

Las tablas pasan `validate_bridge_table` antes de persistirse, imponiendo los estados permitidos (`measured`, `insufficient_valid_coverage`, `no_swath_coverage`, `on_demand_fetchable`) y rangos físicos estrictos (`pendientes` en `[0°, 90°]`, `rcm_cpr_* >= 0`, `rcm_dop_p50` en `[0, 1]`, fracciones válidas en `[0, 1]`).

---

## 3. Decisiones metodológicas y filtros de calidad

### 3.1 Altimetría láser (`pipelines/etl_altimetry.py`)

- **Reemplazo de `h_te_uncertainty` por `te_quality_score` y conteo de fotones:** las primeras pruebas reales sobre desierto desnudo mostraron que `h_te_uncertainty` en `ATL08` v007 reporta entre `20 m` y `300 m` incluso sobre terreno plano sin vegetación, descartando trazas enteras válidas. Se eliminó como filtro y se exige en su lugar `te_quality_score >= 60` (`MIN_TE_QUALITY_SCORE = 60`) y `n_te_photons >= 20` (`MIN_TE_PHOTONS = 20`) por segmento de `100 m`.
- **Convención de cobertura nival (`SNOW_CODE_MIN = 2`):** en `ATL08`, `segment_snowcover == 1` denota suelo libre de nieve; por ello solo se contabilizan con nieve los segmentos con `segment_snowcover >= 2`. La métrica `snow_flag_fraction` documenta esta fracción sin descartar el perfil cuando el resto de filtros se cumplen.
- **Marco vertical homogéneo (`EGM2008` → `WGS84`):** `ATL08` entrega `h_te_best_fit` referido al geoide `EGM2008` (`EPSG:4326+3855`), mientras que los puntos de control de `GLO‑30` se comparan sobre el elipsoide `WGS84` (`EPSG:4979`). El extractor reproyecta explícitamente la altura vertical con `pyproj` antes de calcular `dem_minus_laser_median_m` y `dem_minus_laser_nmad_m`.
- **Pendiente a lo largo de la traza y pendiente diferencial:** sobre perfiles contiguos sin huecos dentro del núcleo de `3 km` se calculan pendientes en pares de `20 m` y `100 m` y pendientes diferenciales $s_{\text{diff}}(L) = \left| \frac{h(x+L) - h(x)}{L} - \frac{h(x+L) - h(x-L)}{2L} \right|$ para `DIFF_BASELINES_M = (200.0, 600.0)`. El umbral de suficiencia para estado `measured` es `MIN_PAIRS_100M = 20`.
- **Subsetting en servidor con `Harmony` y seguridad de credenciales:** dado que leer archivos `ATL08` completos sobre la conexión local (`~0,14 MB/s`) requeriría ~12 horas solo para las pasadas iniciales, el módulo invoca `Harmony` (`sds/trajectory-subsetter`, colección `C3565574177-NSIDC_CPRD`) restringiendo al bbox extendido y a los grupos mínimos de `gt*l/r`. Cuando se accede vía HTTP por rangos (`RangeFile`), `_StripAuthOnRedirect` impide reenviar el token Bearer de Earthdata al redirigirse a otro host y valida explícitamente el host permitido.

### 3.2 Radar polarimétrico compacto (`pipelines/etl_radar.py`)

- **Derivación compacta de Stokes (`cpr`, `total_power_db`, `degree_of_polarization`):** a partir de las intensidades calibradas $\gamma^0$ en transmisión circular (`CH_CV` en matriz MLC pública de NRCan: $C_{HH} = \langle |S_{CH}|^2 \rangle$, $C_{VV} = \langle |S_{CV}|^2 \rangle$ y covarianza compleja $C_{HV}$), el extractor reconstruye las potencias circulares $\mathrm{RR}$ y $\mathrm{RL}$ y deriva:
  $$\mathrm{CPR} = \frac{\mathrm{RR}}{\mathrm{RL}}, \qquad S_1\,[\text{dB}] = 10\log_{10}(\mathrm{RR} + \mathrm{RL}), \qquad \mathrm{DoP} = \sqrt{1 - \frac{4\,\det(\mathbf{C})}{(\mathrm{RR}+\mathrm{RL})^2}}$$
- **Enmascaramiento y estacionalidad (`DEFAULT_MONTHS = (7, 8, 9)`):** solo se conservan escenas de julio a septiembre para evitar contaminación por manto nival húmedo/seco; se aplica la máscara de validez geométrica de NRCan (`VALID_BIT_VALUE = 1`, excluyendo layover y shadow), máscara de agua permanente/estacional `JRC >= 50 %` (`WATER_OCCURRENCE_PCT = 50.0`), soporte mínimo de celda válida por escena `>= 99,9 %` (`MIN_SCENE_SUPPORT = 0.999`) y fracción válida agregada mínima `>= 80 %` (`MIN_VALID_FRACTION = 0.8`). Las métricas resumen utilizan la mediana entre escenas en celdas válidas compartidas (`summarize_cells`).

---

## 4. Cobertura y resultados reales de radar polarimétrico (`RCM`)

La corrida real de `RCM` (`scripts/etl_puentes.py rcm`) evaluó los tres sitios canadienses de control el 14 de noviembre de 2026:

| Sitio de control (`region_id`) | Coordenadas | Agua JRC >= 50 % | Escenas encontradas / medidas | Estado | Métricas principales |
|---|---|---:|---:|---|---|
| **Cráter Haughton, Devon** (`control-v1:haughton-devon`) | `75,367° N, 89,683° O` | `0,01 %` | `0 / 0` | `no_swath_coverage` | Sin cobertura pública `NRCan rcm-ard` ni `EODMS` |
| **Cráter Mistastin, anillo sur** (`control-v1:mistastin-sur`) | `55,8156° N, 63,2995° O` | `3,87 %` | `0 / 0` | `no_swath_coverage` | Sin escenas públicas `rcm-ard` en la ventana |
| **Manicouagan, levantamiento central** (`control-v1:manicouagan-centro`) | `51,38° N, 68,70° O` | `1,77 %` | `60 / 12` | `measured` | `CPR P50 = 0,6220`, `CPR P90 = 0,6927`, `S1 P50 = −6,42 dB`, `DoP P50 = 0,2538`, `θ_inc P50 = 29,26°`, `valid = 0,9823` |

### Hallazgos clave de RCM

1. **Límite de latitud pública sobre Devon y ausencia en Mistastin:** el catálogo público `NRCan rcm-ard` (`s3://rcm-ceos-ard`) no cubre latitudes al norte de `~69,9° N`, y la consulta al catálogo público completo `EODMS RCMImageProducts` sobre el entorno de Devon (`74–77° N, 95–85° O`) devuelve `0` escenas públicas disponibles. Mistastin sur (`55,82° N`, seleccionado de forma reproducible en una retícula de `1,5 km` como el núcleo más cercano al centro con agua `<= 5 %`) tampoco presenta escenas en el repositorio público `rcm-ard`. Ambos se registran explícitamente en el store como `no_swath_coverage`.
2. **Control funcional completo en Manicouagan (`CPR P50 = 0,6220`):** elegido también con regla reproducible de mínima fracción de agua cerca del centro de la isla René‑Levasseur (`1,77 %` en el núcleo de `3 km`), reúne `60` escenas y `12` escenas válidas entre `2025-07-04` y `2026-09-01` (`9` pases descendentes y `3` ascendentes, manifesto `4796df7c6befce5d`). La fracción válida del núcleo alcanza `0,9823`, con `CPR P50 = 0,6220` (`P90 = 0,6927`), `S1 P50 = −6,42 dB` y `DoP P50 = 0,2538` a una incidencia local mediana de `29,26°`.
3. **Interpretación física del control boreal:** un $\mathrm{CPR} \approx 0,62$ acompañado de baja polarización ($\mathrm{DoP} \approx 0,25$) en banda C es la firma esperada de **dispersión volumétrica múltiple en dosel arbóreo boreal**, no de rocas superficiales expuestas ni hielo subsuperficial compacto. El resultado valida de extremo a extremo la calibración MLC, las máscaras geométricas y de agua, y el cálculo de Stokes en [`pipelines/etl_radar.py`](../../../pipelines/etl_radar.py), dejando a Manicouagan como control metodológico y boreal mientras el puente polarimétrico sin vegetación queda restringido por disponibilidad pública de `RCM ARD`.

---

## 5. Resultados reales de altimetría láser (`ICESat‑2`) vs `GLO‑30`

Hasta la migración a nube se dispone de dos comprobaciones completas en campo distinto (un control boreal en store y un piloto árido reportado antes del corte de cuota) además de una prueba parcial de `6` gránulos sobre Devon:

| Sitio (`region_id`) | Estado en store | Gránulos (útiles / CMR) | Trazas / pares `100 m` | Pendiente `100 m` `P50` (láser / `GLO‑30`) | Pendiente dif. `600 m` `P50` (láser / `GLO‑30`) | `DEM − láser` mediana (`NMAD`) |
|---|---|---:|---:|---:|---:|---:|
| **Manicouagan centro** (`control-v1:manicouagan-centro`) | `measured` (`2020-03-15/2026-04-02`) | `7 / 43` | `13` / `291` | `1,12°` / `1,25°` (`P90`: `3,52°` / `3,32°`) | `0,29°` / `0,33°` (`200 m`: `0,57°` / `0,60°`) | `+1,89 m` (`1,50 m`) |
| **Atacama candidata** (`utm-ups-v1-10000-32719-723-61`) | Piloto pre-corte *(pendiente de repetir en GCP y persistir en Parquet)* | `35` CMR | — | `1,16°` / `1,15°` | — | `+0,26 m` (`0,34 m`) |
| **Cráter Haughton, Devon** (`control-v1:haughton-devon`) | `no_swath_coverage` *(solo prueba `--max-granules 6`)* | `0 / 6` probados (`120` en CMR) | `0` / `0` | — | — | — |

### Interpretación física

- **Desierto desnudo (piloto en Atacama):** en superficie expuesta sin dosel (`utm-ups-v1-10000-32719-723-61`, rango 4 frente a Jezero y 9 frente a Haworth), `GLO‑30` reproduce la pendiente mediana a `100 m` con `0,01°` de diferencia (`1,16°` en `ATL08` frente a `1,15°` en `GLO‑30`) y un sesgo vertical de apenas `+0,26 m` (`NMAD = 0,34 m`). El subconjunto de `Harmony` redujo los `35` gránulos de `3,41 GiB` originales a `400,00 MiB` (`−88,53 %`), pero sigue siendo demasiado lento sobre la red local (`~0,14 MB/s`) para escalar a los `15` sitios.
- **Control boreal (Manicouagan, persistido en `data/feature_store_v1`):** con `311` segmentos válidos (`1519` pares a `20 m` con `P50 = 1,39°` / `P90 = 5,63°`, `291` a `100 m`, `238` a `200 m` y `147` a `600 m`), el acuerdo de pendientes diferenciales a `200 m` (`0,57°` vs `0,60°`) y `600 m` (`0,29°` vs `0,33°`) confirma la consistencia morfológica multibanda entre el perfil láser y `GLO‑30`, mientras el desplazamiento vertical positivo `DEM − láser = +1,89 m` (`NMAD = 1,50 m`, con `snow_flag_fraction = 0,897` entre invierno y primavera) refleja físicamente el comportamiento de modelo digital de superficie en banda X sobre bosque boreal frente a los fotones de terreno de `ATL08`.

---

## 6. Inventario CMR (1263 gránulos) y migración del barrido a GCP Spot

El muestreo especificado en [`specs/sources/puentes-laser-radar-v1.json`](../../../specs/sources/puentes-laser-radar-v1.json) une las `8` mejores candidatas áridas (`arid_mars_surface_v2` frente a Jezero) y las `12` mejores polares frías (`polar_cold_v1` frente al fondo de Haworth): al coincidir las `8` candidatas áridas también dentro del top 10 polar frío, la unión consta de **`12` candidatas únicas (`1040` gránulos `ATL08` v007)** más **`3` sitios de control (`223` gránulos)**, totalizando **`1263` gránulos CMR**:

| `region_id` | Tipo | Lat / Lon | Ranking Jezero / Haworth | Gránulos CMR (`ATL08` v007) | Estado actual |
|---|---|---:|---:|---:|---|
| `utm-ups-v1-10000-32637-306-73` | Candidata | `27,64° N, 41,33° E` | `#1` / `#6` | `45` | Pendiente de GCP |
| `utm-ups-v1-10000-32631-323-71` | Candidata | `29,18° N, 5,16° E` | `#2` / `#8` | `47` | Pendiente de GCP |
| `utm-ups-v1-10000-32642-358-70` | Candidata | `32,34° N, 71,13° E` | `#3` / `#3` | `27` | Pendiente de GCP |
| `utm-ups-v1-10000-32719-723-61` *(Atacama)* | Candidata | `25,04° S, 67,91° O` | `#4` / `#9` | `35` | Piloto pre-corte (`−88,53 %` Harmony); repetir en GCP |
| `utm-ups-v1-10000-32632-251-74` | Candidata | `22,68° N, 11,34° E` | `#5` / `#5` | `44` | Pendiente de GCP |
| `utm-ups-v1-10000-32718-841-39` | Candidata | `14,38° S, 76,02° O` | `#6` / `#10` | `34` | Pendiente de GCP |
| `utm-ups-v1-10000-32719-747-39` | Candidata | `22,87° S, 70,07° O` | `#7` / `#7` | `29` | Pendiente de GCP |
| `utm-ups-v1-10000-32733-690-75` | Candidata | `28,00° S, 17,54° E` | `#8` / `#1` | `45` | Pendiente de GCP |
| `utm-ups-v1-10000-32635-776-46` | Candidata | `69,94° N, 25,95° E` | `—` / `#2` | `118` | Pendiente de GCP |
| `utm-ups-v1-10000-32618-894-45` | Candidata | `80,51° N, 77,72° O` | `—` / `#4` | `228` | Pendiente de GCP |
| `utm-ups-v1-10000-32617-794-45` | Candidata | `71,56° N, 82,42° O` | `—` / `#11` | `114` | Pendiente de GCP |
| `utm-ups-v1-10000-32626-915-52` | Candidata | `82,40° N, 25,64° O` | `—` / `#12` | `274` | Pendiente de GCP |
| `control-v1:haughton-devon` | Control | `75,37° N, 89,68° O` | Control | `120` | Re-ejecutar completo en GCP (`6` probados hasta hoy) |
| `control-v1:mistastin-sur` | Control | `55,82° N, 63,30° O` | Control | `60` | Pendiente de GCP |
| `control-v1:manicouagan-centro` | Control | `51,38° N, 68,70° O` | Control | `43` | **`measured`** en store (`7` gránulos con datos) |
| **Total (15 sitios)** | — | — | — | **`1263`** | **`1` completo, `1` parcial (`6` grán.), `13` en GCP** |

### Preparación de la migración a GCP Spot (`cloud/gcp/`)

Para ejecutar el barrido completo de `1263` gránulos sin el cuello de botella local ni interferir con archivos sincronizados de evidencia:

- [`scripts/etl_puentes.py`](../../../scripts/etl_puentes.py) honra `ANALOGOS_FEATURE_STORE_DIR` como almacén por defecto, actualiza [`docs/evidencia-puentes-laser-radar/resultados.json`](../../evidencia-puentes-laser-radar/resultados.json) sitio a sitio recargando el archivo desde disco con escritura atómica (evitando que procesos o subcomandos distintos de `rcm` e `icesat2` se sobrescriban mutuamente) y permite reconstruir con `resumen` registros faltantes desde `data/feature_store_v1` sin sobreescribir diagnósticos en vivo ni claves adicionales como `cmr_inventory_and_pilot`.
- [`cloud/gcp/Dockerfile`](../../../cloud/gcp/Dockerfile), [`cloud/gcp/launch-spot.sh`](../../../cloud/gcp/launch-spot.sh), [`cloud/gcp/run-etl-spot.sh`](../../../cloud/gcp/run-etl-spot.sh) y [`cloud/gcp/README.md`](../../../cloud/gcp/README.md) exponen la variable `ETL_SCRIPT` (por defecto `scripts/etl_pipeline.py`, reutilizable como `ETL_SCRIPT=scripts/etl_puentes.py`), preparan `.tools/minerales`, descargan y suben por `gcloud storage rsync` tanto el `FeatureStore` en Parquet (ignorado en Git por `.gitignore`) como `docs/evidencia-puentes-laser-radar/`, y documentan la re-ejecución completa de `haughton-devon` sin `--skip-measured` dado su registro parcial de `6/120` gránulos.
