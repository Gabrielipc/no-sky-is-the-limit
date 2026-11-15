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
# The store has ~65k small files (one base part, batch record and source manifest per batch) and a
# per-object rsync takes most of an hour. Each run therefore leaves a single-object snapshot at the
# end, and the next run restores it in seconds and only rsyncs what is newer.
STORE_SNAPSHOT="${STORE_SNAPSHOT:-${GCS_BUCKET}/snapshots/feature_store_v1.tar}"
WRITE_SNAPSHOT="${WRITE_SNAPSHOT:-1}"

export HOME="${HOME:-/root}"
export PATH="$HOME/.pixi/bin:$PATH"
# Many small objects: transfers are latency bound, so use many parallel requests.
export CLOUDSDK_STORAGE_PROCESS_COUNT="${CLOUDSDK_STORAGE_PROCESS_COUNT:-$(nproc)}"
export CLOUDSDK_STORAGE_THREAD_COUNT="${CLOUDSDK_STORAGE_THREAD_COUNT:-32}"
export ATLAS_CACHE_DIR="$SCRATCH_DIR"
export ANALOGOS_FEATURE_STORE_DIR="$WORKDIR/data/feature_store_v1"
export ANALOGOS_GLOBAL_LAYERS_DIR="$WORKDIR/data/global_layers"
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
    if [[ "$WRITE_SNAPSHOT" == "1" && -d "$WORKDIR/data/feature_store_v1/base" ]]; then
        log "Writing store snapshot ${STORE_SNAPSHOT}..."
        tar -C "$WORKDIR/data" --exclude='duckdb_spill' --exclude='.stream_tmp' --exclude='tmp*' --exclude='._*' --format=gnu -cf - feature_store_v1 \
            | gcloud storage cp - "${STORE_SNAPSHOT}.part-$(hostname)" \
            && gcloud storage mv "${STORE_SNAPSHOT}.part-$(hostname)" "$STORE_SNAPSHOT" || log "WARNING: snapshot not written"
    fi
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
if gcloud storage ls "$STORE_SNAPSHOT" >/dev/null 2>&1; then
    log "Restoring store snapshot ${STORE_SNAPSHOT} (single object)..."
    # Archives made on macOS carry com.apple.* extended headers: GNU tar warns once per file and the
    # serial console (~70 lines/s) then paces the whole extraction. Drop those warnings.
    gcloud storage cat "$STORE_SNAPSHOT" | tar -x --warning=no-unknown-keyword -C "$WORKDIR/data" 2>/dev/null \
        || log "WARNING: snapshot not restored"
fi
log "Completing the store with files newer than the snapshot..."
# gcloud matches --exclude from the start of the relative path: keep the leading `(.*/)?`.
APPLEDOUBLE='(.*/)?\._.*'
gcloud storage rsync -r --no-clobber --exclude="$APPLEDOUBLE" "${GCS_BUCKET}/data/feature_store_v1" "$WORKDIR/data/feature_store_v1" 2>&1 \
    | grep -v '^Copying\|^\.Copying' || true
gcloud storage rsync -r --exclude="$APPLEDOUBLE" "${GCS_BUCKET}/data/feature_store_v1/enrichment" "$WORKDIR/data/feature_store_v1/enrichment" 2>&1 \
    | grep -v '^Copying\|^\.Copying' || true
# macOS archives carry AppleDouble `._*` files next to every file (and a faulty run uploaded some to the
# bucket); DuckDB would read `._part_*.parquet` as Parquet. They hold no data: drop them all.
find "$WORKDIR/data/feature_store_v1" -name '._*' -delete
gcloud storage rsync -r "${GCS_BUCKET}/releases" "$WORKDIR/releases" || true
for evidence in $(gcloud storage ls "${GCS_BUCKET}/docs/" 2>/dev/null | grep -o 'evidencia-[^/]*' | sort -u); do
    mkdir -p "$WORKDIR/docs/$evidence"
    gcloud storage rsync -r "${GCS_BUCKET}/docs/$evidence" "$WORKDIR/docs/$evidence" || true
done
# Global surface layers (several GB with AG1km) are only needed to build or sample them.
if [[ "$ETL_SCRIPT" == *"etl_capa_global.py"* ]]; then
    log "Restoring global surface layers from ${GCS_BUCKET} (if any)..."
    mkdir -p "$ANALOGOS_GLOBAL_LAYERS_DIR"
    gcloud storage rsync -r "${GCS_BUCKET}/data/global_layers" "$ANALOGOS_GLOBAL_LAYERS_DIR" || true
fi

if [[ "$SYNC_INTERVAL_S" -gt 0 ]]; then
    log "Periodic sync every ${SYNC_INTERVAL_S} s"
    # `sleep` runs in the background and is awaited: bash defers a TERM trap until the
    # foreground child exits, so a foreground `sleep` would stall the final sync for up to
    # SYNC_INTERVAL_S. `wait` is interrupted at once; an upload in progress is let finish.
    (
        sleep_pid=""
        trap '[[ -n "$sleep_pid" ]] && kill "$sleep_pid" 2>/dev/null; exit 0' TERM
        while true; do
            sleep "$SYNC_INTERVAL_S" &
            sleep_pid=$!
            wait "$sleep_pid"
            sleep_pid=""
            bash "$WORKDIR/cloud/gcp/sync-outputs.sh" || true
        done
    ) &
    SYNC_PID=$!
fi

if [[ "$ETL_SCRIPT" == *"etl_pipeline.py"* || "$ETL_SCRIPT" == *"atlas30.py"* ]]; then
    log "Ensuring atlas30 inventory (land mask + GLO-30 tile list)..."
    pixi run python "$WORKDIR/scripts/atlas30.py" inventory
fi

# The store keeps one small Parquet per delta (tens of thousands of manifests); publish reads them
# all in one query and DuckDB needs a descriptor per file. Raise the soft limit as far as the hard one allows.
for limit in 1048576 524288 262144 65536 "$(ulimit -Hn)"; do ulimit -n "$limit" 2>/dev/null && break; done
log "Open-files limit: $(ulimit -n)"

log "Running ETL: ${ETL_SCRIPT} ${ETL_ARGS}"
# shellcheck disable=SC2086
bash "$WORKDIR/scripts/ejecutar_minerales.sh" "$ETL_SCRIPT" $ETL_ARGS
log "ETL finished successfully."
