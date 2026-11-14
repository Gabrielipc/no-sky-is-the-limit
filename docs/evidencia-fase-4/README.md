# Evidencia de fase 4

Ver la [ficha de entrega, método y resultados](../02-versiones-anteriores/etapa-1-mvp-escenarios/Fase%204%20-%20busqueda%20regional%20terrestre.md).

- `auditoria-gmted.json`: identidades locales, CRC de todos los miembros de ambos ZIP, metadatos y muestras. La validez numérica no demuestra tierra ni observaciones.
- `manifiesto-gmted.json`: subconjunto conciliado del manifiesto de adquisición; no altera otras fuentes.
- `mn*-metadata.xml`, `mn*-prj.adf`: metadatos copiados de los ZIP verificados.
- `seleccion-de-ventana.json`: cobertura de Jezero al probar seis tamaños; se elige 3000 m con cobertura completa a ambas escalas.
- `candidatas.json`: 970 ventanas nuevas y tres controles; métricas, geometrías y decisiones de tres perfiles a 300/600 m. Las 18 combinaciones área/escala/perfil incluyen IDs aceptados.
- `procesamiento.json`: hashes de configuración y código, referencia y recortes, versiones, conteos, recursos y tiempo local.
- `detalle/utah-010-007.json`: evaluación de detalle exploratoria de una ventana nueva, sin descarga adicional; las demás conservan estado pendiente.
- `manifest-local.json`: identidad de los registros científicos principales, código y configuración que publica el pipeline.
- `repeticion.json`: comparación idéntica de dos ejecuciones finales del catálogo; el tiempo de procesamiento no es determinista.
- `verificacion.json`, `entrega-manifest.json`: controles de esta entrega y hashes complementarios de archivos y documentación.
- `recorrido.jpg`, `detalle-utah.jpg`: capturas del barrido y de la evaluación local en la aplicación.

Los originales permanecen en `data/raw/`. Los recortes regenerables se guardan en `data/normalized/fase4/`. Ni esta evidencia ni sus hashes sustituyen validación científica o controles de autenticidad externa.
