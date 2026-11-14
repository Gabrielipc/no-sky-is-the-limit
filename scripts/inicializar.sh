#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

for tool in curl bash; do
  command -v "$tool" >/dev/null 2>&1 || { printf 'Error: falta %s.\n' "$tool" >&2; exit 1; }
done
for file in pixi.toml frontend/package-lock.json data/regions.json; do
  [[ -f "$file" ]] || { printf 'Error: falta %s.\n' "$file" >&2; exit 1; }
done

export PIXI_HOME="$ROOT/.tools/pixi"
PIXI="$PIXI_HOME/bin/pixi"
if [[ ! -x "$PIXI" ]]; then
  printf '\nInstalando Pixi localmente desde el instalador oficial...\n'
  installer="$(mktemp "${TMPDIR:-/tmp}/pixi-install.XXXXXX")"
  trap 'rm -f "$installer"' EXIT
  curl -fsSL https://pixi.sh/install.sh -o "$installer"
  PIXI_HOME="$ROOT/.tools/pixi" PIXI_BIN_DIR="$ROOT/.tools/pixi/bin" \
    PIXI_NO_PATH_UPDATE=1 PIXI_NO_TELEMETRY=1 bash "$installer"
fi

mkdir -p data/raw data/normalized data/features data/visual releases
printf '\nInstalando entorno Pixi...\n'
if [[ -f pixi.lock ]]; then
  "$PIXI" install --locked
else
  printf 'No existe pixi.lock: se resolverán dependencias y se creará. Comparte ese archivo con el equipo.\n'
  "$PIXI" install
fi
printf '\nComprobando CRS planetarios...\n'
"$PIXI" run check-env
printf '\nInstalando dependencias del frontend...\n'
(cd frontend && "$PIXI" run npm ci --no-audit --no-fund)
printf '\nEjecutando pruebas y compilación...\n'
"$PIXI" run test
"$PIXI" run build
printf '\nProyecto inicializado. En terminales separadas ejecuta:\n  make backend\n  make frontend\n\nAbre http://localhost:5173\n'
