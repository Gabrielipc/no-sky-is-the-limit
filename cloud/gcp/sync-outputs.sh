#!/usr/bin/env bash
# Uploads the Feature Store, releases, global surface layers and evidence from the VM to GCS.
# Called periodically while the ETL runs, by the VM shutdown-script (Spot preemption)
# and once more when the ETL ends. Only files already moved into place are uploaded:
# the store writes each delta into a `tmp*` directory and then renames it, so those
# staging directories are excluded and a completed batch never reaches GCS half-written.
# Global layer rasters are written as `*.part.tif` and renamed when complete; `.part` files are excluded.
set -uo pipefail

GCS_BUCKET="${GCS_BUCKET:?Set GCS_BUCKET}"
WORKDIR="${WORKDIR:-/opt/analogos}"
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
    gcloud storage rsync -r --exclude="$EXCLUDE" "$src" "$dst" || status=1
}

sync_dir "$WORKDIR/data/feature_store_v1" "${GCS_BUCKET}/data/feature_store_v1"
sync_dir "$WORKDIR/releases" "${GCS_BUCKET}/releases"
sync_dir "$WORKDIR/data/global_layers" "${GCS_BUCKET}/data/global_layers"
for evidence in "$WORKDIR"/docs/evidencia-*; do
    [[ -d "$evidence" ]] && sync_dir "$evidence" "${GCS_BUCKET}/docs/$(basename "$evidence")"
done
log "done (status ${status})"
exit "$status"
