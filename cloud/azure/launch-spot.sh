#!/usr/bin/env bash
# Launches an ephemeral Azure Spot VM that runs one ETL and deletes itself (cloud/azure/run-etl-azure.sh).
#
# Persistent resources (created once, reused): resource group DATA_RESOURCE_GROUP with the storage
# account + container, the Key Vault holding the Earthdata token and a user-assigned managed
# identity with only: Storage Blob Data Contributor (storage account), Key Vault Secrets User
# (vault) and Contributor on the run's own resource group (to delete itself at the end).
# Per run: a new resource group RUN_RESOURCE_GROUP with the VM, its disk and its public IP
# (outbound only: the NSG admits no inbound traffic).
set -euo pipefail

STORAGE_ACCOUNT="${STORAGE_ACCOUNT:?Set STORAGE_ACCOUNT (3-24 lowercase letters/digits, globally unique)}"
KEYVAULT="${KEYVAULT:?Set KEYVAULT (3-24 chars, globally unique)}"
REPO_URL="${REPO_URL:?Set REPO_URL (e.g. https://github.com/usuario/repo.git)}"
REPO_BRANCH="${REPO_BRANCH:-main}"
# westus2 (Washington) is the Azure region closest to NASA Earthdata Cloud (AWS us-west-2).
LOCATION="${LOCATION:-westus2}"
CONTAINER="${CONTAINER:-analogos}"
DATA_RESOURCE_GROUP="${DATA_RESOURCE_GROUP:-analogos-data}"
IDENTITY_NAME="${IDENTITY_NAME:-analogos-etl-identity}"
EARTHDATA_SECRET="${EARTHDATA_SECRET:-earthdata-token}"
STAMP="$(date +%Y%m%d-%H%M%S)"
RUN_RESOURCE_GROUP="${RUN_RESOURCE_GROUP:-analogos-etl-${STAMP}}"
VM_NAME="${VM_NAME:-analogos-etl-${STAMP}}"
VM_SIZE="${VM_SIZE:-Standard_D8s_v5}"      # 8 vCPU, 32 GB (the ATI layer keeps ~6 GB in memory)
DISK_SIZE_GB="${DISK_SIZE_GB:-128}"
IMAGE="${IMAGE:-Canonical:ubuntu-24_04-lts:server:latest}"
MAX_PRICE="${MAX_PRICE:--1}"               # -1 = up to the on-demand price, never evicted for price
ETL_SCRIPT="${ETL_SCRIPT:-scripts/etl_secuencia.py}"
ETL_ARGS="${ETL_ARGS:---steps build,sample,ati-cluster}"
AUTO_DELETE="${AUTO_DELETE:-1}"
SYNC_INTERVAL_S="${SYNC_INTERVAL_S:-600}"

az account show --output none 2>/dev/null || { echo "Run 'az login' first." >&2; exit 1; }
SUBSCRIPTION_ID=$(az account show --query id -o tsv)
ME=$(az ad signed-in-user show --query id -o tsv 2>/dev/null || true)

echo "Persistent resources in ${DATA_RESOURCE_GROUP} (${LOCATION})..."
az group create --name "$DATA_RESOURCE_GROUP" --location "$LOCATION" --output none
if ! az storage account show --name "$STORAGE_ACCOUNT" --resource-group "$DATA_RESOURCE_GROUP" --output none 2>/dev/null; then
    echo "Creating storage account ${STORAGE_ACCOUNT}..."
    az storage account create --name "$STORAGE_ACCOUNT" --resource-group "$DATA_RESOURCE_GROUP" \
        --location "$LOCATION" --sku Standard_LRS --kind StorageV2 --min-tls-version TLS1_2 \
        --allow-blob-public-access false --output none
fi
STORAGE_ID=$(az storage account show --name "$STORAGE_ACCOUNT" --resource-group "$DATA_RESOURCE_GROUP" --query id -o tsv)

if ! az keyvault show --name "$KEYVAULT" --resource-group "$DATA_RESOURCE_GROUP" --output none 2>/dev/null; then
    echo "Creating Key Vault ${KEYVAULT}..."
    az keyvault create --name "$KEYVAULT" --resource-group "$DATA_RESOURCE_GROUP" --location "$LOCATION" \
        --enable-rbac-authorization true --output none
fi
KEYVAULT_ID=$(az keyvault show --name "$KEYVAULT" --resource-group "$DATA_RESOURCE_GROUP" --query id -o tsv)

assign() {  # assignee-object-id principal-type role scope (idempotent)
    if [[ -z "$(az role assignment list --assignee "$1" --role "$3" --scope "$4" --query '[0].id' -o tsv 2>/dev/null)" ]]; then
        az role assignment create --assignee-object-id "$1" --assignee-principal-type "$2" \
            --role "$3" --scope "$4" --output none
    fi
}

if [[ -n "$ME" ]]; then
    assign "$ME" User "Storage Blob Data Contributor" "$STORAGE_ID"
    assign "$ME" User "Key Vault Secrets Officer" "$KEYVAULT_ID"
fi
for _ in 1 2 3 4 5 6; do
    az storage container create --name "$CONTAINER" --account-name "$STORAGE_ACCOUNT" --auth-mode login \
        --output none 2>/dev/null && break
    echo "Waiting for storage permissions to propagate..."; sleep 20
done

if [[ -n "${EARTHDATA_TOKEN:-}" ]]; then
    echo "Storing EARTHDATA_TOKEN in Key Vault ${KEYVAULT}/${EARTHDATA_SECRET}..."
    token_file=$(mktemp); chmod 600 "$token_file"
    printf '%s' "$EARTHDATA_TOKEN" > "$token_file"
    for _ in 1 2 3 4 5 6; do
        az keyvault secret set --vault-name "$KEYVAULT" --name "$EARTHDATA_SECRET" --file "$token_file" \
            --output none 2>/dev/null && break
        echo "Waiting for Key Vault permissions to propagate..."; sleep 20
    done
    rm -f "$token_file"
fi

if ! az identity show --name "$IDENTITY_NAME" --resource-group "$DATA_RESOURCE_GROUP" --output none 2>/dev/null; then
    echo "Creating managed identity ${IDENTITY_NAME}..."
    az identity create --name "$IDENTITY_NAME" --resource-group "$DATA_RESOURCE_GROUP" --location "$LOCATION" --output none
fi
IDENTITY_ID=$(az identity show --name "$IDENTITY_NAME" --resource-group "$DATA_RESOURCE_GROUP" --query id -o tsv)
IDENTITY_PRINCIPAL=$(az identity show --name "$IDENTITY_NAME" --resource-group "$DATA_RESOURCE_GROUP" --query principalId -o tsv)
IDENTITY_CLIENT_ID=$(az identity show --name "$IDENTITY_NAME" --resource-group "$DATA_RESOURCE_GROUP" --query clientId -o tsv)
assign "$IDENTITY_PRINCIPAL" ServicePrincipal "Storage Blob Data Contributor" "$STORAGE_ID"
assign "$IDENTITY_PRINCIPAL" ServicePrincipal "Key Vault Secrets User" "$KEYVAULT_ID"

echo "Run resource group ${RUN_RESOURCE_GROUP}..."
az group create --name "$RUN_RESOURCE_GROUP" --location "$LOCATION" --tags purpose=analogos-etl --output none
RUN_RG_ID="/subscriptions/${SUBSCRIPTION_ID}/resourceGroups/${RUN_RESOURCE_GROUP}"
assign "$IDENTITY_PRINCIPAL" ServicePrincipal "Contributor" "$RUN_RG_ID"

CLOUD_INIT=$(mktemp)
trap 'rm -f "$CLOUD_INIT"' EXIT
cat > "$CLOUD_INIT" <<EOF
#!/usr/bin/env bash
set -euo pipefail
exec > >(tee -a /var/log/analogos-etl.log /dev/console) 2>&1
export STORAGE_ACCOUNT="${STORAGE_ACCOUNT}"
export CONTAINER="${CONTAINER}"
export IDENTITY_CLIENT_ID="${IDENTITY_CLIENT_ID}"
export RUN_RESOURCE_GROUP="${RUN_RESOURCE_GROUP}"
export KEYVAULT="${KEYVAULT}"
export EARTHDATA_SECRET="${EARTHDATA_SECRET}"
export REPO_URL="${REPO_URL}"
export REPO_BRANCH="${REPO_BRANCH}"
export ETL_SCRIPT="${ETL_SCRIPT}"
export ETL_ARGS="${ETL_ARGS}"
export AUTO_DELETE="${AUTO_DELETE}"
export SYNC_INTERVAL_S="${SYNC_INTERVAL_S}"
export HOME=/root
apt-get update -qq && apt-get install -y -qq curl git >/dev/null
WORKDIR=/opt/analogos
if [[ ! -d "\$WORKDIR/.git" ]]; then
    git clone --depth 1 --branch "\$REPO_BRANCH" "\$REPO_URL" "\$WORKDIR"
fi
bash "\$WORKDIR/cloud/azure/run-etl-azure.sh"
EOF

echo "Launching Spot VM ${VM_NAME} (${VM_SIZE}) in ${LOCATION}..."
az vm create --resource-group "$RUN_RESOURCE_GROUP" --name "$VM_NAME" --location "$LOCATION" \
    --image "$IMAGE" --size "$VM_SIZE" --os-disk-size-gb "$DISK_SIZE_GB" \
    --priority Spot --eviction-policy Delete --max-price "$MAX_PRICE" \
    --assign-identity "$IDENTITY_ID" --custom-data "$CLOUD_INIT" \
    --public-ip-sku Standard --nsg-rule NONE --generate-ssh-keys \
    --admin-username analogos --output none
az vm boot-diagnostics enable --resource-group "$RUN_RESOURCE_GROUP" --name "$VM_NAME" --output none || true

BLOB_URL="https://${STORAGE_ACCOUNT}.blob.core.windows.net/${CONTAINER}"
cat <<MSG

Spot VM launched: ${VM_NAME} (resource group ${RUN_RESOURCE_GROUP}, deleted when the ETL ends)
Live log (console):  az vm boot-diagnostics get-boot-log -g ${RUN_RESOURCE_GROUP} -n ${VM_NAME} | tail -40
Log in the container (every ${SYNC_INTERVAL_S} s):
  az storage blob download --account-name ${STORAGE_ACCOUNT} -c ${CONTAINER} --auth-mode login -n logs/current-${VM_NAME}.log -f /dev/stdout | tail -40
Is it still running?  az group exists -n ${RUN_RESOURCE_GROUP}
Light results:       PROVIDER=azure STORAGE_ACCOUNT=${STORAGE_ACCOUNT} bash cloud/descargar-resultados.sh
MSG
