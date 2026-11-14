# Extracción y preparación de la primera muestra real

El catálogo `regions.json` está listo para la API. Contiene una ventana marciana y dos terrestres, seleccionadas para probar el recorrido; sus centros son provisionales y no representan sitios validados. Los datos originales en `data/raw/` están excluidos de Git, pero el catálogo y el registro `procesamiento.json` sí pueden compartirse sin ellos.

## 1. Extracción de las fuentes

Descargas realizadas el 5 de noviembre de 2026:

| Región | Centro provisional | Producto y archivo |
|---|---|---|
| Jezero | 18.44° N, 77.45° E | [MOLA MEGDR 128 píxeles/grado](https://pds-geosciences.wustl.edu/missions/mgs/megdr.html), tesela de topografía `megt44n000hb.img` y recuentos `megc44n000hb.img`, con sus etiquetas `.xml`, `.lbl` y cabeceras `.hdr`. |
| Atacama | −23.8°, −67.9° | SRTM GL1, `S24W068.tif`. |
| Utah | 38.6°, −110.6° | SRTM GL1, `N38W111.tif`. |

Los productos MOLA están disponibles en el [directorio oficial MEG128](https://pds-geosciences.wustl.edu/mgs/urn-nasa-pds-mgs_mola_topography_derived/meg128/); las dos teselas cubren 0–44° N, 0–90° E. La topografía contiene enteros de 16 bits con orden de bytes big-endian y unidades en metros respecto al areoide; los recuentos son enteros sin signo de 8 bits. Las etiquetas del producto son la referencia para interpretación.

Los GeoTIFF terrestres proceden de la [distribución pública SRTM GL1 de OpenTopography](https://portal.opentopography.org/raster?jobId=rt1674642591184), obtenida de estos enlaces:

- https://opentopography.s3.sdsc.edu/raster/SRTM_GL1/SRTM_GL1_srtm/S24W068.tif
- https://opentopography.s3.sdsc.edu/raster/SRTM_GL1/SRTM_GL1_srtm/N38W111.tif

Atribuir OpenTopography y la fuente del conjunto según las condiciones indicadas por el distribuidor. El archivo de Islandia del prototipo original se omitió: el centro está fuera de la cobertura SRTM. Requiere otro producto y revisión por separado.

## 2. Transformación

El código está en `scripts/preparar_datos.py`. Para cada centro:

1. Lee la tesela, su georreferencia y su valor sin datos. Para MOLA usa la geometría y el tipo de dato de su etiqueta y convierte explícitamente el orden de bytes a la representación nativa antes de reproyectar.
2. Proyecta a un sistema azimutal equidistante local centrado en el punto: esfera MOLA de 3.396.000 m de radio para Marte y WGS84 para la Tierra.
3. Construye una cuadrícula de 20 × 20 celdas de 500 m (10 × 10 km), con una celda adicional alrededor para calcular pendientes en el borde. SRTM se agrega por promedio; MOLA se remuestrea por interpolación bilineal. La cuadrícula común no iguala la resolución efectiva ni elimina las diferencias entre instrumentos.
4. Calcula la **pendiente media** como la media de `atan(sqrt(dx² + dy²))`, en grados, usando diferencias centrales y solo celdas con los vecinos necesarios. Calcula **relieve relativo** como percentil 95 menos percentil 5 de las elevaciones válidas en metros. No compara elevaciones absolutas entre planetas.
5. Calcula `coverage` como celdas de elevación válidas divididas por 400. Es cobertura del modelo, no de mediciones directas. Remuestrea los recuentos de MOLA por vecino más cercano y registra la fracción de celdas de salida con recuento mayor que cero como indicador aproximado y separado de soporte directo. MOLA incluye valores interpolados en celdas sin observación; el recuento no es una máscara completa de calidad.
6. Escribe `data/regions.json` en el contrato que lee FastAPI y `data/procesamiento.json` con rutas, proyecciones, recuentos de celdas, método y SHA-256 de los archivos de entrada.

No se ha establecido un umbral científico de calidad. Las ventanas y la cuadrícula son una primera hipótesis; se deben revisar su sensibilidad, precisión y cobertura antes de sacar conclusiones científicas. Las escalas del motor (10° y 300 m) siguen siendo ilustrativas; los porcentajes no validan analogía ni transitabilidad.

## 3. Repetir la preparación

Desde la raíz del proyecto, con `uv` y Python instalados, y con los archivos originales en las rutas indicadas:

```sh
cd backend
uv sync
cd ..
backend/.venv/bin/python scripts/preparar_datos.py
```

El comando sobrescribe `data/regions.json` y `data/procesamiento.json`; falla si faltan entradas o si las teselas binarias MOLA no tienen el tamaño esperado. Las versiones de las dependencias están fijadas en `backend/uv.lock`. Después se puede iniciar el backend y el frontend según el README principal. El procesamiento no necesita acceso a internet una vez descargados los archivos y dependencias.

Para agregar sitios se necesitan teselas que cubran toda la ventana y su margen, centros y CRS comprobados, y una entrada en `SITES` del script. No se debe declarar un producto diferente como SRTM ni usar suposiciones de proyección, escala o formato sin revisar sus metadatos.

## Visualización en Cesium

La misma ejecución del script genera `frontend/public/regions/{id}.json`: elevaciones en la cuadrícula de 20 × 20 celdas y los 21 × 21 vértices geográficos transformados desde la proyección local. Cada globo dibuja los polígonos y el contorno de la ventana usando el elipsoide del cuerpo. La escala azul–amarillo se ajusta al mínimo y máximo de cada ventana, por lo que los colores de ventanas distintas no son directamente comparables. No es una superficie de terreno tridimensional. Las celdas se dibujan 30 m por encima del elipsoide solo para evitar superposición gráfica; ese desplazamiento no modifica las elevaciones ni las métricas.

Los fondos globales son imágenes locales de contexto: [Blue Marble, NASA/Goddard Space Flight Center Scientific Visualization Studio](https://svs.gsfc.nasa.gov/2915/) para la Tierra y el mosaico de topografía MOLA en colores falsos [NASA Mars Trek](https://trek.nasa.gov/tiles/apidoc/trekAPI.html?body=mars) para Marte. Este último fue compuesto a partir de las ocho teselas de nivel 1 de `Mars_MGS_MOLA_ClrShade_merge_global_463m`. La textura marciana es un mapa topográfico coloreado, no una fotografía en color natural. Las imágenes de contexto no se usan en el cálculo de similitud.

En cada visor, usa los botones `+` y `−` para acercarte o alejarte, `Vista global` para regresar y `Ver área analizada` para centrar la ventana. El selector permite ocultar o mostrar la capa de elevación; el contorno se mantiene. También se puede arrastrar con el botón izquierdo para girar, usar la rueda para zoom y Ctrl + arrastrar para inclinar.
