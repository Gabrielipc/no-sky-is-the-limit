# Evidencia de fase 5

Ver [entrega, pregunta y límites](../02-versiones-anteriores/etapa-1-mvp-escenarios/Fase%205%20-%20expansion%20condicionada.md).

- `resultados.json`: diez ventanas seleccionadas, siete evaluadas y tres pendientes; cuatro escalas SRTM, contraste con GMTED a 300/600 m, estratos y decisiones de expansión.
- `procesamiento.json`: originales, hashes, metadatos de referencia, versiones, tiempo y recursos locales. No hubo peticiones de red.
- `manifest-local.json`: identidades de resultados, procesamiento, configuraciones y código de generación. No prueba autenticidad externa ni precisión científica.
- `repeticion.json`: dos resultados idénticos bajo bloqueo de red y verificación de los 58 archivos previos preservados de fases 2 y 4.
- `verificacion.json`: controles automatizados e interactivos de esta entrega.
- `recorrido.png`, `detalle.png`, `pendiente.png`: capturas del nuevo escenario, del contraste de Utah y del control de Mojave sin detalle.

Reproducir con `./.pixi/envs/default/bin/python scripts/evaluar_expansion.py`. Se usan solo originales ya revisados; el programa no descarga archivos. Los recortes de cuadrícula nativa se guardan en `data/normalized/fase5/`. El detalle previo de fase 4 permanece preservado; los nuevos valores de fase 5 emplean recortes sin desplazar el origen de píxel.

No hay etiquetas verdaderas de analogía ni evaluación experta independiente. Esta muestra condicionada por archivos locales no representa todo el catálogo y no justifica ML ni soporte lunar o polar.
