#!/usr/bin/env python3
"""Unified ETL CLI: Raw geospatial rasters -> Entrega 3 Parquet Feature Store + DuckDB out-of-core."""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from contextlib import ExitStack
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import time

import rasterio

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipelines import atlas_sources as sources
from pipelines import atlas_topography as topo
from pipelines import etl_extractors as extractors
from pipelines import etl_stream as stream_engine
from pipelines.etl_store import FeatureStore

DEFAULT_STORE = ROOT / 'data/feature_store_v1'
JEZERO_REF = {'relief_m': 120.27, 'slope_p50_deg': 3.07, 'slope_p90_deg': 9.24}


def _process_single_batch(
    batch: topo.Batch,
    stride: int,
    mode: str,
    include_cover: bool,
    store_dir: str,
    memory_limit: str,
    threads: int,
) -> tuple[str, str, int, int, float]:
    started = time.perf_counter()
    land = topo.Land()
    inventory = sources.glo_inventory()
    store = FeatureStore(Path(store_dir), memory_limit=memory_limit, threads=threads)
    rows = []
    manifests = []
    with ExitStack() as stack:
        stack.enter_context(rasterio.Env(
            GDAL_DISABLE_READDIR_ON_OPEN='EMPTY_DIR',
            GDAL_HTTP_MAX_RETRY=2,
            GDAL_HTTP_TIMEOUT=30,
            GDAL_CACHEMAX=256 * 1024 ** 2,
        ))
        rasters = topo.Rasters(stack, mode)
        for site in topo.windows(batch, stride):
            row, m_rows = extractors.extract_base_window(
                site, land, rasters, inventory, include_cover=include_cover
            )
            rows.append(row)
            manifests.extend(m_rows)
    written = store.write_base_batch(batch.id, rows, manifests)
    store.mark_batch_completed(batch.id, {
        'batch_id': batch.id,
        'label': batch.label,
        'windows': len(rows),
        'partitions': len(written),
        'mode': mode,
        'completed_at': datetime.now(timezone.utc).isoformat(),
    })
    return batch.label, batch.id, len(rows), len(written), time.perf_counter() - started


def _filter_cached_batches(selected: list[topo.Batch]) -> list[topo.Batch]:
    glo_cache_dir = sources.CACHE / 'glo30'
    cached_tifs = {p.name for p in glo_cache_dir.glob('*.tif')} if glo_cache_dir.exists() else set()
    if not cached_tifs:
        return []
    inventory = sources.glo_inventory()
    kept: list[topo.Batch] = []
    for batch in selected:
        assets, _ = topo.batch_assets(batch, inventory, context=False)
        if any(entry['id'] in cached_tifs for entry in assets):
            kept.append(batch)
    return kept


def _select_batches(args: argparse.Namespace, store: FeatureStore) -> list[topo.Batch]:
    land = topo.Land()
    if args.scope == 'pilot':
        selected = list(topo.benchmark_batches())
    else:
        from scripts.atlas30 import batches as atlas_batches
        selected = atlas_batches('world', land)

    total_candidates = len(selected)
    if getattr(args, 'mode', None) == 'cache':
        selected = _filter_cached_batches(selected)
        print(f'Modo cache: {len(selected)} lotes con teselas GLO-30 locales de {total_candidates} totales.', flush=True)

    if not args.overwrite:
        done_ids = store.completed_batch_ids()
        before = len(selected)
        selected = [b for b in selected if b.id not in done_ids]
        skipped = before - len(selected)
        if skipped:
            print(f'Skip resume: omitidos {skipped} lotes ya procesados ({len(selected)} pendientes).', flush=True)

    if args.max_batches > 0:
        selected = selected[args.start:args.start + args.max_batches]
    else:
        selected = selected[args.start:]
    return selected


def run_batch(args: argparse.Namespace) -> None:
    store = FeatureStore(Path(args.store_dir), memory_limit=args.memory_limit, threads=args.threads)
    selected = _select_batches(args, store)
    if not selected:
        print('No hay lotes pendientes.', flush=True)
        return

    workers = max(1, min(args.workers, len(selected)))
    t0 = time.perf_counter()
    if workers == 1:
        for batch in selected:
            label, bid, n_rows, n_parts, elapsed = _process_single_batch(
                batch, args.stride, args.mode, not args.no_cover,
                args.store_dir, args.memory_limit, args.threads,
            )
            print(f'{label} {bid}: {n_rows} ventanas -> {n_parts} particiones ({elapsed:.2f} s)', flush=True)
    else:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            futures = [
                pool.submit(
                    _process_single_batch,
                    batch, args.stride, args.mode, not args.no_cover,
                    args.store_dir, args.memory_limit, args.threads,
                )
                for batch in selected
            ]
            for fut in as_completed(futures):
                label, bid, n_rows, n_parts, elapsed = fut.result()
                print(f'{label} {bid}: {n_rows} ventanas -> {n_parts} particiones ({elapsed:.2f} s)', flush=True)
    print(f'Total ({len(selected)} lotes, {workers} workers): {time.perf_counter() - t0:.2f} s', flush=True)


def run_stream_cmd(args: argparse.Namespace) -> None:
    store = FeatureStore(Path(args.store_dir), memory_limit=args.memory_limit, threads=args.threads)
    selected = _select_batches(args, store)
    if not selected:
        print('No hay lotes pendientes para streaming.', flush=True)
        return
    t0 = time.perf_counter()
    summary = stream_engine.run_stream(
        batches=selected,
        store_dir=Path(args.store_dir),
        stride=args.stride,
        include_cover=not args.no_cover,
        cpu_workers=max(1, min(args.workers, len(selected))),
        io_workers=args.io_workers,
        max_temp_gb=args.max_temp_gb,
        memory_limit=args.memory_limit,
        threads=args.threads,
    )
    summary['elapsed_s'] = round(time.perf_counter() - t0, 2)
    print(json.dumps(summary, indent=2, ensure_ascii=False), flush=True)


def run_rank(args: argparse.Namespace) -> None:
    store = FeatureStore(Path(args.store_dir), memory_limit=args.memory_limit, threads=args.threads)
    results = store.rank_similar(
        ref_relief_m=args.ref_relief,
        ref_slope_p50_deg=args.ref_slope_p50,
        ref_slope_p90_deg=args.ref_slope_p90,
        limit=args.limit,
        only_eligible=not args.include_ineligible,
    )
    print(json.dumps(results, indent=2, ensure_ascii=False))


def run_compact(args: argparse.Namespace) -> None:
    store = FeatureStore(Path(args.store_dir), memory_limit=args.memory_limit, threads=args.threads)
    targets = ('spectral', 'temporal') if args.subset == 'all' else (args.subset,)
    out = {}
    for sub in targets:
        res = store.compact(sub)
        out[sub] = str(res) if res else None
    print(json.dumps(out, indent=2, ensure_ascii=False))


def run_stats(args: argparse.Namespace) -> None:
    store = FeatureStore(Path(args.store_dir), memory_limit=args.memory_limit, threads=args.threads)
    print(json.dumps(store.store_stats(), indent=2, ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--store-dir', default=str(DEFAULT_STORE))
    parser.add_argument('--memory-limit', default='6GB')
    parser.add_argument('--threads', type=int, default=os.cpu_count() or 4)
    sub = parser.add_subparsers(dest='command', required=True)

    p_batch = sub.add_parser('batch', help='Primera pasada batch (topografía 240m + elegibilidad WorldCover/JRC)')
    p_batch.add_argument('--scope', choices=('pilot', 'world'), default='pilot')
    p_batch.add_argument('--stride', choices=(3000, 10000), type=int, default=10000)
    p_batch.add_argument('--mode', choices=('auto', 'cache', 'range'), default='auto')
    p_batch.add_argument('--start', type=int, default=0)
    p_batch.add_argument('--max-batches', type=int, default=5, help='Máximo de lotes a procesar (0 = todos)')
    p_batch.add_argument('--workers', type=int, default=min(8, os.cpu_count() or 4))
    p_batch.add_argument('--no-cover', action='store_true')
    p_batch.add_argument('--overwrite', action='store_true', help='Reprocesar lotes ya completados')

    p_stream = sub.add_parser('stream', help='Streaming asíncrono (prefetch temporal -> CPU -> borrado raw inmediato)')
    p_stream.add_argument('--scope', choices=('pilot', 'world'), default='world')
    p_stream.add_argument('--stride', choices=(3000, 10000), type=int, default=10000)
    p_stream.add_argument('--start', type=int, default=0)
    p_stream.add_argument('--max-batches', type=int, default=5, help='Máximo de lotes a procesar (0 = todos)')
    p_stream.add_argument('--workers', type=int, default=min(8, os.cpu_count() or 4), help='Workers CPU')
    p_stream.add_argument('--io-workers', type=int, default=12, help='Hilos de descarga asíncrona')
    p_stream.add_argument('--max-temp-gb', type=float, default=4.0, help='Tope de disco temporal en GB')
    p_stream.add_argument('--no-cover', action='store_true')
    p_stream.add_argument('--overwrite', action='store_true', help='Reprocesar lotes ya completados')

    p_rank = sub.add_parser('rank', help='Ranking de similitud out-of-core con DuckDB')
    p_rank.add_argument('--ref-relief', type=float, default=JEZERO_REF['relief_m'])
    p_rank.add_argument('--ref-slope-p50', type=float, default=JEZERO_REF['slope_p50_deg'])
    p_rank.add_argument('--ref-slope-p90', type=float, default=JEZERO_REF['slope_p90_deg'])
    p_rank.add_argument('--limit', type=int, default=15)
    p_rank.add_argument('--include-ineligible', action='store_true')

    p_compact = sub.add_parser('compact', help='Compactar deltas on-demand out-of-core')
    p_compact.add_argument('--subset', choices=('spectral', 'temporal', 'all'), default='all')

    sub.add_parser('stats', help='Uso de almacenamiento vs presupuesto de 100 GB y conteos')

    args = parser.parse_args()
    if args.command == 'batch':
        run_batch(args)
    elif args.command == 'stream':
        run_stream_cmd(args)
    elif args.command == 'rank':
        run_rank(args)
    elif args.command == 'compact':
        run_compact(args)
    elif args.command == 'stats':
        run_stats(args)


if __name__ == '__main__':
    main()
