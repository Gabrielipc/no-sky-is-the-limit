#!/usr/bin/env bash
# Merges the Feature Store written by an Azure ETL run into the one in GCS.
#
# Two ETL jobs of different bodies (for example `etl_referencias.py luna` on GCP and `marte` on Azure) write
# different store partitions, so the merge is a copy without overwriting: nothing already in GCS is replaced.
# The outputs are small (the store holds features, not rasters), so they go through a local temporary folder.
#
#   STORAGE_ACCOUNT=miprueba CONTAINER=analogos GCS_BUCKET=gs://mi-bucket bash cloud/unir-almacen-azure-gcs.sh
#
# DRY_RUN=1 lists what would be copied and changes nothing.
set -euo pipefail

STORAGE_ACCOUNT="${STORAGE_ACCOUNT:?Set STORAGE_ACCOUNT}"
CONTAINER="${CONTAINER:-analogos}"
GCS_BUCKET="${GCS_BUCKET:?Set GCS_BUCKET (e.g. gs://mi-bucket-analogos)}"
PREFIXES="${PREFIXES:-data/feature_store_v1 docs releases}"
DRY_RUN="${DRY_RUN:-0}"
# Not data: macOS AppleDouble files and the store's staging folders.
EXCLUDE='(.*/)?(tmp[^/]*|\.stream_tmp|duckdb_spill)(/.*)?$|(.*/)?\._.*|.*\.part(\.tif)?$'

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
log() { echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] unir: $*"; }

for prefix in $PREFIXES; do
    log "Descargando ${prefix} de Azure (${STORAGE_ACCOUNT}/${CONTAINER})..."
    mkdir -p "$TMP/$prefix"
    az storage blob download-batch --account-name "$STORAGE_ACCOUNT" --auth-mode login --source "$CONTAINER" \
        --pattern "${prefix}/*" --destination "$TMP" --overwrite false --only-show-errors || {
        log "Sin objetos en ${prefix}: se omite"; continue; }
    find "$TMP/$prefix" -name '._*' -delete 2>/dev/null || true
    [[ -d "$TMP/$prefix" ]] || continue
    log "$(find "$TMP/$prefix" -type f | wc -l | tr -d ' ') archivos en ${prefix}"
    if [[ "$DRY_RUN" == "1" ]]; then
        gcloud storage rsync -r --no-clobber --dry-run --exclude="$EXCLUDE" "$TMP/$prefix" "${GCS_BUCKET}/${prefix}"
    else
        gcloud storage rsync -r --no-clobber --exclude="$EXCLUDE" "$TMP/$prefix" "${GCS_BUCKET}/${prefix}"
    fi
done
log "Listo${DRY_RUN:+ (DRY_RUN=${DRY_RUN})}"
