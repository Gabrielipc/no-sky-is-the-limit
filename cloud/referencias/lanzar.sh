#!/usr/bin/env bash
# Launches the two mirror jobs of the Moon and Mars rasters at the same time, one per cloud, and tells you how to
# merge them in GCS afterwards. Nothing is launched unless you pass RUN=1: the default is a dry run that checks
# everything and prints the exact commands.
#
#   bash cloud/referencias/lanzar.sh            # dry run: checks and commands
#   RUN=1 bash cloud/referencias/lanzar.sh      # launches GCP (Moon) and Azure (Mars) in parallel
#   RUN=1 ONLY=gcp bash cloud/referencias/lanzar.sh   # only one of them (gcp or azure), e.g. to retry the one that failed
#
#   GCP   Moon  scripts/etl_referencias.py espejo --body Moon   ~7.7 GB  (LOLA 20 m, PSR, illumination, Diviner, Mini-RF)
#   Azure Mars  scripts/etl_referencias.py espejo --body Mars   ~0.5 GB  (HiRISE DTM, THEMIS, CRISM of Jezero)
#               Regular D4s_v5 by default (free-trial subscriptions have no Spot); see AZURE_PRIORITY / AZURE_VM_SIZE.
#
# The two jobs write different files (`data/raw/espejo/moon/...` and `.../mars/...`, and `docs/evidencia-espejo/<body>.json`),
# so there is nothing to merge but to copy Azure's output into the GCS bucket (see cloud/referencias/README.md).
# The VMs clone REPO_URL at REPO_BRANCH from GitHub, so the branch must be pushed: this script refuses to run otherwise.
set -euo pipefail
cd "$(dirname "$0")/../.."

RUN="${RUN:-0}"
PROJECT_ID="${PROJECT_ID:-$(gcloud config get-value project 2>/dev/null || true)}"
GCS_BUCKET="${GCS_BUCKET:-gs://regolith-analogos-gabi0808}"
STORAGE_ACCOUNT="${STORAGE_ACCOUNT:-analogosdatos22363}"
KEYVAULT="${KEYVAULT:-analogos-kv-18333}"
REPO_URL="${REPO_URL:-$(git remote get-url origin)}"
REPO_BRANCH="${REPO_BRANCH:-$(git branch --show-current)}"
# The sources (NASA PDS, PGDA, HiRISE, Zenodo) are in the US: keep the VMs close to them.
GCP_ZONE="${GCP_ZONE:-us-central1-a}"
AZURE_LOCATION="${AZURE_LOCATION:-westus2}"
# A free-trial Azure subscription has no Spot VMs and allows 4 vCPU per region: Regular D4s_v5 (4 vCPU, 16 GB) is
# enough for the Mars mirror (~0.5 GB) and is paid from the free credit. With a paid subscription and Spot quota:
# AZURE_PRIORITY=Spot AZURE_VM_SIZE=Standard_D8s_v5.
AZURE_PRIORITY="${AZURE_PRIORITY:-Regular}"
AZURE_VM_SIZE="${AZURE_VM_SIZE:-Standard_D4s_v5}"
WORKERS="${WORKERS:-8}"
ONLY="${ONLY:-}"
# The job is I/O bound (downloads and hashing), so 4 vCPU are plenty. GCP also caps the project at CPUS_ALL_REGIONS
# vCPU across every running VM, including other ETL runs: a smaller VM leaves room for them.
GCP_MACHINE_TYPE="${GCP_MACHINE_TYPE:-e2-standard-4}"
STAMP="$(date +%Y%m%d-%H%M%S)"
GCP_VM="${GCP_VM:-analogos-espejo-moon-${STAMP}}"
AZURE_VM="${AZURE_VM:-analogos-espejo-mars-${STAMP}}"

fail() { echo "ERROR: $*" >&2; exit 1; }
[[ -z "$ONLY" || "$ONLY" == gcp || "$ONLY" == azure ]] || fail "ONLY debe ser gcp o azure"
use_gcp=1; use_azure=1
[[ "$ONLY" == azure ]] && use_gcp=0
[[ "$ONLY" == gcp ]] && use_azure=0
ok() { echo "  ok   $*"; }

echo "Comprobaciones previas"
[[ -n "$PROJECT_ID" ]] || fail "PROJECT_ID vacío (gcloud config set project ...)"
[[ -x scripts/etl_referencias.py ]] || fail "falta scripts/etl_referencias.py: ¿estás en la raíz del repositorio?"
git fetch origin "$REPO_BRANCH" --quiet 2>/dev/null || fail "la rama $REPO_BRANCH no existe en origin: súbela primero"
[[ -z "$(git status --porcelain --untracked-files=no)" ]] || fail "hay cambios sin commitear: las VM clonan GitHub, no tu carpeta"
local_head="$(git rev-parse HEAD)"; remote_head="$(git rev-parse "origin/$REPO_BRANCH")"
[[ "$local_head" == "$remote_head" ]] || fail "tu HEAD ($local_head) no es el de origin/$REPO_BRANCH ($remote_head): sube la rama o haz pull"
ok "rama $REPO_BRANCH en origin = HEAD (${local_head:0:7})"
gcloud storage buckets describe "$GCS_BUCKET" --project="$PROJECT_ID" --format='value(location)' >/dev/null 2>&1 \
    || fail "no encuentro el bucket $GCS_BUCKET en $PROJECT_ID (¿gcloud auth login?)"
ok "bucket $GCS_BUCKET"
if [[ "$use_gcp" == 1 ]]; then
    need_cpus="${GCP_MACHINE_TYPE##*-}"
    quota="$(gcloud compute project-info describe --project="$PROJECT_ID" --format=json 2>/dev/null | python3 -c "
import sys, json
q = [x for x in json.load(sys.stdin).get('quotas', []) if x['metric'] == 'CPUS_ALL_REGIONS']
print(int(q[0]['limit'] - q[0]['usage']) if q else '')" 2>/dev/null || true)"
    if [[ -n "$quota" && "$quota" -lt "$need_cpus" ]]; then
        msg="la cuota global de GCP deja $quota vCPU libres y $GCP_MACHINE_TYPE necesita $need_cpus (hay otras VM en marcha: gcloud compute instances list)"
        if [[ "$RUN" == "1" ]]; then fail "$msg"; else echo "  AVISO $msg"; fi
    else
        ok "cuota de GCP: ${quota:-sin dato} vCPU libres, se piden $need_cpus"
    fi
fi
az account show --output none 2>/dev/null || fail "az no tiene sesión (az login)"
az storage account show -n "$STORAGE_ACCOUNT" --query name -o tsv >/dev/null 2>&1 || fail "no encuentro la cuenta de Azure $STORAGE_ACCOUNT"
az keyvault show -n "$KEYVAULT" --query name -o tsv >/dev/null 2>&1 || fail "no encuentro el Key Vault $KEYVAULT"
ok "Azure $STORAGE_ACCOUNT / $KEYVAULT"
if [[ -x .pixi/envs/default/bin/python ]]; then
    .pixi/envs/default/bin/python scripts/espejar_referencias.py plan --tier 1 --root "$(mktemp -d)" | tail -1 | sed 's/^/  ok   /'
fi

gcp=(env PROJECT_ID="$PROJECT_ID" GCS_BUCKET="$GCS_BUCKET" REPO_URL="$REPO_URL" REPO_BRANCH="$REPO_BRANCH"
     ZONE="$GCP_ZONE" VM_NAME="$GCP_VM" MACHINE_TYPE="$GCP_MACHINE_TYPE" DISK_SIZE_GB=100
     ETL_SCRIPT=scripts/etl_referencias.py ETL_ARGS="espejo --body Moon --workers $WORKERS"
     bash cloud/gcp/launch-spot.sh)
azure=(env STORAGE_ACCOUNT="$STORAGE_ACCOUNT" KEYVAULT="$KEYVAULT" REPO_URL="$REPO_URL" REPO_BRANCH="$REPO_BRANCH"
       LOCATION="$AZURE_LOCATION" VM_NAME="$AZURE_VM" RUN_RESOURCE_GROUP="$AZURE_VM"
       PRIORITY="$AZURE_PRIORITY" VM_SIZE="$AZURE_VM_SIZE"
       ETL_SCRIPT=scripts/etl_referencias.py ETL_ARGS="espejo --body Mars --workers $WORKERS"
       bash cloud/azure/launch-spot.sh)

echo
# %q quotes each word, so the printed commands can be pasted into a shell as they are.
[[ "$use_gcp" == 1 ]] && { printf 'GCP   (Luna):  '; printf '%q ' "${gcp[@]}"; echo; }
[[ "$use_azure" == 1 ]] && { printf 'Azure (Marte): '; printf '%q ' "${azure[@]}"; echo; }
if [[ "$RUN" != "1" ]]; then
    echo
    echo "Simulación: no se lanzó nada. Para lanzar las dos a la vez: RUN=1 bash cloud/referencias/lanzar.sh"
    exit 0
fi

logs="$(mktemp -d)"
echo
echo "Lanzando las dos VM en paralelo (registros en $logs)..."
gcp_pid=""; azure_pid=""
[[ "$use_gcp" == 1 ]] && { "${gcp[@]}" >"$logs/gcp.log" 2>&1 & gcp_pid=$!; }
[[ "$use_azure" == 1 ]] && { "${azure[@]}" >"$logs/azure.log" 2>&1 & azure_pid=$!; }
status=0
[[ -n "$gcp_pid" ]] && { wait "$gcp_pid" || { echo "GCP falló: $logs/gcp.log" >&2; status=1; }; }
[[ -n "$azure_pid" ]] && { wait "$azure_pid" || { echo "Azure falló: $logs/azure.log" >&2; status=1; }; }
for f in gcp azure; do [[ -f "$logs/$f.log" ]] && tail -n 6 "$logs/$f.log"; done
echo
echo "Siguiente:"
[[ "$use_gcp" == 1 ]] && echo "  - Seguimiento GCP:   gcloud compute ssh $GCP_VM --zone=$GCP_ZONE --project=$PROJECT_ID --command='tail -f /var/log/analogos-etl.log'"
[[ "$use_azure" == 1 ]] && echo "  - Seguimiento Azure: STORAGE_ACCOUNT=$STORAGE_ACCOUNT bash cloud/azure/ver-log.sh $AZURE_VM blob"
echo "  - Las VM se borran solas al terminar. Cuando acaben, uníos en GCS y bajad la copia local:"
echo "    ver cloud/referencias/README.md"
exit "$status"
