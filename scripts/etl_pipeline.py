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
from pipelines import etl_contract as contract
from pipelines import etl_cover as cover
from pipelines import etl_eligibility as eligibility
from pipelines import etl_framing as framing
from pipelines import etl_publish as publish
from pipelines import etl_extractors as extractors
from pipelines import etl_stream as stream_engine
from pipelines.etl_store import FeatureStore

DEFAULT_STORE = Path(os.environ.get('ANALOGOS_FEATURE_STORE_DIR') or (ROOT / 'data/feature_store_v1'))
JEZERO_REF = {'relief_m': framing.JEZERO_RELIEF_M, 'slope_p50_deg': 3.07, 'slope_p90_deg': 9.24,
              'hypsometric_integral': framing.JEZERO_HYPSOMETRIC_INTEGRAL}


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
        outcome = extractors.batch_outcome(rows, rasters, extractors.run_identity(stride))
    written = store.write_base_batch(batch.id, rows, manifests)
    store.mark_batch_completed(batch.id, {
        'batch_id': batch.id,
        'label': batch.label,
        **outcome,
        'partitions': len(written),
        'mode': mode,
        'include_cover': include_cover,
        'completed_at': datetime.now(timezone.utc).isoformat(),
    })
    return batch.label, batch.id, len(rows), len(written), time.perf_counter() - started, outcome['status']


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

    if getattr(args, 'reopen_legacy_gaps', False):
        # Legacy runs mixed catalogue gaps with access failures under dem_unavailable.
        legacy = {b for b, m in store.batch_records().items() if 'identity' not in m}
        reopen = store.batches_with_qa(('dem_unavailable', 'insufficient_dem_support')) & legacy
        selected = [b for b in selected if b.id in reopen]
        print(f'Reapertura: {len(selected)} lotes antiguos con dem_unavailable o soporte DEM insuficiente.', flush=True)
    elif not args.overwrite:
        identity = extractors.run_identity(getattr(args, 'stride', 10000))
        done_ids = store.completed_batch_ids(identity)
        before = len(selected)
        selected = [b for b in selected if b.id not in done_ids]
        skipped = before - len(selected)
        retried = len(store.incomplete_batch_ids() & {b.id for b in selected})
        if skipped or retried:
            print(f'Skip resume: omitidos {skipped} lotes completos con la misma identidad; '
                  f'{retried} lotes incompletos se reintentan ({len(selected)} pendientes).', flush=True)

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
            label, bid, n_rows, n_parts, elapsed, status = _process_single_batch(
                batch, args.stride, args.mode, not args.no_cover,
                args.store_dir, args.memory_limit, args.threads,
            )
            print(f'{label} {bid}: {n_rows} ventanas -> {n_parts} particiones ({elapsed:.2f} s) {status}', flush=True)
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
                label, bid, n_rows, n_parts, elapsed, status = fut.result()
                print(f'{label} {bid}: {n_rows} ventanas -> {n_parts} particiones ({elapsed:.2f} s) {status}', flush=True)
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
    if args.stage == 'densified':
        results = store.rank_densified(
            ref_relief_m=args.ref_relief,
            ref_hypsometric_integral=args.ref_hypsometric_integral,
            lattice_step_m=args.step,
            max_offset_m=args.max_offset,
            limit=args.limit,
            profile=args.profile,
        )
        if not results:
            print('No hay candidatas encuadradas con esa referencia y retícula; ejecuta antes `refine`.',
                  file=sys.stderr, flush=True)
        print(json.dumps(results, indent=2, ensure_ascii=False))
        return
    results = store.rank_similar(
        ref_relief_m=args.ref_relief,
        ref_slope_p50_deg=args.ref_slope_p50,
        ref_slope_p90_deg=args.ref_slope_p90,
        limit=args.limit,
        only_eligible=not args.include_ineligible,
        profile=args.profile,
        ref_hypsometric_integral=args.ref_hypsometric_integral,
    )
    print(json.dumps(results, indent=2, ensure_ascii=False))


def run_refine(args: argparse.Namespace) -> None:
    """Densified stage: best-framing hypsometric integral for the top topographic candidates."""
    store = FeatureStore(Path(args.store_dir), memory_limit=args.memory_limit, threads=args.threads)
    candidates = store.rank_similar(
        ref_relief_m=args.ref_relief,
        ref_slope_p50_deg=args.ref_slope_p50,
        ref_slope_p90_deg=args.ref_slope_p90,
        limit=args.limit,
        profile=args.profile,
    )
    if not args.overwrite:
        candidates = [c for c in candidates if c['framing_status'] == 'on_demand_fetchable']
    if not candidates:
        print('No hay candidatas pendientes de encuadre.', flush=True)
        return
    land = topo.Land()
    inventory = sources.glo_inventory()
    rows, manifests = [], []
    t0 = time.perf_counter()
    with ExitStack() as stack:
        stack.enter_context(rasterio.Env(
            GDAL_DISABLE_READDIR_ON_OPEN='EMPTY_DIR', GDAL_HTTP_MAX_RETRY=2,
            GDAL_HTTP_TIMEOUT=30, GDAL_CACHEMAX=256 * 1024 ** 2,
        ))
        rasters = topo.Rasters(stack, args.mode)
        for cand in candidates:
            row, m_rows = framing.extract_framing_record(
                cand, land, rasters, inventory,
                reference_hi=args.ref_hypsometric_integral,
                reference_relief_m=args.ref_relief,
                step_m=args.step, max_offset_m=args.max_offset,
            )
            rows.append(row)
            manifests.extend(m_rows)
            print(f"{cand['region_id']}: {row['framing_status']} centro={row['hi_center']} "
                  f"mejor={row['hi_best']} ({row['best_offset_east_m']}, {row['best_offset_north_m']}) m "
                  f"relieve={row['best_relief_p95_p05_m']} d={row['best_distance_score']}", flush=True)
    store.append_enrichment('framing', rows, manifests)
    print(f'{len(rows)} candidatas encuadradas en {time.perf_counter() - t0:.1f} s', flush=True)


def run_cover(args: argparse.Namespace) -> None:
    """Cover backfill for rankable windows whose WorldCover/JRC fractions were never read."""
    store = FeatureStore(Path(args.store_dir), memory_limit=args.memory_limit, threads=args.threads)
    reference = None if args.unordered else {
        'relief_m': args.ref_relief, 'slope_p50_deg': args.ref_slope_p50, 'slope_p90_deg': args.ref_slope_p90}
    bbox = tuple(args.bbox) if args.bbox else None
    windows = cover.select_windows(store, limit=args.limit or None, order_by_reference=reference, bbox=bbox)
    print(f'{len(windows)} ventanas pendientes de cobertura seleccionadas '
          f'({"orden topográfico respecto a la referencia" if reference else "orden por región"}).', flush=True)
    if not windows:
        return
    summary = cover.run_cover_backfill(Path(args.store_dir), windows, transport=args.transport,
                                       workers=args.workers)
    store.compact_if_needed('cover')
    summary.pop('blocks_detail')
    print(json.dumps(summary, indent=2, ensure_ascii=False), flush=True)


def run_publish(args: argparse.Namespace) -> None:
    """Publish the store as an Atlas 30 m release readable by the API and the map."""
    store = FeatureStore(Path(args.store_dir), memory_limit=args.memory_limit, threads=args.threads)
    manifest = publish.publish_release(store, args.version, profile_id=args.profile, set_current=args.set_current)
    print(json.dumps({k: manifest[k] for k in ('version', 'coverage_status', 'counts', 'eligibility_counts',
                                               'cover_counts', 'normalization', 'incomplete_batches')},
                     indent=2, ensure_ascii=False))
    if not args.set_current:
        print(f'Publicado sin activar. Para mostrarlo en el mapa: --set-current, o '
              f'GET /api/atlas?version={args.version}', flush=True)


def run_compact(args: argparse.Namespace) -> None:
    store = FeatureStore(Path(args.store_dir), memory_limit=args.memory_limit, threads=args.threads)
    targets = contract.ENRICHMENT_SUBSETS if args.subset == 'all' else (args.subset,)
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
    p_batch.add_argument('--reopen-legacy-gaps', action='store_true',
                        help='Reprocesar solo lotes antiguos con dem_unavailable o soporte DEM insuficiente')

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
    p_stream.add_argument('--reopen-legacy-gaps', action='store_true',
                        help='Reprocesar solo lotes antiguos con dem_unavailable o soporte DEM insuficiente')

    p_rank = sub.add_parser('rank', help='Ranking de similitud out-of-core con DuckDB')
    p_rank.add_argument('--ref-relief', type=float, default=JEZERO_REF['relief_m'])
    p_rank.add_argument('--ref-slope-p50', type=float, default=JEZERO_REF['slope_p50_deg'])
    p_rank.add_argument('--ref-slope-p90', type=float, default=JEZERO_REF['slope_p90_deg'])
    p_rank.add_argument('--limit', type=int, default=15)
    p_rank.add_argument('--include-ineligible', action='store_true')
    p_rank.add_argument('--profile', choices=tuple(eligibility.PROFILES), default=eligibility.DEFAULT_PROFILE,
                        help='Perfil de elegibilidad por escenario')
    p_rank.add_argument('--ref-hypsometric-integral', type=float, default=JEZERO_REF['hypsometric_integral'],
                        help='Referencia de la integral: informativa en el barrido, entra en la distancia densificada')
    p_rank.add_argument('--stage', choices=('recon', 'densified'), default='recon',
                        help='recon: relieve y pendientes de la huella fija; densified: relieve e integral '
                             'hipsométrica en el mejor encuadre de `refine` (pendiente de validación ciega)')
    p_rank.add_argument('--step', type=int, default=framing.DEFAULT_STEP_M,
                        help='Paso de la retícula de `refine` a comparar (solo densified)')
    p_rank.add_argument('--max-offset', type=int, default=framing.DEFAULT_MAX_OFFSET_M,
                        help='Desplazamiento máximo de `refine` a comparar (solo densified)')

    p_refine = sub.add_parser('refine', help='Etapa densificada: mejor encuadre de la integral hipsométrica')
    p_refine.add_argument('--ref-relief', type=float, default=JEZERO_REF['relief_m'])
    p_refine.add_argument('--ref-slope-p50', type=float, default=JEZERO_REF['slope_p50_deg'])
    p_refine.add_argument('--ref-slope-p90', type=float, default=JEZERO_REF['slope_p90_deg'])
    p_refine.add_argument('--ref-hypsometric-integral', type=float, default=JEZERO_REF['hypsometric_integral'])
    p_refine.add_argument('--profile', choices=tuple(eligibility.PROFILES), default=eligibility.DEFAULT_PROFILE)
    p_refine.add_argument('--limit', type=int, default=25, help='Candidatas topográficas a encuadrar')
    p_refine.add_argument('--step', type=int, default=framing.DEFAULT_STEP_M, help='Paso de la retícula (m)')
    p_refine.add_argument('--max-offset', type=int, default=framing.DEFAULT_MAX_OFFSET_M,
                          help='Desplazamiento máximo por eje (m)')
    p_refine.add_argument('--mode', choices=('auto', 'cache', 'range'), default='auto')
    p_refine.add_argument('--overwrite', action='store_true', help='Reencuadrar candidatas ya procesadas')

    p_cover = sub.add_parser('cover', help='Relleno de cobertura WorldCover/JRC sobre ventanas ya calculadas')
    p_cover.add_argument('--limit', type=int, default=0, help='Máximo de ventanas (0 = todas las pendientes)')
    p_cover.add_argument('--unordered', action='store_true',
                         help='No priorizar por cercanía topográfica a la referencia')
    p_cover.add_argument('--ref-relief', type=float, default=JEZERO_REF['relief_m'])
    p_cover.add_argument('--ref-slope-p50', type=float, default=JEZERO_REF['slope_p50_deg'])
    p_cover.add_argument('--ref-slope-p90', type=float, default=JEZERO_REF['slope_p90_deg'])
    p_cover.add_argument('--bbox', type=float, nargs=4, metavar=('W', 'S', 'E', 'N'))
    p_cover.add_argument('--transport', choices=('download', 'range'), default='download')
    p_cover.add_argument('--workers', type=int, default=min(4, os.cpu_count() or 2))

    p_publish = sub.add_parser('publish', help='Publicar el almacén como release del Atlas para la API y el mapa')
    p_publish.add_argument('--version', required=True, help='Nombre de la publicación, p. ej. etl-30m-r1')
    p_publish.add_argument('--profile', choices=tuple(eligibility.PROFILES), default=eligibility.DEFAULT_PROFILE)
    p_publish.add_argument('--set-current', action='store_true', help='Activar como publicación por defecto')

    p_compact = sub.add_parser('compact', help='Compactar deltas on-demand out-of-core')
    p_compact.add_argument('--subset', choices=(*contract.ENRICHMENT_SUBSETS, 'all'), default='all')

    sub.add_parser('stats', help='Uso de almacenamiento vs presupuesto de 100 GB y conteos')

    args = parser.parse_args()
    if args.command == 'batch':
        run_batch(args)
    elif args.command == 'stream':
        run_stream_cmd(args)
    elif args.command == 'rank':
        run_rank(args)
    elif args.command == 'refine':
        run_refine(args)
    elif args.command == 'cover':
        run_cover(args)
    elif args.command == 'publish':
        run_publish(args)
    elif args.command == 'compact':
        run_compact(args)
    elif args.command == 'stats':
        run_stats(args)


if __name__ == '__main__':
    main()
