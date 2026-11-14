#!/usr/bin/env bash
# Runs the ETL pipeline inside a GCP Spot VM using ephemeral scratch storage
# and syncs only the compact Feature Store + releases back to GCS.
set -euo pipefail

GCS_BUCKET="${GCS_BUCKET:?Set GCS_BUCKET (e.g. gs://mi-proyecto-analogos)}"
REPO_URL="${REPO_URL:-}"
REPO_BRANCH="${REPO_BRANCH:-main}"
WORKDIR="${WORKDIR:-/opt/analogos}"
SCRATCH_DIR="${SCRATCH_DIR:-/tmp/atlas30_cache}"
ETL_SCRIPT="${ETL_SCRIPT:-scripts/etl_pipeline.py}"
ETL_ARGS="${ETL_ARGS:-stream --scope world --stride 10000 --max-batches 50 --workers 8 --io-workers 16 --max-temp-gb 12}"
AUTO_DELETE="${AUTO_DELETE:-1}"

export PATH="$HOME/.pixi/bin:$PATH"
export ATLAS_CACHE_DIR="$SCRATCH_DIR"
export ANALOGOS_FEATURE_STORE_DIR="$WORKDIR/data/feature_store_v1"

log() { echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] $*"; }

cleanup_and_exit() {
    local code=$?
    log "Syncing outputs to ${GCS_BUCKET} (exit code: ${code})..."
    mkdir -p "$WORKDIR/data/feature_store_v1" "$WORKDIR/releases"
    gcloud storage rsync -r "$WORKDIR/data/feature_store_v1" "${GCS_BUCKET}/data/feature_store_v1" || true
    gcloud storage rsync -r "$WORKDIR/releases" "${GCS_BUCKET}/releases" || true
    if [[ -d "$WORKDIR/docs/evidencia-puentes-laser-radar" ]]; then
        gcloud storage rsync -r "$WORKDIR/docs/evidencia-puentes-laser-radar" "${GCS_BUCKET}/docs/evidencia-puentes-laser-radar" || true
    fi
    gcloud storage cp /var/log/analogos-etl.log "${GCS_BUCKET}/logs/etl-$(hostname)-$(date -u +%Y%m%d-%H%M%S).log" || true

    if [[ "$AUTO_DELETE" == "1" ]]; then
        local name zone
        name=$(curl -sf -H "Metadata-Flavor: Google" http://metadata.google.internal/computeMetadata/v1/instance/name || true)
        zone=$(curl -sf -H "Metadata-Flavor: Google" http://metadata.google.internal/computeMetadata/v1/instance/zone | awk -F/ '{print $NF}' || true)
        if [[ -n "$name" && -n "$zone" ]]; then
            log "Auto-deleting Spot VM ${name} in ${zone}..."
            gcloud compute instances delete "$name" --zone="$zone" --quiet || true
        fi
    fi
    exit "$code"
}
trap cleanup_and_exit EXIT

mkdir -p "$SCRATCH_DIR" "$WORKDIR"

if ! command -v pixi >/dev/null 2>&1; then
    log "Installing pixi..."
    curl -fsSL https://pixi.sh/install.sh | bash
    export PATH="$HOME/.pixi/bin:$PATH"
fi

if [[ ! -d "$WORKDIR/.git" ]]; then
    if [[ -z "$REPO_URL" ]]; then
        echo "ERROR: REPO_URL is required when $WORKDIR is not already checked out." >&2
        exit 1
    fi
    log "Cloning $REPO_URL ($REPO_BRANCH)..."
    git clone --depth 1 --branch "$REPO_BRANCH" "$REPO_URL" "$WORKDIR"
fi

cd "$WORKDIR"

log "Installing pixi environment..."
pixi install

log "Verifying planetary CRS..."
pixi run check-env

if [[ -f "$WORKDIR/requirements-minerales.txt" ]]; then
    log "Preparing analysis environment (h5py)..."
    bash "$WORKDIR/scripts/preparar_minerales.sh"
fi

log "Restoring existing Feature Store / manifests from ${GCS_BUCKET} (if any)..."
mkdir -p "$WORKDIR/data/feature_store_v1" "$WORKDIR/releases" "$WORKDIR/docs/evidencia-puentes-laser-radar"
gcloud storage rsync -r "${GCS_BUCKET}/data/feature_store_v1" "$WORKDIR/data/feature_store_v1" || true
gcloud storage rsync -r "${GCS_BUCKET}/releases" "$WORKDIR/releases" || true
gcloud storage rsync -r "${GCS_BUCKET}/docs/evidencia-puentes-laser-radar" "$WORKDIR/docs/evidencia-puentes-laser-radar" || true

log "Running ETL: ${ETL_SCRIPT} ${ETL_ARGS}"
# shellcheck disable=SC2086
bash "$WORKDIR/scripts/ejecutar_minerales.sh" "$ETL_SCRIPT" $ETL_ARGS
log "ETL finished successfully."
