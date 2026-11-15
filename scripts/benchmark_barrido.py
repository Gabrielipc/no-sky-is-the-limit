"""Cost per usable window of the world sweep on stratified 100 km blocks.

Runs, on the five benchmark blocks (desert, mountain, coast, tropics, polar) and a
throw-away store:
  A. topographic stream without cover (GLO-30 tiles downloaded and deleted),
  B. cover backfill downloading each WorldCover/JRC tile once,
  C. cover by HTTP range on a sample of windows, for comparison.
A usable window is `rankable` with cover `measured`. Extrapolates to the local world
store when it exists. No raw tile is kept.

    bash scripts/ejecutar_minerales.sh scripts/benchmark_barrido.py [--workers 4] [--range-sample 10]
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
import os
from pathlib import Path
import platform
import shutil
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipelines import atlas_topography as topo  # noqa: E402
from pipelines import etl_cover as cover  # noqa: E402
from pipelines import etl_stream as stream_engine  # noqa: E402
from pipelines.etl_store import FeatureStore  # noqa: E402
from scripts import explorar_fuentes_atlas as eda  # noqa: E402

OUT = ROOT / 'docs/evidencia-barrido'
WORLD_STORE = ROOT / 'data/feature_store_v1'


def _counts(store: FeatureStore, column: str) -> dict:
    with store._connect() as conn:
        return dict(conn.execute(
            f"SELECT {column}, count(*) FROM base_windows GROUP BY 1 ORDER BY 2 DESC").fetchall())


def _by_label(store: FeatureStore, labels: dict[str, str]) -> dict:
    with store._connect() as conn:
        rows = conn.execute("""
            SELECT batch_id, qa_status, cover_status, analog_surface_eligibility, count(*)
            FROM base_windows GROUP BY ALL""").fetchall()
    out: dict = {}
    for batch_id, qa, cov, elig, n in rows:
        d = out.setdefault(labels[batch_id], {'windows': 0, 'rankable': 0, 'usable': 0, 'eligible_arid': 0,
                                              'cover_status': Counter()})
        d['windows'] += n
        if qa == 'rankable':
            d['rankable'] += n
            d['cover_status'][cov] += n
            if cov == 'measured':
                d['usable'] += n
            if elig == 'eligible_arid_exposed':
                d['eligible_arid'] += n
    return {k: {**v, 'cover_status': dict(v['cover_status'])} for k, v in out.items()}


def world_counts() -> dict | None:
    if not (WORLD_STORE / 'base').exists():
        return None
    store = FeatureStore(WORLD_STORE)
    with store._connect() as conn:
        total, rankable, pending = conn.execute("""
            SELECT count(*), count(*) FILTER (WHERE qa_status = 'rankable'),
                   count(*) FILTER (WHERE qa_status = 'rankable'
                                    AND (cover_status IS NULL OR cover_status IN ('not_requested', 'cover_fetch_failed')))
            FROM base_windows""").fetchone()
    return {'windows': total, 'rankable': rankable, 'rankable_pending_cover': pending,
            'batches_recorded': len(store.batch_records())}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workers', type=int, default=min(4, os.cpu_count() or 2))
    parser.add_argument('--range-sample', type=int, default=10, help='Ventanas por estrato leídas por rangos')
    parser.add_argument('--use-local-cache', action='store_true',
                        help='Usar teselas ya cacheadas (por defecto se ignoran para medir transferencia real)')
    args = parser.parse_args()
    if not args.use_local_cache:
        os.environ['ATLAS_IGNORE_LOCAL_CACHE'] = '1'  # inherited by worker processes

    batches = list(topo.benchmark_batches())
    labels = {b.id: b.label for b in batches}
    tmp = Path(tempfile.mkdtemp(prefix='benchmark-barrido-'))
    try:
        store_dir = tmp / 'store'
        store = FeatureStore(store_dir, memory_limit='2GB', threads=2)

        t0 = time.perf_counter()
        topo_summary = stream_engine.run_stream(batches, store_dir, include_cover=False,
                                                cpu_workers=args.workers, io_workers=8, max_temp_gb=6.0)
        t_topo = time.perf_counter() - t0
        after_topo = _by_label(store, labels)

        windows = cover.select_windows(store)
        t0 = time.perf_counter()
        cover_summary = cover.run_cover_backfill(store_dir, windows, transport='download', workers=args.workers)
        t_cover = time.perf_counter() - t0
        by_stratum = _by_label(store, labels)

        # C. Range transport on a sample per stratum, written to a separate store.
        sample = []
        per_label: Counter = Counter()
        with store._connect() as conn:
            ids = conn.execute("""
                SELECT region_id, longitude, latitude, land_fraction, batch_id FROM base_windows
                WHERE qa_status = 'rankable' ORDER BY hash(region_id)""").fetchall()
        for rid, lon, lat, lf, bid in ids:
            if per_label[labels[bid]] < args.range_sample:
                per_label[labels[bid]] += 1
                sample.append({'region_id': rid, 'longitude': lon, 'latitude': lat, 'land_fraction': lf})
        range_dir = tmp / 'range'
        FeatureStore(range_dir)
        t0 = time.perf_counter()
        range_summary = cover.run_cover_backfill(range_dir, sample, transport='range', workers=args.workers)
        t_range = time.perf_counter() - t0

        rankable = sum(v['rankable'] for v in by_stratum.values())
        usable = sum(v['usable'] for v in by_stratum.values())
        world = world_counts()
        result = {
            'schema': 1,
            'question': 'Costo por ventana utilizable (rankable con cobertura medida) del barrido mundial',
            'machine': {'platform': platform.platform(), 'cpu_count': os.cpu_count(), 'workers': args.workers},
            'local_cache_used': args.use_local_cache,
            'blocks': {b.label: {'batch_id': b.id, 'zone': b.zone} for b in batches},
            'phase_topography': {
                'elapsed_s': round(t_topo, 1), 'downloaded_tiles': topo_summary['downloaded_tiles'],
                'downloaded_mb': round(topo_summary['downloaded_bytes'] / 1e6, 1),
                'download_failures': topo_summary['download_failures'],
                'incomplete_batches': topo_summary['incomplete_batches'],
                'windows_by_stratum': {k: {kk: v[kk] for kk in ('windows', 'rankable')} for k, v in after_topo.items()},
            },
            'phase_cover_download': {
                'elapsed_s': round(t_cover, 1), 'windows': cover_summary['windows'],
                'blocks': cover_summary['blocks'], 'downloaded_mb': round(cover_summary['downloaded_bytes'] / 1e6, 1),
                'cover_status': cover_summary['cover_status'], 'download_failures': cover_summary['download_failures'],
                'asset_failures': cover_summary['asset_failures'],
                's_per_window': round(t_cover / max(cover_summary['windows'], 1), 3),
            },
            'phase_cover_range_sample': {
                'elapsed_s': round(t_range, 1), 'windows': range_summary['windows'],
                'cover_status': range_summary['cover_status'],
                's_per_window_wall': round(t_range / max(range_summary['windows'], 1), 3),
            },
            'by_stratum': by_stratum,
            'totals': {'rankable': rankable, 'usable': usable,
                       's_per_usable_window': round((t_topo + t_cover) / max(usable, 1), 3),
                       'mb_per_usable_window': round(
                           (topo_summary['downloaded_bytes'] + cover_summary['downloaded_bytes']) / 1e6 / max(usable, 1), 3)},
            'world_store': world,
        }
        if world:
            per_win = t_cover / max(cover_summary['windows'], 1)
            mb_per_win = cover_summary['downloaded_bytes'] / 1e6 / max(cover_summary['windows'], 1)
            result['world_cover_extrapolation'] = {
                'windows': world['rankable_pending_cover'],
                'hours_at_benchmark_rate': round(world['rankable_pending_cover'] * per_win / 3600, 1),
                'transfer_gb_at_benchmark_rate': round(world['rankable_pending_cover'] * mb_per_win / 1000, 1),
                'note': 'Ritmo medido con los mismos workers en 5 bloques; la reutilización de teselas en el '
                        'barrido real (más ventanas por tesela) reduce bytes por ventana.',
            }
        OUT.mkdir(parents=True, exist_ok=True)
        eda.write(OUT / 'benchmark.json', result)
        eda.write(OUT / 'manifest.json', {'schema': 1, 'files': [
            {'path': str(p.relative_to(ROOT)), 'bytes': p.stat().st_size, 'sha256': eda.digest(p)}
            for p in (Path(__file__), ROOT / 'pipelines/etl_cover.py', ROOT / 'pipelines/etl_stream.py',
                      OUT / 'benchmark.json')]})
        print(json.dumps({k: result[k] for k in ('phase_topography', 'phase_cover_download',
                                                 'phase_cover_range_sample', 'totals')}, indent=1))
        print(json.dumps(result.get('world_cover_extrapolation'), indent=1))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == '__main__':
    main()
