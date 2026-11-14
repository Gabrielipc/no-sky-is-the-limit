#!/usr/bin/env bash
# Runs the ETL pipeline inside a GCP Spot VM using ephemeral scratch storage
# and syncs only the compact Feature Store + releases back to GCS.
#
# Outputs are uploaded every SYNC_INTERVAL_S seconds while the ETL runs, and the VM
# shutdown-script uploads them again on a Spot preemption, so a replacement VM resumes
# from the batches already in GCS (`completed_batch_ids` / `--skip-measured`).
set -euo pipefail

GCS_BUCKET="${GCS_BUCKET:?Set GCS_BUCKET (e.g. gs://mi-proyecto-analogos)}"
REPO_URL="${REPO_URL:-}"
REPO_BRANCH="${REPO_BRANCH:-main}"
WORKDIR="${WORKDIR:-/opt/analogos}"
SCRATCH_DIR="${SCRATCH_DIR:-/tmp/atlas30_cache}"
ETL_SCRIPT="${ETL_SCRIPT:-scripts/etl_pipeline.py}"
ETL_ARGS="${ETL_ARGS:-stream --scope world --stride 10000 --max-batches 50 --workers 8 --io-workers 16 --max-temp-gb 12}"
AUTO_DELETE="${AUTO_DELETE:-1}"
SYNC_INTERVAL_S="${SYNC_INTERVAL_S:-600}"
EARTHDATA_SECRET="${EARTHDATA_SECRET:-}"

export HOME="${HOME:-/root}"
export PATH="$HOME/.pixi/bin:$PATH"
export ATLAS_CACHE_DIR="$SCRATCH_DIR"
export ANALOGOS_FEATURE_STORE_DIR="$WORKDIR/data/feature_store_v1"
export GCS_BUCKET WORKDIR

log() { echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] $*"; }
metadata() { curl -sf -H "Metadata-Flavor: Google" "http://metadata.google.internal/computeMetadata/v1/$1"; }

SYNC_PID=""
cleanup_and_exit() {
    local code=$?
    if [[ -n "$SYNC_PID" ]]; then
        kill "$SYNC_PID" 2>/dev/null || true
        wait "$SYNC_PID" 2>/dev/null || true
    fi
    log "Final sync to ${GCS_BUCKET} (exit code: ${code})..."
    mkdir -p "$WORKDIR/data/feature_store_v1" "$WORKDIR/releases"
    SYNC_LOCK_WAIT_S=300 bash "$WORKDIR/cloud/gcp/sync-outputs.sh" || true
    gcloud storage cp /var/log/analogos-etl.log "${GCS_BUCKET}/logs/etl-$(hostname)-$(date -u +%Y%m%d-%H%M%S).log" || true

    if [[ "$AUTO_DELETE" == "1" ]]; then
        local name zone
        name=$(metadata instance/name || true)
        zone=$(metadata instance/zone | awk -F/ '{print $NF}' || true)
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
    export HOME="${HOME:-/root}"
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
log "Code revision: $(git rev-parse --short HEAD)"

if [[ -z "${EARTHDATA_TOKEN:-}" && -n "$EARTHDATA_SECRET" ]]; then
    log "Reading Earthdata token from Secret Manager (${EARTHDATA_SECRET})..."
    project=$(metadata project/project-id)
    EARTHDATA_TOKEN=$(gcloud secrets versions access latest --secret="$EARTHDATA_SECRET" --project="$project")
    export EARTHDATA_TOKEN
fi

log "Installing pixi environment (locked)..."
pixi install --locked

log "Verifying planetary CRS..."
pixi run check-env

if [[ -f "$WORKDIR/requirements-minerales.txt" ]]; then
    log "Preparing analysis environment (h5py)..."
    bash "$WORKDIR/scripts/preparar_minerales.sh"
fi

log "Restoring existing Feature Store / manifests from ${GCS_BUCKET} (if any)..."
mkdir -p "$WORKDIR/data/feature_store_v1" "$WORKDIR/releases"
gcloud storage rsync -r "${GCS_BUCKET}/data/feature_store_v1" "$WORKDIR/data/feature_store_v1" || true
gcloud storage rsync -r "${GCS_BUCKET}/releases" "$WORKDIR/releases" || true
for evidence in $(gcloud storage ls "${GCS_BUCKET}/docs/" 2>/dev/null | grep -o 'evidencia-[^/]*' | sort -u); do
    mkdir -p "$WORKDIR/docs/$evidence"
    gcloud storage rsync -r "${GCS_BUCKET}/docs/$evidence" "$WORKDIR/docs/$evidence" || true
done

if [[ "$SYNC_INTERVAL_S" -gt 0 ]]; then
    log "Periodic sync every ${SYNC_INTERVAL_S} s"
    (
        trap 'exit 0' TERM
        while sleep "$SYNC_INTERVAL_S"; do
            bash "$WORKDIR/cloud/gcp/sync-outputs.sh" || true
        done
    ) &
    SYNC_PID=$!
fi

log "Running ETL: ${ETL_SCRIPT} ${ETL_ARGS}"
# shellcheck disable=SC2086
bash "$WORKDIR/scripts/ejecutar_minerales.sh" "$ETL_SCRIPT" $ETL_ARGS
log "ETL finished successfully."
