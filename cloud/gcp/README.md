# Migración del ETL a Google Cloud (Spot VM efímera)

Esta carpeta contiene la configuración mínima para ejecutar los pipelines de recolección y ETL en una **VM Spot efímera de Google Cloud**, evitando la latencia y consumo de ancho de banda local sin pagar servidores encendidos 24/7 ni DBUs de Databricks.

## Qué incluye

- `Dockerfile`: imagen reproducible basada en `pixi.toml` + `requirements-minerales.txt` (`h5py`, instalado mediante `scripts/preparar_minerales.sh` y ejecutado con `scripts/ejecutar_minerales.sh`) con verificación de CRS planetarios (`IAU_2015:49900` y `IAU_2015:30100`). Útil si luego quieres usar **Cloud Run Jobs** o **Azure Container Apps**.
- `run-etl-spot.sh`: script que corre dentro de la VM, instala `pixi` y `.tools/minerales` (`h5py`), restaura `feature_store_v1`, `releases/` y `docs/evidencia-puentes-laser-radar/` desde GCS, ejecuta `ETL_SCRIPT` (por defecto `scripts/etl_pipeline.py`) usando caché temporal en `/tmp/atlas30_cache`, sube los resultados a GCS y **auto-elimina la VM** al finalizar (`AUTO_DELETE=1`).
- `launch-spot.sh`: script para lanzar la VM Spot desde tu Mac usando `gcloud`.
- `sync-outputs.sh`: sube a GCS el Feature Store, `releases/` y `docs/evidencia-*`. Se ejecuta cada `SYNC_INTERVAL_S` segundos (600 por defecto; `0` lo desactiva), desde el `shutdown-script` de la VM cuando Google la interrumpe (≈30 s de aviso) y una última vez al terminar. Excluye los directorios temporales `tmp*` donde el almacén prepara cada delta antes de moverlo, así que en GCS solo quedan lotes completos y la VM siguiente retoma con `completed_batch_ids` o `--skip-measured`.

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
