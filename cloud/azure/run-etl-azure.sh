#!/usr/bin/env bash
# Runs an ETL inside an ephemeral Azure Spot VM (same method as cloud/gcp/run-etl-spot.sh):
# scratch storage on the VM, light outputs synced to Azure Blob every SYNC_INTERVAL_S seconds,
# on a Spot eviction notice (Scheduled Events, ~30 s) and once more at the end, then the run's
# resource group (VM, disk, IP) deletes itself. Credentials come from a user-assigned managed
# identity: the Earthdata token is read from Key Vault, never from the VM metadata.
set -euo pipefail

STORAGE_ACCOUNT="${STORAGE_ACCOUNT:?Set STORAGE_ACCOUNT}"
CONTAINER="${CONTAINER:-analogos}"
IDENTITY_CLIENT_ID="${IDENTITY_CLIENT_ID:?Set IDENTITY_CLIENT_ID (user-assigned managed identity)}"
RUN_RESOURCE_GROUP="${RUN_RESOURCE_GROUP:-}"
KEYVAULT="${KEYVAULT:-}"
EARTHDATA_SECRET="${EARTHDATA_SECRET:-earthdata-token}"
REPO_URL="${REPO_URL:-}"
REPO_BRANCH="${REPO_BRANCH:-main}"
WORKDIR="${WORKDIR:-/opt/analogos}"
SCRATCH_DIR="${SCRATCH_DIR:-/mnt/analogos_cache}"
ETL_SCRIPT="${ETL_SCRIPT:-scripts/etl_secuencia.py}"
ETL_ARGS="${ETL_ARGS:-}"
AUTO_DELETE="${AUTO_DELETE:-1}"
SYNC_INTERVAL_S="${SYNC_INTERVAL_S:-600}"
LOG_FILE="${LOG_FILE:-/var/log/analogos-etl.log}"

export HOME="${HOME:-/root}"
export PATH="$HOME/.pixi/bin:/usr/local/bin:$PATH"
export ATLAS_CACHE_DIR="$SCRATCH_DIR"
export ANALOGOS_FEATURE_STORE_DIR="$WORKDIR/data/feature_store_v1"
export ANALOGOS_GLOBAL_LAYERS_DIR="$WORKDIR/data/global_layers"
export BLOB_URL="https://${STORAGE_ACCOUNT}.blob.core.windows.net/${CONTAINER}"
export AZCOPY_AUTO_LOGIN_TYPE=MSI AZCOPY_MSI_CLIENT_ID="$IDENTITY_CLIENT_ID"
export WORKDIR LOG_FILE

log() { echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] $*"; }
imds() { curl -sf -H Metadata:true "http://169.254.169.254/metadata/$1"; }

# Role assignments of a new identity can take a few minutes to propagate: retry.
retry() {
    local tries="$1"; shift
    local i
    for ((i = 1; i <= tries; i++)); do
        "$@" && return 0
        log "retry $i/$tries: $*"
        sleep 20
    done
    return 1
}

SYNC_PID=""
EVICTION_PID=""
cleanup_and_exit() {
    local code=$?
    for pid in "$SYNC_PID" "$EVICTION_PID"; do
        [[ -n "$pid" ]] && { kill "$pid" 2>/dev/null || true; wait "$pid" 2>/dev/null || true; }
    done
    log "Final sync to ${BLOB_URL} (exit code: ${code})..."
    SYNC_LOCK_WAIT_S=300 bash "$WORKDIR/cloud/azure/sync-outputs-azure.sh" || true
    azcopy copy "$LOG_FILE" "${BLOB_URL}/logs/etl-$(hostname)-$(date -u +%Y%m%d-%H%M%S).log" --log-level=ERROR || true
    if [[ "$AUTO_DELETE" == "1" && -n "$RUN_RESOURCE_GROUP" ]]; then
        log "Deleting resource group ${RUN_RESOURCE_GROUP} (VM, disk, network)..."
        az group delete --name "$RUN_RESOURCE_GROUP" --yes --no-wait || true
    fi
    exit "$code"
}
trap cleanup_and_exit EXIT

mkdir -p "$SCRATCH_DIR" "$WORKDIR"

log "Installing Azure CLI and AzCopy..."
if ! command -v az >/dev/null 2>&1; then
    curl -fsSL https://aka.ms/InstallAzureCLIDeb | bash >/dev/null
fi
if ! command -v azcopy >/dev/null 2>&1; then
    tmp=$(mktemp -d)
    curl -fsSL https://aka.ms/downloadazcopy-v10-linux | tar -xz -C "$tmp"
    install -m 0755 "$tmp"/azcopy_linux_amd64_*/azcopy /usr/local/bin/azcopy
    rm -rf "$tmp"
fi
retry 30 az login --identity --client-id "$IDENTITY_CLIENT_ID" --output none \
    || retry 3 az login --identity --username "$IDENTITY_CLIENT_ID" --output none

if ! command -v pixi >/dev/null 2>&1; then
    log "Installing pixi..."
    curl -fsSL https://pixi.sh/install.sh | bash
fi

if [[ ! -d "$WORKDIR/.git" ]]; then
    [[ -n "$REPO_URL" ]] || { echo "ERROR: REPO_URL is required" >&2; exit 1; }
    log "Cloning $REPO_URL ($REPO_BRANCH)..."
    git clone --depth 1 --branch "$REPO_BRANCH" "$REPO_URL" "$WORKDIR"
fi
cd "$WORKDIR"
log "Code revision: $(git rev-parse --short HEAD)"

if [[ -z "${EARTHDATA_TOKEN:-}" && -n "$KEYVAULT" ]]; then
    log "Reading Earthdata token from Key Vault ${KEYVAULT}/${EARTHDATA_SECRET}..."
    EARTHDATA_TOKEN=$(retry 15 az keyvault secret show --vault-name "$KEYVAULT" --name "$EARTHDATA_SECRET" \
                      --query value -o tsv) || { log "WARNING: token not readable; Earthdata sources will fail"; EARTHDATA_TOKEN=""; }
    export EARTHDATA_TOKEN
fi

log "Installing pixi environment (locked)..."
pixi install --locked
pixi run check-env
if [[ -f "$WORKDIR/requirements-minerales.txt" ]]; then
    bash "$WORKDIR/scripts/preparar_minerales.sh"
fi

log "Restoring outputs from ${BLOB_URL} (if any)..."
retry 15 azcopy list "$BLOB_URL" --log-level=ERROR >/dev/null || log "WARNING: container not listable yet"
mkdir -p "$ANALOGOS_FEATURE_STORE_DIR" "$WORKDIR/releases"
azcopy copy "${BLOB_URL}/data/feature_store_v1/*" "$ANALOGOS_FEATURE_STORE_DIR" --recursive --overwrite=true --log-level=ERROR || true
azcopy copy "${BLOB_URL}/releases/*" "$WORKDIR/releases" --recursive --overwrite=true --log-level=ERROR || true
azcopy copy "${BLOB_URL}/docs/*" "$WORKDIR/docs" --recursive --overwrite=true --log-level=ERROR || true
if [[ "$ETL_SCRIPT" == *"etl_capa_global.py"* || "$ETL_SCRIPT" == *"etl_secuencia.py"* ]]; then
    mkdir -p "$ANALOGOS_GLOBAL_LAYERS_DIR"
    azcopy copy "${BLOB_URL}/data/global_layers/*" "$ANALOGOS_GLOBAL_LAYERS_DIR" --recursive --overwrite=true --log-level=ERROR || true
fi

if [[ "$SYNC_INTERVAL_S" -gt 0 ]]; then
    log "Periodic sync every ${SYNC_INTERVAL_S} s"
    (
        sleep_pid=""
        trap '[[ -n "$sleep_pid" ]] && kill "$sleep_pid" 2>/dev/null; exit 0' TERM
        while true; do
            sleep "$SYNC_INTERVAL_S" &
            sleep_pid=$!
            wait "$sleep_pid"
            sleep_pid=""
            bash "$WORKDIR/cloud/azure/sync-outputs-azure.sh" || true
        done
    ) &
    SYNC_PID=$!
fi

# Spot eviction: Azure posts a Preempt scheduled event ~30 s before deallocating the VM.
(
    sleep_pid=""
    trap '[[ -n "$sleep_pid" ]] && kill "$sleep_pid" 2>/dev/null; exit 0' TERM
    while true; do
        events=$(imds 'scheduledevents?api-version=2020-07-01' || true)
        if [[ "$events" == *'"EventType":"Preempt"'* || "$events" == *'"EventType": "Preempt"'* ]]; then
            log "Spot eviction notice: syncing outputs"
            SYNC_LOCK_WAIT_S=5 timeout 25 bash "$WORKDIR/cloud/azure/sync-outputs-azure.sh" || true
            exit 0
        fi
        sleep 5 &
        sleep_pid=$!
        wait "$sleep_pid"
        sleep_pid=""
    done
) &
EVICTION_PID=$!

if [[ "$ETL_SCRIPT" == *"etl_pipeline.py"* || "$ETL_SCRIPT" == *"atlas30.py"* ]]; then
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
