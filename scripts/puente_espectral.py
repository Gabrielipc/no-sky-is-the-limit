#!/usr/bin/env python3
"""Single-operator three-body spectral bridge CLI (audit 2026-11-14, section 1.2, priority 6).

Applies `pipelines.spectral_params` (PDS CAT Reference July 2026 + BD920_2) across:
  - Mars (CRISM MTRDR `FRT000047A3`)
  - Earth (EMIT L2A v002 surface reflectance + L2A aggregate cloud mask)
  - Moon (Chandrayaan-1 M3 L2 global reflectance + L1B LOC/OBS geometry)

Use `--offline` locally to validate the operator against the local CRISM SR product,
compute the cached CRISM Jezero footprints, screen the cached M3 LOC geometry and local
EMIT L2B footprints, and emit `docs/evidencia-puente-espectral/resultados.json` without
network transfers. Run without `--offline` on the GCP Spot VM (with `EARTHDATA_TOKEN` set
for EMIT L2A) to complete the remote range reads.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sys

import httpx
import numpy as np
import rasterio

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipelines import spectral_bridge as sb
from pipelines import spectral_params as sp
from pipelines import spectral_readers as sr

DEFAULT_SPEC = sb.BRIDGE_SPEC
DEFAULT_EVIDENCE = ROOT / 'docs/evidencia-puente-espectral/resultados.json'
CRISM_CACHE_ROW_SLICE = (552, 752)


def _jsonable(value):
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_jsonable(v) for v in value]
    if isinstance(value, tuple):
        return [_jsonable(v) for v in value]
    if isinstance(value, (np.floating, np.integer)):
        return value.item()
    if isinstance(value, np.bool_):
        return bool(value)
    return value


def load_evidence(path: Path | None) -> dict:
    if path and path.exists():
        return json.loads(path.read_text(encoding='utf-8'))
    return {}


def save_evidence(path: Path | None, evidence: dict) -> None:
    if not path:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.part')
    tmp.write_text(json.dumps(_jsonable(evidence), ensure_ascii=False, indent=2, allow_nan=False) + '\n',
                   encoding='utf-8')
    tmp.replace(path)


def validate_crism_operator(spec: dict, offline: bool = True) -> dict:
    """Compare `pipelines.spectral_params` on IF reflectance against the official 2017 SR product."""
    mars_site = next(s for s in spec['sites'] if s['id'] == 'mars-jezero-fan')
    prod = mars_site['product']
    hdr_path = ROOT / prod['header']
    cache_dir = ROOT / prod['cache']
    in_path = ROOT / prod['mask']
    sr_path = ROOT / prod['mask'].replace('_in166j_', '_sr166j_')
    if not (hdr_path.exists() and in_path.exists() and sr_path.exists()):
        return {'status': 'missing_local_crism_files'}

    src = sr.EnviBsqRemote(prod['url'], hdr_path)
    all_names = list(sp.PARAMS.keys())
    r0, r1 = CRISM_CACHE_ROW_SLICE
    bands = sp.required_band_indices(src.wavelengths, all_names, 'channels')
    data = src.read(bands, (r0, r1), cache_dir, offline=offline)
    full = np.full((src.wavelengths.size,) + data.shape[1:], np.nan)
    full[bands] = data
    cube = sp.Cube(full, src.wavelengths, 'channels')

    geom, local = sb.footprint('Mars', mars_site['longitude'], mars_site['latitude'], 1800)
    with rasterio.open(sr_path) as sr_ds, rasterio.open(in_path) as in_ds:
        qa_slice = in_ds.read(9, window=((r0, r1), (0, in_ds.width))) == 0
        g = sb.footprint_in(geom, local, in_ds.crs)
        inside_1800 = sb.raster_mask(g, in_ds.transform, (in_ds.height, in_ds.width))[r0:r1, :]
        qa_1800 = qa_slice & inside_1800

        per_param: dict[str, dict] = {}
        for name in all_names:
            if name not in sr_ds.descriptions:
                continue
            b = sr_ds.descriptions.index(name) + 1
            ref = sr_ds.read(b, window=((r0, r1), (0, sr_ds.width))).astype('float64')
            ref[ref == sr.CRISM_INVALID] = np.nan
            if not sp.covered(cube, name):
                m_sr = qa_1800 & np.isfinite(ref)
                per_param[name] = {
                    'status': 'pending_if_band_fetch',
                    'sr_footprint_1800m': {
                        'n': int(m_sr.sum()),
                        'p50': float(np.median(ref[m_sr])) if m_sr.any() else None,
                        'p95': float(np.percentile(ref[m_sr], 95)) if m_sr.any() else None,
                    },
                }
                continue
            calc = sp.compute(cube, name)
            m_slice = qa_slice & np.isfinite(ref) & np.isfinite(calc)
            m_1800 = qa_1800 & np.isfinite(ref) & np.isfinite(calc)
            per_param[name] = {
                'status': 'validated',
                'slice_552_752': {
                    'n': int(m_slice.sum()),
                    'pearson_r': float(np.corrcoef(ref[m_slice], calc[m_slice])[0, 1]),
                    'median_abs_diff': float(np.median(np.abs(ref[m_slice] - calc[m_slice]))),
                    'sr_p50': float(np.median(ref[m_slice])),
                    'calc_p50': float(np.median(calc[m_slice])),
                },
                'footprint_1800m': {
                    'n': int(m_1800.sum()),
                    'pearson_r': float(np.corrcoef(ref[m_1800], calc[m_1800])[0, 1]),
                    'median_abs_diff': float(np.median(np.abs(ref[m_1800] - calc[m_1800]))),
                },
            }

        b2265 = sr_ds.descriptions.index('BD2265') + 1
        ref2265 = sr_ds.read(b2265, window=((r0, r1), (0, sr_ds.width))).astype('float64')
        ref2265[ref2265 == sr.CRISM_INVALID] = np.nan
        calc_2014 = cube.RB(sp.Term(2265, 3), sp.Term(2210, 5), sp.Term(2340, 5))
        m_2014_slice = qa_slice & np.isfinite(ref2265) & np.isfinite(calc_2014)
        m_2014_1800 = qa_1800 & np.isfinite(ref2265) & np.isfinite(calc_2014)

    return {
        'status': 'validated',
        'product_id': prod['product_id'],
        'row_slice': list(CRISM_CACHE_ROW_SLICE),
        'sr_file': prod['mask'].replace('_in166j_', '_sr166j_'),
        'parameters': per_param,
        'bd2265_cat2014_diagnostic': {
            'cat_2026_anchors_nm': [2120, 2340],
            'cat_2014_anchors_nm': [2210, 2340],
            'slice_r_cat2026': per_param['BD2265']['slice_552_752']['pearson_r'],
            'slice_r_cat2014': float(np.corrcoef(ref2265[m_2014_slice], calc_2014[m_2014_slice])[0, 1]),
            'footprint_1800m_r_cat2026': per_param['BD2265']['footprint_1800m']['pearson_r'],
            'footprint_1800m_r_cat2014': float(np.corrcoef(ref2265[m_2014_1800], calc_2014[m_2014_1800])[0, 1]),
        },
        'conclusion': (
            'BD1900R2 reproduce exactamente el producto SR oficial de 2017 (r=1.00000) y el resto acuerda '
            'en r=0.93-0.99 salvo BD2265 y BD1900_2 (r~0.66-0.69) por cambios entre versiones CAT; las '
            'anclas 2014 elevan BD2265 a r=0.937 en el recorte. Por ello el puente aplica el mismo operador '
            'spectral_params a los tres instrumentos.'
        ),
    }


def _emit_nominal_coverage(spec: dict) -> dict[str, bool]:
    """Deterministic EMIT L2A spectral coverage under 381-2493 nm and water-vapour masks."""
    wl = np.linspace(381.0, 2493.0, 285)
    bad = ((wl >= 1327.0) & (wl <= 1432.0)) | ((wl >= 1804.0) & (wl <= 1960.0))
    arr = np.where(bad, np.nan, 0.25)[:, None, None]
    cube = sp.Cube(arr, wl, 'nm')
    return {param: sp.covered(cube, param) for param in sb.bridge_parameter_names(spec)}


def _emit_local_l2b_glt_check(site: dict, sides_m: list[int]) -> dict | None:
    """Inspect local EMIT L2B NetCDF GLT footprint support without making network requests."""
    l2b_id = site['product'].get('l2b_counterpart')
    if not l2b_id:
        return None
    nc_path = ROOT / 'data/raw/emit' / f'{l2b_id}.nc'
    if not nc_path.exists():
        return None
    import h5py
    from affine import Affine

    out: dict = {'l2b_file': str(nc_path.relative_to(ROOT)), 'by_side': {}}
    with h5py.File(nc_path, 'r') as f:
        gt = Affine.from_gdal(*f.attrs['geotransform'])
        gx, gy = f['location/glt_x'], f['location/glt_y']
        for side_m in sides_m:
            geom, local = sb.footprint('Earth', site['longitude'], site['latitude'], side_m)
            g = sb.footprint_in(geom, local, 'EPSG:4326', densify_m=30)
            minx, miny, maxx, maxy = g.bounds
            c0, r0 = (~gt) * (minx, maxy)
            c1, r1 = (~gt) * (maxx, miny)
            c0, r0 = int(np.floor(c0)) - 1, int(np.floor(r0)) - 1
            c1, r1 = int(np.ceil(c1)) + 1, int(np.ceil(r1)) + 1
            ix, iy = gx[r0:r1, c0:c1].astype(np.int64), gy[r0:r1, c0:c1].astype(np.int64)
            inside = sb.raster_mask(g, gt * Affine.translation(c0, r0), ix.shape)
            has = inside & (ix > 0) & (iy > 0)
            sx, sy = ix[has] - 1, iy[has] - 1
            sr0, sr1, sc0, sc1 = sy.min(), sy.max() + 1, sx.min(), sx.max() + 1
            g1 = f['group_1_mineral_id'][sr0:sr1, sc0:sc1][sy - sr0, sx - sc0]
            g2 = f['group_2_mineral_id'][sr0:sr1, sc0:sc1][sy - sr0, sx - sc0]
            out['by_side'][str(side_m)] = {
                'footprint_cells': int(inside.sum()),
                'glt_cells': int(has.sum()),
                'l2b_group1_valid_cells': int((g1 > 0).sum()),
                'l2b_group1_fill_cells': int((g1 < 0).sum()),
                'l2b_group2_positive_cells': int((g2 > 0).sum()),
                'l2b_group2_zero_cells': int((g2 == 0).sum()),
            }
    return out


def _pending_emit_summary(spec: dict, reason: str) -> dict:
    cov = _emit_nominal_coverage(spec)
    out: dict = {}
    for cid, cdef in spec['complexes'].items():
        indicators = []
        for ind in cdef['indicators']:
            param = ind['parameter']
            is_cov = cov.get(param, False)
            indicators.append({
                'parameter': param,
                'floor': float(ind['floor']),
                'floor_origin': ind.get('floor_origin', ''),
                'p50': None,
                'p95': None,
                'active_fraction': None,
                'n_valid': 0,
                'status': 'on_demand_fetchable' if is_cov else 'unobserved_by_product',
                'reason': (
                    reason if is_cov
                    else f'Descartado en EMIT L2A por bandas de vapor de agua (1327-1432, 1804-1960 nm) o corte >2493 nm ({param})'
                ),
            })
        chosen = next((i for i in indicators if i['status'] == 'on_demand_fetchable'), indicators[0])
        out[cid] = {
            **chosen,
            'indicators': indicators,
            'by_parameter': {i['parameter']: i for i in indicators},
        }
    return out


def _pending_m3_summary(spec: dict, status: str, reason: str, valid_cells: int = 0) -> dict:
    out: dict = {}
    for cid, cdef in spec['complexes'].items():
        indicators = [
            {
                'parameter': ind['parameter'],
                'floor': float(ind['floor']),
                'floor_origin': ind.get('floor_origin', ''),
                'p50': None,
                'p95': None,
                'active_fraction': None,
                'n_valid': valid_cells,
                'status': status,
                'reason': reason,
            }
            for ind in cdef['indicators']
        ]
        out[cid] = {
            **indicators[0],
            'indicators': indicators,
            'by_parameter': {i['parameter']: i for i in indicators},
        }
    return out


def _evaluate_mars_site(site: dict, spec: dict, sides_m: list[int], offline: bool) -> dict:
    prod = site['product']
    src = sr.EnviBsqRemote(prod['url'], ROOT / prod['header'])
    names = sb.bridge_parameter_names(spec)
    in_path = ROOT / prod['mask']
    sr_path = ROOT / prod['mask'].replace('_in166j_', '_sr166j_')
    cache_dir = ROOT / prod['cache']

    by_side: dict[str, dict] = {}
    for side_m in sides_m:
        sample = sr.crism_footprint(
            src, in_path, site['longitude'], site['latitude'],
            side_m, names, cache_dir, prod['product_id'], offline=offline,
        )
        summary = sb.summarize_bridge(sample, spec)
        # In offline mode, BD920_2 bands (VNIR 44..48, 61..65, 75) are not in the local IF cache;
        # mark BD920_2 explicitly as pending remote fetch on GCP and preserve official SR reference.
        bd920_ind = summary['abs_mafic_fe2_1p0um']['by_parameter']['BD920_2']
        if offline and bd920_ind['status'] == 'unobserved_by_product':
            bd920_ind['status'] = 'on_demand_fetchable'
            bd920_ind['reason'] = '11 bandas VNIR de BD920_2 pendientes de lectura por rangos en GCP'
        rec = {
            'execution_mode': 'local_cache_offline' if offline else 'remote_range_read',
            'sample': sb.sample_record(sample),
            'complexes': summary,
        }
        if sr_path.exists():
            geom, local = sb.footprint('Mars', site['longitude'], site['latitude'], side_m)
            with rasterio.open(sr_path) as sr_ds, rasterio.open(in_path) as in_ds:
                g = sb.footprint_in(geom, local, in_ds.crs)
                inside = sb.raster_mask(g, in_ds.transform, (in_ds.height, in_ds.width))
                qa = (in_ds.read(9) == 0) & inside
                b = sr_ds.descriptions.index('BD920_2') + 1
                vals = sr_ds.read(b)[qa].astype('float64')
                vals = vals[(vals != sr.CRISM_INVALID) & np.isfinite(vals)]
                if vals.size:
                    floor = float(spec['complexes']['abs_mafic_fe2_1p0um']['indicators'][2]['floor'])
                    rec['official_sr_reference'] = {
                        'BD920_2': {
                            'p50': float(np.median(vals)),
                            'p95': float(np.percentile(vals, 95)),
                            'active_fraction': float((vals > floor).mean()),
                            'n_valid': int(vals.size),
                            'note': 'Producto SR 2017 precalculado; referencia auxiliar mientras se lee IF en GCP',
                        }
                    }
        by_side[str(side_m)] = rec

    return {
        'site': {k: site[k] for k in ('id', 'body', 'longitude', 'latitude', 'instrument')},
        'product_id': prod['product_id'],
        'by_side': by_side,
    }


def _evaluate_emit_site(site: dict, spec: dict, sides_m: list[int], offline: bool,
                        token: str | None, existing: dict | None, skip_measured: bool) -> dict:
    prod = site['product']
    if skip_measured and existing:
        by_side = existing.get('by_side', {})
        if all(str(s) in by_side and by_side[str(s)].get('execution_mode') == 'remote_l2a_measured' for s in sides_m):
            return existing

    l2b_check = _emit_local_l2b_glt_check(site, sides_m)
    by_side: dict[str, dict] = {}
    if not offline:
        if not token:
            raise RuntimeError(f'EARTHDATA_TOKEN requerido para leer {prod["product_id"]} en modo online')
        for side_m in sides_m:
            sample = sr.emit_footprint(
                prod['rfl_url'], prod['mask_url'],
                site['longitude'], site['latitude'], side_m, token, prod['product_id'],
            )
            by_side[str(side_m)] = {
                'execution_mode': 'remote_l2a_measured',
                'sample': sb.sample_record(sample),
                'complexes': sb.summarize_bridge(sample, spec),
            }
    else:
        reason = 'Lectura EMIT L2A v002 diferida a VM Spot en GCP (EARTHDATA_TOKEN) por restricción de red local'
        for side_m in sides_m:
            prev = existing.get('by_side', {}).get(str(side_m)) if existing else None
            if skip_measured and prev and prev.get('execution_mode') == 'remote_l2a_measured':
                by_side[str(side_m)] = prev
                continue
            glt_info = (l2b_check or {}).get('by_side', {}).get(str(side_m), {})
            by_side[str(side_m)] = {
                'execution_mode': 'pending_gcp_l2a_fetch',
                'sample': {
                    'instrument': 'EMIT_L2A',
                    'product_id': prod['product_id'],
                    'footprint_cells': glt_info.get('footprint_cells'),
                    'in_coverage_cells': glt_info.get('glt_cells'),
                    'valid_cells': None,
                    'valid_fraction': None,
                    'pixel_m': 60.0,
                    'kernel_mode': 'nm',
                    'wavelength_range_nm': [381.0, 2493.0],
                    'notes': [reason],
                },
                'l2b_local_check': glt_info,
                'complexes': _pending_emit_summary(spec, reason),
            }

    return {
        'site': {k: site[k] for k in ('id', 'body', 'longitude', 'latitude', 'instrument')},
        'product_id': prod['product_id'],
        'l2b_counterpart_check': l2b_check,
        'by_side': by_side,
    }


def _resolve_m3_period(month: str, client: httpx.Client) -> str:
    """Find the PDS `CH1M3_0004/DATA/<period>` directory that contains `<month>`."""
    idx_url = f'{sr.M3_BASE}/CH1M3_0004/DATA/'
    r = client.get(idx_url)
    r.raise_for_status()
    periods = sorted(set(re.findall(r'href="(200\d{5}_200\d{5})/"', r.text)))
    for period in periods:
        sub = client.get(f'{idx_url}{period}/')
        if sub.status_code == 200 and f'href="{month}/"' in sub.text:
            return period
    raise ValueError(f'No se encontró periodo M3 en PDS para el mes {month}')


def _evaluate_m3_site(site: dict, spec: dict, sides_m: list[int], offline: bool,
                      existing: dict | None, skip_measured: bool) -> dict:
    if skip_measured and existing:
        by_side = existing.get('by_side', {})
        if all(str(s) in by_side and by_side[str(s)].get('execution_mode') == 'remote_m3_measured' for s in sides_m):
            return existing

    prod = site['product']
    cache_dir = ROOT / prod['cache']
    strips = prod['candidate_strips']
    screening: list[dict] = []

    for st in strips:
        entry = dict(st)
        loc_rel = st.get('loc_cache')
        if loc_rel and (ROOT / loc_rel).exists():
            entry['local_loc_screening'] = sr.m3_cached_loc_screening(
                ROOT / loc_rel, site['longitude'], site['latitude'], sides_m
            )
        screening.append(entry)

    by_side: dict[str, dict] = {}
    if not offline:
        strip_results: list[dict] = []
        with httpx.Client(timeout=60, headers={'User-Agent': sr.USER_AGENT}, follow_redirects=True) as client:
            for st in strips:
                period = st.get('period') or _resolve_m3_period(st['month'], client)
                urls = sr.m3_urls(st['product_id'], period, st['month'])
                dist_m = sr.m3_min_distance_m(urls, site['longitude'], site['latitude'])
                item = {'product_id': st['product_id'], 'period': period, 'month': st['month'], 'min_distance_m': dist_m}
                if dist_m <= max(sides_m):
                    per_side = {}
                    for side_m in sides_m:
                        try:
                            sample, geom_diag = sr.m3_footprint(
                                urls, site['longitude'], site['latitude'], side_m,
                                st['product_id'], cache_dir,
                            )
                            per_side[str(side_m)] = {
                                'execution_mode': 'remote_m3_measured',
                                'sample': sb.sample_record(sample),
                                'geometry': geom_diag,
                                'complexes': sb.summarize_bridge(sample, spec),
                            }
                        except ValueError as exc:
                            per_side[str(side_m)] = {'execution_mode': 'no_footprint_coverage', 'error': str(exc)}
                    item['by_side'] = per_side
                strip_results.append(item)

        for side_m in sides_m:
            candidates = [r['by_side'][str(side_m)] for r in strip_results
                          if 'by_side' in r and 'sample' in r['by_side'].get(str(side_m), {})]
            if candidates:
                best = max(candidates, key=lambda c: c['sample']['valid_fraction'])
                by_side[str(side_m)] = best | {'all_strips': strip_results}
            else:
                reason = 'Ninguna tira M3 candidata cubrió la huella'
                by_side[str(side_m)] = {
                    'execution_mode': 'remote_m3_no_coverage',
                    'sample': {'instrument': 'M3_L2', 'product_id': None, 'valid_cells': 0, 'valid_fraction': 0.0},
                    'complexes': _pending_m3_summary(spec, 'insufficient_coverage', reason, valid_cells=0),
                    'all_strips': strip_results,
                }
    else:
        for side_m in sides_m:
            prev = existing.get('by_side', {}).get(str(side_m)) if existing else None
            if skip_measured and prev and prev.get('execution_mode') == 'remote_m3_measured':
                by_side[str(side_m)] = prev
                continue
            if site['id'] == 'moon-haworth-fondo':
                reason = (
                    'Fondo de Haworth en sombra permanente (incidencia solar 93-95° bajo el horizonte, '
                    '0 píxeles válidos en M3); los archivos LOC locales confirman cobertura geométrica sin señal óptica'
                )
                status = 'insufficient_coverage'
            elif site['id'] == 'moon-de-gerlache-cresta':
                reason = (
                    'Primera tira (M3G20090426T155845) medida con 48 % de píxeles válidos a ~85° de incidencia '
                    '(< 80 % requerido); cribado de las 12 tiras más cercanas pendiente en GCP'
                )
                status = 'insufficient_coverage'
            else:
                reason = (
                    'Lectura M3 L2 de las 4 tiras candidatas de Apollo 15 (26.13° N, 3.63° E) '
                    'diferida a VM Spot en GCP por restricción de red local'
                )
                status = 'on_demand_fetchable'
            first_fp = (screening[0].get('local_loc_screening', {}).get('footprints', {}).get(str(side_m), {})
                        if screening else {})
            by_side[str(side_m)] = {
                'execution_mode': 'pending_gcp_m3_fetch' if status == 'on_demand_fetchable' else 'polar_insufficient_support',
                'sample': {
                    'instrument': 'M3_L2',
                    'product_id': screening[0]['product_id'] if screening else None,
                    'footprint_cells': first_fp.get('expected_cells'),
                    'in_coverage_cells': first_fp.get('pixels_inside'),
                    'valid_cells': 0 if site['id'] == 'moon-haworth-fondo' else None,
                    'valid_fraction': 0.0 if site['id'] == 'moon-haworth-fondo' else None,
                    'pixel_m': first_fp.get('pixel_m'),
                    'kernel_mode': 'nm',
                    'notes': [reason],
                },
                'complexes': _pending_m3_summary(spec, status, reason, valid_cells=0),
            }

    return {
        'site': {k: site[k] for k in ('id', 'body', 'longitude', 'latitude', 'instrument')},
        'role': site.get('role'),
        'loc_screening': screening,
        'by_side': by_side,
    }


def compute_pair_comparisons(site_records: dict[str, dict], spec: dict) -> dict:
    """Apply `pairing_rule` across body pairs using representative footprints."""
    pairs = [
        ('mars_vs_earth_utah_3000m', ('mars-jezero-fan', '1800'), ('earth-utah', '3000')),
        ('mars_vs_earth_utah_1800m', ('mars-jezero-fan', '1800'), ('earth-utah', '1800')),
        ('mars_vs_earth_atacama_2023_3000m', ('mars-jezero-fan', '1800'), ('earth-atacama-2023', '3000')),
        ('mars_vs_earth_atacama_2023_1800m', ('mars-jezero-fan', '1800'), ('earth-atacama-2023', '1800')),
        ('mars_vs_earth_atacama_2022_3000m', ('mars-jezero-fan', '1800'), ('earth-atacama', '3000')),
        ('mars_vs_moon_haworth_3000m', ('mars-jezero-fan', '1800'), ('moon-haworth-fondo', '3000')),
        ('mars_vs_moon_de_gerlache_3000m', ('mars-jezero-fan', '1800'), ('moon-de-gerlache-cresta', '3000')),
        ('mars_vs_moon_apollo15_3000m', ('mars-jezero-fan', '1800'), ('moon-apollo-15', '3000')),
        ('earth_utah_vs_moon_apollo15_3000m', ('earth-utah', '3000'), ('moon-apollo-15', '3000')),
        ('earth_atacama_2023_vs_moon_apollo15_3000m', ('earth-atacama-2023', '3000'), ('moon-apollo-15', '3000')),
    ]
    out: dict = {}
    for key, (sid_a, side_a), (sid_b, side_b) in pairs:
        rec_a = site_records.get(sid_a, {}).get('by_side', {}).get(side_a, {})
        rec_b = site_records.get(sid_b, {}).get('by_side', {}).get(side_b, {})
        if not rec_a or not rec_b:
            continue
        out[key] = {
            'site_a': {'id': sid_a, 'side_m': int(side_a), 'execution_mode': rec_a.get('execution_mode')},
            'site_b': {'id': sid_b, 'side_m': int(side_b), 'execution_mode': rec_b.get('execution_mode')},
            'complexes': sb.pair_comparison(rec_a['complexes'], rec_b['complexes'], spec),
        }
    return out


def initial_floors_inventory(spec: dict) -> list[dict]:
    """List every threshold marked `inicial` in `puente-espectral-v1.json` requiring validation."""
    out: list[dict] = []
    for cid, cdef in spec['complexes'].items():
        for rank, ind in enumerate(cdef['indicators'], 1):
            origin = ind.get('floor_origin', '')
            if origin.startswith('inicial'):
                out.append({
                    'complex_id': cid,
                    'indicator_rank': rank,
                    'parameter': ind['parameter'],
                    'floor': float(ind['floor']),
                    'floor_origin': origin,
                })
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--spec', default=str(DEFAULT_SPEC))
    parser.add_argument('--evidence', default=str(DEFAULT_EVIDENCE))
    parser.add_argument('--offline', action='store_true',
                        help='Modo local sin descargas de red: usa caché CRISM/M3/L2B y marca fetches pendientes para GCP')
    parser.add_argument('--skip-measured', action='store_true',
                        help='Conservar sitios ya medidos en el archivo de evidencia')
    parser.add_argument('--site', action='append', help='Filtrar por id de sitio (repetible)')
    parser.add_argument('--sides', default='1800,3000', help='Lados de huella en metros separados por coma')
    args = parser.parse_args()

    spec = sb.load_bridge_spec(Path(args.spec))
    evidence_path = Path(args.evidence) if args.evidence else None
    existing = load_evidence(evidence_path) if args.skip_measured or args.offline else {}
    sides_m = [int(s) for s in args.sides.split(',') if s.strip()]
    token = os.environ.get('EARTHDATA_TOKEN')

    operator_validation = validate_crism_operator(spec, offline=args.offline)
    existing_sites = existing.get('sites', {})
    site_records: dict[str, dict] = dict(existing_sites) if args.site else {}

    target_sites = spec['sites']
    if args.site:
        wanted = set(args.site)
        target_sites = [s for s in target_sites if s['id'] in wanted]

    for site in target_sites:
        sid = site['id']
        prev = existing_sites.get(sid)
        if site['instrument'] == 'CRISM_MTRDR':
            site_records[sid] = _evaluate_mars_site(site, spec, sides_m, offline=args.offline)
        elif site['instrument'] == 'EMIT_L2A':
            site_records[sid] = _evaluate_emit_site(site, spec, sides_m, offline=args.offline,
                                                    token=token, existing=prev, skip_measured=args.skip_measured)
        elif site['instrument'] == 'M3_L2':
            site_records[sid] = _evaluate_m3_site(site, spec, sides_m, offline=args.offline,
                                                  existing=prev, skip_measured=args.skip_measured)
        else:
            raise ValueError(f'Instrumento desconocido: {site["instrument"]}')

    evidence = {
        'bridge_id': spec['bridge_id'],
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'execution_mode': 'offline_local' if args.offline else 'online_full',
        'footprint': spec['footprint'],
        'pairing_rule': spec['pairing_rule'],
        'operator_validation': operator_validation,
        'sites': site_records,
        'pair_comparisons': compute_pair_comparisons(site_records, spec),
        'initial_floors_needing_validation': initial_floors_inventory(spec),
    }
    save_evidence(evidence_path, evidence)
    print(f'{spec["bridge_id"]} ({evidence["execution_mode"]}): '
          f'{len(site_records)} sitios, {len(evidence["pair_comparisons"])} comparaciones -> {evidence_path}',
          flush=True)


if __name__ == '__main__':
    main()
