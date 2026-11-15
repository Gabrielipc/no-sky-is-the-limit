#!/usr/bin/env python3
"""Latency benchmark of the similarity engine: SQL path versus the in-memory candidate pool.

    python scripts/benchmark_motor.py
    python scripts/benchmark_motor.py --reference jezero --repeat 5 --scale-to 1500000 --json out.json

`--scale-to` tiles the in-memory pool to simulate the cloud store (~1.45 M windows) without needing it.
The scaled run measures the numeric part only; the SQL scan is measured at the real local size.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import platform
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

from pipelines import similarity_ml as sim  # noqa: E402

DEFAULT_STORE = Path(os.environ.get('ANALOGOS_FEATURE_STORE_DIR') or (ROOT / 'data/feature_store_v1'))
DEFAULT_MODEL = sim.DEFAULT_MODEL_DIR / 'motor-similitud-ml-v1.joblib'


def timed(fn, repeat: int) -> dict:
    samples = []
    for _ in range(repeat):
        t = time.perf_counter()
        fn()
        samples.append(time.perf_counter() - t)
    return {'median_s': round(statistics.median(samples), 4), 'min_s': round(min(samples), 4),
            'max_s': round(max(samples), 4), 'runs': repeat}


def scaled(pool: sim.CandidatePool, size: int) -> sim.CandidatePool:
    """Tile the pool's arrays up to `size` rows with unique region ids."""
    n = len(pool)
    reps = -(-size // n)

    def tile(d: dict) -> dict:
        out = {}
        for k, v in d.items():
            arr = np.ma.filled(v, np.nan) if np.ma.isMaskedArray(v) and v.dtype.kind == 'f' else v
            out[k] = np.tile(np.asarray(arr), reps)[:size]
        return out

    data = tile(pool.data)
    ids = np.asarray(pool.data['region_id'], dtype=object)
    data['region_id'] = np.array([f'{ids[i % n]}#{i // n}' for i in range(size)], dtype=object)
    return sim.CandidatePool(profile=pool.profile, conn=pool.conn, present=pool.present, data=data,
                             cand_raw=tile(pool.cand_raw), cand_z=tile(pool.cand_z),
                             eligible=np.tile(pool.eligible, reps)[:size])


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--store', type=Path, default=DEFAULT_STORE)
    ap.add_argument('--model', type=Path, default=DEFAULT_MODEL)
    ap.add_argument('--reference', default='jezero')
    ap.add_argument('--repeat', type=int, default=3)
    ap.add_argument('--limit', type=int, default=25)
    ap.add_argument('--scale-to', type=int, default=0, help='simulate a store with this many windows')
    ap.add_argument('--json', type=Path, help='write the results to this file')
    args = ap.parse_args()

    engine = sim.SimilarityEngine.load(args.model)
    report = {'machine': {'platform': platform.platform(), 'cpu_count': os.cpu_count()},
              'reference': args.reference, 'limit': args.limit, 'sql_path': {}, 'pool_path': {}}

    for eligible in (True, False):
        key = 'only_eligible' if eligible else 'all_windows'
        report['sql_path'][key] = timed(lambda e=eligible: engine.search(
            args.store, args.reference, only_eligible=e, limit=args.limit), args.repeat)

    t = time.perf_counter()
    pool = engine.build_pool(args.store)
    report['pool_build_s'] = round(time.perf_counter() - t, 3)
    report['pool_rows'] = len(pool)
    report['pool_eligible_rows'] = int(pool.eligible.sum())
    for eligible in (True, False):
        key = 'only_eligible' if eligible else 'all_windows'
        engine.search(args.store, args.reference, only_eligible=eligible, limit=args.limit, pool=pool)  # warm up
        report['pool_path'][key] = timed(lambda e=eligible: engine.search(
            args.store, args.reference, only_eligible=e, limit=args.limit, pool=pool), args.repeat)

    if args.scale_to > len(pool):
        big = scaled(pool, args.scale_to)
        report['scaled'] = {'rows': len(big)}
        engine.search(args.store, args.reference, only_eligible=False, limit=args.limit, pool=big)
        report['scaled']['all_windows'] = timed(lambda: engine.search(
            args.store, args.reference, only_eligible=False, limit=args.limit, pool=big), max(1, args.repeat - 1))
    pool.close()

    print(f"Referencia {args.reference} · {report['pool_rows']} ventanas rankables "
          f"({report['pool_eligible_rows']} elegibles) · {report['machine']['cpu_count']} CPU")
    print(f"{'camino':<12}{'filtro':<16}{'mediana':>9}{'mínimo':>9}{'máximo':>9}")
    for path in ('sql_path', 'pool_path'):
        for key, r in report[path].items():
            print(f"{path[:-5]:<12}{key:<16}{r['median_s']:>8.3f}s{r['min_s']:>8.3f}s{r['max_s']:>8.3f}s")
    print(f"construcción del pool: {report['pool_build_s']:.2f} s (una vez, al arrancar)")
    if 'scaled' in report:
        r = report['scaled']['all_windows']
        print(f"pool simulado de {report['scaled']['rows']} filas, todas las ventanas: "
              f"mediana {r['median_s']:.2f} s, máximo {r['max_s']:.2f} s")
    if args.json:
        args.json.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
