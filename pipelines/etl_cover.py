"""Cover backfill: WorldCover 2021 + JRC GSW fractions for windows already in the store.

The world topographic sweep can run without cover (fast), leaving `rankable` windows
pending the eligibility gate. This stage reads cover only for those windows and writes
`enrichment_cover` deltas that the `base_windows` view overlays, so topography is never
recomputed.

Transport. Windows are grouped by JRC tile (10°) and, inside it, by WorldCover tile (3°).
With `transport='download'` each tile is downloaded once into a temporary directory and
deleted when its group ends (WorldCover v200 is ~47 MB per tile on average); windows whose
halo crosses into a neighbouring tile read that tile by HTTP range. `transport='range'`
reads everything by range, which suits small shortlists.
"""
from __future__ import annotations

from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from contextlib import ExitStack
from datetime import datetime, timezone
import math
from pathlib import Path
import shutil
import tempfile
import time

import rasterio

from pipelines import atlas_sources as sources
from pipelines import atlas_topography as topo
from pipelines import etl_eligibility as eligibility
from pipelines import etl_extractors as ex
from pipelines.etl_stream import StreamRasters, download_tile_to_temp
from pipelines.etl_store import FeatureStore

RETRY_STATUSES = ('not_requested', 'cover_fetch_failed')
FLUSH_ROWS = 5000


def select_windows(store: FeatureStore, limit: int | None = None, order_by_reference: dict | None = None,
                   bbox: tuple[float, float, float, float] | None = None) -> list[dict]:
    """Rankable Earth windows whose cover was never read or failed to read.

    With `order_by_reference` ({'relief_m', 'slope_p50_deg', 'slope_p90_deg'}) the
    windows topographically closest to the reference come first, so a `limit` gives a
    shortlist instead of an arbitrary subset.
    """
    where = ["body = 'Earth'", "qa_status = 'rankable'",
             f"(cover_status IS NULL OR cover_status IN {RETRY_STATUSES!r})"]
    params: list = []
    if bbox:
        where.append('longitude BETWEEN ? AND ? AND latitude BETWEEN ? AND ?')
        params += [bbox[0], bbox[2], bbox[1], bbox[3]]
    order = 'region_id'
    if order_by_reference:
        order = ('abs(relief_p95_p05_m - ?) / 50.0 + abs(slope_240m_p50_deg - ?) + '
                 'abs(slope_240m_p90_deg - ?) / 2.0, region_id')
        params += [order_by_reference['relief_m'], order_by_reference['slope_p50_deg'],
                   order_by_reference['slope_p90_deg']]
    sql = (f"SELECT region_id, longitude, latitude, land_fraction FROM base_windows "
           f"WHERE {' AND '.join(where)} ORDER BY {order}")
    if limit:
        sql += f' LIMIT {int(limit)}'
    with store._connect() as conn:
        cur = conn.execute(sql, params)
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]


def tile_key(lon: float, lat: float, step: int) -> tuple[int, int]:
    return (math.floor(lat / step) * step, math.floor(lon / step) * step)


def group_windows(windows: list[dict]) -> dict[tuple[int, int], dict[tuple[int, int], list[dict]]]:
    """{JRC 10° key: {WorldCover 3° key: [windows]}} by window centre."""
    groups: dict = defaultdict(lambda: defaultdict(list))
    for w in windows:
        groups[tile_key(w['longitude'], w['latitude'], 10)][tile_key(w['longitude'], w['latitude'], 3)].append(w)
    return groups


def cover_record(window: dict, land: topo.Land, rasters: topo.Rasters, now: datetime) -> tuple[dict, list[str]]:
    zone = topo.owner(window['longitude'], window['latitude'])
    x, y = topo.projection(topo.WGS84, zone).transform(window['longitude'], window['latitude'])
    crs, bounds, affine, shape = ex.window_grid(zone, x, y, ex.WINDOW_M // 2 + ex.HALO_M)
    land_mask = land.mask(crs, bounds, affine, shape)
    core_land = ex.center_crop(land_mask.astype('float64'), ex.WINDOW_M, ex.CELL_M) > 0.5
    fields, asset_ids, _ = ex.compute_cover_fields(rasters, crs, bounds, affine, shape, core_land)
    status = eligibility.classify(fields, land_fraction=window['land_fraction'],
                                  cover_valid_fraction=ex.gate_cover_support(fields))
    row = {'region_id': window['region_id'], **fields, 'analog_surface_eligibility': status,
           'eligibility_profile': eligibility.DEFAULT_PROFILE, 'updated_at': now}
    return row, asset_ids


def _manifests(rows_assets: list[tuple[dict, list[str]]], rasters: topo.Rasters, now: datetime) -> list[dict]:
    manifests = {}
    for row, asset_ids in rows_assets:
        mid = ex.make_manifest_id(asset_ids, f'cover:{rasters.mode}')
        row['source_manifest_id'] = mid
        for aid in asset_ids:
            identity = rasters.identities.get(aid) or {}
            manifests[(mid, aid)] = {
                'source_manifest_id': mid,
                'product_id': 'esa-worldcover-2021' if aid.startswith('ESA_WorldCover') else 'jrc-gsw-v1_5',
                'asset_id': aid,
                'access_mode': identity.get('status', rasters.mode),
                'sha256_or_etag': identity.get('sha256') or identity.get('etag'),
                'native_resolution_m': 10.0 if aid.startswith('ESA_WorldCover') else 30.0,
                'effective_resolution_m': float(ex.CELL_M),
                'observation_period': '2021' if aid.startswith('ESA_WorldCover') else '1984-2024',
                'created_at': now,
            }
    return list(manifests.values())


def process_block(jrc_key: tuple[int, int], wc_groups: dict, store_dir: str, transport: str,
                  memory_limit: str = '1GB', threads: int = 2) -> dict:
    """Read cover for every window of one JRC tile; returns counts, bytes and failures."""
    started = time.perf_counter()
    land = topo.Land()
    store = FeatureStore(Path(store_dir), memory_limit=memory_limit, threads=threads)
    stats = {'block': list(jrc_key), 'windows': 0, 'downloaded_bytes': 0, 'download_failures': {},
             'cover_status': defaultdict(int), 'asset_failures': {}}
    tmp_root = Path(store_dir) / '.cover_tmp'
    tmp_root.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(dir=tmp_root))
    pending: list[tuple[dict, list[str]]] = []
    try:
        overrides: dict[str, Path] = {}
        failures: dict[str, str] = {}

        def fetch(entry: dict) -> None:
            if transport != 'download' or sources.local_identity(entry) is not None:
                return
            aid, path, nbytes, cause = download_tile_to_temp(entry, tmp)
            if path is not None:
                overrides[aid] = path
                stats['downloaded_bytes'] += nbytes
            elif cause:
                failures[aid] = cause
                stats['download_failures'][aid] = cause

        fetch(sources.jrc_asset(*jrc_key))
        for wc_key, windows in sorted(wc_groups.items()):
            wc_entry = sources.worldcover_asset(*wc_key)
            fetch(wc_entry)
            with ExitStack() as stack:
                stack.enter_context(rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN='EMPTY_DIR', GDAL_HTTP_MAX_RETRY=3,
                                                 GDAL_HTTP_TIMEOUT=60, GDAL_CACHEMAX=256 * 1024 ** 2))
                rasters = StreamRasters(stack, overrides, failures)
                if transport == 'range':
                    rasters.mode = 'range'
                now = datetime.now(timezone.utc)
                for w in windows:
                    row, asset_ids = cover_record(w, land, rasters, now)
                    pending.append((row, asset_ids))
                    stats['cover_status'][row['cover_status']] += 1
                stats['asset_failures'].update(
                    {k: v for k, v in rasters.failures.items() if v not in ex.MISSING_TILE_CAUSES})
                if len(pending) >= FLUSH_ROWS or wc_key == max(wc_groups):
                    rows = [r for r, _ in pending]
                    manifests = _manifests(pending, rasters, now)
                    store.append_enrichment('cover', rows, manifests)
                    stats['windows'] += len(rows)
                    pending = []
            path = overrides.pop(wc_entry['id'], None)
            if path is not None:
                path.unlink(missing_ok=True)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    stats['cover_status'] = dict(stats['cover_status'])
    stats['elapsed_s'] = round(time.perf_counter() - started, 2)
    return stats


def run_cover_backfill(store_dir: Path, windows: list[dict], transport: str = 'download', workers: int = 4,
                       log=print) -> dict:
    groups = group_windows(windows)
    totals = {'blocks': len(groups), 'windows': 0, 'downloaded_bytes': 0, 'cover_status': defaultdict(int),
              'download_failures': {}, 'asset_failures': {}, 'blocks_detail': []}
    t0 = time.perf_counter()
    jobs = sorted(groups.items(), key=lambda kv: -sum(len(v) for v in kv[1].values()))
    with ProcessPoolExecutor(max_workers=max(1, min(workers, len(jobs) or 1))) as pool:
        futures = {pool.submit(process_block, k, dict(v), str(store_dir), transport): k for k, v in jobs}
        for fut in as_completed(futures):
            s = fut.result()
            totals['windows'] += s['windows']
            totals['downloaded_bytes'] += s['downloaded_bytes']
            for k, v in s['cover_status'].items():
                totals['cover_status'][k] += v
            totals['download_failures'].update(s['download_failures'])
            totals['asset_failures'].update(s['asset_failures'])
            totals['blocks_detail'].append({k: s[k] for k in ('block', 'windows', 'downloaded_bytes', 'elapsed_s')})
            log(f"[cover] bloque {s['block']}: {s['windows']} ventanas, {s['downloaded_bytes'] / 1e6:.1f} MB, "
                f"{s['elapsed_s']} s | {dict(s['cover_status'])} ({time.perf_counter() - t0:.0f} s)")
    shutil.rmtree(Path(store_dir) / '.cover_tmp', ignore_errors=True)
    totals['cover_status'] = dict(totals['cover_status'])
    totals['elapsed_s'] = round(time.perf_counter() - t0, 1)
    return totals

