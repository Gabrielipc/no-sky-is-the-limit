#!/usr/bin/env bash
# Merges what an Azure run wrote (Feature Store, evidence, or the Moon/Mars mirror) into the GCS bucket.
#
# Two jobs that touch different files (for example `etl_referencias.py espejo --body Moon` on GCP and `--body Mars` on
# Azure) leave nothing to merge but a copy without overwriting: nothing already in GCS is replaced.
# The outputs are small (features, evidence, the ~0.5 GB Mars mirror), so they go through a local temporary folder.
# For another set of prefixes: PREFIXES="data/raw/espejo docs/evidencia-espejo".
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
    # "No blobs" and "the download failed" are different: a transient error must not look like an empty prefix.
    blobs="$(az storage blob list --account-name "$STORAGE_ACCOUNT" --auth-mode login -c "$CONTAINER" --prefix "${prefix}/" \
        --num-results 1 --query 'length(@)' -o tsv --only-show-errors)" || { log "ERROR: no se pudo listar ${prefix}"; exit 1; }
    if [[ "${blobs:-0}" == "0" ]]; then log "Sin objetos en ${prefix}: se omite"; continue; fi
    ok=0
    for attempt in 1 2 3; do
        if az storage blob download-batch --account-name "$STORAGE_ACCOUNT" --auth-mode login --source "$CONTAINER" \
            --pattern "${prefix}/*" --destination "$TMP" --overwrite false --only-show-errors; then ok=1; break; fi
        log "descarga de ${prefix} falló (intento ${attempt}/3)"
        sleep $((attempt * 5))
    done
    [[ "$ok" == 1 ]] || { log "ERROR: ${prefix} no se pudo descargar; no se copió nada de él"; exit 1; }
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
