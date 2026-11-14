# Preparación de datos para el atlas multidimensional

El objetivo de esta etapa es dejar originales verificados y entradas fijadas para la siguiente fase. Los comandos de esta página se limitan a inventario y adquisición. Las muestras anteriores de WorldCover, JRC, HLS y Landsat se leyeron por rangos y dejaron resultados de prueba. Ahora se pueden conservar los originales seleccionados para trabajar sin depender de esas lecturas al preparar el análisis.

Consulta el [catálogo y diccionario de datos](../arquitectura-y-vision/Atlas%20-%20catalogo%20y%20diccionario%20de%20datos.md) para revisar las resoluciones, ventanas, unidades y reglas de armonización.

## Prioridad y función de cada dimensión

| Dimensión | Entrada inicial | Uso posterior |
| --- | --- | --- |
| Cobertura terrestre | ESA WorldCover 2021 v200, 10 m. | Filtro y contexto terrestre. Guardar la leyenda y calcular más adelante fracciones por clase dentro de cada ventana. |
| Agua superficial | JRC Global Surface Water v1.5, ocurrencia histórica 1984–2024. | Contexto terrestre. Conservar el período y la máscara. Un cero observado y un píxel sin observaciones son estados distintos. |
| Reflectancia | HLS L30/S30 v2.0, bandas verde, rojo, NIR, SWIR y Fmask. Escenas del piloto fijadas en la especificación. | Probar firmas e índices de superficie terrestres. Registrar fecha y sensor. NDVI queda como contexto terrestre. |
| Temperatura | Landsat 8/9 Collection 2 ST, con ST_B10, QA_PIXEL y ST_QA. | Temperatura terrestre por observación. Mantener el paso térmico nominal de 100 m en los metadatos aunque el archivo se distribuya a 30 m. La inercia térmica THEMIS de Jezero describe otra magnitud. |
| Materiales | CRISM local de Jezero y EMIT local de Utah/Atacama, con productos de incertidumbre de EMIT. | Prioridad para la futura comparación de materiales. Usar los casos con cobertura verificada. Revisar correspondencias de bandas, escalas e incertidumbre antes de proponer una distancia común. |
| Capas especializadas | GLiM, EnMAP, nieve/hielo, viento y humedad del suelo. | Seleccionar productos según la pregunta del escenario y la cobertura. El contexto climático o geológico conserva su escala regional. |

El índice topográfico sigue como referencia del ranking. Las capas de contexto se pueden integrar por `region_id`, con cobertura y período propios. El piloto antártico documenta la ausencia de escenas HLS/Landsat seleccionadas y huecos en WorldCover/JRC.

## Adquisición reproducible

Desde la raíz del proyecto, inventariar primero. El modo predeterminado consulta identidades y tamaños, sin guardar rásteres. `--fetch` conserva los archivos originales y verifica SHA-256, bajo el presupuesto indicado. Ambos modos escriben un manifiesto por selección en `data/manifests/atlas30/`. Los originales se guardan bajo `data/raw/atlas30/`.

```sh
PY=.pixi/envs/default/bin/python
# Capas estáticas en los cinco bloques piloto.
"$PY" scripts/atlas30.py context --layers worldcover jrc
"$PY" scripts/atlas30.py context --layers worldcover jrc --fetch --max-gb 1
# Probar primero los originales de un bloque temporal.
"$PY" scripts/atlas30.py context --layers hls landsat --areas desierto
"$PY" scripts/atlas30.py context --layers hls landsat --areas desierto --fetch --max-gb 1
# Inventariar los otros bloques temporales antes de ampliar la descarga.
"$PY" scripts/atlas30.py context --layers hls landsat --areas montana costa tropico polar
```

HLS necesita el acceso Earthdata existente. Para Landsat se conserva el identificador USGS y se utiliza la copia del mismo producto que funcionó en el piloto. Las credenciales y las firmas de acceso se usan en memoria. La especificación fija las escenas de 2024 para evitar que una búsqueda posterior cambie el conjunto de prueba. Las descargas comparten el límite local de 100 GB con GLO-30.

La primera descarga estática verificó ocho teselas WorldCover y cinco de JRC, **778,4 MB** en total. El manifiesto registra seis entradas WorldCover y dos JRC no disponibles. El inventario del desierto seleccionó **20 archivos HLS y seis Landsat**, con un total previsto de **606,1 MB**. Para materiales ya se comprobaron contra sus manifiestos los siete archivos de CRISM, seis de EMIT y el original de THEMIS.

## Entrada a procesamiento, armonización y feature engineering

1. **Procesamiento nativo.** Leer originales verificados, interpretar unidades, valores de relleno y bandas QA. Generar un reporte de soporte y dejar los rásteres originales intactos.
2. **Armonización por variable.** Fijar los mismos identificadores y huellas de 3 × 3 km. Para categorías, conservar clases y agregar fracciones. Para observaciones continuas, conservar unidades, período, máscaras y soporte efectivo antes de comparar o remuestrear. Reservar ventanas de cada ambiente para comprobar costuras, costas y faltantes. Al escalar, reservar bloques completos para validar fuera de la muestra de ajuste.
3. **Primeras características.** Priorizar fracciones de WorldCover, ocurrencia y soporte JRC, después índices HLS y estadísticas térmicas por observación. Registrar `region_id`, producto, versión, activo, fecha o período, resolución nativa y de análisis, unidad, valor, fracción válida y estado QA. Los datos ausentes se representan con `null` y un motivo.
4. **Comparabilidad planetaria.** Dar a cada variable una función explícita como filtro, contexto, evidencia de expediente o distancia comparable. Materiales requieren una ficha de correspondencia EMIT–CRISM. Temperatura terrestre y THEMIS deben conservar salidas separadas.

[ESA WorldCover](https://esa-worldcover.org/en/data-access) · [JRC Global Surface Water](https://global-surface-water.appspot.com/download) · [NASA HLS](https://hls.gsfc.nasa.gov/data-access-and-tools/) · [USGS Landsat ST](https://www.usgs.gov/landsat-missions/landsat-collection-2-surface-temperature)
