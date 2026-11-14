# Evidencia de la fase 1

Consulta: **6 de noviembre de 2026, America/Managua**. Los sellos de tiempo UTC del día 7 corresponden a la misma sesión local. Este directorio respalda la [ficha de viabilidad](../02-versiones-anteriores/etapa-1-mvp-escenarios/Ficha%20de%20viabilidad%20-%20primer%20caso.md); no es un conjunto de datos de análisis ni una validación científica.

## Contenido e interpretación

| Archivo(s) | Qué acredita | Qué no acredita |
|---|---|---|
| `areas-marte.json`, `areas-tierra.geojson` | Polígonos, centros, tamaño nominal, cuerpo y convenciones explícitos | Sitios operativos validados, similitud o permisos de acceso. El JSON marciano no es GeoJSON terrestre RFC7946. |
| `jezero-dtm-etiqueta.txt` | Etiqueta PDS completa extraída del comienzo del IMG | Integridad del IMG completo. |
| `jezero-dtm-prefix.bin` | Primeros 65 536 bytes del IMG; incluye etiqueta y parte de datos | Producto completo; no utilizar para calcular estadísticas. |
| `PSP_*_ORTHO.LBL` | Identidad y geometría de dos imágenes distintas | Píxeles válidos de las JP2, que no se descargaron. |
| `jezero-fila-*.bin`, `jezero-muestreo.json` | 17 segmentos de filas nativas obtenidos mediante HTTP 206; rangos, SHA-256 y conteos reproducibles | Máscara completa, muestreo aleatorio, observaciones independientes o exactitud del DTM. |
| `auditoria-local.json` | Metadatos y cobertura disponible de los SRTM locales dentro de los polígonos; extensión del DTM | Procedencia remota autenticada ni origen de los rellenos SRTM. |
| `tnm-*-1m.json` | Respuestas originales de búsquedas TNM para extensiones concretas | Cobertura válida de las teselas encontradas; intersección no equivale a contención. |
| `utah-1m.xml`, `mojave-1m.xml` | Metadatos específicos de las teselas 3DEP elegidas | Exactitud local: remiten a la documentación del proyecto fuente. |
| `*-1m-prefix.tif`, `auditoria-3dep.json` | Primeros 65 536 bytes de cada GeoTIFF y contención de esquinas en su geotransformación real | TIFF completo o lectura de píxeles; no usarlos para análisis. |
| `*.html`, `consultas-remotas.json` | Páginas de contexto/documentación y registro de URL, estado, fecha y hash de esas consultas | Que todos los enlaces de una página sigan vigentes o que una página sustituya al producto. |
| `fuentes.json` | Consultas iniciales y fuentes complementarias, incluidas limitaciones de acceso | Verificación que no se haya realizado. |
| `matriz-evidencia.json` | Una entrada por sitio, variable y producto; incluye vacíos explícitos para dimensiones complementarias | Contrato nuevo para la API: es un anexo documental y no lo consume la aplicación. |
| `manifest-local.json` | Tamaño y SHA-256 de cada archivo de evidencia excepto el propio manifiesto | Autenticidad externa, integridad de un producto remoto completo o calidad científica. |

Se conservan respuestas públicas y fragmentos pequeños; no se descargaron DTM/ortoimágenes completos ni teselas 3DEP completas. Los originales SRTM se leyeron en su ubicación previa, sin modificación. No se calcularon nuevas pendientes, relieves ni puntuaciones.

## Consultas y selección

Endpoint TNM: `https://tnmaccess.nationalmap.gov/api/v1/products`, parámetros `datasets=Digital Elevation Model (DEM) 1 meter`, `max=10`, `outputFormat=JSON`.

- Utah: `bbox=-110.62,38.58,-110.58,38.62`, total 1; producto seleccionado `65b9e4b5d34e18c6baf2ca59`.
- Mojave: `bbox=-116.12,35.31,-116.08,35.35`, total 8; seleccionado `675905a7d34edfeb87103aa1`, proyecto CA_FEMALevee_D23, tesela x58y392. La búsqueda precedió al ajuste final del centro a 35,35° N. La contención final se verificó sobre el TIFF seleccionado, no sobre la extensión inicial de búsqueda.
- La respuesta Mojave también incluye productos D24 publicados en 2026; no se mezclaron con D23. La selección D23 conserva un producto y fecha concretos con XML accesible; no implica que sea el producto más reciente o mejor.

El prefijo IMG y la etiqueta C se obtuvieron con `curl` antes del registro agrupado de consultas. Sus URLs, longitudes y rangos se declaran en `fuentes.json`; el manifiesto acredita los archivos conservados. No se inventan cabeceras HTTP históricas para esas consultas iniciales.

La página del mapa USGS SIM 3464 fue localizada mediante búsqueda web, pero su descarga directa respondió 403 y la apertura posterior agotó el tiempo. No hay copia local de ese GIS ni verificación de su intersección con el polígono. La referencia Bell et al. (2022), consultada por navegador de investigación, aporta contexto independiente; solo se guarda aquí la referencia y su alcance, no el artículo completo.

## Método de comprobación

Entorno utilizado: Python, rasterio, NumPy, GDAL y pyproj del entorno `.pixi/envs/default`. Las operaciones fueron de lectura y escritura exclusiva de esta documentación y sus anexos.

1. Construir las cuatro esquinas a distancia 900√2 m del centro con `pyproj.Geod.fwd`, rumbos 225°, 135°, 45° y 315°. Tierra: WGS84. Marte: esfera local de la etiqueta. Cerrar el anillo y mantener los cuerpos separados.
2. Abrir prefijos únicamente para leer metadatos. Reproyectar las esquinas a cada CRS nativo y verificar que queden dentro de los límites. Los productos elegidos tienen rectángulos sin rotación; el control no sustituye una máscara de datos válidos. La transformación NAD83/WGS84 utilizada por el entorno no constituye una corregistración de precisión; verificarla en fase 2.
3. Para cada SRTM, formar la ventana envolvente con offsets redondeados hacia fuera. Leer `masked=True`. Aplicar `rasterio.features.geometry_mask(..., invert=True, all_touched=False)` a la geometría WGS84 con la transformación de esa ventana. Contar únicamente centros dentro del polígono, finitos y no nodata. La cobertura disponible no acredita el soporte de observación original.
4. Para el IMG, primer byte de imagen 27 736, ancho 6934, muestras Float32 little-endian de cuatro bytes. Tomar 17 filas equiespaciadas entre los índices extremos del rectángulo envolvente del polígono. Descargar en cada fila las columnas completas entre sus extremos mediante `Range: bytes=inicio-fin`, comprobando HTTP 206, `Content-Range` y tamaño exacto. El primer byte de una muestra es `27736 + (fila*6934 + columna)*4`, índices desde cero. Comparar muestras con nodata y rango válido de la etiqueta. Los segmentos y parámetros se conservan en `jezero-muestreo.json`.
5. Guardar SHA-256 local. No interpretar coincidencia de hash como control científico.

Para repetir las lecturas de metadatos desde la raíz del proyecto:

```sh
.pixi/envs/default/bin/gdalinfo docs/evidencia-fase-1/jezero-dtm-prefix.bin
.pixi/envs/default/bin/gdalinfo docs/evidencia-fase-1/utah-1m-prefix.tif
.pixi/envs/default/bin/gdalinfo docs/evidencia-fase-1/mojave-1m-prefix.tif
```

No añadir `-stats`: los archivos son fragmentos deliberados. El proceso no necesita corregir ni regenerar los originales.

## Pendientes que pasan a la fase 2

- Leer recorte marciano y margen completos, comprobar cobertura efectiva, artefactos y referencias de coordenadas antes de calcular.
- Corroborar referencia vertical, unidades y procedencia/versión del SRTM concreto; documentar rellenos y diferencias DEM/DSM.
- Revisar licencias y atribuciones por producto antes de publicar o redistribuir; no extrapolar política de imágenes a cualquier archivo vinculado.
- Para análisis de detalle, comprobar los píxeles 3DEP y los metadatos de sus proyectos, además de corregistro e incertidumbre.
- Completar fuentes locales de materiales, imágenes terrestres y térmica antes de habilitar esas comparaciones.

El resultado de fase 1 es viabilidad documental y acceso comprobado a muestras, no un resultado cuantitativo de analogía.
