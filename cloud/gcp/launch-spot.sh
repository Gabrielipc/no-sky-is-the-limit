#!/usr/bin/env bash
# Launches an ephemeral GCP Spot VM to run the ETL pipeline and auto-delete on completion.
set -euo pipefail

PROJECT_ID="${PROJECT_ID:?Set PROJECT_ID (your GCP project id)}"
GCS_BUCKET="${GCS_BUCKET:?Set GCS_BUCKET (e.g. gs://mi-bucket-analogos)}"
REPO_URL="${REPO_URL:?Set REPO_URL (e.g. https://github.com/usuario/repo.git)}"
REPO_BRANCH="${REPO_BRANCH:-main}"

# europe-west3 (Frankfurt) is closest to Copernicus GLO-30 / ESA WorldCover / JRC.
# us-west1 (Oregon) is closest to NASA Earthdata / USGS 3DEP and has Tier-1 pricing.
ZONE="${ZONE:-europe-west3-a}"
REGION="${ZONE%-*}"
MACHINE_TYPE="${MACHINE_TYPE:-e2-standard-8}"
DISK_SIZE_GB="${DISK_SIZE_GB:-80}"
VM_NAME="${VM_NAME:-analogos-etl-$(date +%Y%m%d-%H%M%S)}"
ETL_SCRIPT="${ETL_SCRIPT:-scripts/etl_pipeline.py}"
ETL_ARGS="${ETL_ARGS:-stream --scope world --stride 10000 --max-batches 50 --workers 8 --io-workers 16 --max-temp-gb 12}"
AUTO_DELETE="${AUTO_DELETE:-1}"

if ! gcloud storage buckets describe "$GCS_BUCKET" --project="$PROJECT_ID" >/dev/null 2>&1; then
    echo "Creating bucket ${GCS_BUCKET} in ${REGION}..."
    gcloud storage buckets create "$GCS_BUCKET" --project="$PROJECT_ID" --location="$REGION" --uniform-bucket-level-access
fi

STARTUP_SCRIPT=$(mktemp)
trap 'rm -f "$STARTUP_SCRIPT"' EXIT

cat > "$STARTUP_SCRIPT" <<EOF
#!/usr/bin/env bash
set -euo pipefail
exec > >(tee -a /var/log/analogos-etl.log) 2>&1

export GCS_BUCKET="${GCS_BUCKET}"
export REPO_URL="${REPO_URL}"
export REPO_BRANCH="${REPO_BRANCH}"
export ETL_SCRIPT="${ETL_SCRIPT}"
export ETL_ARGS="${ETL_ARGS}"
export AUTO_DELETE="${AUTO_DELETE}"
export EARTHDATA_TOKEN="${EARTHDATA_TOKEN:-}"

apt-get update -qq && apt-get install -y -qq curl git >/dev/null

WORKDIR=/opt/analogos
mkdir -p "\$WORKDIR"
if [[ ! -d "\$WORKDIR/.git" ]]; then
    git clone --depth 1 --branch "\$REPO_BRANCH" "\$REPO_URL" "\$WORKDIR"
fi

bash "\$WORKDIR/cloud/gcp/run-etl-spot.sh"
EOF

echo "Launching Spot VM ${VM_NAME} (${MACHINE_TYPE}) in ${ZONE}..."
gcloud compute instances create "$VM_NAME" \
    --project="$PROJECT_ID" \
    --zone="$ZONE" \
    --machine-type="$MACHINE_TYPE" \
    --provisioning-model=SPOT \
    --instance-termination-action=DELETE \
    --boot-disk-size="${DISK_SIZE_GB}GB" \
    --boot-disk-type=pd-balanced \
    --image-family=ubuntu-2404-lts-amd64 \
    --image-project=ubuntu-os-cloud \
    --scopes=cloud-platform \
    --metadata-from-file=startup-script="$STARTUP_SCRIPT"

echo ""
echo "Spot VM launched: ${VM_NAME}"
echo "Tail logs:        gcloud compute ssh ${VM_NAME} --zone=${ZONE} --project=${PROJECT_ID} --command='tail -f /var/log/analogos-etl.log'"
echo "Sync results:     gcloud storage rsync -r ${GCS_BUCKET}/data/feature_store_v1 ./data/feature_store_v1"
echo "                  gcloud storage rsync -r ${GCS_BUCKET}/releases ./releases"
