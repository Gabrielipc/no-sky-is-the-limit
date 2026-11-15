# Migración del ETL a Google Cloud (Spot VM efímera)

Esta carpeta contiene la configuración mínima para ejecutar los pipelines de recolección y ETL en una **VM Spot efímera de Google Cloud**, evitando la latencia y consumo de ancho de banda local sin pagar servidores encendidos 24/7 ni DBUs de Databricks.

## Qué incluye

- `Dockerfile`: imagen reproducible basada en `pixi.toml` + `requirements-minerales.txt` (`h5py`, instalado mediante `scripts/preparar_minerales.sh` y ejecutado con `scripts/ejecutar_minerales.sh`) con verificación de CRS planetarios (`IAU_2015:49900` y `IAU_2015:30100`). Útil si luego quieres usar **Cloud Run Jobs** o **Azure Container Apps**.
- `run-etl-spot.sh`: script que corre dentro de la VM, instala `pixi` y `.tools/minerales` (`h5py`), restaura `feature_store_v1`, `releases/` y `docs/evidencia-puentes-laser-radar/` desde GCS, ejecuta `ETL_SCRIPT` (por defecto `scripts/etl_pipeline.py`) usando caché temporal en `/tmp/atlas30_cache`, sube los resultados a GCS y **auto-elimina la VM** al finalizar (`AUTO_DELETE=1`).
- `launch-spot.sh`: script para lanzar la VM Spot desde tu Mac usando `gcloud`.
- `sync-outputs.sh`: sube a GCS el Feature Store, `releases/`, `data/global_layers/` y `docs/evidencia-*`. Se ejecuta cada `SYNC_INTERVAL_S` segundos (600 por defecto; `0` lo desactiva), desde el `shutdown-script` de la VM cuando Google la interrumpe (≈30 s de aviso) y una última vez al terminar. Excluye los directorios temporales `tmp*` donde el almacén prepara cada delta antes de moverlo, así que en GCS solo quedan lotes completos y la VM siguiente retoma con `completed_batch_ids` o `--skip-measured`.

## Seguridad y reproducibilidad

- **Token de Earthdata en Secret Manager.** `launch-spot.sh` nunca escribe el token en los metadatos de la VM. Si `EARTHDATA_TOKEN` está definido en tu Mac, lo guarda (o agrega una versión nueva) en el secreto `EARTHDATA_SECRET` (`earthdata-token` por defecto), da a la cuenta de servicio de la VM el rol `roles/secretmanager.secretAccessor` sobre ese secreto y pasa a la VM solo el nombre. La VM lo lee al arrancar con `gcloud secrets versions access`.
- **Entorno bloqueado.** La VM ejecuta `pixi install --locked`, así que usa exactamente las versiones de `pixi.lock` probadas en local, y registra en el log el commit que ejecuta.
- **Sube los commits antes de lanzar.** La VM clona `REPO_BRANCH` desde `REPO_URL`; lo que no esté en GitHub no se ejecuta.

## Prerrequisitos

1. Tener `gcloud` CLI instalado y autenticado (`gcloud auth login`).
2. Tener el repositorio accesible por Git (`REPO_URL`) o subirlo a un repo privado/público.
3. No guardar credenciales ni `EARTHDATA_TOKEN` en el repositorio.

## Uso rápido (prueba piloto)

```bash
export PROJECT_ID="tu-proyecto-gcp"
export GCS_BUCKET="gs://tu-bucket-analogos"
export REPO_URL="https://github.com/tu-usuario/tu-repo.git"

# Opcional: si usas fuentes NASA Earthdata (EMIT / HLS / ICESat-2)
# export EARTHDATA_TOKEN="tu_token_aqui"   # se guarda en Secret Manager, no en la VM

# Prueba rápida con 5 lotes piloto
ETL_ARGS="stream --scope pilot --stride 10000 --max-batches 5 --workers 8 --io-workers 16 --max-temp-gb 8" \
  bash cloud/gcp/launch-spot.sh
```

## Puentes láser y de radar (`scripts/etl_puentes.py`)

Dado que `*.parquet` está excluido de Git, sube primero el `FeatureStore` local (incluidos los deltas ya medidos) al bucket para que `etl_puentes.py` pueda seleccionar las candidatas de Jezero y Haworth y omitir las ventanas ya medidas:

```bash
gcloud storage rsync -r ./data/feature_store_v1 "$GCS_BUCKET/data/feature_store_v1"
gcloud storage rsync -r ./docs/evidencia-puentes-laser-radar "$GCS_BUCKET/docs/evidencia-puentes-laser-radar"
```

Para correr **ICESat-2 ATL08** en `us-west1-a` (Oregón, menor latencia hacia NASA Earthdata / Harmony en `us-west-2`):

```bash
ZONE="us-west1-a" \
ETL_SCRIPT="scripts/etl_puentes.py" \
ETL_ARGS="icesat2 --skip-measured --workers 16" \
  bash cloud/gcp/launch-spot.sh
```

> **Nota sobre `control-v1:haughton-devon`:** el registro actual del almacén proviene de una prueba previa con `--max-granules 6` (6 de 120 gránulos en CMR, con resultado `no_swath_coverage`). Como `--skip-measured` omite cualquier fila distinta de `on_demand_fetchable`, vuelve a medir Devon con el catálogo completo ejecutando después (o en otra pasada):
> `ETL_SCRIPT="scripts/etl_puentes.py" ETL_ARGS="icesat2 --controls-only --site haughton-devon --workers 16" ZONE="us-west1-a" bash cloud/gcp/launch-spot.sh`

Para generar el resumen láser vs. DEM en la misma evidencia o correr `rcm` en controles:

```bash
ZONE="us-west1-a" \
ETL_SCRIPT="scripts/etl_puentes.py" \
ETL_ARGS="resumen" \
  bash cloud/gcp/launch-spot.sh
```

## Dimensiones de superficie e inercia térmica aparente (`scripts/etl_superficie.py`)

Todas las fuentes salvo el permafrost (CEDA, público) están en NASA Earthdata (`us-west-2`), así que conviene `us-west1-a`. Antes, autoriza la aplicación de GES DISC en tu perfil de Earthdata (sin ese paso IMERG responde `403 EULA Acceptance Failure`). MODIS se descarga por gránulos HDF4 completos que se borran después de leerlos, así que la ATI es la dimensión más pesada (≈ 6 GB por tesela y año):

```bash
ZONE="us-west1-a" \
ETL_SCRIPT="scripts/etl_superficie.py" \
ETL_ARGS="--skip-measured --batch-size 10 --workers 16" \
  bash cloud/gcp/launch-spot.sh

# Solo algunas dimensiones (las demás conservan su valor guardado):
ETL_ARGS="--dimension apparent_thermal_inertia --ati-year 2023 --skip-measured --workers 16"
```

## Mitigación del sesgo de selección topográfica

Implementa el [plan](../../docs/01-vigentes/etapa-actual-armonizacion/Plan%20de%20mitigacion%20del%20sesgo%20de%20seleccion%20topografica.md). Requiere el barrido mundial ya en el bucket (`base/` con la identidad actual). Todo corre en `us-west1-a`, junto a los DAAC de Earthdata. El orden es:

**1. Capa global barata (fase A).** `build` reduce cada producto a un ráster global en `data/global_layers/`, que también se sube al bucket. Necesita unos 30 GB de transferencia y unas horas. La ATI mantiene 12 meses de LST y albedo en memoria (~6 GB), así que conviene `e2-standard-8` o mayor. Una capa con `layer.json` no se reconstruye, y si un producto falla (por ejemplo IMERG sin autorización de GES DISC) los demás siguen:

```bash
ZONE="us-west1-a" DISK_SIZE_GB=100 \
ETL_SCRIPT="scripts/etl_capa_global.py" ETL_ARGS="build --workers 8" \
  bash cloud/gcp/launch-spot.sh

# Cuando estén las capas (minutos): muestrear todas las ventanas -> enrichment_global
ZONE="us-west1-a" ETL_SCRIPT="scripts/etl_capa_global.py" ETL_ARGS="sample" \
  bash cloud/gcp/launch-spot.sh
```

Para construir una sola capa: `ETL_ARGS="build --layer emissivity"`. Para ver qué hay construido: `ETL_ARGS="status"`.

**2. Muestra de fondo y listas cortas (fases B y C).** Se enriquecen igual que las candidatas, y cada ventana queda registrada en `enrichment_selection` con su motivo:

```bash
# Muestra estratificada (todas las dimensiones menos la ATI fina) + ATI fina por conglomerados
ZONE="us-west1-a" ETL_SCRIPT="scripts/etl_superficie.py" \
ETL_ARGS="--background-sample 1000 --background-cluster-tiles 40 --background-per-tile 5 --skip-measured --workers 16" \
  bash cloud/gcp/launch-spot.sh

# Listas cortas por vista, repartidas según los pesos de la consulta (topografía en 0)
ETL_ARGS="--no-topographic-candidates --retrieval-total 60 --weight escabrosidad=0 --weight forma_hipsometrica=0 \
--weight organizacion=0 --weight regimen_morfologico=0 --weight termica=0.5 --weight entorno_superficial=0.5 \
--target termica:ati_cmg_per_k=0.7 --skip-measured --workers 16"

# Puente láser sobre la misma población de fondo
ETL_SCRIPT="scripts/etl_puentes.py" ETL_ARGS="icesat2 --background-sample 300 --skip-measured"
```

**3. Ajuste y recall (fase D), en local.** El modelo se guarda en `data/features/` y no se sube al bucket, así que conviene traer el almacén y ajustar en tu Mac (unos 40 s):

```bash
gcloud storage rsync -r "$GCS_BUCKET/data/feature_store_v1" ./data/feature_store_v1
pixi run python scripts/motor_similitud.py fit
bash scripts/ejecutar_minerales.sh scripts/motor_similitud.py recall --reference jezero \
  --retriever topografica=20 --retriever entorno=20 --retriever espectral=20
```

`fit` registra en cada vista puente su población de ajuste: `background_weighted`, o `biased_enriched_only` si faltan ventanas de fondo. `search` avisa cuando una vista con mucho peso cubre menos del 1 % de las candidatas. `recall` escribe `docs/evidencia-sesgo-seleccion/recall.json`.

## Elección de región para minimizar latencia y costo

- **`europe-west3-a` (Fráncfort, por defecto):** ideal para `atlas30` / `etl_pipeline.py` (Copernicus GLO-30, ESA WorldCover y JRC Surface Water están en Europa / `eu-central-1`).
- **`us-west1-a` (Oregón):** ideal para pipelines con **NASA Earthdata / Harmony / USGS 3DEP** (`us-west-2`), además de tener tarifas Tier-1 muy bajas.

## Descargar resultados a tu Mac

Una vez que la VM termine y se auto-elimine, sincroniza el Feature Store (~475 MB), las publicaciones (~5 MB) y la evidencia de puentes:

```bash
gcloud storage rsync -r "$GCS_BUCKET/data/feature_store_v1" ./data/feature_store_v1
gcloud storage rsync -r "$GCS_BUCKET/releases" ./releases
gcloud storage rsync -r "$GCS_BUCKET/docs/evidencia-puentes-laser-radar" ./docs/evidencia-puentes-laser-radar
```

## Variables de entorno soportadas por los pipelines

- `ATLAS_CACHE_DIR`: carpeta para caché temporal de rasters (por defecto `data/raw/atlas30`).
- `ATLAS_MANIFESTS_DIR`: carpeta para manifests de assets (por defecto `data/manifests/atlas30`).
- `ANALOGOS_FEATURE_STORE_DIR`: ruta del Feature Store Parquet/DuckDB (por defecto `data/feature_store_v1`).
- `ANALOGOS_GLOBAL_LAYERS_DIR`: rásteres de la capa global de superficie (por defecto `data/global_layers`; en la VM se restaura del bucket solo para `etl_capa_global.py`).
