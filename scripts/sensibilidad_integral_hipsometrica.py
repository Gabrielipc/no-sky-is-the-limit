"""Sensitivity of the hypsometric integral to displacing and resizing the footprint.

For Jezero (HiRISE DTM) and the Entrega 3 development windows (GLO-30), recompute the
ETL topographic contract after shifting the 3 km footprint 120, 300, 750 and 1500 m in
eight directions, and with a 1.8 km footprint. Compares how much each descriptor moves
under displacement with how much it differs between windows. Holdout blocks are never read.

    bash scripts/ejecutar_minerales.sh scripts/sensibilidad_integral_hipsometrica.py [--mode auto]
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from contextlib import ExitStack
import json
import math
import os
from pathlib import Path
import sys
import time

import numpy as np
import rasterio
from rasterio.transform import from_origin
from rasterio.warp import Resampling, transform_bounds
from rasterio.windows import Window, from_bounds
from scipy.stats import spearmanr

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipelines import atlas_sources as sources  # noqa: E402
from pipelines import atlas_topography as topo  # noqa: E402
from pipelines import etl_extractors as ex  # noqa: E402
from scripts import analizar_primer_caso as terrain  # noqa: E402
from scripts import explorar_fuentes_atlas as eda  # noqa: E402
from scripts.evaluar_descriptores_forma import development_windows  # noqa: E402

OUT = ROOT / 'docs/evidencia-descriptores-forma'
SHIFTS_M = (120, 300, 750, 1500)
MAX_SHIFT_M = max(SHIFTS_M)
DIRECTIONS = {'N': (0, 1), 'NE': (1, 1), 'E': (1, 0), 'SE': (1, -1),
              'S': (0, -1), 'SW': (-1, -1), 'W': (-1, 0), 'NW': (-1, 1)}
DESCRIPTORS = ('hypsometric_integral', 'relief_p95_p05_m', 'slope_240m_p50_deg',
               'slope_240m_p90_deg', 'aspect_240m_resultant_length')
BASE_SIZE = (ex.WINDOW_M + 2 * ex.HALO_M) // ex.CELL_M
MARGIN = MAX_SHIFT_M // ex.CELL_M
BIG_SIZE = BASE_SIZE + 2 * MARGIN


def offsets(distance_m: int) -> dict[str, tuple[int, int]]:
    """Cell offsets (east, north) per direction; diagonals keep the same Euclidean distance."""
    out = {}
    for name, (ex_, ny) in DIRECTIONS.items():
        scale = distance_m / math.hypot(ex_, ny) / ex.CELL_M
        out[name] = (round(ex_ * scale), round(ny * scale))
    return out


def configurations() -> list[dict]:
    configs = [{'config': 'base', 'shift_m': 0, 'direction': None, 'cells': (0, 0), 'window_m': ex.WINDOW_M},
               {'config': 'window_1800', 'shift_m': 0, 'direction': None, 'cells': (0, 0), 'window_m': 1800}]
    for d in SHIFTS_M:
        for name, cells in offsets(d).items():
            configs.append({'config': f'shift_{d}_{name}', 'shift_m': d, 'direction': name,
                            'cells': cells, 'window_m': ex.WINDOW_M})
    return configs


def describe(z_big: np.ndarray, land_big: np.ndarray) -> list[dict]:
    rows = []
    for c in configurations():
        de, dn = c['cells']
        r0, c0 = MARGIN - dn, MARGIN + de  # row 0 is north
        z = z_big[r0:r0 + BASE_SIZE, c0:c0 + BASE_SIZE]
        land = land_big[r0:r0 + BASE_SIZE, c0:c0 + BASE_SIZE]
        feats = ex.compute_topography_features(z, land, window_m=c['window_m'])
        rows.append({'config': c['config'], 'shift_m': c['shift_m'], 'direction': c['direction'],
                     'window_m': c['window_m'], **{k: feats[k] for k in DESCRIPTORS}})
    return rows


def _earth_block(windows: list[dict], mode: str) -> list[dict]:
    land = topo.Land()
    inventory = sources.glo_inventory()
    half = BIG_SIZE * ex.CELL_M / 2
    out = []
    with ExitStack() as stack:
        stack.enter_context(rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN='EMPTY_DIR', GDAL_HTTP_MAX_RETRY=3,
                                         GDAL_HTTP_TIMEOUT=60, GDAL_CACHEMAX=256 * 1024 ** 2))
        rasters = topo.Rasters(stack, mode)
        for w in windows:
            zone = topo.owner(w['longitude'], w['latitude'])
            x, y = topo.projection(topo.WGS84, zone).transform(w['longitude'], w['latitude'])
            bounds = topo.geographic_boxes(zone, (x - half, y - half, x + half, y + half))
            affine = from_origin(x - half, y + half, ex.CELL_M, ex.CELL_M)
            shape = (BIG_SIZE, BIG_SIZE)
            land_mask = land.mask(zone, bounds, affine, shape)
            entries = [inventory[k] for k in topo.tile_keys(bounds, 1) if k in inventory]
            z, ids = topo.mosaic(rasters, entries, zone, bounds, affine, shape, Resampling.average)
            if not ids:
                continue
            out.append({**w, 'configs': describe(z, land_mask)})
    return out


def jezero() -> dict:
    site = json.loads(terrain.DEFAULT_CONFIG.read_text())['sites'][0]
    path = terrain.acquire(site, False)
    # The enlarged crop (7.4 km) exceeds the DTM width (~7 km), so it is read boundless here
    # instead of with terrain.read_crop, whose corner integrity checks require in-bounds samples.
    # Cells outside the DTM stay NaN and the affected shifts fail the 95 % support rule.
    dst = terrain.local_crs(site)
    half = BIG_SIZE * ex.CELL_M / 2
    with rasterio.open(path) as ds:
        bounds = transform_bounds(dst, ds.crs, -half, -half, half, half, densify_pts=41)
        w = from_bounds(*bounds, ds.transform)
        c, r = math.floor(w.col_off) - 2, math.floor(w.row_off) - 2
        win = Window(c, r, math.ceil(w.col_off + w.width) + 2 - c, math.ceil(w.row_off + w.height) + 2 - r)
        a = ds.read(1, window=win, boundless=True, masked=True).astype('float64')
        data = a.filled(np.nan)
        valid = ~np.ma.getmaskarray(a) & np.isfinite(data)
        if 'valid_range_m' in site:
            lo, hi = site['valid_range_m']
            valid &= (data >= lo) & (data <= hi)
        data[~valid] = np.nan
        transform_, src = ds.window_transform(win), ds.crs
    z, _ = terrain.aggregate(data, valid, transform_, src, dst,
                             from_origin(-half, half, ex.CELL_M, ex.CELL_M), (BIG_SIZE, BIG_SIZE), 1e-6)
    return {'site': site['name'], 'product': site['product_id'], 'sha256': site['sha256'],
            'configs': describe(z, np.ones(z.shape, bool))}


def analyse(earth: list[dict], ref: dict) -> dict:
    names = [c['config'] for c in configurations()]

    def values(config: str, key: str) -> np.ndarray:
        return np.array([next(c for c in w['configs'] if c['config'] == config)[key] for w in earth], dtype=float)

    summary = {}
    for key in DESCRIPTORS:
        base = values('base', key)
        q25, q75 = np.nanpercentile(base, [25, 75])
        iqr = float(q75 - q25)
        per_distance = {}
        for d in [*SHIFTS_M, 'window_1800']:
            cfgs = [n for n in names if n == 'window_1800'] if d == 'window_1800' else \
                [n for n in names if n.startswith(f'shift_{d}_')]
            deltas, rhos = [], []
            for n in cfgs:
                shifted = values(n, key)
                ok = np.isfinite(base) & np.isfinite(shifted)
                deltas.append(np.abs(shifted[ok] - base[ok]))
                rhos.append(float(spearmanr(base[ok], shifted[ok]).statistic))
            all_d = np.concatenate(deltas)
            med = float(np.median(all_d))
            per_distance[str(d)] = {
                'median_abs_change': round(med, 5),
                'p90_abs_change': round(float(np.percentile(all_d, 90)), 5),
                'iqr_between_windows_over_median_change': round(iqr / med, 2) if med > 0 else None,
                'rank_spearman_min': round(min(rhos), 4),
                'rank_spearman_median': round(float(np.median(rhos)), 4),
            }
        summary[key] = {'iqr_between_windows': round(iqr, 5), 'by_shift': per_distance}

    base_hi = values('base', 'hypsometric_integral')
    base_hi = base_hi[np.isfinite(base_hi)]
    ref_rows = []
    for c in ref['configs']:
        hi = c['hypsometric_integral']
        pct = None if hi is None else round(float((base_hi < hi).mean() * 100), 1)
        ref_rows.append({**c, 'hypsometric_integral_percentile_in_development': pct})
    by_d = defaultdict(list)
    for r in ref_rows:
        if r['hypsometric_integral'] is not None and r['shift_m']:
            by_d[r['shift_m']].append(r)
    jezero_summary = {
        str(d): {'n_valid': len(rs), 'hi_min': round(min(r['hypsometric_integral'] for r in rs), 4),
                 'hi_max': round(max(r['hypsometric_integral'] for r in rs), 4),
                 'percentile_min': min(r['hypsometric_integral_percentile_in_development'] for r in rs),
                 'percentile_max': max(r['hypsometric_integral_percentile_in_development'] for r in rs)}
        for d, rs in sorted(by_d.items())
    }
    return {'earth_windows': len(earth), 'descriptors': summary,
            'jezero': {'configs': ref_rows, 'by_shift': jezero_summary}}


def compact_earth(earth: list[dict]) -> dict:
    """Per-window values as one array per descriptor and configuration (4 significant decimals)."""
    names = [c['config'] for c in configurations()]

    def r(v):
        return None if v is None else float(f'{v:.4g}')

    return {
        'window_ids': [w['id'] for w in earth],
        'values': {k: {n: [r(next(c for c in w['configs'] if c['config'] == n)[k]) for w in earth]
                       for n in names} for k in DESCRIPTORS},
    }


def write_manifest() -> None:
    tracked = [Path(__file__), ROOT / 'pipelines/etl_extractors.py', ROOT / 'scripts/evaluar_descriptores_forma.py',
               OUT / 'sensibilidad-huella.json']
    eda.write(OUT / 'manifest-sensibilidad.json', {
        'schema': 1,
        'files': [{'path': str(p.relative_to(ROOT)), 'bytes': p.stat().st_size, 'sha256': eda.digest(p)}
                  for p in tracked],
    })


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=('auto', 'cache', 'range'), default='auto')
    parser.add_argument('--workers', type=int, default=min(6, os.cpu_count() or 2))
    args = parser.parse_args()
    t0 = time.perf_counter()
    by_block = defaultdict(list)
    for w in development_windows():
        by_block[w['block_id']].append(w)
    earth = []
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures = {b: pool.submit(_earth_block, ws, args.mode) for b, ws in sorted(by_block.items())}
        for b, fut in futures.items():
            earth.extend(fut.result())
            print(f'  {b} listo ({time.perf_counter() - t0:.0f} s)', flush=True)
    earth.sort(key=lambda w: w['id'])
    ref = jezero()
    stats = analyse(earth, ref)
    eda.write(OUT / 'sensibilidad-huella.json', {
        'schema': 1,
        'question': 'Cuánto cambia la integral hipsométrica al desplazar o reducir la huella, frente a su variación entre ventanas',
        'design': {'shifts_m': list(SHIFTS_M), 'directions': list(DIRECTIONS), 'window_m': ex.WINDOW_M,
                   'reduced_window_m': 1800, 'cell_m': ex.CELL_M, 'halo_m': ex.HALO_M,
                   'dem_earth': 'Copernicus GLO-30', 'dem_mars': ref['product'], 'access_mode': args.mode,
                   'split_used': 'development', 'holdout_read': False},
        'analysis': stats,
        'earth': compact_earth(earth),
        'elapsed_s': round(time.perf_counter() - t0, 1),
    })
    write_manifest()
    print(json.dumps({k: v['by_shift'] for k, v in stats['descriptors'].items()}, indent=1))
    print(json.dumps(stats['jezero']['by_shift'], indent=1))


if __name__ == '__main__':
    main()
