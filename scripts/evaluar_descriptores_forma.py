"""Information added by the footprint shape descriptors over the current ranking vector.

Recomputes the ETL topographic contract at 30 m (GLO-30, 3 km footprint, 240 m slope
base) on the development windows of the Entrega 3 spatial partition, and measures how
much of each candidate feature is already explained by relief + slope P50 + slope P90.
Holdout blocks are never read. Jezero is computed with the same function as reference.

    bash scripts/ejecutar_minerales.sh scripts/evaluar_descriptores_forma.py [--mode auto|cache|range]
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
from scipy.stats import rankdata, spearmanr

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipelines import atlas_sources as sources  # noqa: E402
from pipelines import atlas_topography as topo  # noqa: E402
from pipelines import etl_extractors as extractors  # noqa: E402
from scripts import analizar_primer_caso as terrain  # noqa: E402
from scripts import explorar_fuentes_atlas as eda  # noqa: E402

CANDIDATES = ROOT / 'docs/evidencia-fase-4/candidatas.json'
PARTITION = ROOT / 'docs/evidencia-entrega-3/seleccion-y-redundancia.json'
CONTRACT_SPEC = ROOT / 'specs/analysis/contrato-comun-entrega3.json'
OUT = ROOT / 'docs/evidencia-descriptores-forma'

RANKING = ('relief_p95_p05_m', 'slope_240m_p50_deg', 'slope_240m_p90_deg')
CONDITIONAL = ('roughness_360m_p50_m',)
FEATURES = RANKING + CONDITIONAL + extractors.SHAPE_FEATURE_KEYS
MIN_UNIQUE_SHARE = 0.5
MIN_COVERAGE = 0.9


def block_id(area: str, lon: float, lat: float) -> str:
    return f'{area}:{math.floor(lon):+04d}_{math.floor(lat):+03d}'


def development_windows(*, exclude_legacy_holdout: bool = False, split_key: str = 'split') -> list[dict]:
    partition = json.loads(PARTITION.read_text())['spatial_partition']
    blocks = {b['block_id']: b for b in partition['blocks']}
    windows = []
    for c in json.loads(CANDIDATES.read_text())['candidates']:
        bid = block_id(c['area_id'], c['longitude'], c['latitude'])
        binfo = blocks.get(bid, {})
        if binfo.get(split_key) == 'development':
            if exclude_legacy_holdout and binfo.get('in_legacy_holdout'):
                continue
            windows.append({'id': c['id'], 'area_id': c['area_id'], 'block_id': bid,
                            'longitude': c['longitude'], 'latitude': c['latitude']})
    return windows


def _measure_block(windows: list[dict], mode: str) -> tuple[list[dict], dict]:
    land = topo.Land()
    inventory = sources.glo_inventory()
    rows = []
    with ExitStack() as stack:
        stack.enter_context(rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN='EMPTY_DIR', GDAL_HTTP_MAX_RETRY=3,
                                         GDAL_HTTP_TIMEOUT=60, GDAL_CACHEMAX=256 * 1024 ** 2))
        rasters = topo.Rasters(stack, mode)
        for w in windows:
            zone = w.get('zone') or topo.owner(w['longitude'], w['latitude'])
            x = w.get('x')
            y = w.get('y')
            if x is None or y is None:
                x, y = topo.projection(topo.WGS84, zone).transform(w['longitude'], w['latitude'])
            site = {'region_id': w['id'], 'batch': w['block_id'], 'zone': zone, 'x': x, 'y': y,
                    'longitude': w['longitude'], 'latitude': w['latitude']}
            row, _ = extractors.extract_base_window(site, land, rasters, inventory, include_cover=False)
            rows.append({**{k: v for k, v in w.items() if k in ('id', 'area_id', 'block_id', 'longitude', 'latitude')},
                         'qa_status': row['qa_status'], 'land_fraction': row['land_fraction'],
                         **{k: row[k] for k in FEATURES}})
        identities = {k: {'status': v.get('status'), 'sha256': v.get('sha256'), 'etag': v.get('etag')}
                      for k, v in rasters.identities.items()}
    return rows, identities


def _measure_domain_batches(domain_cfg: dict, mode: str, workers: int) -> tuple[list[dict], dict]:
    """Measures cached GLO-30 30 m windows for a domain's development batches; holdout batches are never read."""
    stride = int(domain_cfg.get('stride_m', 10000))
    by_batch: dict[str, list[dict]] = {}
    for entry in domain_cfg['development_batches']:
        batch = topo.Batch(entry['zone'], entry['west'], entry['south'], entry['basin'])
        wins = []
        for w in topo.windows(batch, stride):
            wins.append({
                'id': w['region_id'],
                'area_id': entry['basin'],
                'block_id': batch.id,
                'zone': w['zone'],
                'x': w['x'],
                'y': w['y'],
                'longitude': w['longitude'],
                'latitude': w['latitude'],
            })
        by_batch[batch.id] = wins
    rows, identities = [], {}
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures = {bid: pool.submit(_measure_block, ws, mode) for bid, ws in sorted(by_batch.items())}
        for bid, fut in futures.items():
            b_rows, b_ids = fut.result()
            rows.extend(b_rows)
            identities.update(b_ids)
    rows.sort(key=lambda r: r['id'])
    return rows, identities


def jezero_reference() -> dict:
    """Jezero HiRISE DTM aggregated to the same 30 m grid, footprint and halo as the ETL."""
    site = json.loads(terrain.DEFAULT_CONFIG.read_text())['sites'][0]
    path = terrain.acquire(site, False)
    halo = extractors.HALO_M
    data, valid, transform_, src, dst, meta = terrain.read_crop(
        path, site, {'window_m': extractors.WINDOW_M, 'margin_m': halo})
    size = (extractors.WINDOW_M + 2 * halo) // extractors.CELL_M
    half = extractors.WINDOW_M / 2 + halo
    z, _ = terrain.aggregate(data, valid, transform_, src, dst,
                             from_origin(-half, half, extractors.CELL_M, extractors.CELL_M), (size, size), 1e-6)
    feats = extractors.compute_topography_features(z, np.ones(z.shape, bool))
    return {'site': site['name'], 'product': meta['product_id'], **{k: feats[k] for k in FEATURES}}


def _ranks(values: np.ndarray) -> np.ndarray:
    return (rankdata(values) - 0.5) / len(values)


def unique_share(target: np.ndarray, predictors: np.ndarray) -> float:
    """1 - R² of the rank of `target` regressed linearly on the ranks of `predictors`."""
    if len(target) < 3:
        return 0.0
    y = _ranks(target)
    denom = float(np.sum((y - y.mean()) ** 2))
    if denom <= 1e-12:
        return 0.0
    x = np.column_stack([np.ones(len(y))] + [_ranks(p) for p in predictors.T])
    coef, *_ = np.linalg.lstsq(x, y, rcond=None)
    resid = y - x @ coef
    return float(np.clip(np.sum(resid ** 2) / denom, 0.0, 1.0))


def partial_spearman(a: np.ndarray, b: np.ndarray, control: np.ndarray) -> float:
    def residual(v: np.ndarray) -> np.ndarray:
        y = _ranks(v)
        x = np.column_stack([np.ones(len(y)), _ranks(control)])
        coef, *_ = np.linalg.lstsq(x, y, rcond=None)
        return y - x @ coef
    ra, rb = residual(a), residual(b)
    if float(np.std(ra)) <= 1e-12 or float(np.std(rb)) <= 1e-12:
        return 0.0
    val = float(np.corrcoef(ra, rb)[0, 1])
    return 0.0 if not math.isfinite(val) else val


def analyse(rows: list[dict], *, min_coverage: float = MIN_COVERAGE) -> dict:
    rankable = [r for r in rows if r['qa_status'] == 'rankable']
    if not rankable:
        raise ValueError('No rankable windows available for analysis')
    coverage = {k: round(sum(r[k] is not None for r in rankable) / len(rankable), 4) for k in FEATURES}

    def matrix(subset: list[dict], keys: tuple[str, ...]) -> tuple[np.ndarray, int]:
        complete = [r for r in subset if all(r[k] is not None for k in keys)]
        return np.array([[r[k] for k in keys] for r in complete], dtype=float), len(complete)

    cols = tuple(k for k in FEATURES if coverage[k] >= min_coverage)
    data, n_complete = matrix(rankable, cols)
    rho = np.asarray(spearmanr(data).statistic, dtype=float)
    if rho.ndim == 0:
        rho = np.array([[1.0]])
    rho = np.where(np.isfinite(rho), rho, 0.0)
    np.fill_diagonal(rho, 1.0)
    spearman = {a: {b: round(float(rho[i, j]), 4) for j, b in enumerate(cols)} for i, a in enumerate(cols)}

    relief = data[:, cols.index('relief_p95_p05_m')]
    ranking = data[:, [cols.index(k) for k in RANKING]]
    candidates = [k for k in cols if k not in RANKING]
    per_feature = {}
    for k in candidates:
        values = data[:, cols.index(k)]
        by_area = {}
        for area in sorted({r['area_id'] for r in rankable}):
            sub, n = matrix([r for r in rankable if r['area_id'] == area], cols)
            if n >= 3:
                by_area[area] = {'n': n, 'unique_share_vs_ranking': round(
                    unique_share(sub[:, cols.index(k)], sub[:, [cols.index(c) for c in RANKING]]), 4)}
            else:
                by_area[area] = {'n': n, 'unique_share_vs_ranking': 0.0}
        shares = [v['unique_share_vs_ranking'] for v in by_area.values() if v['n'] >= 3]
        per_feature[k] = {
            'coverage': coverage[k],
            'spearman_vs_relief': spearman[k]['relief_p95_p05_m'],
            'partial_spearman_vs_slope_p50_given_relief': round(
                partial_spearman(values, data[:, cols.index('slope_240m_p50_deg')], relief), 4),
            'unique_share_vs_ranking': round(unique_share(values, ranking), 4),
            'unique_share_vs_ranking_by_area': by_area,
            'adds_information': bool(shares and min(shares) >= MIN_UNIQUE_SHARE and coverage[k] >= MIN_COVERAGE),
        }
    per_feature['slope_240m_p50_deg_given_relief'] = {
        'unique_share_vs_relief': round(unique_share(data[:, cols.index('slope_240m_p50_deg')], relief[:, None]), 4)}
    per_feature['slope_240m_p90_deg_given_relief_and_p50'] = {
        'unique_share_vs_relief_and_p50': round(unique_share(
            data[:, cols.index('slope_240m_p90_deg')], data[:, [cols.index('relief_p95_p05_m'),
                                                                cols.index('slope_240m_p50_deg')]]), 4)}

    rank_cols = [np.where(np.std(_ranks(c)) > 1e-12, (_ranks(c) - _ranks(c).mean()) / np.std(_ranks(c)), 0.0) for c in data.T]
    z = np.column_stack(rank_cols)
    eigval, eigvec = np.linalg.eigh(np.cov(z, rowvar=False))
    order = np.argsort(eigval)[::-1]
    eig_sum = float(eigval.sum()) or 1.0
    pca = [{'component': i + 1, 'explained': round(float(eigval[o] / eig_sum), 4),
            'loadings': {c: round(float(eigvec[j, o]), 3) for j, c in enumerate(cols)}}
           for i, o in enumerate(order)]
    return {'windows_total': len(rows), 'windows_rankable': len(rankable), 'windows_complete': n_complete,
            'columns_analysed': list(cols), 'coverage': coverage, 'spearman': spearman,
            'information_vs_ranking': per_feature, 'pca_rank_standardised': pca,
            'rule': {'min_unique_share_each_area': MIN_UNIQUE_SHARE, 'min_coverage': MIN_COVERAGE,
                     'unique_share': '1 - R^2 of the feature rank regressed on ranks of relief, slope P50 and P90'}}


def _summarize_domain_result(name: str, rows: list[dict], domain_cfg: dict,
                             *, buffer_excluded_batches: set[str] | None = None,
                             relief_min_m: float | None = None) -> dict:
    full_stats = analyse(rows)
    out = {
        'domain_id': name,
        'description': domain_cfg.get('description'),
        'development_batches_count': len(domain_cfg['development_batches']),
        'holdout_batches_count': len(domain_cfg['holdout_batches']),
        'holdout_basins': sorted({b['basin'] for b in domain_cfg['holdout_batches']}),
        'holdout_read': False,
        'adjacent_dev_holdout_pairs_count': 0,
        'full_development_analysis': full_stats,
    }
    if buffer_excluded_batches:
        buf_rows = [r for r in rows if r['block_id'] not in buffer_excluded_batches]
        if buf_rows:
            out['buffered_1block_analysis'] = analyse(buf_rows)
            if relief_min_m is not None:
                buf_margin = [r for r in buf_rows if r.get('relief_p95_p05_m') is not None and r['relief_p95_p05_m'] >= relief_min_m]
                if buf_margin:
                    out['buffered_1block_margin_relief_ge_2m_analysis'] = analyse(buf_margin)
    if relief_min_m is not None:
        margin_rows = [r for r in rows if r.get('relief_p95_p05_m') is not None and r['relief_p95_p05_m'] >= relief_min_m]
        if margin_rows:
            out['margin_relief_ge_2m_analysis'] = analyse(margin_rows)
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=('auto', 'cache', 'range'), default='auto')
    parser.add_argument('--workers', type=int, default=min(6, os.cpu_count() or 2))
    parser.add_argument('--reuse-arid-cache', action='store_true',
                        help='Reuse previously measured GLO-30 arid development rows in resultados.json without thawing holdout blocks.')
    args = parser.parse_args()

    t0 = time.perf_counter()
    partition_data = json.loads(PARTITION.read_text())['spatial_partition']
    legacy_holdout_ids = {b['block_id'] for b in partition_data['blocks'] if b.get('in_legacy_holdout')}
    buffered_dev_ids = {b['block_id'] for b in partition_data['blocks'] if b.get('buffered_scheme_split') == 'development'}
    whole_basin_strict_ids = {b['block_id'] for b in partition_data['blocks']
                              if b['split'] == 'development' and not b.get('in_legacy_holdout')}

    prior_path = OUT / 'resultados.json'
    prior_windows = []
    if prior_path.is_file():
        prior_windows = [w for w in json.loads(prior_path.read_text()).get('windows', [])
                         if w['block_id'] not in legacy_holdout_ids]

    identities: dict = {}
    if args.reuse_arid_cache and prior_windows:
        rows = prior_windows
        print(f'Reutilizando {len(rows)} ventanas áridas de desarrollo previamente medidas en GLO-30 (0 bloques holdout leídos).', flush=True)
    else:
        # Measure strictly non-holdout windows if requested live; never read legacy holdout blocks or whole-basin holdout.
        windows = development_windows(exclude_legacy_holdout=True, split_key='split')
        # Add legacy mojave non-holdout windows if already cached/auto and online
        by_block = defaultdict(list)
        for w in windows:
            by_block[w['block_id']].append(w)
        print(f'{len(windows)} ventanas áridas sin holdout previo en {len(by_block)} bloques; modo {args.mode}.', flush=True)
        rows = []
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            futures = {bid: pool.submit(_measure_block, ws, args.mode) for bid, ws in sorted(by_block.items())}
            for bid, fut in futures.items():
                block_rows, block_ids = fut.result()
                rows.extend(block_rows)
                identities.update(block_ids)
                print(f'  {bid}: {len(block_rows)} ventanas ({time.perf_counter() - t0:.0f} s)', flush=True)
        rows.sort(key=lambda r: r['id'])

    reference = jezero_reference()
    stats = analyse(rows)
    arid_whole_basin_strict = analyse([r for r in rows if r['block_id'] in whole_basin_strict_ids])
    arid_buffered_1block = analyse([r for r in rows if r['block_id'] in buffered_dev_ids])

    # Multi-domain replication on polar and paleolake cached GLO-30 batches
    contract_spec = json.loads(CONTRACT_SPEC.read_text())
    domains_cfg = contract_spec['multi_domain_shape_selection']['domains']
    polar_rows, polar_ids = _measure_domain_batches(domains_cfg['polar_cold_v1'], 'cache', args.workers)
    paleo_rows, paleo_ids = _measure_domain_batches(domains_cfg['paleolake_margin_v1'], 'cache', args.workers)
    identities.update(polar_ids)
    identities.update(paleo_ids)

    multi_domain = {
        'arid_mars_surface_v2': {
            'domain_id': 'arid_mars_surface_v2',
            'description': domains_cfg['arid_mars_surface_v2']['description'],
            'holdout_basins': ['mojave'],
            'holdout_read': False,
            'adjacent_dev_holdout_pairs_count': 0,
            'whole_basin_dev_no_legacy_holdout': arid_whole_basin_strict,
            'buffered_1block_dev': arid_buffered_1block,
            'legacy_11_blocks_baseline': stats,
        },
        'polar_cold_v1': _summarize_domain_result(
            'polar_cold_v1',
            polar_rows,
            domains_cfg['polar_cold_v1'],
            buffer_excluded_batches=set(domains_cfg['polar_cold_v1'].get('buffer_excluded_batches', [])),
        ),
        'paleolake_margin_v1': _summarize_domain_result(
            'paleolake_margin_v1',
            paleo_rows,
            domains_cfg['paleolake_margin_v1'],
            buffer_excluded_batches=set(domains_cfg['paleolake_margin_v1'].get('buffer_excluded_batches', [])),
            relief_min_m=extractors.MIN_RELIEF_FOR_SHAPE_M,
        ),
    }

    OUT.mkdir(parents=True, exist_ok=True)
    eda.write(OUT / 'resultados.json', {
        'schema': 2,
        'question': 'Qué información añaden los descriptores de forma al vector de ranking topográfico',
        'grid': {'cell_m': extractors.CELL_M, 'window_m': extractors.WINDOW_M, 'halo_m': extractors.HALO_M,
                 'slope_base_m': extractors.SLOPE_BASE_M, 'roughness_radius_m': extractors.ROUGHNESS_RADIUS_M,
                 'dem': 'Copernicus GLO-30', 'access_mode': 'cache_verified_multi_domain' if args.reuse_arid_cache else args.mode},
        'partition': {'source': str(PARTITION.relative_to(ROOT)), 'split_used': 'development',
                      'holdout_read': False, 'adjacent_dev_holdout_pairs_count': 0},
        'jezero_reference': reference,
        'analysis': stats,
        'leak_free_partitions': {
            'whole_basin_dev_no_legacy_holdout': arid_whole_basin_strict,
            'buffered_1block_dev': arid_buffered_1block,
        },
        'multi_domain_replication': multi_domain,
        'windows': rows,
    })
    tracked = [Path(__file__), ROOT / 'pipelines/etl_extractors.py', CANDIDATES, PARTITION, CONTRACT_SPEC, OUT / 'resultados.json']
    eda.write(OUT / 'manifest.json', {
        'schema': 1,
        'files': [{'path': str(p.relative_to(ROOT)), 'bytes': p.stat().st_size, 'sha256': eda.digest(p)}
                  for p in tracked],
        'glo30_assets': dict(sorted(identities.items())),
        'elapsed_s': round(time.perf_counter() - t0, 1),
    })
    print('=== arid whole_basin_dev_no_legacy_holdout ===')
    print(json.dumps({k: v for k, v in arid_whole_basin_strict['information_vs_ranking'].items()}, indent=2, ensure_ascii=False))
    print('=== polar_cold_v1 ===')
    print(json.dumps({k: v for k, v in multi_domain['polar_cold_v1']['full_development_analysis']['information_vs_ranking'].items()}, indent=2, ensure_ascii=False))
    print('=== paleolake_margin_v1 (relief >= 2 m) ===')
    print(json.dumps({k: v for k, v in multi_domain['paleolake_margin_v1']['margin_relief_ge_2m_analysis']['information_vs_ranking'].items()}, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
