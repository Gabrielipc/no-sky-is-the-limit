# Pipelines

La primera búsqueda regional reproducible está implementada en `scripts/buscar_candidatas.py`, con configuración en `specs/search/busqueda-regional-v1.json`.

Las etapas `audit`, `search` y `detail CANDIDATE_ID` verifican GMTED, generan ventanas regionales y calculan detalle bajo demanda. La API sirve los registros revisados de `docs/evidencia-fase-4/`; no procesa rásteres en cada consulta.

Ver [alcance, comandos, controles y resultados](../docs/Fase%204%20-%20busqueda%20regional%20terrestre.md). Todavía no hay orquestación distribuida ni publicación de releases transaccional; los archivos JSON individuales se escriben mediante reemplazo atómico y la API comprueba sus hashes.
