#!/usr/bin/env bash
# Readable log of an Azure ETL run.
#
#   bash cloud/azure/ver-log.sh                       # latest run: log uploaded to the container
#   bash cloud/azure/ver-log.sh <vm> consola          # live serial console of a running VM
#   bash cloud/azure/ver-log.sh <vm> blob [lineas]    # log uploaded every SYNC_INTERVAL_S (default 600 s)
#
# The VM name and its resource group are the same (analogos-etl-AAAAMMDD-HHMMSS).
# Needs STORAGE_ACCOUNT (and CONTAINER, default analogos) for the `blob` mode.
set -euo pipefail

VM="${1:-}"
MODE="${2:-blob}"
LINES="${3:-60}"
CONTAINER="${CONTAINER:-analogos}"

if [[ -z "$VM" ]]; then
    VM=$(az group list --query "[?starts_with(name,'analogos-etl-')].name | sort(@) | [-1]" -o tsv 2>/dev/null)
    [[ -n "$VM" ]] || { echo "No hay ejecuciones activas; indica el nombre de la VM." >&2; exit 1; }
    echo "== Ejecución activa: $VM"
fi

case "$MODE" in
consola)
    # The console comes back as a single JSON string with \r\n and NUL padding; cloud-init echoes
    # every line twice (with a kernel timestamp), so keep only the plain copy.
    az vm boot-diagnostics get-boot-log -g "$VM" -n "$VM" 2>/dev/null | python3 -c '
import json, re, sys
text = json.load(sys.stdin).replace("\x00", "")
text = re.sub(r"\x1b\[[0-9;]*m", "", text)
lines = [l.rstrip("\r") for l in text.splitlines()]
lines = [l for l in lines if l.strip() and "cloud-init[" not in l]
print("\n".join(lines[-int(sys.argv[1]):]))' "$LINES"
    ;;
blob)
    STORAGE_ACCOUNT="${STORAGE_ACCOUNT:?Define STORAGE_ACCOUNT}"
    for name in "logs/current-${VM}.log" $(az storage blob list --account-name "$STORAGE_ACCOUNT" -c "$CONTAINER" \
            --auth-mode login --prefix "logs/etl-${VM}" --query "[].name" -o tsv 2>/dev/null); do
        if az storage blob download --account-name "$STORAGE_ACCOUNT" -c "$CONTAINER" --auth-mode login \
                -n "$name" -f /dev/stdout --output none 2>/dev/null \
                | grep -av 'Number of\|INFO:\|^Job \|Log file is located\|Elapsed Time\|Total Number\|Final Job Status\|^\s*$' \
                | tail -n "$LINES"; then
            echo "== ($name)"
            break
        fi
    done
    ;;
*)
    echo "Modo desconocido: $MODE (consola | blob)" >&2
    exit 1
    ;;
esac
