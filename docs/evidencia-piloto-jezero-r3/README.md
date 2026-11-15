# Piloto multivista de Jezero

El piloto compara materiales por reflectancia en una huella de **1,8 km** y relieve en una huella de **3 km**, ambas centradas en **77,41° E, 18,49° N**. El ranking combinado exige dos de los tres indicadores compartidos y aplica **75 % relieve y 25 % espectro**. El modo **Solo relieve** permite comparar la lista. El experimento se limita a su cobertura EMIT y sus perfiles terrestres de suelo árido y margen de paleolago.

La [evidencia diagnóstica](resultados.json) contiene las mediciones reales iniciales y el recuento polar. La comparación geológica ciega sigue pendiente. La publicación activa del atlas es `etl-30m-r2c`.

- **Diseño terrestre.** Los dos perfiles seleccionaron 1.000 ventanas de desarrollo y 300 de reserva a partir de 2.066 escenas EMIT inventariadas. Es una selección de coordenadas con cobertura de catálogo. El control de Utah y la referencia CRISM son las mediciones espectrales realizadas en esta corrida.
- **Reflectancia.** Jezero registró 8.897 de 10.200 celdas válidas (87,2 %). Utah registró 1.140 de 1.140 (100 %). En Utah se observó el intervalo de Fe/Mg–OH con soporte suficiente y `BD2290` quedó por debajo del umbral de absorción. Los fondos de ajuste y los controles repetidos todavía no alcanzan los mínimos. El evaluador devolvió `diagnostic`.
- **Térmica.** La mediana de THEMIS pasó de 253,2 a 239,8 J m⁻² K⁻¹ s⁻½ entre 1,8 y 3 km. En el almacén, las 100 ventanas con ATI fina se repartían por coordenadas en 24 teselas MODIS y todas tenían ATI gruesa. La correlación de Spearman fina–gruesa fue 0,937 en esa muestra. El contraste estacional y con más teselas queda pendiente.
- **Polar.** De 1.459.470 ventanas terrestres clasificables, el perfil frío admite 44.622 del norte y 687 del sur. En el sur, 122.947 quedan pendientes de comprobar cobertura. Haworth tiene sombra permanente en toda su huella y Tmax mediana de 59,83 K. De Gerlache es el contraste de cresta, con 22,4° de pendiente P90.
- **Antártida.** En la tesela REMA 18_35 de 32 m, una ventana cerca del borde tuvo 66,9 % de píxeles válidos. Una segunda ventana en el interior alcanzó 100 % de soporte y 20,4 % de afloramiento cartografiado. Son dos pruebas de cobertura en McMurdo.

## Preparar el diseño

Usar el almacén derivado que acompaña a `r2c` y su `similarity/model.joblib`. La CLI se ejecuta con el entorno de `scripts/ejecutar_minerales.sh`. Los ejemplos usan una carpeta temporal para catálogos, insumos y resultados.

```bash
mkdir -p /tmp/jezero-r3
bash scripts/ejecutar_minerales.sh scripts/piloto_jezero.py catalog \
  --bbox -117.5 34.5 -115.5 36 \
  --bbox -71 -25 -68 -23 \
  --bbox 13 -26 16 -23 \
  --bbox -112 37 -108 40 \
  --bbox 136 -26 139 -23 \
  --bbox -5 24 2 30 \
  --output /tmp/jezero-r3/emit.json
```

Preparar `inventory.json` con `scenes` del catálogo, las entradas CRISM y `sites`. Reservar Mojave con la caja predeterminada y agregar al campo `holdouts` dos cajas confirmadas. La corrida de diagnóstico usó Atacama `[-70,-24.5,-68,-23]` y Namib `[14,-25.5,16,-24]`. El diseño excluye del ajuste escenas que toquen la reserva y aplica un margen de **0,04°** alrededor de los bloques. Dentro del catálogo consultado, cualquier escena que cruce dos bloques obliga a revisar la partición.

Cada escena CRISM tiene `id`, `body: "Mars"`, `reflectance_url`, `header` y `mask`. Pasar las rutas de cabecera ENVI IF y máscara IN relativas a `--input-root`. La referencia se identifica con `role: "reference"` y el producto `FRT000047A3_07_IF166J_MTR3`. Cada sitio tiene `region_id`, `body`, `longitude`, `latitude`, `role` y `scene_ids`. Indicar también `geologic_unit` para el fondo marciano. Seleccionar ventanas marcianas repartidas entre escenas y unidades del mapa USGS, con una sola medición de fondo por ventana. Para repetibilidad, suministrar controles con dos adquisiciones válidas por cuerpo. Los controles terrestres pertenecen a escenas fuera de la reserva. [Mapa USGS](https://pubs.usgs.gov/publication/sim3464) · [Archivo CRISM MTRDR](https://pds-geosciences.wustl.edu/missions/mro/crism.htm)

```bash
bash scripts/ejecutar_minerales.sh scripts/piloto_jezero.py design \
  --store /tmp/jezero-r3/store --inventory /tmp/jezero-r3/inventory.json \
  --output /tmp/jezero-r3/design.json
bash scripts/ejecutar_minerales.sh scripts/piloto_jezero.py reference \
  --output /tmp/jezero-r3/reference.json
bash scripts/ejecutar_minerales.sh scripts/piloto_jezero.py measure \
  --design /tmp/jezero-r3/design.json --input-root /tmp/jezero-r3/rasters \
  --output /tmp/jezero-r3/observations.json
```

Usar `--profile paleolake_margin_v1` para congelar el segundo diseño en otra ruta. `measure` lee por rangos y guarda el avance por sitio. `--site` permite medir un lote identificado antes de continuar. EMIT usa `EARTHDATA_TOKEN` desde el entorno y la máscara L2A v002. El diseño registra la probabilidad de selección por estrato. La cobertura efectiva se comprueba de nuevo con bandas y píxeles válidos dentro de la huella completa. El resultado distingue absorción ausente con observación válida, banda fuera de alcance y cobertura insuficiente.

## Evaluar y publicar

La primera evaluación genera la ficha ciega mediante `--blind-sheet` si ya existe soporte para la métrica. Entregar la misma ficha a dos personas para revisión independiente. Cada registro devuelto contiene `region_id`, `reviewer`, `score` y `source`. La escala de 0 a 3 representa incompatibilidad de materiales, similitud débil, similitud parcial o similitud fuerte. Las fuentes son mapas, descripciones de campo u otra evidencia geológica independiente que sustente la puntuación. Los casos indeterminados quedan pendientes de evidencia. Conservar los archivos de revisión separados hasta evaluar.

```bash
bash scripts/ejecutar_minerales.sh scripts/piloto_jezero.py evaluate \
  --store /tmp/jezero-r3/store --design /tmp/jezero-r3/design.json \
  --measurements /tmp/jezero-r3/observations.json \
  --r2c-model /tmp/jezero-r3/model.joblib --aligned-reference /tmp/jezero-r3/reference.json \
  --reviews /tmp/jezero-r3/reviews.json --run-stability \
  --output /tmp/jezero-r3/evaluation.json
```

Por indicador se requieren 200 ventanas terrestres de ajuste y 100 marcianas, antes del remuestreo. La repetibilidad requiere diez pares de control y una correlación de Spearman de al menos 0,7 por cuerpo. La recuperación ejecuta las listas sobre las ventanas reservadas, con el mismo presupuesto de ventanas únicas. Como señal de recuperación espectral, la regresión Ridge usa emisividad gruesa y precipitación ajustadas en los bloques de desarrollo. La métrica final usa las observaciones espectrales. El informe mide nDCG@20 sobre las mismas ventanas puntuadas por los cuatro rankings, y estima el intervalo pareado del 95 % por bloques. La evaluación completa exige al menos 20 ventanas comparables por bloque, mejor recuperación que solo relieve y al menos 80 coincidencias en el top 100 de cada una de las diez semillas.

Solo un informe `publishable_experiment` admite el empaquetado. El siguiente comando crea una versión inmutable con el ranking, la procedencia, las observaciones derivadas y los resultados de evaluación.

```bash
bash scripts/ejecutar_minerales.sh scripts/piloto_jezero.py publish \
  --report /tmp/jezero-r3/evaluation.json --design /tmp/jezero-r3/design.json \
  --measurements /tmp/jezero-r3/observations.json \
  --root /tmp/jezero-r3/releases --version jezero-r3-piloto1
```

Configurar `REGOLITH_JEZERO_PILOT_DIR` en el servidor con el directorio versionado. El modo científico de Jezero consulta `GET /api/similarity/jezero-pilot` solo al elegir uno de sus modos. El directorio del piloto se monta de forma independiente del motor estable y del puntero del atlas.

## Diagnósticos adicionales

- **Relieve.** `stability --store … --output …` compara el método de ajuste de r2c, Ledoit–Wolf fijo y la variante sin GMM. La corrida reducida con `--sample-size 20000` sirve para examinar sensibilidad y alcance. Para validar una publicación, `evaluate --run-stability` repite el ajuste completo en el conjunto medido.
- **Térmica.** `themis --raster … --output …` extrae P10, P50 y P90 a las dos escalas. La medición terrestre sigue el ETL por conglomerados MODIS de `scripts/etl_superficie.py`. Para evaluar el puente hay que extender el muestreo de teselas independientes y contrastar ATI fina y gruesa por estación, humedad y soporte. [Fuente THEMIS](https://doi.org/10.5281/zenodo.4931348)
- **Luna polar.** `audit --store … --output …` vuelve a aplicar la compuerta fría al almacén y extrae iluminación, fracción de sombra permanente y Tmax de Diviner. `antarctic --outcrops … --rema … --center LON LAT --output …` mide conjuntamente afloramientos y soporte del DEM en una huella de 3 km. La cobertura de roca y nieve se evalúa antes de proponer cambios al perfil polar. [SCAR ADD](https://data.bas.ac.uk/items/9df510e3-ea1c-450b-9950-d742db1efd96/) · [REMA](https://www.pgc.umn.edu/data/rema/)
