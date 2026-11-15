#!/usr/bin/env python3
"""Run, in order, every ETL step that can run with the data available now (cloud-agnostic).

Steps (default: build,sample,ati-cluster):
  build        Global surface layers (`etl_capa_global.py build`). Needs only Earthdata/CEDA.
  sample       Sample the layers at every Earth window (`etl_capa_global.py sample`).
               Skipped while the store has no base windows (world sweep not restored).
  ati-cluster  Fine apparent thermal inertia on K random MODIS tiles (`etl_superficie.py`),
               the background population of the engine's thermal view. Needs base windows.
  publish      Publish an Atlas release (`etl_pipeline.py publish`), with engine results if
               --similarity-model is given. Needs base windows.

A failing step is reported and the next ones still run (unless they depend on it). A summary
is written to docs/evidencia-capa-global/secuencia.json, which the cloud sync uploads.

  bash scripts/ejecutar_minerales.sh scripts/etl_secuencia.py --steps build,sample
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

DEFAULT_STORE = Path(os.environ.get('ANALOGOS_FEATURE_STORE_DIR') or (ROOT / 'data/feature_store_v1'))
DEFAULT_SUMMARY = ROOT / 'docs/evidencia-capa-global/secuencia.json'
STEPS = ('build', 'sample', 'ati-cluster', 'publish')


def base_windows(store_dir: Path) -> int:
    """Number of base parquet parts (cheap proxy for 'the sweep is restored')."""
    return sum(1 for _ in (store_dir / 'base').rglob('*.parquet')) if (store_dir / 'base').is_dir() else 0


def commands(args: argparse.Namespace) -> dict[str, list[str]]:
    py = sys.executable
    layers = sum((['--layer', layer] for layer in args.layer or []), [])
    return {
        'build': [py, str(ROOT / 'scripts/etl_capa_global.py'), 'build', '--workers', str(args.workers), *layers],
        'sample': [py, str(ROOT / 'scripts/etl_capa_global.py'), 'sample', '--store-dir', str(args.store_dir)],
        'ati-cluster': [py, str(ROOT / 'scripts/etl_superficie.py'), '--store-dir', str(args.store_dir),
                        '--dimension', 'apparent_thermal_inertia', '--no-topographic-candidates',
                        '--background-cluster-tiles', str(args.ati_tiles), '--background-per-tile',
                        str(args.ati_per_tile), '--skip-measured', '--workers', str(args.workers)],
        'publish': [py, str(ROOT / 'scripts/etl_pipeline.py'), '--store-dir', str(args.store_dir), 'publish',
                    '--version', args.release_version or f"etl-{datetime.now(timezone.utc):%Y%m%d-%H%M}",
                    *(['--similarity-model', args.similarity_model] if args.similarity_model else [])],
    }


def run(args: argparse.Namespace, runner=subprocess.run) -> dict:
    steps = [s.strip() for s in args.steps.split(',') if s.strip()]
    unknown = set(steps) - set(STEPS)
    if unknown:
        raise SystemExit(f'Pasos desconocidos: {sorted(unknown)}; válidos: {", ".join(STEPS)}')
    cmds = commands(args)
    summary = {'started_at': datetime.now(timezone.utc).isoformat(timespec='seconds'), 'steps': {}}
    for step in steps:
        needs_base = step in ('sample', 'ati-cluster', 'publish')
        if needs_base and base_windows(args.store_dir) == 0:
            summary['steps'][step] = {'status': 'skipped', 'reason': 'el almacén no tiene ventanas base todavía'}
            print(f'== {step}: omitido (sin ventanas base en {args.store_dir})', flush=True)
            continue
        print(f'== {step}: {" ".join(cmds[step][1:])}', flush=True)
        t0 = time.monotonic()
        proc = runner(cmds[step], cwd=str(ROOT))
        status = 'ok' if proc.returncode == 0 else 'failed'
        summary['steps'][step] = {'status': status, 'returncode': proc.returncode,
                                  'elapsed_s': round(time.monotonic() - t0, 1)}
        print(f'== {step}: {status} en {summary["steps"][step]["elapsed_s"]} s', flush=True)
    summary['finished_at'] = datetime.now(timezone.utc).isoformat(timespec='seconds')
    if args.summary:
        path = Path(args.summary)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return summary


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--steps', default='build,sample,ati-cluster', help=f'Separados por coma: {", ".join(STEPS)}')
    parser.add_argument('--store-dir', type=Path, default=DEFAULT_STORE)
    parser.add_argument('--layer', action='append', help='Solo estas capas en build (repetible)')
    parser.add_argument('--workers', type=int, default=8)
    parser.add_argument('--ati-tiles', type=int, default=40)
    parser.add_argument('--ati-per-tile', type=int, default=5)
    parser.add_argument('--release-version')
    parser.add_argument('--similarity-model')
    parser.add_argument('--summary', default=str(DEFAULT_SUMMARY), help="'' para omitir")
    parser.add_argument('--strict', action='store_true', help='Salir con error si algún paso falla')
    args = parser.parse_args(argv)
    summary = run(args)
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
    if args.strict and any(s['status'] == 'failed' for s in summary['steps'].values()):
        sys.exit(1)


if __name__ == '__main__':
    main()
