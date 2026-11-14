# Auditoría de datos geoespaciales locales

Fecha: 5 de noviembre de 2026. Alcance: inventario y metadatos de `data/raw/mola/` y `data/raw/srtm/`; sin descargar, modificar originales ni ejecutar el procesamiento. Los metadatos son declaraciones de los archivos, no una validación científica independiente.

## Inventario y huellas

Tamaños en bytes; SHA-256 calculado localmente. Los cuatro hashes de imágenes coinciden con los registrados en `data/procesamiento.json`; esto verifica identidad con ese registro local, no autenticidad ni origen remoto.

| Archivo bajo `data/raw/` | Bytes | SHA-256 |
|---|---:|---|
| `mola/megc44n000hb.img` | 64880640 | `cfb4d7e3626106ef4ed2a466eb03a538feed9c163be99e860b7ae8700a8ecab5` |
| `mola/megc44n000hb.lbl` | 3088 | `e7bde6960c05e9fc48ff6417ee3e2b12ed271af16ea85294a775a6948d890a1e` |
| `mola/megc44n000hb.hdr` | 1029 | `4871add22f0e8096281ea6c3b79fc0555a541cf72785e4abe87055e38970d20a` |
| `mola/megc44n000hb.xml` | 13859 | `65e44d550d0117766b9bd52cc5f1d307263fe031767ba57938413c5078bea1f5` |
| `mola/megt44n000hb.img` | 129761280 | `14022166079edafc99650f354e5a634e6eb2c2ea544b444c01cd8ee55437df36` |
| `mola/megt44n000hb.lbl` | 4820 | `bc624a238ba6d71a770a09f959ead96f1c144970fae435b8ca5e26208b42eec5` |
| `mola/megt44n000hb.hdr` | 1029 | `4871add22f0e8096281ea6c3b79fc0555a541cf72785e4abe87055e38970d20a` |
| `mola/megt44n000hb.xml` | 15513 | `f6de640ed5603eb03395616214c9a5707c9d49273f699d2cbeec53e93df6bd08` |
| `srtm/N38W111.tif` | 14938692 | `73520c1f4d04871db3a999fb2570c4eef723fb18d5a507cc60ba5c22ccac828c` |
| `srtm/S24W068.tif` | 16464310 | `4f64ff3421208d6f1c95cd94e1df9d9c686a877e3905b53fd940ab9cf194db4a` |

Hay dos imágenes binarias MOLA, cada una con `.lbl` PDS3, `.xml` PDS4 y `.hdr` ENVI, y dos GeoTIFF sin etiquetas externas en los directorios inspeccionados. Además existen `data/regions.json` y `data/procesamiento.json`, derivados y registro del prototipo, no originales auditados aquí.

## Metadatos observados

**MOLA.** Las etiquetas PDS identifican MGS/MOLA, conjunto `MGS-M-MOLA-5-MEGDR-L3-V1.0`, producto 2.0, y 11 520 columnas × 5632 filas. Topografía (`megt`) declara entero con signo de 16 bits, byte más significativo primero, metros respecto al areoide; recuentos (`megc`) declara entero sin signo de 8 bits y número de observaciones por celda. Los tamaños de los binarios coinciden aritméticamente con esas dimensiones y tipos, pero esto no verifica sus valores. Las etiquetas no especifican factor de escala, offset de valores ni valor sin dato; el `offset` XML de cero es de **bytes**, no de valores.

Ambas etiquetas declaran cobertura 0–44° N y 0–90° E, latitud planetocéntrica, longitud positiva al este, 128 píxeles/grado y proyección cilíndrica simple, con radios de 3396 km. La etiqueta topográfica menciona IAU2000 y el areoide GMM3; no se ha validado su equivalencia con un código CRS concreto. El XML describe proyección equirectangular y escala de 0,4630576672 km/píxel; indica que corrigió esos campos frente a una versión anterior. El `.lbl` redondea a 0,463 km/píxel. La etiqueta topográfica indica que suministra valores interpolados donde no hay observaciones; el recuento describe observaciones por celda. La proporción observada y la calidad local no se han calculado ni validado.

**Inconsistencia relevante:** los dos `.hdr` son idénticos y declaran `data type = 2`, `byte order = 1` y `data ignore value = 0`. GDAL abre ambos `.img` mediante ENVI como Int16 y sin dato 0. Para recuentos esto contradice los 8 bits sin signo de `.lbl` y `.xml`, y el tamaño disponible solo corresponde a un byte por celda. Para topografía, la etiqueta PDS no declara 0 como sin dato; para recuentos, cero puede representar ausencia de observaciones. No se ha establecido cuál es la interpretación correcta del valor 0 ni corregido las cabeceras. Leer recuentos directamente con esta cabecera puede producir una lectura incorrecta o incompleta; requiere revisión antes de usarla.

**GeoTIFF.** GDAL identifica ambos como GTiff, una banda Int16, 3601 × 3601, compresión DEFLATE, `AREA_OR_POINT=Point`, paso de 0,000277777777778° y sin dato −32768. El CRS declarado es WGS 84 horizontal, EPSG:4326; no se identificó CRS vertical, unidad de banda, escala ni offset explícitos en la salida inspeccionada. Las esquinas que informa GDAL son bordes de píxel, no deben confundirse con centros:

| Archivo | Extensión de bordes GDAL (longitud; latitud) | Centros extremos, inferidos del origen, paso y `Point` |
|---|---|---|
| `S24W068.tif` | −68,0001389 a −66,9998611; −24,0001389 a −22,9998611 | −68 a −67; −24 a −23 |
| `N38W111.tif` | −111,0001389 a −109,9998611; 37,9998611 a 39,0001389 | −111 a −110; 38 a 39 |

La extensión y CRS son metadatos leídos, no una comprobación de exactitud geográfica ni de cobertura válida real. No se ha revisado el contenido de píxeles ni los rellenos o interpolaciones de SRTM.

## Procedencia, riesgos y decisiones pendientes

- [README de datos](../../data/README-datos-reales.md) declara descargas el 5 de noviembre de 2026 desde [PDS MEG128](https://pds-geosciences.wustl.edu/mgs/urn-nasa-pds-mgs_mola_topography_derived/meg128/) y [OpenTopography](https://portal.opentopography.org/raster?jobId=rt1674642591184), con URLs concretas de las teselas SRTM. Las etiquetas identifican MOLA y sus productos; no se comprobó el servidor, la descarga original ni una huella publicada externamente. El README pide atribuir OpenTopography y la fuente según sus condiciones, pero no documenta una licencia específica verificable para cada archivo. [Arquitectura objetivo](Arquitectura%20objetivo%20y%20plataforma%20de%20datos.md) propone «dominio público NASA; citar producto» en un ejemplo; no se verificaron derechos ni condiciones de redistribución. Confirmarlos con las fuentes oficiales antes de publicar o redistribuir.
- Revisar la discrepancia `.hdr`/PDS y el significado de cero, orientación, escala, unidades y datum vertical mediante documentación de producto y puntos de referencia independientes. `DSMAP.CAT`, referenciado por las etiquetas, no está en los directorios auditados. No se han validado valores de control ni exactitud de lectura.
- La guía local afirma que el prototipo remuestrea recuentos y registra una fracción aproximada; `procesamiento.json` registra 0,44 para celdas de salida de Jezero. Es un resultado declarado por un procesamiento anterior, no una fracción nativa ni una validación de observación directa. Evaluar su significado y separar elevación disponible, observación e interpolación; revisar también el tratamiento de rellenos SRTM.
- Definir qué cobertura, fuentes adicionales, metadatos, pruebas independientes, convenciones de coordenadas y referencias verticales necesita el equipo antes de fijar contratos o parámetros científicos. Las cifras y propuestas de [Plan de arranque](Plan%20de%20arranque%20desde%20cero.md), [Arquitectura para el hackathon](Arquitectura%20para%20el%20hackathon.md) y la arquitectura objetivo son hipótesis, no controles validados.
- Verificar las reglas vigentes del evento sobre preparación previa antes de decidir qué trabajo o datos adicionales preparar; no se ha supuesto su contenido.

## Reproducción y límites

Desde la raíz, en macOS, se usaron los comandos siguientes; para tamaños en otro sistema adaptar `stat`. GDAL del entorno local Pixi informa versión 3.12.3. `gdalinfo` sobre MOLA selecciona el controlador ENVI y utiliza el `.hdr`, no resuelve la discrepancia con las etiquetas PDS. No se calcularon estadísticas ni puntos de control y no se consultaron fuentes remotas o licencias externas. La auditoría es de metadatos locales y trazabilidad parcial.

```sh
find data/raw -type f -print0 | xargs -0 stat -f '%z %N'
shasum -a 256 data/raw/mola/* data/raw/srtm/*
cat data/raw/mola/*.lbl data/raw/mola/*.hdr
rg -n -i 'missing|invalid|scal|offset|unit|latitude|longitude|lines|samples|sample_type|sample_bits|projection|radius|interpol|license|copyright|description' data/raw/mola/*.xml
.pixi/envs/default/bin/gdalinfo --version
.pixi/envs/default/bin/gdalinfo data/raw/mola/megt44n000hb.img
.pixi/envs/default/bin/gdalinfo data/raw/mola/megc44n000hb.img
.pixi/envs/default/bin/gdalinfo data/raw/srtm/S24W068.tif
.pixi/envs/default/bin/gdalinfo data/raw/srtm/N38W111.tif
cat data/README-datos-reales.md data/procesamiento.json
```
