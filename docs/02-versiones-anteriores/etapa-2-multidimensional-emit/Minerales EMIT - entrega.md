# Mapas de minerales EMIT y preparación para CRISM

Entrega del 8 de noviembre de 2026. Abre [Más dimensiones → Minerales](http://localhost:5173/?view=dimensions&dimensionSection=minerals). Utah y Atacama muestran datos EMIT reales; la comparación mineral con Marte permanece pendiente.

## Qué puedes hacer

- Cambiar entre los dos lugares y los dos grupos espectrales del producto.
- Ver identificaciones minerales, ajuste espectral, incertidumbre e inclinación en el mapa.
- Seleccionar una barra o una celda para resaltar una identificación; recorrer celdas con flechas y seleccionar con Enter.
- Abrir **Filtrar detecciones** para exigir mayor ajuste o limitar la inclinación. **Ver todas las detecciones** restablece los filtros.
- Consultar fechas, escenas descartadas, muestras originales, fuentes y evidencia sin abandonar la vista. El estado se conserva en la URL y en Atrás/Adelante.

Las secciones **Formas del terreno** y **Térmica y pendientes** mantienen los análisis anteriores. No se modifica su cálculo ni se añade una puntuación mineral a las comparaciones existentes.

## Cómo leer el resultado

| Elemento | Significado |
|---|---|
| Color mineral | Entrada de la biblioteca espectral que coincide con la señal del producto. El número conserva su identidad; dos entradas pueden tener el mismo nombre mineral. |
| Dos grupos | Detecciones en distintas regiones del espectro. Una celda puede tener una identificación en cada grupo; los porcentajes se leen por separado. |
| Barra y porcentaje | Celdas del mapa que pasan los filtros, divididas entre todas las celdas de la ventana. No es concentración química. |
| Ajuste R² | Medida del ajuste de la coincidencia con la biblioteca. El umbral interactivo es exploratorio; no es probabilidad de acierto. |
| Incertidumbre | Desviación estándar de la profundidad de banda, sin unidad. No es un porcentaje de confianza. |
| Sin coincidencia | El código 0 del producto: hay dato, pero no se identificó una entrada en ese grupo. |
| Sin dato | El producto no aporta una clasificación válida. No demuestra ausencia de minerales. |
| Fuera del filtro | Existía una detección, pero no pasa el criterio seleccionado. |

Las mezclas de biblioteca se identifican expresamente como mezclas y conservan el nombre original de su espectro al inspeccionar la celda. El mapa no demuestra composición pura. Los nombres son identificaciones del producto, no una validación independiente de campo.

## Datos utilizados y controles

| Lugar | Escena seleccionada | Celdas GLT en ventana | Muestras originales únicas | Detecciones grupo 1 / grupo 2 |
|---|---|---:|---:|---:|
| Utah | 2023-06-09T17:11:10 | 1.140 | 747 | 1.140 / 1.140 |
| Atacama | 2023-01-30T13:54:27 | 990 | 726 | 990 / 927 |

Atacama tiene además 63 celdas con código 0 en el segundo grupo. La escena original de Atacama del 2022-09-09 contiene valores de relleno dentro de esta ventana: se conserva en la auditoría, con cero identificaciones disponibles. Se adquirió otro par MIN/MINUNCERT de una escena previamente catalogada, con 97.391.816 bytes. La selección maximiza soporte de clasificaciones antes de aplicar los filtros interactivos; los desempates usan el identificador del producto. No se selecciona una escena para mejorar una puntuación.

Se verifica tamaño y SHA-256 de los seis archivos originales. Se aplica la tabla de geolocalización entregada por EMIT, con índices desde uno, conservando los códigos categóricos y la cuadrícula geográfica nativa. La máscara usa centros de píxel dentro del mismo polígono terrestre de 1.800 × 1.800 m de fase 2. Algunas celdas GLT repiten muestras originales: no son observaciones independientes ni una resolución física mayor.

El cruce con inclinación asigna el valor más cercano de la cuadrícula de pendiente de fase 2 a 60 m. Es una superposición para explorar y filtrar; no crea una medición conjunta a mayor resolución. No se adquirieron las máscaras L2A de nubes/sombra: los controles L2B disponibles no certifican cielo despejado. Las escalas de color de incertidumbre y pendiente saturan en 0,05 y 25° respectivamente, indicadas con ≥; la inspección conserva el valor numérico.

Los criterios y archivos exactos están en `specs/analysis/minerales-emit-v1.json`. El resultado, procesamiento y manifiesto están en `docs/evidencia-minerales/`. La API valida su inventario e identidades antes de servirlos; si falta o cambia evidencia devuelve 503, sin sustituirla por datos ilustrativos.

## Reproducción

La aplicación puede consultar la evidencia publicada sin abrir NetCDF ni instalar un lector adicional. Para regenerarla con los seis originales locales declarados en la configuración:

```sh
bash scripts/preparar_minerales.sh
bash scripts/ejecutar_minerales.sh scripts/analizar_minerales.py
```

El lector HDF5 usa `h5py==3.16.0` en `.tools/minerales`, separado del entorno histórico Pixi. El ejecutor conserva las rutas de datos PROJ/GDAL del entorno base. No se cambia `pixi.lock`. Los originales y planes locales de adquisición permanecen bajo `data/`, fuera de Git; para el par adicional de Atacama se conservó `data/manifests/emit-atacama-alternativa.json`.

Endpoints nuevos:

```text
/api/minerals?candidate_id=earth-utah
/api/minerals?candidate_id=earth-atacama
/api/minerals/evidence/resultados.json
/api/minerals/evidence/procesamiento.json
/api/minerals/evidence/manifest-local.json
```

Comprobaciones ejecutadas: 56 pruebas científicas y de adquisición, 32 de API, 11 del frontend y compilación de producción. Incluyen índices GLT, relleno antes de aplicar escalas, código 0, mezclas, denominadores fijos, filtros, URL e identidades alteradas. Para repetir la suite científica completa:

```sh
bash scripts/ejecutar_minerales.sh -m unittest discover -s tests -v
```

La revisión visual de la compilación de producción comprobó ambas candidatas y grupos, selección con ratón y teclado, filtros y estados vacíos, navegación y vistas anteriores. No hubo desbordamiento horizontal a 320, 390 y 1.440 px ni avisos o errores de consola en el recorrido probado. Una segunda generación conservó los hashes de los tres archivos publicados; los 126 archivos de evidencia anteriores conservaron sus identidades. [Verificación](../../evidencia-minerales/verificacion.json), [captura de escritorio](../../evidencia-minerales/mapa-utah.jpg), [vista completa](../../evidencia-minerales/mapa-utah-completa.jpg) y [móvil](../../evidencia-minerales/mapa-atacama-movil.jpg).

## Qué hace falta para Marte

Se localizaron y descargaron únicamente los metadatos de **CRISM FRT000047A3**, producto MTRDR de Jezero. El [directorio público de PDS](https://pds-geosciences.wustl.edu/mro/mro-m-crism-5-rdr-mptargeted-v1/mrocr_4001/mtrdr/2007/2007_057/frt000047a3/) respondió a lecturas parciales sin credenciales; esta ruta no necesita otro token Earthdata. PDS documenta [la corrección y organización de MTRDR](https://pds-geosciences.wustl.edu/missions/mro/crism.htm).

Su rectángulo declarado contiene la ventana de Jezero del análisis. Eso todavía no confirma que todos sus píxeles sean válidos dentro del polígono. La cuadrícula declarada es de 18 m, con 847 columnas y 808 filas; el paso de píxel no demuestra resolución efectiva.

| Opción | Archivos científicos | Descarga aproximada | Uso |
|---|---|---:|---|
| Parámetros espectrales y calidad | `SR` (60 bandas) + `IN` (9 bandas), con HDR y etiquetas PDS | 188.887.776 bytes ≈189 MB | Empezar con indicadores de firmas espectrales y máscaras. |
| Espectro completo corregido | `IF` (489 bandas), tabla `WV`, etiquetas y controles de calidad | IF: 1.338.639.456 bytes ≈1,34 GB, más auxiliares | Revisar espectros y desarrollar una identificación más detallada. |

El plan está en `specs/sources/crism-jezero-v1.json`, con URLs, tamaños y requisitos. Las copias de metadatos y las comprobaciones de cobertura declarada y acceso están en `docs/investigacion-marte/`. La entrega inicial no descargó los IMG. Una ampliación posterior implementó la [adquisición CRISM](../../01-vigentes/operacion-y-datos/Adquisicion%20CRISM%20de%20Marte.md) y adquirió el paquete SR/IN con sus metadatos; el cubo completo IF sigue siendo opcional. **No se publicaron mediciones minerales marcianas ni una comparación con EMIT.**

Tras adquirirlos hay que registrar sus identidades completas, comprobar máscaras y píxeles válidos en la ventana exacta, evaluar los indicadores o espectros, y definir una correspondencia revisada con los materiales EMIT. Los parámetros CRISM son indicadores espectrales, no las mismas clases de biblioteca EMIT. Descargar el archivo permite empezar ese análisis; no habilita por sí solo una comparación mineral Tierra–Marte.

[Método oficial de los productos minerales EMIT](https://nasa.github.io/LPDAAC-Data-Resources/external/Working_with_EMIT_L2B_Mineralogy.html).
