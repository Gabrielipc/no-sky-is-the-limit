# Primera release: ajuste del motor y empaquetado

Procedimiento para publicar `etl-30m-r1`: el atlas mundial de 30 m con el motor de similitud ajustado y sus resultados para Jezero. Todo corre en una VM efímera junto al bucket. A tu Mac no llega nada pesado.

## Qué contiene

| Pieza | Estado en r1 |
|---|---|
| `windows/windows.parquet` | ~1,8 M ventanas terrestres: topografía, forma, cobertura, elegibilidad. Columnas `*_cmg` presentes pero vacías (`on_demand_fetchable`) |
| Motor: vistas ajustadas | `escabrosidad`, `forma_hipsometrica`, `organizacion`, `regimen_morfologico` (topografía del barrido nuevo) |
| Motor: vistas sin ajustar | `termica`, `espectral`, `radar`, `entorno_superficial`, `emisividad_cmg` aparecen como `not_fitted` hasta las releases siguientes |
| `similarity/jezero.json` | Top 100 de análogos con pesos por defecto, perfil árido |
| `similarity/haworth-fondo.json`, `de-gerlache-cresta.json` | **No se generan** (`failed`): el almacén del bucket solo tiene ventanas terrestres. Hacen falta las ventanas lunares (`scripts/etl_luna.py`) |
| `similarity/model.joblib` | El modelo ajustado: el backend lo usa para búsquedas con pesos personalizados |
| `manifest.json` | `release_contract: atlas30-release-v1`, conteos, normalización, bloque `similarity` |

Estado del motor: `unsupervised_pending_blind_validation`. El frontend lo muestra como experimental.

## Paso 0: requisitos

1. **El barrido mundial terminó.** Debe haber 22 303 lotes:
   ```bash
   gcloud storage ls gs://regolith-analogos-gabi0808/data/feature_store_v1/manifests/batches/ | wc -l
   ```
   Y no debe quedar ninguna VM `analogos-etl-*` en `gcloud compute instances list`.
2. **El código está en `fuentes-de-datos`:** contratos, `publish --similarity-model`, pasos `fit`/`publish`/`verify` del orquestador y `verificar_release.py`.

## Paso 1: ajustar y publicar (una VM, ~15–25 min)

En `europe-west3`, la región del bucket: el almacén se restaura sin salir de la región y no hace falta Earthdata.

```bash
PROJECT_ID="adroit-hall-514719-d5" GCS_BUCKET="gs://regolith-analogos-gabi0808" \
REPO_URL="https://github.com/Gabrielipc/no-sky-is-the-limit.git" REPO_BRANCH="fuentes-de-datos" \
ZONE="europe-west3-a" ETL_SCRIPT="scripts/etl_secuencia.py" \
ETL_ARGS="--steps fit,publish,verify --release-version etl-30m-r1 --set-current" \
  bash cloud/gcp/launch-spot.sh
```

Qué hace la VM:
1. **Restaura** el almacén desde el bucket.
2. **`fit`:**
   - muestra 200 000 ventanas terrestres rankables fuera de la cuenca reservada de Mojave;
   - ajusta las transformaciones cuantil-normal, las covarianzas robustas por vista y la GMM de regímenes;
   - guarda `data/features/modelos-similitud/motor-similitud-ml-v1.joblib`.
3. **`publish`:**
   - escribe `releases/atlas30/etl-30m-r1/` (ventanas, procedencia, lotes);
   - ejecuta el motor para cada referencia con nombre y copia el modelo a `similarity/`;
   - marca la versión como activa (`current`).
4. **`verify`:** comprueba la release contra `specs/api/` y deja el informe en `docs/evidencia-capa-global/verificacion-etl-30m-r1.json`.
5. **Cierre:** sube `releases/` y `docs/evidencia-*` al bucket y se borra.

Para seguirla:

```bash
gcloud compute instances get-serial-port-output <vm> --zone=europe-west3-a --project=adroit-hall-514719-d5 | grep startup-script | tail -30
```

## Paso 2: comprobar sin descargar la release

```bash
gcloud storage cat gs://regolith-analogos-gabi0808/docs/evidencia-capa-global/secuencia.json
gcloud storage cat gs://regolith-analogos-gabi0808/docs/evidencia-capa-global/verificacion-etl-30m-r1.json | head -60
```

- **`errors` debe estar vacío.**
- **Avisos esperados en r1:**
  - `similitud haworth-fondo: failed` y `de-gerlache-cresta: failed` (sin ventanas lunares);
  - columnas `*_cmg` todas `on_demand_fetchable`.
- **`summary.similarity.jezero`:** debe traer 100 resultados, los avisos del motor y las 3 primeras ventanas.

## Paso 3: entregar al equipo

La release vive en `gs://regolith-analogos-gabi0808/releases/atlas30/etl-30m-r1/`. Para el servidor del backend:

```bash
gcloud storage rsync -r gs://regolith-analogos-gabi0808/releases/atlas30/etl-30m-r1 releases/atlas30/etl-30m-r1
echo etl-30m-r1 > releases/atlas30/current
python scripts/verificar_release.py releases/atlas30/etl-30m-r1
```

- **Endpoints que funcionan sin cambios:** `/api/atlas`, `/coverage`, `/search` y `/candidates/{id}` leen la release. La ficha de candidata ya muestra las columnas nuevas.
- **Similitud:** `similarity/jezero.json` se expone con el endpoint `GET /api/atlas/similarity/{referencia}` de la [guía de backend](guia-backend.md#1-similitud-precalculada-recomendado-para-empezar).
- **Búsquedas con pesos personalizados:** usad `similarity/model.joblib` de la misma release y el almacén del bucket ([guía](guia-backend.md#2-motor-en-tiempo-de-consulta-pesos-personalizados)).
- **Si la quieres en tu Mac:** `PROVIDER=gcp GCS_BUCKET=gs://regolith-analogos-gabi0808 WITH_RELEASES=1 bash cloud/descargar-resultados.sh`. Son cientos de MB.

## Siguientes releases

| Release | Qué añade | Requisito |
|---|---|---|
| r2 | Columnas `*_cmg` con valores. Se ajustan `entorno_superficial` y `emisividad_cmg` | Capas globales construidas (Azure) y muestreadas junto al barrido (`--steps sample`) |
| r3 | Vista `termica` ajustada sin sesgo | ATI fina por conglomerados (`--steps ati-cluster`, ~3–6 h) |
| r4 | Referencias lunares | Ventanas lunares en el almacén (`etl_luna.py`) |
| — | Vista `espectral` | Conectar `puente_espectral.py` al almacén |

Cada release nueva repite el paso 1 con otro `--release-version`. Las releases son inmutables y la anterior queda disponible para volver atrás.
