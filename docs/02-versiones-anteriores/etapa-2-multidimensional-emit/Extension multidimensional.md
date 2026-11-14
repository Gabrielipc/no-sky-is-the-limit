# Extensión multidimensional del atlas

El recorrido **Más dimensiones** (`/?view=dimensions`) compara Jezero con Utah y Atacama en tres descriptores geométricos y muestra la inercia térmica de Jezero como una observación separada. Mantiene disponibles los recorridos anteriores. Sus resultados son exploratorios; no hay puntuación combinada, detección de obstáculos ni validación de analogía.

Ampliación posterior: ahora abre la sección **Minerales**, con mapas EMIT terrestres y filtros de ajuste e inclinación. **Formas del terreno** y **Térmica y pendientes** conservan los resultados descritos aquí. Consulta la [entrega de minerales y preparación CRISM](Minerales%20EMIT%20-%20entrega.md); los estados históricos de este análisis se conservan en su evidencia original.

## Cálculo implementado

La configuración es `specs/scenarios/superficie-multidimensional-v1.json`. Reutiliza originales e identidades del primer caso, sin reescribir su configuración ni sus resultados.

| Variable | Método y unidad | Soporte |
|---|---|---|
| Rugosidad sin inclinación | RMS residual después del ajuste por mínimos cuadrados de un plano local; metros | Cuadrado de ±360 m entre centros de muestras |
| Posición topográfica | Elevación central menos media local; metros | El mismo cuadrado |
| Curvatura discreta | Laplaciano con cuatro vecinos, suma de sus diferencias al centro dividida por celda²; m⁻¹ | Centro y vecinos axiales |

Ventana central de 1.800 × 1.800 m; celdas de 60 y 120 m; margen de 480 m. La elevación se agrega por promedio y solo se acepta con soporte completo. Para rugosidad y posición todos los valores del vecindario deben ser válidos; no se renormalizan huecos. Son 13 × 13 muestras a 60 m y 7 × 7 a 120 m, con el mismo radio entre centros. El área efectiva de integración incluye media celda adicional en cada borde y cambia con la escala.

Por variable/sitio se conservan p10, p50, p90, celdas válidas, cobertura y mapa con `null` para ausencias. Solo se comparan ventanas con cobertura ≥95 %, un criterio operativo explícito, no un umbral de validez científica. La distancia de Wasserstein conserva la unidad original; la diferencia de medianas se expresa como candidata−Jezero.

Los tres descriptores comparten información con pendiente y relieve. El Laplaciano no es curvatura geométrica normalizada y es sensible al ruido. No se interpreta como seguridad de conducción.

## Térmica y dimensiones pendientes

Se lee el GeoTIFF cuantitativo de Edwards y Buz, `Jezero_Thermal_Inertia_v1.tiff`, DOI `10.5281/zenodo.4931348`. Se comprueban bytes, SHA-256, una banda, CRS, radio marciano y nodata 0. La máscara del polígono selecciona centros de píxel en su cuadrícula proyectada nativa de 100 m. El resultado actual tiene 342 centros y 342 valores válidos; se conserva una capa nativa y cuantiles en J m⁻² K⁻¹ s⁻¹/², sin remuestrearla a 60 m.

La superposición interpreta longitudes y latitudes del polígono en la esfera del producto térmico. Su radio difiere del usado por el DTM: el corregistro independiente permanece pendiente. Un 100 % de soporte no significa 100 % de exactitud.

Para Tierra no hay inercia térmica comparable adquirida; permanece `not_acquired`. La comparación térmica es `not_comparable` y su distancia es `null`. Los cuatro grupos restantes —materiales, rocas, polvo, agua/hielo— conservan `not_evaluated`, razón y fuentes candidatas. Descargar una imagen o un cubo no los convierte automáticamente en mediciones de estas dimensiones. EMIT necesita geolocalización, máscaras, evaluación del ajuste y correspondencias revisadas con CRISM antes de integrar comparaciones minerales.

## Reproducir y consultar

Desde la raíz del proyecto:

```sh
.pixi/envs/default/bin/python scripts/analizar_dimensiones.py
```

Genera `docs/evidencia-dimensiones/{resultados,procesamiento,manifest-local}.json`. La API verifica su manifiesto, configuración, catálogo y scripts antes de servir resultados; funciona con la evidencia revisada sin abrir originales ni hacer peticiones remotas por consulta. Si cambia una entrada de ese manifiesto, devuelve 503 hasta regenerar y revisar la evidencia. El generador verifica las identidades de los originales antes del cálculo. La procedencia conserva versiones e identidades de entradas.

Endpoints:

- `/api/multidimensional?candidate_id=earth-utah&cell_m=60`
- `/api/scenarios/superficie-multidimensional/comparison?candidate_id=earth-atacama&cell_m=120`
- `/api/multidimensional/sources`
- `/api/multidimensional/evidence/resultados.json`

En la pantalla se seleccionan candidata, celda y descriptor. Los dos mapas comparten rango de color para esa selección; para variables firmadas el rango es simétrico respecto a cero. Las flechas permiten inspeccionar celdas con teclado. El estado se conserva en la URL y en Atrás/Adelante. El panel térmico conserva la escala nativa y explica la falta de contraparte terrestre. Las fuentes y el método quedan disponibles en un desplegable.

## Nuevas adquisiciones locales

`scripts/adquirir_dimensiones.py` agrega un flujo independiente del recolector histórico. Planifica fuentes públicas THEMIS, 3DEP Utah, ortoimagen HiRISE de detalle y su etiqueta, y los archivos MIN/MINUNCERT de un gránulo EMIT V002 seleccionado por candidata. Usa los identificadores de la investigación; no descarga todas las escenas ni hace un barrido global.

```sh
.pixi/envs/default/bin/python scripts/adquirir_dimensiones.py discover
.pixi/envs/default/bin/python scripts/adquirir_dimensiones.py fetch --sources themis 3dep-utah --max-new-gb 0.3
.pixi/envs/default/bin/python scripts/adquirir_dimensiones.py verify --sources themis 3dep-utah
```

El plan por defecto es `data/manifests/dimensiones.json`. Si ya existe, `discover` pide otra ruta `--plan` para conservar los hashes previos. `discover` funciona con el catálogo local; añadir `--refresh` consulta cabeceras, sin descargar rásteres. `fetch` comprueba tamaños con HEAD y limita el lote completo antes de transferir. El presupuesto limita **bytes nuevos en esa ejecución**, no los datos históricos ya descargados. Se mantiene una reserva de 1 GiB y se conservan parciales con comprobación de identidad/rangos. `verify` exige tamaño y SHA-256 registrados; los hashes calculados localmente no demuestran autenticidad independiente.

Las descargas quedan bajo `data/raw/` y el plan bajo `data/manifests/`, excluidos de Git. Los nuevos originales no reemplazan silenciosamente las fuentes del análisis: 3DEP se adquiere para el siguiente contraste de detalle; las comparaciones de esta entrega siguen utilizando SRTM y HiRISE declarados en el caso base.

En esta implementación se descargó y verificó la tesela 3DEP de 272.131.915 bytes. La lectura local encontró 3.237.461 centros de píxel dentro del polígono de Utah, todos con valores válidos. La identidad y el control nominal están en `docs/investigacion-dimensiones/3dep-utah-adquisicion.json`; la cobertura no establece exactitud ni resolución efectiva.

Para EMIT, generar un token por el [procedimiento oficial de Earthdata](https://urs.earthdata.nasa.gov/documentation/for_users/user_token), cargarlo en `EARTHDATA_TOKEN` en el entorno de la terminal y ejecutar:

```sh
.pixi/envs/default/bin/python scripts/adquirir_dimensiones.py fetch --sources emit --max-new-gb 0.5
.pixi/envs/default/bin/python scripts/adquirir_dimensiones.py verify --sources emit
```

El programa no solicita ni guarda contraseñas. El token se utiliza únicamente ante el host oficial de LP DAAC, se retira en redirecciones a otro host y no se guarda en planes ni errores. Sin token la adquisición EMIT informa `awaiting_auth`. También pueden utilizarse las descargas manuales de Earthdata Search; una copia manual no se adopta como verificada sin identidad registrada.

### EMIT: 403 al comprobar el tamaño con un token válido

Corregido el 8 de noviembre de 2026: LP DAAC redirige a una URL de CloudFront firmada para `GET`. Una comprobación `HEAD` de esa misma ruta puede devolver 403 aunque una lectura autenticada funcione. El script ahora consulta EMIT con `GET` y `Range: bytes=0-0`, toma el tamaño completo de `Content-Range` y cierra la respuesta; no confunde el byte de prueba con el tamaño del archivo. Los proveedores públicos mantienen su comprobación anterior.

El token no necesita reemplazarse por este problema. Para reintentar el plan existente y verificar únicamente si la descarga termina correctamente:

```sh
.pixi/envs/default/bin/python scripts/adquirir_dimensiones.py fetch --sources emit --max-new-gb 0.5 && \
.pixi/envs/default/bin/python scripts/adquirir_dimensiones.py verify --sources emit
```

`NO VERIFICADO` tras una descarga rechazada significa que el archivo no está disponible con identidad local comprobada; no es una evaluación de su calidad científica. Otros errores 401/403 pueden requerir revisar el token y la autorización del proveedor: esta corrección resuelve el caso de `HEAD`, sin omitir la autenticación.

Comprobación posterior de la corrección: se descargaron los cuatro archivos MIN/MINUNCERT seleccionados, con 189.879.372 bytes en total, dentro del presupuesto de 0,5 GB. `verify --sources emit` devolvió `OK` en los cuatro y se comprobó su cabecera HDF5/NetCDF4. Pasaron doce pruebas del adquiridor y nueve del transporte histórico. La adquisición registra identidad local; no incorpora automáticamente mediciones minerales al análisis.

## Comprobaciones

```sh
bash scripts/preparar_minerales.sh
bash scripts/ejecutar_minerales.sh -m unittest discover -s tests -v
cd backend
../.pixi/envs/default/bin/python -m unittest discover -s tests -v
cd ../frontend
npm test
npm run build
```

Los controles nuevos utilizan un plano inclinado, un paraboloide con solución analítica, huecos, cambios de resolución, diferencias firmadas, nodata térmico, identidad de archivos y presupuestos de adquisición. La API comprueba las dos candidatas/escalas, ausencias explícitas, rutas y rechazo de evidencia alterada. La compilación valida el contrato TypeScript.

La verificación de entrega pasó las pruebas científicas/adquisición, 29 pruebas de API y 9 del frontend, además de la compilación de producción. Se comprobó visualmente el recorrido, cambio de candidata/descriptor/escala y navegación atrás. A 390 px no hubo desbordamiento horizontal, incluso con el catálogo abierto; la consola del recorrido no mostró errores. Capturas: [escritorio](../../evidencia-dimensiones/captura-escritorio.jpg), [vista completa](../../evidencia-dimensiones/captura-completa.jpg) y [móvil](../../evidencia-dimensiones/captura-movil.jpg). Estos controles verifican el cálculo y el software; no validan analogía física.
