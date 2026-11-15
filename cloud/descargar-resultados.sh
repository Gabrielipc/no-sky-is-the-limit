#!/usr/bin/env bash
# Downloads to this machine only the light processed outputs of a cloud run (GCP or Azure):
#   - data/feature_store_v1/enrichment/  (global layer, selection, surface, bridges: tens of MB)
#   - data/feature_store_v1/manifests/   (provenance and batch records)
#   - docs/evidencia-*                   (summaries and evidence JSON)
# Heavy outputs are opt-in: WITH_BASE=1 (world sweep, ~0.5 GB), WITH_RELEASES=1,
# WITH_LAYERS=1 (global rasters, several GB). Raw products are never stored in the cloud.
#
#   PROVIDER=gcp   GCS_BUCKET=gs://mi-bucket                  bash cloud/descargar-resultados.sh
#   PROVIDER=azure STORAGE_ACCOUNT=micuenta CONTAINER=analogos bash cloud/descargar-resultados.sh
set -euo pipefail

PROVIDER="${PROVIDER:?Set PROVIDER=gcp or PROVIDER=azure}"
DEST="${DEST:-$(cd "$(dirname "$0")/.." && pwd)}"
PREFIXES=(data/feature_store_v1/enrichment data/feature_store_v1/manifests)
[[ "${WITH_BASE:-0}" == "1" ]] && PREFIXES+=(data/feature_store_v1/base)
[[ "${WITH_RELEASES:-0}" == "1" ]] && PREFIXES+=(releases)
[[ "${WITH_LAYERS:-0}" == "1" ]] && PREFIXES+=(data/global_layers)

case "$PROVIDER" in
gcp)
    GCS_BUCKET="${GCS_BUCKET:?Set GCS_BUCKET (gs://...)}"
    for p in "${PREFIXES[@]}"; do
        mkdir -p "$DEST/$p"
        echo "gcs: $p"
        gcloud storage rsync -r "$GCS_BUCKET/$p" "$DEST/$p" 2>/dev/null || echo "  (sin datos en $p)"
    done
    for evidence in $(gcloud storage ls "$GCS_BUCKET/docs/" 2>/dev/null | grep -o 'evidencia-[^/]*' | sort -u); do
        mkdir -p "$DEST/docs/$evidence"
        echo "gcs: docs/$evidence"
        gcloud storage rsync -r "$GCS_BUCKET/docs/$evidence" "$DEST/docs/$evidence"
    done
    ;;
azure)
    STORAGE_ACCOUNT="${STORAGE_ACCOUNT:?Set STORAGE_ACCOUNT}"
    CONTAINER="${CONTAINER:-analogos}"
    for p in "${PREFIXES[@]}" docs/evidencia-; do
        pattern="$p*"
        [[ "$p" == docs/evidencia- ]] || pattern="$p/*"
        echo "azure: $pattern"
        az storage blob download-batch --account-name "$STORAGE_ACCOUNT" --source "$CONTAINER" \
            --destination "$DEST" --pattern "$pattern" --auth-mode login --overwrite true --output none \
            || echo "  (sin datos en $p)"
    done
    ;;
*)
    echo "PROVIDER debe ser gcp o azure" >&2
    exit 1
    ;;
esac
echo "Listo en $DEST (la base del barrido solo con WITH_BASE=1)."
