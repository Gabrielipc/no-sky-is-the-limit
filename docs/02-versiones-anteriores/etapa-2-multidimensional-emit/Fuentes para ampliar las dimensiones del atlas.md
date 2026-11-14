# Fuentes para ampliar las dimensiones del atlas

**Investigación:** 7 de noviembre de 2026, America/Managua.  
**Alcance:** Jezero y las candidatas terrestres actuales. Se investigaron fuentes, se consultaron catálogos públicos y se descargó un piloto térmico de 1,72 MB. No se modificaron las métricas, la API ni la interfaz.

**Implementación posterior:** la [extensión multidimensional](Extension%20multidimensional.md) incorpora nuevos descriptores, el panel térmico y adquisición local. El alcance anterior describe la investigación original; el catálogo conserva sus estados de investigación, no un inventario dinámico de todas las descargas.

## Recomendación

La siguiente ampliación debería combinar **geometría del terreno, materiales y morfología superficial**. La térmica ya tiene un producto marciano local utilizable para exploración, pero aún necesita una contraparte terrestre que mida la misma propiedad. Agua/hielo requiere una pregunta específica; polvo superficial y polvo atmosférico deben mantenerse separados.

No todas las nuevas variables constituyen dimensiones independientes: pendiente, rugosidad y curvatura derivadas del mismo DEM pueden estar muy relacionadas. Añadirlas no equivale a obtener tres evidencias físicas independientes.

El catálogo estructurado está en [catalogo-fuentes.json](../../investigacion-dimensiones/catalogo-fuentes.json). Sus estados distinguen fuentes documentadas, productos identificados y archivos realmente descargados. **No es un plan compatible directamente con `scripts/recolectar_datos.py`.**

## 1. Punto de partida comprobado

Se revisaron la guía del atlas, el plan orientado a escenarios, `specs/analysis/primer-caso-fase2.json`, las fuentes de fase 1 y `backend/app/scenarios.py`. El recorrido actual calcula pendientes y relieve; las otras cinco dimensiones aparecen como no evaluadas.

Ya existen en `data/raw/` un DTM HiRISE y una ortoimagen de Jezero, dos SRTM y GMTED. La configuración del caso usa estos centros:

| Área | Longitud, latitud | Ventana local |
|---|---|---|
| Jezero, abanico | 77,41; 18,49 | 1,8 × 1,8 km |
| Utah | −110,6; 38,6 | 1,8 × 1,8 km |
| Atacama | −67,9; −23,8 | 1,8 × 1,8 km |

Los polígonos efectivos deben leerse de `docs/evidencia-fase-2/areas-*.json` o `.geojson`; estos centros no los sustituyen. Las 970 ventanas regionales requieren consultas y validación propias: disponibilidad sobre las dos candidatas iniciales no garantiza cobertura regional.

## 2. Dimensiones, fuentes y utilidad

### A. Geometría: rugosidad, posición y organización del relieve

**Primero reutilizar los DEM locales.** Probar residuo de elevación respecto a una superficie local, posición topográfica —altura respecto al vecindario— y curvatura, declarando fórmula, unidades, tamaño de celda y radio físico del vecindario. Son propuestas de método, todavía no implementadas. Evaluar sensibilidad a 60/120 m y mantener separados los resultados regionales de 300/600 m. La segunda derivada amplifica ruido; el suavizado cambia el significado.

Para obtener detalle terrestre, la API oficial [TNMAccess](https://www.usgs.gov/faqs/there-api-accessing-national-map-data) permite localizar productos **USGS 3DEP**, con descargas GeoTIFF y, según proyecto, nubes lidar LAZ. El inventario de fase 1 ya identifica una tesela de 1 m para Utah:

`USGS_1M_12_x53y428_UT_FEMA_FS_FlamingGorge_2020_B20.tif`

Su tamaño registrado es **272.131.915 bytes**, confirmado con HEAD HTTP 200 en esta investigación. El enlace completo está en el catálogo. La auditoría previa comprobó que el rectángulo del ráster contiene la ventana, pero solo leyó una cabecera parcial: aún faltan descarga completa y máscara válida. No confundir el nombre del proyecto con una comprobación de la fecha de cada píxel. Para Mojave hay productos identificados en `docs/evidencia-fase-1/tnm-mojave-1m.json`; Atacama necesita otra fuente de detalle.

Un DEM de suelo desnudo de 1 m ayuda a estudiar microtopografía a esa escala; no representa automáticamente todas las rocas y obstáculos sobre el terreno.

### B. Materiales: geología y mineralogía

**Marte — cartografía:** el [mapa geológico de Jezero, USGS SIM 3464](https://pubs.usgs.gov/sim/3464/), lista una base GIS (`sim3464_database.zip`, aproximadamente 333 MB según el índice), metadatos y explicación. El acceso directo al ZIP devolvió HTTP 403 en la comprobación HEAD: se verificó su publicación, pero la descarga permanece pendiente. Permitiría intersectar unidades y calcular proporciones de área, después de revisar escala y leyenda. Es interpretación geológica; las unidades no son mediciones químicas por píxel. El formato GIS concreto y sus capas internas deben inspeccionarse tras descargar el ZIP.

**Marte — espectros:** [CRISM/PDS](https://pds-geosciences.wustl.edu/missions/mro/crism.htm) proporciona reflectancia y productos derivados. Investigar primero MTRDR y sus parámetros, conservando etiquetas y geometría; si no existe un producto adecuado, evaluar TRDR/TER y el procesamiento adicional. Las observaciones `FRT000047A3`, `FRT00005C5E` y `HRL000040FF` están documentadas sobre Jezero en [estudios originales](https://pmc.ncbi.nlm.nih.gov/articles/PMC8243932/). Esto no comprueba cobertura de nuestro polígono: la selección exacta y el soporte válido siguen pendientes. Descargar cubos y parámetros numéricos, no solo composiciones RGB. Tamaño pendiente de seleccionar archivos.

**Tierra — minerales:** priorizar **EMIT L2B MIN V002**, a 60 m nominales, para identificaciones minerales, profundidad de bandas e incertidumbre; consultar [Earthdata Search](https://search.earthdata.nasa.gov/search/granules?p=C4079846859-LPCLOUD). El catálogo CMR describe datos sin ortorrectificar, con geolocalización y GLT: hace falta aplicar esa geometría antes de recortar. Descargar los dos NetCDF, identificación e incertidumbre. Los índices de mineral no coinciden necesariamente con las etiquetas o parámetros CRISM: construir una correspondencia física revisada y usar únicamente categorías respaldadas por ambos.

La consulta pública por **punto central**, guardada en la evidencia, encontró:

| Sitio | Resultados V002 | Ejemplo identificado | Tamaño informado por CMR |
|---|---:|---|---:|
| Utah | 9 | `EMIT_L2B_MIN_002_20230609T171110` | 124,66 MB por gránulo |
| Atacama | 10 | `EMIT_L2B_MIN_002_20220909T131332` | 109,54 MB por gránulo |

Estos recuentos no son imágenes despejadas ni ventanas completamente válidas. Antes de elegir: comprobar toda la huella, nubes, calidad del ajuste espectral, incertidumbre y soporte dentro del polígono. V001 devolvió 31 y 20 resultados, respectivamente; no mezclar versiones por conveniencia. V002 está disponible según la consulta actual; revisar el avance del reprocesamiento antes de fijar el lote.

**EMIT L2A RFL** queda como segunda descarga si necesitamos analizar espectros, con reflectancia, incertidumbre y máscaras de una versión compatible. Es más costosa que empezar por los derivados L2B; sus gránulos y tamaños aún no se seleccionaron. La [guía oficial de adquisición](https://github.com/nasa/EMIT-Data-Resources/blob/main/guides/Getting_EMIT_Data_using_EarthData_Search.md) explica el acceso con NASA Earthdata Login.

**Tierra — cartografía:** [Utah Geological Survey](https://geomap.geology.utah.gov/) permite descargar mapas y exportar resultados geológicos a GeoJSON. Para Atacama, buscar la hoja correspondiente en [SERNAGEOMIN](https://portalsdnmext.sernageomin.cl/publicacionesgeologicas). Falta seleccionar mapa, escala, formato y condiciones de cada hoja. Una clasificación común —por ejemplo, depósitos no consolidados, rocas sedimentarias, volcánicas— exige revisar las leyendas; compartir nombre no demuestra igual granulometría, resistencia o compactación.

### C. Morfología superficial, rocas y obstáculos

**Marte:** ya está descargada la ortoimagen `PSP_002387_1985_RED_C_01_ORTHO`, de aproximadamente 1 m/píxel. Existe la variante `RED_A_01_ORTHO`, de aproximadamente 0,252 m/píxel según su etiqueta local y **386.772.481 bytes**, confirmados con HEAD HTTP 200. Enlace exacto en el catálogo; su máscara aún no está examinada. La [página del DTM](https://www.uahirise.org/dtm/PSP_002387_1985) documenta los productos asociados. La imagen de mayor detalle no aumenta la resolución del DTM.

**Tierra:** [NAIP de Utah](https://gis.utah.gov/products/sgid/aerial-photography/naip/) ofrece ortofotografía de 0,6 m en campañas recientes; comprobar año y tesela. Consultar también TNM para Mojave. No ofrece cobertura de Atacama: allí Sentinel-2 sirve para formas mayores y contexto; contar obstáculos pequeños necesitará ortofotos o levantamientos de campo con permisos y resolución adecuados.

Primera variable viable: fracción de superficie cubierta por formas visibles, textura o depósitos, con anotación manual y tamaño mínimo declarado. Para rocas exigir varios píxeles por objeto, evaluación con etiquetas y control de sombras. No comparar intensidades o texturas crudas sin controlar iluminación, bandas y escala. Una imagen de 0,6 m no respalda un inventario completo de rocas de decenas de centímetros.

### D. Propiedades térmicas

Se localizó y descargó el producto de Edwards y Buz [THEMIS-derived Thermal Inertia of Jezero Crater](https://experts.nau.edu/en/datasets/themis-derived-thermal-inertia-of-jezero-crater-mars/), DOI [10.5281/zenodo.4931348](https://doi.org/10.5281/zenodo.4931348).

Archivo local: `data/raw/themis/Jezero_Thermal_Inertia_v1.tiff`.

- 1.721.889 bytes; GeoTIFF Float32 de 890 × 890 celdas, paso proyectado de 100 m.
- Inercia térmica en J m⁻² K⁻¹ s⁻¹/²; nodata 0. Licencia CC BY 4.0 según el registro.
- MD5 coincide con el publicado; se registró SHA-256 local.
- Comprobación nominal: 342 centros de celda dentro del polígono de fase 2 y 342 valores válidos.
- La proyección usa esfera marciana de radio 3.396.190 m; el caso topográfico usa otra esfera local. La comprobación reutiliza longitudes/latitudes sobre la esfera del producto térmico, sin validar corregistro independiente. No equivale a exactitud del 100 %.

Identidad y lectura constan en [el manifiesto](../../investigacion-dimensiones/descarga-piloto-termica.json) y [el control espacial](../../investigacion-dimensiones/qa-piloto-termica.json). No se integró al análisis existente.

**Tierra:** [Landsat 8/9 Collection 2 Level-2 Surface Temperature](https://www.usgs.gov/landsat-missions/landsat-collection-2-surface-temperature) permite adquirir temperatura superficial, QA e incertidumbre en GeoTIFF. Elegir escenas `L2SP` con temperatura disponible y conservar `ST_B10`, `ST_QA`, `QA_PIXEL` y metadatos. La banda térmica tiene [100 m nativos y entrega remuestreada a 30 m](https://www.usgs.gov/faqs/what-are-band-designations-landsat-satellites); 30 m no es detalle térmico nuevo. Acceso por EarthExplorer y rutas oficiales de Landsat; el lote exacto está pendiente.

**Landsat no mide la misma magnitud que este GeoTIFF marciano.** Puede describir el ambiente terrestre por separado. Para comparar inercia térmica se necesita una estimación terrestre con modelo, observaciones temporales y validación apropiados, o mediciones de campo. Un mosaico THEMIS diurno/nocturno o una captura de pantalla tampoco sustituye al producto cuantitativo descargado.

### E. Polvo y procesos eólicos

Separar polvo depositado, arena/dunas y aerosoles atmosféricos. La primera extensión defendible es cartografiar formas eólicas con HiRISE y NAIP, agregadas a una escala comparable y con revisión visual. EMIT describe minerales de superficies fuente; no mide cuánto polvo se levanta ni concentración atmosférica.

El [TES Dust Cover Index distribuido por ASU](https://mars.asu.edu/data/tes_ruffdust/) tiene aproximadamente 3,5 km/píxel y esa página ofrece PNG. Queda registrado como **contexto**, no como entrada numérica para la ventana de 1,8 km. Para cuantificar polvo harán falta datos numéricos originales, interpretación del índice y contraparte terrestre específica. Tampoco sustituir este índice por profundidad óptica de aerosoles: describen cosas diferentes.

### F. Agua/hielo y ambiente sedimentario

Para investigar el **ambiente sedimentario antiguo** de Jezero, empezar por geología y morfología, sin inferir agua actual.

Para agua superficial terrestre, [JRC Global Surface Water](https://global-surface-water.appspot.com/download) ofrece ocurrencia y series históricas a 30 m, descargables para uso local. La página anuncia actualización 1984–2024 y advierte cambios de geolocalización entre colecciones Landsat; elegir y fijar la versión. Sirve para contexto hidrológico terrestre, no para comparar directamente lagos actuales con un paleolago marciano.

Si el escenario pasa a **hielo subsuperficial**, [SWIM4MIM](https://swim.psi.edu/SWIM4MIMProducts.php) ofrece GeoTIFF a 3 km/píxel entre 60° S y 60° N, con consistencia de evidencia por intervalos de profundidad y nodata −30. No es una probabilidad calibrada ni una medición de hielo en cada píxel; resulta demasiado grueso para resolver nuestra ventana. Necesita otro diseño regional y fuentes terrestres de hielo comparables. No se seleccionó un escenario lunar/polar en esta investigación.

## 3. Lote local recomendado y orden de adquisición

| Orden | Adquisición | Coste conocido o pendiente | Resultado esperado |
|---|---|---|---|
| 0 | Reutilizar DTM HiRISE y SRTM | Sin nueva descarga | Prototipar más descriptores geométricos |
| 1 | THEMIS Jezero | **1,72 MB, descargado** | Dimensión térmica marciana disponible para preparar |
| 2 | Un EMIT L2B V002 por candidata, con incertidumbre | Aproximadamente 234 MB según dos ejemplos CMR; confirmar bytes de archivos | Viabilidad de materiales terrestres |
| 3 | GIS Jezero y hoja geológica de Utah | Jezero ~333 MB; Utah por seleccionar | Primera correspondencia revisada de unidades |
| 4 | 3DEP Utah 1 m | 272 MB en inventario previo; verificar cabecera actual | Detalle topográfico terrestre |
| 5 | CRISM seleccionado y ortofoto terrestre | Pendiente de producto y tamaño | Cerrar comparación mineralógica y morfológica |
| 6 | Landsat, JRC o SWIM | Solo si el escenario los requiere | Contexto ambiental o escenario diferente |

Los componentes conocidos suman aproximadamente **0,84 GB**, sin CRISM, ortofotos ni derivados. Reservar inicialmente 2 GB es un presupuesto de trabajo propuesto, no una garantía de que quepan todos los productos. Verificar tamaños desconocidos antes de descargar; el pico de disco incluye ZIP, extracción y originales. No hace falta descargar colecciones globales completas.

## 4. Cómo adquirirlos y conservarlos en local

1. Usar los enlaces directos del catálogo para productos ya identificados. Guardar datos en `data/raw/<fuente>/`; los rásteres están excluidos de Git.
2. Para EMIT, iniciar sesión en Earthdata Search, abrir la colección V002, buscar cada ID de la tabla y descargar identificación e incertidumbre. Las consultas de metadatos CMR no necesitan credenciales; los NetCDF sí requieren Earthdata Login. Los enlaces están guardados en los JSON de evidencia y en el catálogo. Usar el cliente oficial/autenticación del proveedor fuera de Git.
3. Para CRISM, usar ODE/PDS, comprobar la intersección con el polígono y descargar producto, etiqueta, parámetros y geometría. Para NAIP/3DEP, usar TNMAccess o el descargador de The National Map; para geología terrestre, descargar la hoja y su leyenda desde el proveedor.
4. Antes de calcular, leer CRS, unidades, nodata, fecha, escala y calidad. Para EMIT aplicar GLT y máscaras; en variables categóricas conservar etiquetas —vecino más cercano o fracciones por clase, nunca promedio de códigos minerales—. Armonizar mapas de clase e incertidumbre de manera coherente.
5. Registrar URL, producto, versión, bytes, licencia, checksum publicado cuando exista y SHA-256 local. Guardar derivados en `data/normalized/` y descriptores en `data/features/`, con parámetros y máscaras separados. Una falta de datos permanece como ausencia explícita.

Ejemplo reproducible de consulta de **metadatos** de EMIT para Utah, desde la raíz:

```sh
mkdir -p data/manifests
curl --fail --get 'https://cmr.earthdata.nasa.gov/search/granules.json' \
  --data-urlencode 'short_name=EMITL2BMIN' \
  --data-urlencode 'version=002' \
  --data-urlencode 'point=-110.6,38.6' \
  --data-urlencode 'page_size=20' \
  --output data/manifests/emit-utah-v002-consulta.json
```

Para Atacama cambiar `point` por `-67.9,-23.8` y el nombre de salida. Los resultados pueden cambiar. Para búsqueda por polígono y paginación consultar la [API CMR](https://cmr.earthdata.nasa.gov/search/site/docs/search/api.html). La respuesta incluye enlaces de datos y vistas previas; no procesar el PNG como si fuera el NetCDF.

El recolector actual admite sus fuentes históricas, no EMIT/CRISM/THEMIS/NAIP. Para automatizar esta ampliación habrá que añadir adaptadores por proveedor, selección espacial y autenticación apropiada; el catálogo de esta investigación sirve de entrada al diseño, no activa esas descargas.

## 5. Extensión propuesta del proyecto

Crear un escenario independiente de **materiales y morfología de superficie**, conservando el análisis topográfico actual. Preparar primero una sola candidata terrestre —Utah, por disponibilidad de detalle— y mantener Atacama como contraste cuando sus máscaras sean suficientes.

Cada descriptor debería incluir: sitio y polígono, dimensión, variable, unidad, método/versionado, celda y vecindario, fecha, fuentes/hashes, fracción válida, incertidumbre disponible y estado de comparabilidad. Distinguir `measured`, `not_acquired`, `insufficient_quality` y `not_comparable`; no reducir estos estados a cero. Conservar las métricas por dimensión antes de considerar un índice combinado.

Criterio para integrar una dimensión en la aplicación: referencia y al menos una candidata con productos seleccionados, geometría y calidad verificadas, método físico compatible, resultados reproducibles y revisión de sensibilidad. Tener un GeoTIFF marciano descargado o una escena terrestre localizada todavía no completa ese criterio.

## Evidencia y límites de esta investigación

- `investigacion-dimensiones/emit-collections.json`: versiones y descripción publicadas por CMR.
- `emit-{utah,atacama}-v{1,2}.json`: consultas por centro, dos ejemplos por respuesta y total informado en `CMR-Hits`; no es el inventario completo ni control de píxeles.
- `jezero-thermal-record.json`: registro del autor, archivos, licencia y checksum.
- `descarga-piloto-termica.json` y `qa-piloto-termica.json`: identidad y lectura local del piloto.
- `cabeceras-productos.json`: comprobaciones HEAD; un enlace sin respuesta favorable no se considera descarga verificada.

Se verificaron catálogos y documentación, no todas las teselas ni el contenido de los ZIP. Algunas páginas USGS/Earthdata devolvieron errores al lector web; se conservan los enlaces oficiales y se distingue la evidencia consultada de las comprobaciones pendientes. La validación científica de analogía y de obstáculos sigue fuera de esta investigación.
