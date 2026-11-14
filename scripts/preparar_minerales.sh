#!/usr/bin/env bash
set -euo pipefail
TASK_ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$TASK_ROOT"
if [ ! -x .pixi/envs/default/bin/python ]; then
  echo 'Inicializa primero el entorno con scripts/inicializar.sh.' >&2
  exit 1
fi
.pixi/envs/default/bin/python -m venv --system-site-packages .tools/minerales
.tools/minerales/bin/python -m pip install --only-binary=:all: --no-deps -r requirements-minerales.txt
echo 'Lector listo: bash scripts/ejecutar_minerales.sh scripts/analizar_minerales.py'
