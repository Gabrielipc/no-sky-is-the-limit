# Espejo de las fuentes de la Luna y Marte en la nube

Fecha: 15 de noviembre de 2026. Complementa [`cloud/gcp/`](../gcp/README.md) y [`cloud/azure/`](../azure/README.md); no cambia cómo corre el ETL de la rama `etl-30m-r2`.

## Qué ya está hecho en la nube (no hay que repetirlo)

La ejecución de `scripts/etl_secuencia.py` (`fit`, `publish`, `verify`) terminó bien y dejó **`etl-30m-r2b` como release activa** en `gs://regolith-analogos-gabi0808/releases/atlas30/`:

- 1.793.175 ventanas, 1.459.470 clasificables y 174.595 elegibles para `arid_mars_surface_v2`.
- El modelo ajusta 7 de las 9 vistas; **espectral y radar siguen sin ajustar**.
- Las tres referencias (Jezero, Haworth, de Gerlache) están publicadas con 100 resultados cada una.
- Los dos sitios lunares tienen medidas la iluminación, la PSR, la temperatura máxima de Diviner y el CPR de Mini-RF. Haworth queda `volatile_target_psr` y de Gerlache `excluded_steep`. Temperatura mínima, abundancia de rocas, parámetro H y S1 no existen para el polo sur y quedan sin dato.

La medición lunar la hace el paso `luna` de `etl_secuencia.py`, con lectura remota. **Este espejo no la sustituye**: guarda copias verificadas de los rásteres para no depender de los servidores de NASA y para poder repetirla.

## Qué hace este trabajo

Dos trabajos distintos, uno por nube, a la vez:

| Nube | Cuerpo | Comando de la VM | Tamaño |
|---|---|---|---|
| GCP | Luna | `scripts/etl_referencias.py espejo --body Moon` | ~7,7 GB (LOLA 20 m, PSR, iluminación, Diviner, Mini-RF) |
| Azure | Marte | `scripts/etl_referencias.py espejo --body Mars` | ~0,5 GB (DTM HiRISE, THEMIS y CRISM de Jezero) |

Cada trabajo descarga los productos del [manifiesto](../../specs/sources/espejo-referencias-v1.json), verifica tamaño y hash, y escribe `docs/evidencia-espejo/<cuerpo>.json` con los hashes. Los archivos van a `data/raw/espejo/<cuerpo>/` y la evidencia a `docs/evidencia-espejo/`; los scripts de subida de las VM ya sincronizan ambas carpetas. Como los dos cuerpos escriben archivos distintos, **no hay nada que fusionar**: solo copiar la salida de Azure al bucket de GCS.

## Lanzar

Las VM clonan GitHub, así que la rama tiene que estar subida y sin cambios pendientes. El lanzador lo comprueba y se niega si no.

```bash
bash cloud/referencias/lanzar.sh            # simulación: comprobaciones y comandos exactos
```

```bash
RUN=1 bash cloud/referencias/lanzar.sh      # lanza GCP (Luna) y Azure (Marte) a la vez
```

Valores por defecto (todos se pueden cambiar por variable de entorno): proyecto de `gcloud config`, bucket `gs://regolith-analogos-gabi0808`, cuenta `analogosdatos22363`, Key Vault `analogos-kv-18333`, GCP en `us-central1-a` y Azure en `westus2`, cerca de las fuentes de EE. UU. Azure usa por defecto una VM `Regular` `Standard_D4s_v5` (4 vCPU, 16 GB), porque una suscripción de prueba gratuita no tiene Spot y permite 4 vCPU por región; el coste sale del crédito gratuito. Con una suscripción de pago y cuota Spot: `AZURE_PRIORITY=Spot AZURE_VM_SIZE=Standard_D8s_v5`.

Las VM se borran solas al terminar. Para seguirlas:

```bash
gcloud compute ssh <vm-gcp> --zone=us-central1-a --command='tail -f /var/log/analogos-etl.log'
```

```bash
STORAGE_ACCOUNT=analogosdatos22363 bash cloud/azure/ver-log.sh <vm-azure> blob
```

## Unir en GCS

Cuando terminen las dos, copia lo de Azure al bucket. Es pequeño (~0,5 GB), así que pasa por una carpeta temporal y no sobrescribe nada de lo que ya hay en GCS:

```bash
DRY_RUN=1 PREFIXES="data/raw/espejo docs/evidencia-espejo" STORAGE_ACCOUNT=analogosdatos22363 \
  GCS_BUCKET=gs://regolith-analogos-gabi0808 bash cloud/unir-almacen-azure-gcs.sh
```

Repite sin `DRY_RUN=1` si la lista es la esperada.

## Copia local

Del espejo (verificada contra el manifiesto):

```bash
gcloud storage rsync -r gs://regolith-analogos-gabi0808/data/raw/espejo data/raw/espejo
gcloud storage rsync -r gs://regolith-analogos-gabi0808/docs/evidencia-espejo docs/evidencia-espejo
./.pixi/envs/default/bin/python scripts/espejar_referencias.py verify --tier 1
```

Si todo verifica, fija los hashes en el manifiesto (nunca sobrescribe uno distinto) y commitea el cambio:

```bash
./.pixi/envs/default/bin/python scripts/espejar_referencias.py adopt \
  --evidence docs/evidencia-espejo/moon.json --evidence docs/evidencia-espejo/mars.json
```

De lo ya procesado, para que la API local vea las referencias lunares y los 1,46 M de ventanas (~570 MB: almacén 415 MB, release 120 MB y evidencia 37 MB):

```bash
PROVIDER=gcp GCS_BUCKET=gs://regolith-analogos-gabi0808 WITH_BASE=1 WITH_RELEASES=1 bash cloud/descargar-resultados.sh
mkdir -p data/features/modelos-similitud
cp releases/atlas30/etl-30m-r2b/similarity/model.joblib data/features/modelos-similitud/motor-similitud-ml-v1.joblib
```

La release trae el modelo en `similarity/model.joblib`; la API lo lee de `data/features/modelos-similitud/` (o de `ANALOGOS_SIMILARITY_MODEL`). Con esto `GET /api/similarity/references` debe listar Haworth y de Gerlache como `available: true`.

## Qué no cubre

- **Sitios nuevos de Marte.** Siguen sin existir: falta fijar la lista con fuentes oficiales y medir sus DTM. Cuando exista esa medición será otro paso de `etl_secuencia.py`, no del espejo.
- **Vistas espectral y radar.** El modelo no las ajusta; no depende del espejo.
