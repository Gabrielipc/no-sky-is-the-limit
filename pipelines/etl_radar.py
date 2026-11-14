"""RCM compact-polarimetry bridge to Mini-RF CPR (audit 2026-11-14, section 3, priority 7).

RCM transmits right circular and receives two orthogonal linear channels; the CEOS-ARD
product (NRCan, `rcm-ard` on the EODMS STAC, public on S3) already synthesises the
circular channels as terrain-flattened gamma-0 in linear power (RR, RL), the cross term
RR.RL* and per-pixel masks. Over the 3 km core of a site this module computes:

- CPR = <RR> / <RL> per 30 m cell. For a right-circular transmit, RR is the same sense and
  RL the opposite sense, so CPR is the same SC/OC ratio that Mini-RF (and Arecibo) report.
- S1 = RR + RL (total power, dB) and the degree of polarization
  m = sqrt((RL - RR)^2 + 4|RR.RL*|^2) / (RR + RL).

Each scene is resampled by area average in linear power onto the 30 m UTM grid of the
core, after masking every pixel not flagged valid (layover, shadow, saturation, no data)
and permanent water (JRC occurrence >= 50 %). Cells take the median over scenes; the
window statistics use only cells valid in at least `min_scenes`.

C band (5.6 cm) and Mini-RF S band (12.6 cm) see different roughness scales, and snow
changes C-band backscatter, so only snow-free months enter and bodies are compared by
within-body rank, never by absolute CPR.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import math
import urllib.parse
import urllib.request
import warnings

import numpy as np
import rasterio
import rasterio.errors
from rasterio.enums import Resampling
from rasterio.warp import reproject, transform_bounds
from rasterio.windows import Window, from_bounds

from pipelines import atlas_sources as sources
from pipelines import atlas_topography as topo
from pipelines import etl_extractors as ex
from pipelines.etl_bridges_schema import RADAR_INSTRUMENT

STAC_SEARCH = 'https://eodms-sgdot.nrcan-rncan.gc.ca/search/search'
COLLECTION = 'rcm-ard'
PRODUCT_ID = 'NRCan rcm-ard (CEOS-ARD NRB-POL, MLC, gamma-0)'
ASSET_HOST = 'rcm-ceos-ard.s3.ca-central-1.amazonaws.com'
CORE_HALF_M = ex.WINDOW_M // 2
VALID_BIT_VALUE = 1           # product.xml DataMask: 1 = valid data
WATER_OCCURRENCE_PCT = 50.0
MIN_SCENE_SUPPORT = 0.999     # a 30 m cell needs all its native pixels valid
MIN_VALID_FRACTION = ex.MIN_COVER_SUPPORT
DEFAULT_MONTHS = (7, 8, 9)    # snow-free window at high latitude; recorded in each run
RADAR_VALUE_KEYS = ('rcm_cpr_p50', 'rcm_cpr_p90', 'rcm_s1_p50_db', 'rcm_dop_p50', 'rcm_local_incidence_p50_deg')


# ---------------------------------------------------------------------------
# Polarimetric quantities (pure numpy)
# ---------------------------------------------------------------------------
def cpr(rr: np.ndarray, rl: np.ndarray) -> np.ndarray:
    """Circular polarization ratio SC/OC for a right-circular transmit (RR / RL)."""
    with np.errstate(divide='ignore', invalid='ignore'):
        out = rr / rl
    out[~(np.isfinite(out) & (rl > 0))] = np.nan
    return out


def total_power_db(rr: np.ndarray, rl: np.ndarray) -> np.ndarray:
    s1 = rr + rl
    with np.errstate(divide='ignore', invalid='ignore'):
        out = 10.0 * np.log10(s1)
    out[~(s1 > 0)] = np.nan
    return out


def degree_of_polarization(rr: np.ndarray, rl: np.ndarray, rrrl_abs: np.ndarray) -> np.ndarray:
    """m = |S2, S3, S4| / S1 from the circular-basis covariance; clipped to [0, 1]."""
    s1 = rr + rl
    with np.errstate(divide='ignore', invalid='ignore'):
        m = np.sqrt((rl - rr) ** 2 + 4.0 * rrrl_abs ** 2) / s1
    m[~(s1 > 0)] = np.nan
    return np.clip(m, 0.0, 1.0)


def summarize_cells(stack: dict[str, np.ndarray], min_scenes: int = 1) -> tuple[dict, float]:
    """Window statistics from per-scene grids (scene, row, col); median over scenes per cell."""
    rr, rl = stack['rr'], stack['rl']
    n_valid = np.sum(np.isfinite(rr) & np.isfinite(rl), axis=0)
    keep = n_valid >= min_scenes
    fraction = float(keep.mean()) if keep.size else 0.0
    out = dict.fromkeys(RADAR_VALUE_KEYS)
    if not keep.any():
        return out, fraction
    with warnings.catch_warnings():  # all-NaN cells outside `keep` are expected
        warnings.simplefilter('ignore', RuntimeWarning)
        c = np.nanmedian(cpr(rr, rl), axis=0)[keep]
        s = np.nanmedian(total_power_db(rr, rl), axis=0)[keep]
        m = np.nanmedian(degree_of_polarization(rr, rl, stack['rrrl_abs']), axis=0)[keep]
        inc = np.nanmedian(stack['inc'], axis=0)[keep]
    c, s, m, inc = (v[np.isfinite(v)] for v in (c, s, m, inc))
    out.update({
        'rcm_cpr_p50': float(np.percentile(c, 50)) if c.size else None,
        'rcm_cpr_p90': float(np.percentile(c, 90)) if c.size else None,
        'rcm_s1_p50_db': float(np.percentile(s, 50)) if s.size else None,
        'rcm_dop_p50': float(np.percentile(m, 50)) if m.size else None,
        'rcm_local_incidence_p50_deg': float(np.percentile(inc, 50)) if inc.size else None,
    })
    return out, fraction


def radar_status(n_scenes: int, fraction: float) -> str:
    if n_scenes == 0:
        return 'no_swath_coverage'
    if fraction < MIN_VALID_FRACTION:
        return 'insufficient_coverage'
    return 'measured'


# ---------------------------------------------------------------------------
# Catalogue
# ---------------------------------------------------------------------------
def search_scenes(longitude: float, latitude: float, months: tuple[int, ...] = DEFAULT_MONTHS,
                  limit: int = 500) -> tuple[list[dict], int]:
    """rcm-ard items whose footprint contains the site, filtered to `months`.

    Returns (selected items, total items found at the point). Public STAC, no credentials.
    """
    body = json.dumps({'collections': [COLLECTION], 'limit': limit,
                       'intersects': {'type': 'Point', 'coordinates': [longitude, latitude]}}).encode()
    req = urllib.request.Request(STAC_SEARCH, data=body, headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=120) as response:
        items = json.load(response)['features']
    selected = []
    for item in items:
        p = item['properties']
        if p.get('sar:product_type') != 'MLC' or 'XC' not in (p.get('sar:polarizations') or []):
            continue
        if int(p['datetime'][5:7]) not in months:
            continue
        assets = item['assets']
        if not all(k in assets for k in ('rr', 'rl', 'rrrl', 'local_inc_angle', 'data_mask')):
            continue
        selected.append({
            'id': p.get('order_key') or item['id'],
            'datetime': p['datetime'],
            'orbit_state': p.get('sat:orbit_state'),
            'mode': p.get('sar:instrument_mode'),
            'assets': {k: assets[k]['href'] for k in ('rr', 'rl', 'rrrl', 'local_inc_angle', 'data_mask', 'metadata')},
        })
    selected.sort(key=lambda s: s['datetime'])
    return selected, len(items)


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Grid:
    """30 m UTM grid of the 3 km core of a site (same owner rule as the sweep)."""
    longitude: float
    latitude: float
    zone: int
    x0: float
    y0: float

    @classmethod
    def at(cls, longitude: float, latitude: float) -> 'Grid':
        zone = topo.owner(longitude, latitude)
        x0, y0 = topo.projection(topo.WGS84, zone).transform(longitude, latitude)
        return cls(longitude, latitude, zone, x0, y0)

    def spec(self):
        return ex.window_grid(self.zone, self.x0, self.y0, CORE_HALF_M)


def _check_host(url: str) -> str:
    if urllib.parse.urlsplit(url).hostname != ASSET_HOST:
        raise ValueError(f'Host no permitido para RCM: {url}')
    return '/vsicurl/' + url


def _read_crop(ds, crs, bounds_xy, band: int = 1):
    """Native-resolution crop of `ds` covering bounds (in `crs`), plus its transform."""
    b = transform_bounds(crs, ds.crs, *bounds_xy, densify_pts=21)
    w = from_bounds(*b, ds.transform)
    col, row = math.floor(w.col_off) - 2, math.floor(w.row_off) - 2
    win = Window(col, row, math.ceil(w.col_off + w.width) + 2 - col, math.ceil(w.row_off + w.height) + 2 - row)
    data = ds.read(band, window=win, boundless=True, fill_value=0)
    return data, ds.window_transform(win)


def _to_grid(data: np.ndarray, valid: np.ndarray, src_transform, src_crs, crs, affine, shape):
    """Area average of valid samples onto the core grid; cells without full support are NaN."""
    args = dict(src_transform=src_transform, src_crs=src_crs, dst_transform=affine, dst_crs=crs,
                resampling=Resampling.average, num_threads=1)
    out = np.full(shape, np.nan)
    support = np.zeros(shape)
    reproject(np.where(valid, data, np.nan).astype('float64'), out, src_nodata=np.nan, dst_nodata=np.nan, **args)
    reproject(valid.astype('float64'), support, dst_nodata=0, **args)
    out[support < MIN_SCENE_SUPPORT] = np.nan
    return out


def read_scene(scene: dict, grid: Grid, water: np.ndarray | None) -> tuple[dict[str, np.ndarray], dict]:
    """RR, RL, |RR.RL*| and local incidence of one scene on the core grid."""
    crs, _, affine, shape = grid.spec()
    half = CORE_HALF_M
    bounds_xy = (grid.x0 - half, grid.y0 - half, grid.x0 + half, grid.y0 + half)
    with rasterio.open(_check_host(scene['assets']['data_mask'])) as ds:
        mask, tr = _read_crop(ds, crs, bounds_xy)
        src_crs = ds.crs
    valid = mask == VALID_BIT_VALUE
    layers = {}
    for key in ('rr', 'rl', 'local_inc_angle'):
        with rasterio.open(_check_host(scene['assets'][key])) as ds:
            data, tr_k = _read_crop(ds, crs, bounds_xy)
            if tr_k != tr or data.shape != mask.shape:
                raise ValueError(f'{key} no comparte rejilla con la máscara en {scene["id"]}')
            layers[key] = data.astype('float64')
    with rasterio.open(_check_host(scene['assets']['rrrl'])) as ds:
        cdata, _ = _read_crop(ds, crs, bounds_xy)
    rrrl_abs = np.abs(cdata.astype('complex128'))
    valid &= (layers['rr'] > 0) & (layers['rl'] > 0) & np.isfinite(rrrl_abs)
    grids = {
        'rr': _to_grid(layers['rr'], valid, tr, src_crs, crs, affine, shape),
        'rl': _to_grid(layers['rl'], valid, tr, src_crs, crs, affine, shape),
        # The cross term is averaged in magnitude after the look average of the product.
        'rrrl_abs': _to_grid(rrrl_abs, valid, tr, src_crs, crs, affine, shape),
        'inc': _to_grid(layers['local_inc_angle'], valid, tr, src_crs, crs, affine, shape),
    }
    if water is not None:
        for g in grids.values():
            g[water] = np.nan
    meta = {'mask_valid_fraction': float(valid.mean()) if valid.size else 0.0,
            'crs_wkt': src_crs.to_wkt(), 'native_resolution_m': float(abs(tr.a))}
    return grids, meta


def water_mask(grid: Grid, rasters: topo.Rasters) -> np.ndarray | None:
    """Cells with JRC occurrence >= 50 % on the core grid (None if JRC is unreachable)."""
    crs, bounds, affine, shape = grid.spec()
    entries = [sources.jrc_asset(*k) for k in topo.tile_keys(bounds, 10)]
    occ, ids = topo.mosaic(rasters, entries, crs, bounds, affine, shape, Resampling.average, (0, 100))
    if not ids:
        return None
    return np.isfinite(occ) & (occ >= WATER_OCCURRENCE_PCT)


# ---------------------------------------------------------------------------
# Record
# ---------------------------------------------------------------------------
def extract_radar_record(site: dict, rasters: topo.Rasters | None = None, months: tuple[int, ...] = DEFAULT_MONTHS,
                         max_scenes: int | None = None, min_scenes: int = 1,
                         now: datetime | None = None) -> tuple[dict, list[dict], dict]:
    """CPR, S1 and degree of polarization of RCM over the 3 km core of `site`."""
    now = now or datetime.now(timezone.utc)
    grid = Grid.at(site['longitude'], site['latitude'])
    scenes, found = search_scenes(site['longitude'], site['latitude'], months)
    if max_scenes is not None and len(scenes) > max_scenes:
        # Spread the subset over the period instead of taking the first acquisitions.
        idx = np.unique(np.linspace(0, len(scenes) - 1, max_scenes).round().astype(int))
        scenes = [scenes[i] for i in idx]
    water = water_mask(grid, rasters) if rasters is not None else None
    stacks: dict[str, list[np.ndarray]] = {k: [] for k in ('rr', 'rl', 'rrrl_abs', 'inc')}
    used, failed, metas = [], [], {}
    for scene in scenes:
        try:
            grids, meta = read_scene(scene, grid, water)
        except (rasterio.errors.RasterioIOError, ValueError) as exc:
            failed.append({'id': scene['id'], 'error': f'{type(exc).__name__}: {str(exc)[:160]}'})
            continue
        if not np.isfinite(grids['rr']).any():
            failed.append({'id': scene['id'], 'error': 'sin píxeles válidos en el núcleo'})
            continue
        for k in stacks:
            stacks[k].append(grids[k])
        used.append(scene)
        metas[scene['id']] = meta
    if used:
        values, fraction = summarize_cells({k: np.stack(v) for k, v in stacks.items()}, min_scenes)
    else:
        values, fraction = dict.fromkeys(RADAR_VALUE_KEYS), 0.0
    dates = [s['datetime'][:10] for s in used]
    manifest_id = ex.make_manifest_id([s['id'] for s in used], 'rcm-ard-mlc') if used else 'none'
    row = {
        'region_id': site['region_id'],
        'instrument': RADAR_INSTRUMENT,
        'product_id': PRODUCT_ID,
        'observation_period': f'{dates[0]}/{dates[-1]}' if dates else None,
        'scenes_found': found,
        'n_scenes': len(used),
        **values,
        'rcm_valid_fraction': fraction,
        'radar_status': radar_status(len(used), fraction),
        'source_manifest_id': manifest_id,
        'updated_at': now,
    }
    manifests = [{
        'source_manifest_id': manifest_id,
        'product_id': PRODUCT_ID,
        'asset_id': s['id'],
        'access_mode': 'range',
        'sha256_or_etag': None,
        'native_resolution_m': metas[s['id']]['native_resolution_m'],
        'effective_resolution_m': float(ex.CELL_M),
        'observation_period': s['datetime'][:10],
        'created_at': now,
        'crs_wkt': metas[s['id']]['crs_wkt'],
        'planetary_frame': 'EARTH_WGS84',
    } for s in used]
    diagnostics = {
        'scenes_at_point': found,
        'scenes_selected': len(scenes),
        'months': list(months),
        'min_scenes_per_cell': min_scenes,
        'water_mask': 'jrc_occurrence_ge50' if water is not None else 'not_applied',
        'water_fraction': float(water.mean()) if water is not None else None,
        'scenes_failed': failed,
        'scenes_used': [{'id': s['id'], 'datetime': s['datetime'], 'orbit_state': s['orbit_state'],
                         'mask_valid_fraction': metas[s['id']]['mask_valid_fraction']} for s in used],
    }
    return row, manifests, diagnostics
