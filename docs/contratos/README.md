# Contratos de datos para backend y frontend

Fecha: 15 de noviembre de 2026. Guías: [backend](guia-backend.md) · [frontend](guia-frontend.md) · [primera release](primera-release.md).

Para comprobar una release contra estos contratos: `python scripts/verificar_release.py releases/atlas30/<versión>`.

## Cómo fluyen los datos

```
ETL (GCP)  ──►  almacén (features_unified, interno)  ──►  release versionada  ──►  backend /api  ──►  frontend
                                     │                         ▲
                                     └──► motor de similitud ──┘  (resultados precalculados en la release)
                                     └──► motor en tiempo de consulta (pesos personalizados, opcional)
```

El backend no lee el almacén del ETL. Lee **releases**: carpetas inmutables y versionadas que el ETL publica. Una release contiene los datos ya procesados de cada ventana y, opcionalmente, los resultados del motor de similitud para las referencias con nombre. El backend sirve esos archivos y el frontend los presenta.

## Los tres contratos

| Contrato | Archivo legible por máquina | Estabilidad | Quién lo produce | Quién lo consume |
|---|---|---|---|---|
| **Release del atlas** `atlas30-release-v1` | [`specs/api/release-atlas30-v1.json`](../../specs/api/release-atlas30-v1.json) | **Estable.** Solo se añaden columnas | `pipelines/etl_publish.py` | `backend/app/atlas_store.py` → `/api/atlas/*` |
| **Respuesta del motor** `motor-busqueda-v1` | [`specs/api/motor-busqueda-v1.schema.json`](../../specs/api/motor-busqueda-v1.schema.json) (JSON Schema) | **Estructura estable.** Pesos y estado del motor pueden cambiar con la calibración | `SimilarityEngine.search` | `similarity/<referencia>.json` en la release, o un endpoint del motor |
| **Vista del almacén** `features-unified-v1` | [`specs/api/features-unified-v1.json`](../../specs/api/features-unified-v1.json) | Interna del ETL | `pipelines/etl_contract.py` | Motor y publicación (no el backend) |

Los dos archivos de columnas se **generan del código** con `scripts/exportar_contratos.py`, y `tests/test_contratos.py` falla si quedan desactualizados. La salida real del motor se valida contra el JSON Schema en los tests.

### Release del atlas (`releases/atlas30/<versión>/`)

| Archivo | Contenido |
|---|---|
| `manifest.json` | `release_contract`, `version`, `counts`, `eligibility_counts`, `cover_counts`, `coverage_status`, `profile` (referencia de Jezero), `normalization`, `similarity` (opcional) |
| `windows/windows.parquet` | Una fila por ventana terrestre: identidad, coordenadas, estado QA, topografía, forma, cobertura, elegibilidad y **capa global de superficie** (`*_cmg` y `*_cmg_status`). Columnas, tipos, unidades y rangos en el contrato |
| `sources.json` | Procedencia de cada activo: producto, DOI, versión, periodo, huella (SHA-256/ETag) |
| `batches.json` | Lotes del barrido |
| `similarity/<referencia>.json` | Opcional: respuesta del motor para `jezero`, `haworth-fondo` y `de-gerlache-cresta`, con sus pesos por defecto (perfil árido para Marte, polar para la Luna) |

La clave común es `region_id`: es la misma en la release, en las respuestas del motor y en `/api/atlas/candidates/{region_id}`.

### Respuesta del motor

Un objeto con:
- **la referencia**: sus valores y su percentil terrestre;
- **los pesos**: los pedidos y los efectivos;
- **el informe por vista**: estado, cobertura y población de ajuste;
- **los avisos**;
- **`results`**: ventanas ordenadas, cada una con `score` (menor = más parecida), intervalo `[score_low, score_high]`, `coverage`, `missing_views`, y por vista la distancia y el aporte de cada feature.

Responde a la duda de si el motor «entrega un JSON que el backend manda como response»: hay dos modos, y no son excluyentes.

1. **Precalculado (recomendado para empezar).** El ETL ejecuta el motor al publicar y deja `similarity/<referencia>.json` en la release. El backend lo sirve como cualquier otro dato procesado, sin cargar el modelo.
2. **En tiempo de consulta (pesos personalizados).** El backend carga el modelo una vez y llama a `engine.search`. Necesita el almacén y el modelo en el servidor, y tarda segundos. Ver la [guía de backend](guia-backend.md#2-motor-en-tiempo-de-consulta-pesos-personalizados).

En ambos casos el formato es el mismo (`motor-busqueda-v1`). El backend puede devolverlo tal cual o envolverlo en su propio DTO.

## Reglas de cambio

- **Aditivo:** las columnas y los campos nuevos pueden aparecer; los existentes no cambian de nombre ni de significado. Un cambio incompatible exige `atlas30-release-v2` o `motor-busqueda-v2`.
- **Releases antiguas:** las anteriores a este contrato (p. ej. `mundial-30m-r1`) no tienen las columnas nuevas. El backend debe tratar una columna ausente como nula.
- **Para regenerar los contratos** tras cambiar el ETL:
  ```bash
  bash scripts/ejecutar_minerales.sh scripts/exportar_contratos.py
  ```

## Qué está estable y qué falta

| Pieza | Estado |
|---|---|
| Columnas de topografía, cobertura y elegibilidad | Estables y con datos (el barrido mundial está en curso) |
| Columnas de forma (`hypsometric_integral`, `elevation_skew_p95_p05`, ...) | Estables; con datos en las ventanas del barrido nuevo |
| Capa global (`*_cmg`) | Columnas estables; **todavía sin valores** (`*_cmg_status = on_demand_fetchable`) hasta construir y muestrear las capas |
| Respuesta del motor | Estructura estable; motor `unsupervised_pending_blind_validation`: mostrarlo como experimental |
| Vista espectral del motor | Aparece como `not_fitted` hasta conectar el puente espectral al almacén |
| `similarity/*.json` en la release | Disponible al publicar con `similarity_model` |
