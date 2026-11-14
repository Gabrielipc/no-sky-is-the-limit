# Adquisición CRISM de Jezero

El descargador `scripts/adquirir_marte.py` adquiere una selección explícita de la observación **FRT000047A3**, desde el [archivo público PDS](https://pds-geosciences.wustl.edu/mro/mro-m-crism-5-rdr-mptargeted-v1/mrocr_4001/mtrdr/2007/2007_057/frt000047a3/). No necesita cuenta ni token Earthdata. Usa únicamente la biblioteca estándar de Python del entorno Pixi.

## Paquete por defecto: indicadores y calidad

Desde la raíz del proyecto:

```sh
.pixi/envs/default/bin/python scripts/adquirir_marte.py discover
.pixi/envs/default/bin/python scripts/adquirir_marte.py fetch --max-new-gb 0.25
.pixi/envs/default/bin/python scripts/adquirir_marte.py verify --report docs/investigacion-marte/adquisicion-crism.json
```

`discover` funciona sin red y no descarga archivos. Crea `data/manifests/crism-jezero.json`, sin reemplazar planes existentes. `fetch` y `verify` usan el paquete que quedó registrado en ese plan. Para conservar otro experimento, usa `--plan` con otra ruta en los tres comandos.

El paquete `parameters` contiene siete archivos, **188.972.526 bytes** en total:

- SR: indicadores espectrales refinados, 60 bandas, 164.250.240 bytes.
- IN: información suplementaria y máscara VNIR/IR, 9 bandas, 24.637.536 bytes.
- Cabeceras ENVI `.hdr` y etiquetas PDS `.lbl` de ambos productos, además de `.xml` de SR.

Se conservan bajo `data/raw/crism/frt000047a3/`, excluido de Git. Las etiquetas y cabeceras permiten interpretar la estructura de los IMG; descargar solo el binario no es suficiente.

## Opción: incluir el espectro completo

```sh
.pixi/envs/default/bin/python scripts/adquirir_marte.py discover --package full --plan data/manifests/crism-jezero-full.json
.pixi/envs/default/bin/python scripts/adquirir_marte.py fetch --plan data/manifests/crism-jezero-full.json --max-new-gb 1.6
.pixi/envs/default/bin/python scripts/adquirir_marte.py verify --plan data/manifests/crism-jezero-full.json
```

`full` incluye los siete archivos anteriores y agrega el cubo IF de reflectancia corregida (489 bandas, 1.338.639.456 bytes), sus HDR/LBL/XML y la tabla de longitudes de onda WV con su etiqueta. Son trece archivos y **1.527.666.994 bytes** si aún no existen archivos locales verificados. No se descarga IF al elegir el paquete por defecto.

Si ya adquiriste el paquete por defecto, agrega `--reuse-plan data/manifests/crism-jezero.json` al comando `discover --package full`. Se validan el plan anterior y las identidades de sus archivos locales antes de reutilizarlas; solo quedarán por descargar los archivos adicionales. Los planes permanecen separados. Un archivo existente sin identidad registrada o verificable no se adopta ni se sobrescribe.

## Presupuesto, recuperación y verificación

Antes de transferir un archivo completo se comprueban el presupuesto de todo el lote, el espacio libre con reserva de 1 GiB, la disponibilidad y el tamaño exacto de cada producto. La comprobación remota solicita un solo byte con `GET Range`; si PDS ignora el rango, se inspeccionan sus cabeceras y se cierra la respuesta. Se rechazan HTML, tamaños distintos y destinos fuera de la selección PDS admitida.

`--max-new-gb` limita bytes nuevos de los archivos en esta ejecución, en GB decimales. No limita el tráfico de red de reintentos o comprobaciones de parciales, ni cuenta los datos históricos. Los pequeños archivos internos de recuperación se contabilizan aparte. Los archivos `.part` se conservan ante interrupciones; la reanudación exige el rango exacto y un ETag fuerte o Last-Modified. Una identidad remota distinta no permite modificar el parcial existente. Los archivos finales no se sobrescriben.

Se guarda el SHA-256 de cada descarga completa y se verifica de nuevo al ejecutar `verify`. Las cabeceras y etiquetas también deben coincidir con las copias revisadas del proyecto. El SHA-256 calculado localmente para un IMG fija su identidad y permite detectar cambios; no constituye una comprobación independiente de autenticidad del proveedor.

El informe opcional de `verify` registra URLs, tamaños, hashes y el resultado por archivo, incluyendo los ausentes o alterados. Un error produce un código de salida distinto de cero; `NO VERIFICADO` no significa que el material esté ausente del terreno.

## Adquisición ejecutada y comprobaciones

El 8 de noviembre de 2026 se adquirieron y verificaron los siete archivos del paquete `parameters`: **188.972.526 bytes**, sin parciales pendientes. Una segunda ejecución de `fetch` reutilizó los originales verificados sin acceso de red. La lectura estructural con Rasterio abrió SR e IN como ENVI, con 847 × 808 píxeles, 60 y 9 bandas float32, paso proyectado de 18 m y nodata 65.535. Se comprobó una lectura de píxel por producto; esto no constituye una evaluación de cobertura válida de la ventana.

También se preparó el plan local `data/manifests/crism-jezero-full.json`, que reutiliza las siete identidades anteriores y deja pendientes seis archivos adicionales con 1.338.694.468 bytes. Su descarga con presupuesto de 0,25 GB se rechazó antes de la red o la transferencia, comprobando el límite de lote. No se descargó IF.

Pasaron las **69 pruebas científicas y de adquisición**, incluidas **13 nuevas de CRISM**. Comprueban selección de paquetes, presupuestos y espacio, URLs e inventarios alterados, credenciales, rangos, interrupción/reanudación, reutilización de identidades, archivos modificados e informes de verificación. Los 126 archivos de evidencia anteriores conservaron sus identidades.

Evidencia: [tamaños, URLs y SHA-256](../../investigacion-marte/adquisicion-crism.json), [lectura estructural](../../investigacion-marte/lectura-crism.json) y [verificación de entrega](../../investigacion-marte/verificacion-adquisicion.json).

```sh
bash scripts/ejecutar_minerales.sh -m unittest discover -s tests -v
```

Ese ejecutor permite comprobar la suite completa, incluidos los controles del lector EMIT opcional. Las trece pruebas de adquisición CRISM también se ejecutan directamente con `.pixi/envs/default/bin/python -m unittest discover -s tests -p test_adquirir_marte.py -v`.

## Integración en el atlas

En **Más dimensiones → Minerales**, Jezero aparece junto a Utah o Atacama. Se pueden elegir cinco indicadores espectrales, el residuo de corrección atmosférica o el mapa de cobertura de Jezero. Cada mapa usa una escala propia. Los indicadores son exploratorios y la comparación cuantitativa entre planetas requiere un método de identificación común. [Abrir la vista](http://localhost:5173/?view=dimensions).

Se proyecta el polígono de fase 2 al sistema marciano de la escena y se seleccionan los centros de píxel en la cuadrícula entregada de 18 m. La máscara IN y el indicador SR de referencia coinciden en el recorte. De 10.200 celdas, 8.897 tienen cobertura VNIR/IR válida (código 0), 909 quedan excluidas por la máscara (código 1) y 394 carecen de cobertura (65.535). Los seis mapas numéricos conservan 8.897 valores cada uno. La visualización usa los percentiles 2 y 98 de cada capa para el color y conserva los valores negativos para la inspección. [Definiciones de indicadores y tratamiento VNIR/IR en la especificación de CRISM](https://pds-geosciences.wustl.edu/mro/mro-m-crism-2-edr-v1/mrocr_0015/document/crism_dpsis.htm).

Para reproducir el recorte desde los originales verificados, ejecuta desde la raíz:

```sh
.pixi/envs/default/bin/python scripts/analizar_crism.py
```

El resultado y el manifiesto de identidades se escriben en `docs/evidencia-crism/`. La API sirve el derivado verificado en `/api/minerals/jezero` y sus archivos de evidencia en `/api/minerals/jezero/evidence/`. La lectura durante la consulta se limita a los derivados y sus referencias locales. [Resultado publicado](../../evidencia-crism/resultados.json).
