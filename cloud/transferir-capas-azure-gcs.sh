#!/usr/bin/env bash
# Copies the global surface layers built in Azure (data/global_layers/) into the GCS bucket, service to
# service with Google Storage Transfer Service: nothing goes through this machine. Re-running copies
# only what changed, so it can run after each Azure build.
#
#   STORAGE_ACCOUNT=analogosdatos22363 PROJECT_ID=adroit-hall-514719-d5 \
#   GCS_BUCKET=gs://regolith-analogos-gabi0808 bash cloud/transferir-capas-azure-gcs.sh
#
# Uses a read-only, 1-day user-delegation SAS on the container (no account keys), written to a temporary
# file with mode 600 and deleted at the end.
set -euo pipefail

STORAGE_ACCOUNT="${STORAGE_ACCOUNT:?Set STORAGE_ACCOUNT (Azure)}"
CONTAINER="${CONTAINER:-analogos}"
PROJECT_ID="${PROJECT_ID:?Set PROJECT_ID (GCP)}"
GCS_BUCKET="${GCS_BUCKET:?Set GCS_BUCKET (gs://...)}"
PREFIX="${PREFIX:-data/global_layers/}"
export CLOUDSDK_CORE_DISABLE_PROMPTS=1

echo "Capas en Azure (${STORAGE_ACCOUNT}/${CONTAINER}/${PREFIX}):"
az storage blob list --account-name "$STORAGE_ACCOUNT" -c "$CONTAINER" --auth-mode login --prefix "$PREFIX" \
    --query "[?ends_with(name,'layer.json')].name" -o tsv

expiry=$(date -u -v+1d '+%Y-%m-%dT%H:%MZ' 2>/dev/null || date -u -d '+1 day' '+%Y-%m-%dT%H:%MZ')
sas=$(az storage container generate-sas --account-name "$STORAGE_ACCOUNT" --name "$CONTAINER" \
      --permissions rl --expiry "$expiry" --auth-mode login --as-user -o tsv)
creds=$(mktemp)
chmod 600 "$creds"
trap 'rm -f "$creds"' EXIT
printf '{"sasToken": "%s"}\n' "$sas" > "$creds"

echo "Preparando Storage Transfer Service en ${PROJECT_ID} (una vez)..."
gcloud services enable storagetransfer.googleapis.com --project="$PROJECT_ID" >/dev/null
gcloud transfer authorize --add-missing --project="$PROJECT_ID" >/dev/null

SOURCE="https://${STORAGE_ACCOUNT}.blob.core.windows.net/${CONTAINER}/${PREFIX}"
DEST="${GCS_BUCKET%/}/${PREFIX}"
echo "Transfiriendo ${SOURCE} -> ${DEST} ..."
job=$(gcloud transfer jobs create "$SOURCE" "$DEST" --project="$PROJECT_ID" --source-creds-file="$creds" \
      --description="capas globales Azure -> GCS" --format='value(name)')
echo "Trabajo ${job}; esperando a que termine..."
gcloud transfer jobs monitor "$job" --project="$PROJECT_ID"
echo
gcloud storage ls -r "$DEST" | grep -E 'layer.json$'
