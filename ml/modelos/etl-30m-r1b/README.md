# Motor de similitud · modelo de la release `etl-30m-r1b`

Modelo ajustado del motor de similitud ML no supervisado (`motor-similitud-ml-v1`) que acompaña a la release del atlas `etl-30m-r1b` (activa en `gs://regolith-analogos-gabi0808/releases/atlas30/`).

| Archivo | Contenido |
|---|---|
| `model.joblib` | Modelo ajustado (155 KB): transformaciones cuantil-normal, covarianzas robustas por vista y GMM de regímenes |
| `model.json` | Informe legible del ajuste: vistas, features, población y grados de libertad |
| `jezero.json` | Respuesta del motor para Jezero con los pesos por defecto (top 100), con formato [`motor-busqueda-v1`](../../../specs/api/motor-busqueda-v1.schema.json). Sirve como ejemplo real para el frontend |
| `release-manifest.json` | Manifiesto de la release de la que sale este modelo |

## Procedencia

- **Ajustado:** 2026-11-15T06:48:25Z, en una VM de GCP (`europe-west3`), código `fuentes-de-datos@08f92fd`.
- **Población de ajuste:**
  - 1 459 164 ventanas terrestres rankables del barrido mundial, sin la cuenca reservada de Mojave;
  - muestra de 200 000 ventanas, semilla 20261114.
- **Hash del spec** (`specs/analysis/motor-similitud-ml-v1.json`): `4520fe49764a…`. El motor avisa si el spec local cambia.
- **SHA-256 de `model.joblib`:** `fd8d2327ce9e7c0f6ca56c64c1de5edbde1da5bba8c2e5a0b36874b21654c0ef`.
- **Verificación de la release:** 0 errores (`scripts/verificar_release.py`), con avisos esperados por las referencias lunares ausentes.

## Qué cubre

- **Vistas ajustadas:** `escabrosidad`, `forma_hipsometrica`, `organizacion` y `regimen_morfologico`.
- **Vistas sin ajustar** (aparecen como `not_fitted` y quedan fuera de la fusión con aviso):
  - `espectral` y `radar`: sin mediciones;
  - `termica`: 39 ventanas de fondo, por debajo del mínimo;
  - `entorno_superficial` y `emisividad_cmg`: capa global todavía sin muestrear.
- **Referencias:**
  - Jezero funciona.
  - Haworth y De Gerlache necesitan las ventanas lunares en el almacén.
  - Cualquier ventana terrestre puede servir de referencia por su `region_id`.
- **Estado:** `unsupervised_pending_blind_validation`. Mostradlo como experimental.

## Uso

```python
from pathlib import Path
from pipelines import similarity_ml as sim

engine = sim.SimilarityEngine.load(Path('ml/modelos/etl-30m-r1b/model.joblib'))
result = engine.search(Path('data/feature_store_v1'), 'jezero', limit=25)   # necesita el almacén
```

Para búsquedas en tiempo de consulta hace falta el almacén del bucket (`data/feature_store_v1`). Para servir los resultados precalculados basta con la release. Ver la [guía de backend](../../../docs/contratos/guia-backend.md).
