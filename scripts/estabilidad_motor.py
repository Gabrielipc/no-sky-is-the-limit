#!/usr/bin/env python3
"""How much does the similarity ranking depend on the random fit sample?

Fits the engine with the default seed (the reference), once more with the same seed (it must give
the same model) and with other seeds, and compares the top-N of each reference. A ranking that
changes a lot with the seed is a ranking of the sample, not of the terrain.

  python scripts/estabilidad_motor.py --seeds 1 2 3 --reference jezero --reference haworth-fondo
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipelines import etl_eligibility as eligibility  # noqa: E402
from pipelines import similarity_ml as sim  # noqa: E402

DEFAULT_STORE = Path(os.environ.get('ANALOGOS_FEATURE_STORE_DIR') or (ROOT / 'data/feature_store_v1'))
DEFAULT_EVIDENCE = ROOT / 'docs/evidencia-motor-similitud/estabilidad.json'
PROFILES = {'jezero': 'arid_mars_surface_v2', 'haworth-fondo': 'polar_cold_v1', 'de-gerlache-cresta': 'polar_cold_v1'}


def ranking(model: dict, spec: dict, args: argparse.Namespace, reference: str) -> list[str]:
    result = sim.SimilarityEngine(model, spec).search(
        args.store_dir, reference, profile=PROFILES.get(reference, eligibility.DEFAULT_PROFILE),
        limit=args.limit, memory_limit=args.memory_limit, threads=args.threads)
    return [r['region_id'] for r in result['results']]


def overlap(a: list[str], b: list[str], k: int) -> int:
    return len(set(a[:k]) & set(b[:k]))


def run(args: argparse.Namespace) -> dict:
    spec = sim.load_spec()
    fit = lambda seed: sim.fit_model(args.store_dir, spec, sample_size=args.sample_size, seed=seed,  # noqa: E731
                                     memory_limit=args.memory_limit, threads=args.threads)
    reference_model = fit(None)
    repeat_model = fit(None)
    models = {seed: fit(seed) for seed in args.seeds}
    report = {'measured_at': datetime.now(timezone.utc).isoformat(timespec='seconds'), 'store': str(args.store_dir),
              'sample_size': args.sample_size, 'limit': args.limit, 'references': {}}
    estimators = lambda m: {v: m['views'][v].get('covariance_estimator') for v in m['views'] if  # noqa: E731
                            m['views'][v].get('covariance_estimator')}
    report['covariance_estimators'] = {'default': estimators(reference_model),
                                       **{str(s): estimators(m) for s, m in models.items()}}
    for ref in args.reference:
        try:
            base = ranking(reference_model, spec, args, ref)
        except Exception as exc:  # a reference missing from this store must not hide the others
            report['references'][ref] = {'error': f'{type(exc).__name__}: {exc}'}
            continue
        again = ranking(repeat_model, spec, args, ref)
        report['references'][ref] = {
            'same_seed_identical_ranking': base == again,
            'by_seed': {str(s): {f'top{k}': overlap(base, ranking(m, spec, args, ref), k)
                                 for k in (10, 25, args.limit) if k <= args.limit} for s, m in models.items()},
        }
    flat = [v[key] for r in report['references'].values() for v in r.get('by_seed', {}).values()
            for key in v if key == f'top{args.limit}']
    report['summary'] = {'min_top_overlap': int(min(flat)) if flat else None,
                         'mean_top_overlap': float(np.mean(flat)) if flat else None,
                         'deterministic': all(r.get('same_seed_identical_ranking', True)
                                              for r in report['references'].values())}
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--store-dir', type=Path, default=DEFAULT_STORE)
    parser.add_argument('--seeds', type=int, nargs='+', default=[1, 2, 3])
    parser.add_argument('--sample-size', type=int, default=None)
    parser.add_argument('--reference', action='append', default=None)
    parser.add_argument('--limit', type=int, default=100)
    parser.add_argument('--memory-limit', default='6GB')
    parser.add_argument('--threads', type=int, default=os.cpu_count() or 4)
    parser.add_argument('--evidence', default=str(DEFAULT_EVIDENCE), help="'' para omitir")
    args = parser.parse_args()
    args.reference = args.reference or ['jezero', 'haworth-fondo', 'de-gerlache-cresta']
    report = run(args)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    if args.evidence:
        path = Path(args.evidence)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
