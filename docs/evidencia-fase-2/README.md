# Evidencia del primer análisis reproducible

Ver [ficha de resultados y método](../02-versiones-anteriores/etapa-1-mvp-escenarios/Primer%20analisis%20reproducible%20-%20Jezero%20y%20candidatas%20terrestres.md).

- `resultados.json`: métricas por sitio y escala, distribuciones y diferencias separadas. No hay puntuación combinada.
- `procesamiento.json`: hashes de entradas, código y configuración; versiones; CRS, transformaciones, ventanas, controles de lectura y disponibilidad nativa.
- `areas-marte.json`, `areas-tierra.geojson`: geometrías de las ventanas métricas finales. Marte mantiene su sistema planetario explícito.
- `*-native-crop.tif`: recortes de entrada con nodata, sin cálculo de pendientes nativas. Los originales permanecen en `data/raw/`.
- `*-60m-*.tif`, `*-120m-*.tif`: elevación (m), pendiente (grados) y soporte válido (fracción 0–1). NaN es nodata; elevación cero es válida.
- `*-qa.png`: elevación y sombreado nativos para inspección. El sombreado es contextual; los colores se ajustan por panel.
- `jezero-ortoimagen-qa.png`, `ortoimagen-qa.json`: inspección del mismo recorte mediante la ortoimagen C; identidad y coincidencia de cuadrícula comprobadas con etiqueta.
- `distribuciones-pendiente.png`: distribuciones acumuladas por escala; las curvas usan solo celdas de pendiente válidas.
- `fuentes-y-conflictos.json`: respaldo documental y alcance de discrepancias resueltas o pendientes.
- `verificacion.json`, `manifest-local.json`: resultados de controles y hashes de esta entrega; no son certificados de autenticidad ni exactitud.

Repetir con `make analysis`; comprobar con `make test-analysis`. Para descargar los originales concretos ausentes, consultar el comando `--download` de la ficha. La repetición no necesita red si las cuatro entradas coinciden con sus hashes.

El mapa geológico y los productos 3DEP de fase 1 no se incorporaron como variables medidas aquí. La térmica y los materiales siguen pendientes; no equivalen a cero ni participan en las distancias de terreno.
