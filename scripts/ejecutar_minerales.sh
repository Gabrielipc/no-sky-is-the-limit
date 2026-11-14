#!/usr/bin/env bash
set -euo pipefail
TASK_ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
if [ ! -x "$TASK_ROOT/.tools/minerales/bin/python" ]; then
  echo 'Ejecuta primero: bash scripts/preparar_minerales.sh' >&2
  exit 1
fi
# A system-site-packages venv must retain the geospatial data of its Pixi base.
export PROJ_DATA="$TASK_ROOT/.pixi/envs/default/share/proj"
export GDAL_DATA="$TASK_ROOT/.pixi/envs/default/share/gdal"
exec "$TASK_ROOT/.tools/minerales/bin/python" "$@"
