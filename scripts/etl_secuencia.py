#!/usr/bin/env python3
"""Run, in order, every ETL step that can run with the data available now (cloud-agnostic).

Steps (default: build,sample,ati-cluster):
  build        Global surface layers (`etl_capa_global.py build`). Needs only Earthdata/CEDA.
  sample       Sample the layers at every Earth window (`etl_capa_global.py sample`).
               Skipped while the store has no base windows (world sweep not restored).
  ati-cluster  Fine apparent thermal inertia on K random MODIS tiles (`etl_superficie.py`),
               the background population of the engine's thermal view. Needs base windows.
  fit          Fit the similarity engine (`motor_similitud.py fit`) into --model. Needs base windows.
  publish      Publish an Atlas release (`etl_pipeline.py publish`) with the engine results and the
               model when one is available (--model, written by `fit`). Needs base windows.
  luna         Measure the lunar references (`etl_luna.py referencia`): topography, illumination, PSR,
               Diviner Tmax and Mini-RF CPR. Writes the Moon windows and `enrichment_lunar`; it does not
               need Earth base windows. Run it before `fit` so the lunar references exist.
  verify       Check the published release against the contracts (`verificar_release.py`) and keep
               the report in docs/evidencia-capa-global/verificacion-<version>.json.

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
STEPS = ('build', 'sample', 'ati-cluster', 'luna', 'fit', 'publish', 'verify')
DEFAULT_MODEL = ROOT / 'data/features/modelos-similitud/motor-similitud-ml-v1.joblib'


def base_windows(store_dir: Path) -> int:
    """Number of base parquet parts (cheap proxy for 'the sweep is restored')."""
    return sum(1 for _ in (store_dir / 'base').rglob('*.parquet')) if (store_dir / 'base').is_dir() else 0


def commands(args: argparse.Namespace) -> dict[str, list[str]]:
    py = sys.executable
    if not args.release_version:
        args.release_version = f"etl-{datetime.now(timezone.utc):%Y%m%d-%H%M}"
    layers = sum((['--layer', layer] for layer in args.layer or []), [])
    return {
        'build': [py, str(ROOT / 'scripts/etl_capa_global.py'), 'build', '--workers', str(args.workers), *layers],
        'sample': [py, str(ROOT / 'scripts/etl_capa_global.py'), 'sample', '--store-dir', str(args.store_dir)],
        'ati-cluster': [py, str(ROOT / 'scripts/etl_superficie.py'), '--store-dir', str(args.store_dir),
                        '--dimension', 'apparent_thermal_inertia', '--no-topographic-candidates',
                        '--background-cluster-tiles', str(args.ati_tiles), '--background-per-tile',
                        str(args.ati_per_tile), '--skip-measured', '--workers', str(args.workers)],
        'luna': [py, str(ROOT / 'scripts/etl_luna.py'), '--store-dir', str(args.store_dir),
                 '--memory-limit', args.memory_limit, 'referencia'],
        'fit': [py, str(ROOT / 'scripts/motor_similitud.py'), '--store-dir', str(args.store_dir), '--model',
                str(args.model), '--memory-limit', args.memory_limit, '--threads', str(os.cpu_count() or 4), 'fit'],
        'publish': [py, str(ROOT / 'scripts/etl_pipeline.py'), '--store-dir', str(args.store_dir), 'publish',
                    '--version', args.release_version,
                    *(['--set-current'] if args.set_current else []),
                    *(['--similarity-model', str(args.similarity_model or args.model)]
                      if (args.similarity_model or Path(args.model).is_file() or 'fit' in args.steps) else [])],
        'verify': ['bash', '-c', f'{py} "{ROOT / "scripts/verificar_release.py"}" '
                   f'"{ROOT / "releases/atlas30" / args.release_version}" '
                   f'> "{ROOT / "docs/evidencia-capa-global" / ("verificacion-" + args.release_version + ".json")}"'],
    }


def run(args: argparse.Namespace, runner=subprocess.run) -> dict:
    steps = [s.strip() for s in args.steps.split(',') if s.strip()]
    unknown = set(steps) - set(STEPS)
    if unknown:
        raise SystemExit(f'Pasos desconocidos: {sorted(unknown)}; válidos: {", ".join(STEPS)}')
    cmds = commands(args)
    summary = {'started_at': datetime.now(timezone.utc).isoformat(timespec='seconds'), 'steps': {}}
    for step in steps:
        needs_base = step in ('sample', 'ati-cluster', 'fit', 'publish', 'verify')
        if step == 'verify' and summary['steps'].get('publish', {}).get('status') in ('failed', 'skipped'):
            summary['steps'][step] = {'status': 'skipped', 'reason': 'no se publicó la release'}
            continue
        if step == 'publish' and summary['steps'].get('fit', {}).get('status') == 'failed':
            summary['steps'][step] = {'status': 'skipped', 'reason': 'el ajuste del motor falló'}
            print('== publish: omitido (falló fit)', flush=True)
            continue
        if needs_base and base_windows(args.store_dir) == 0:
            summary['steps'][step] = {'status': 'skipped', 'reason': 'el almacén no tiene ventanas base todavía'}
            print(f'== {step}: omitido (sin ventanas base en {args.store_dir})', flush=True)
            continue
        print(f'== {step}: {" ".join(cmds[step][1:])}', flush=True)
        if step == 'verify':
            (ROOT / 'docs/evidencia-capa-global').mkdir(parents=True, exist_ok=True)
        t0 = time.monotonic()
        proc = runner(cmds[step], cwd=str(ROOT))
        status = 'ok' if proc.returncode == 0 else 'failed'
        summary['steps'][step] = {'status': status, 'returncode': proc.returncode,
                                  'elapsed_s': round(time.monotonic() - t0, 1)}
        if step == 'build':
            report = ROOT / 'docs/evidencia-capa-global/build.json'
            if report.exists():  # per-layer status (a failing product does not fail the step)
                summary['steps'][step]['layers'] = {k: v.get('status') for k, v in
                                                    json.loads(report.read_text(encoding='utf-8')).items()}
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
    parser.add_argument('--similarity-model', help='Modelo existente para publish (por defecto --model)')
    parser.add_argument('--model', type=Path, default=DEFAULT_MODEL, help='Ruta del modelo que escribe fit')
    parser.add_argument('--memory-limit', default='6GB')
    parser.add_argument('--set-current', action='store_true', help='Activar la release publicada')
    parser.add_argument('--summary', default=str(DEFAULT_SUMMARY), help="'' para omitir")
    parser.add_argument('--strict', action='store_true', help='Salir con error si algún paso falla')
    args = parser.parse_args(argv)
    summary = run(args)
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
    if args.strict and any(s['status'] == 'failed' for s in summary['steps'].values()):
        sys.exit(1)


if __name__ == '__main__':
    main()
