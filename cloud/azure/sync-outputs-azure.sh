#!/usr/bin/env bash
# Uploads the Feature Store, releases, global surface layers, evidence and the log to Azure Blob.
# Called periodically, on a Spot eviction notice and at the end of the run (run-etl-azure.sh).
# Staging directories (`tmp*`, `.stream_tmp`) and rasters still being written (`*.part*`) are
# excluded, so only complete batches and layers reach the container.
set -uo pipefail

BLOB_URL="${BLOB_URL:?Set BLOB_URL (https://<account>.blob.core.windows.net/<container>)}"
WORKDIR="${WORKDIR:-/opt/analogos}"
LOG_FILE="${LOG_FILE:-/var/log/analogos-etl.log}"
LOCK_FILE="${SYNC_LOCK_FILE:-/tmp/analogos-sync.lock}"
LOCK_WAIT_S="${SYNC_LOCK_WAIT_S:-20}"
# Matched from the start of the relative path (gcloud) or anywhere (azcopy): both work.
EXCLUDE='(.*/)?(tmp[^/]*|\.stream_tmp)(/.*)?$|.*\.part(\.tif)?$|(.*/)?\._.*'

log() { echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] sync: $*"; }

exec 9>"$LOCK_FILE"
if command -v flock >/dev/null 2>&1 && ! flock -w "$LOCK_WAIT_S" 9; then
    log "another sync is still running; skipping"
    exit 0
fi

status=0
sync_dir() {
    local src="$1" dst="$2"
    [[ -d "$src" ]] || return 0
    azcopy sync "$src" "$dst" --recursive --exclude-regex="$EXCLUDE" --log-level=ERROR || status=1
}

sync_dir "$WORKDIR/data/feature_store_v1" "${BLOB_URL}/data/feature_store_v1"
sync_dir "$WORKDIR/releases" "${BLOB_URL}/releases"
sync_dir "$WORKDIR/data/global_layers" "${BLOB_URL}/data/global_layers"
for evidence in "$WORKDIR"/docs/evidencia-*; do
    [[ -d "$evidence" ]] && sync_dir "$evidence" "${BLOB_URL}/docs/$(basename "$evidence")"
done
[[ -f "$LOG_FILE" ]] && azcopy copy "$LOG_FILE" "${BLOB_URL}/logs/current-$(hostname).log" --overwrite=true --log-level=ERROR >/dev/null || true
log "done (status ${status})"
exit "$status"
