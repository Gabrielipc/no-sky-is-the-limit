# ETL en Azure (VM Spot efímera)

Es el mismo método que [`cloud/gcp/`](../gcp/README.md): una VM Spot que clona el repositorio, procesa en disco temporal, sube a Blob Storage solo los productos ligeros (cada `SYNC_INTERVAL_S`, ante el aviso de desalojo y al terminar) y **se borra sola**. Los productos originales nunca se guardan en la nube ni en tu Mac.

| Archivo | Qué hace |
|---|---|
| `launch-spot.sh` | Se ejecuta desde tu Mac. Crea una sola vez los recursos persistentes (cuenta de almacenamiento, contenedor, Key Vault, identidad administrada) y, por cada ejecución, un grupo de recursos con la VM |
| `run-etl-azure.sh` | Se ejecuta en la VM. Instala Azure CLI, AzCopy y Pixi, lee el token de Key Vault, restaura los resultados previos, ejecuta `ETL_SCRIPT` y borra su grupo de recursos al terminar |
| `sync-outputs-azure.sh` | Sube el almacén, las releases, `data/global_layers/`, `docs/evidencia-*` y el log. Excluye los temporales (`tmp*`, `.stream_tmp`, `*.part*`) |
| `../descargar-resultados.sh` | Descarga a tu Mac solo lo ligero. Sirve también para GCP |

## Seguridad

- **Token de Earthdata:** se guarda en **Key Vault** (`EARTHDATA_SECRET`, por defecto `earthdata-token`) desde un archivo temporal con permisos 600. Nunca va en los metadatos de la VM ni en la línea de comandos.
- **Identidad administrada:** la VM usa una identidad asignada por el usuario (`analogos-etl-identity`) con tres roles mínimos:
  - *Storage Blob Data Contributor* sobre la cuenta de almacenamiento;
  - *Key Vault Secrets User* sobre el vault;
  - *Contributor* solo sobre el grupo de recursos de esa ejecución, para borrarse al final.
- **Red:** la IP pública sirve solo para salir a Internet. El NSG no admite tráfico entrante (`--nsg-rule NONE`) y los logs se leen sin SSH.
- **Entorno bloqueado:** `pixi install --locked` y registro del commit ejecutado, como en GCP.

## Prerrequisitos

1. **Azure CLI** e inicio de sesión:
   ```bash
   brew install azure-cli
   ```
   ```bash
   az login
   ```
2. **Tipo de suscripción.** Con una **prueba gratuita** (`quotaId` `FreeTrial`) no hay VMs Spot y el límite es de 4 vCPU por región: lanza con `PRIORITY=Regular VM_SIZE=Standard_D4s_v5` (4 vCPU, 16 GB, suficiente también para la capa `ati`, que usa ~6 GB). El coste sale del crédito de la prueba. Para ver tu tipo de suscripción:
   ```bash
   az rest --method get --url "https://management.azure.com/subscriptions/$(az account show --query id -o tsv)?api-version=2022-12-01" --query subscriptionPolicies.quotaId -o tsv
   ```
   `launch-spot.sh` registra los proveedores de recursos que falten (`Microsoft.Compute`, `Network`, `Storage`, `KeyVault`, `ManagedIdentity`). Sin ese registro, `az vm list-usage` sale vacío.
3. **Cuota Spot en la región** (suscripciones de pago). Una `Standard_D8s_v5` necesita 8 vCPU de la familia DSv5 y de «Total Regional Spot vCPUs». Las suscripciones nuevas o de prueba suelen tener poca cuota. Revísala con este comando y, si no alcanza, pide más en el portal o usa `VM_SIZE=Standard_D4s_v5` (16 GB: suficiente para todas las capas):
   ```bash
   az vm list-usage --location westus2 -o table | grep -iE "spot|DSv5"
   ```
4. **Código en GitHub:** sube los commits a `REPO_BRANCH` antes de lanzar, porque la VM clona desde GitHub.

## Qué se puede correr ya (sin esperar al barrido mundial)

La **capa global** solo necesita Earthdata y CEDA. `scripts/etl_secuencia.py` ejecuta en orden los pasos disponibles y omite los que necesitan ventanas base (muestreo, ATI por conglomerados, publicación) mientras el almacén del contenedor no tenga el barrido:

```bash
export STORAGE_ACCOUNT="analogosdatos$RANDOM"   # único en Azure; apúntalo para reutilizarlo
export KEYVAULT="analogos-kv-$RANDOM"           # único en Azure
export REPO_URL="https://github.com/Gabrielipc/no-sky-is-the-limit.git"
export REPO_BRANCH="fuentes-de-datos"
# EARTHDATA_TOKEN ya definido en tu terminal: se guarda en Key Vault

ETL_ARGS="--steps build" bash cloud/azure/launch-spot.sh
```

Por adelantado: autoriza la aplicación GES DISC en tu perfil de Earthdata. Si no, IMERG falla y las demás capas siguen. Calcula ~1,5–3 h y ~30 GB descargados en `westus2`, la región de Azure más cercana a Earthdata Cloud (AWS `us-west-2`). Para una prueba corta, prueba primero el camino HDF4 y el del CCI:

```bash
ETL_ARGS="--steps build --layer snow --layer permafrost" bash cloud/azure/launch-spot.sh
```

## Cuando el barrido mundial esté listo

El muestreo de la capa global y la ATI por conglomerados necesitan las ventanas base, que hoy están en el bucket de GCP. Hay dos caminos, y en ninguno los datos pasan por tu Mac:

1. **Copiar el almacén de GCS a Blob (servicio a servicio) y seguir en Azure.** Necesitas AzCopy en tu Mac y una clave JSON de una cuenta de servicio de GCP con permiso de lectura sobre el bucket:
   ```bash
   export GOOGLE_APPLICATION_CREDENTIALS=~/clave-lectura-gcs.json
   azcopy login
   azcopy copy "https://storage.cloud.google.com/regolith-analogos-gabi0808/data/feature_store_v1" \
     "https://$STORAGE_ACCOUNT.blob.core.windows.net/analogos/data" --recursive
   ```
   ```bash
   ETL_ARGS="--steps sample,ati-cluster --ati-tiles 40 --ati-per-tile 5" bash cloud/azure/launch-spot.sh
   ```
2. **Llevar las capas de Azure a GCS y muestrear en GCP.** `bash cloud/transferir-capas-azure-gcs.sh` (con `STORAGE_ACCOUNT`, `PROJECT_ID`, `GCS_BUCKET`) usa Storage Transfer Service con una SAS de solo lectura de un día; al relanzarlo copia solo lo nuevo. Después: `ETL_SCRIPT="scripts/etl_secuencia.py" ETL_ARGS="--steps sample"` con `cloud/gcp/launch-spot.sh`.

## Seguir el progreso

`launch-spot.sh` imprime los comandos exactos al lanzar:

```bash
az vm boot-diagnostics get-boot-log -g <grupo-de-la-ejecucion> -n <vm> | tail -40      # consola en vivo
az storage blob download --account-name "$STORAGE_ACCOUNT" -c analogos --auth-mode login \
  -n logs/current-<vm>.log -f /dev/stdout | tail -40                                    # log subido cada 10 min
az group exists -n <grupo-de-la-ejecucion>                                              # false = terminó y se borró
```

En el contenedor, `docs/evidencia-capa-global/secuencia.json` resume qué pasos se ejecutaron u omitieron y cuánto tardó cada uno.

## Descargar solo lo ligero

```bash
PROVIDER=azure STORAGE_ACCOUNT="$STORAGE_ACCOUNT" bash cloud/descargar-resultados.sh
```

Descarga `data/feature_store_v1/enrichment/` (capa global, selección, superficie y puentes: decenas de MB), los manifiestos y `docs/evidencia-*`. Lo pesado es opcional: `WITH_BASE=1` (barrido, ~0,5 GB), `WITH_RELEASES=1` y `WITH_LAYERS=1` (rásteres globales, varios GB). Desde GCP es lo mismo con `PROVIDER=gcp GCS_BUCKET=gs://...`.

## Costes orientativos

Una `Standard_D8s_v5` Spot en `westus2` cuesta del orden de centavos de dólar por hora: unas horas de capa global salen por menos de 1–2 USD. La descarga desde Earthdata hacia Azure es tráfico de entrada y no se cobra. Blob Standard LRS para unos pocos GB cuesta céntimos al mes. Borra el grupo `analogos-data` cuando ya no lo necesites.
