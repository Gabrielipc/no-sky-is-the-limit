"""Lunar side of the feature store (audit 2026-11-14, section 2.1).

The challenge asks for permanent Moon base locations and Mars, but the contract only
knew Earth and Mars. This module adds the Moon with the same window contract:

- Topography of a lunar window goes to `base_windows` with exactly the Earth footprint
  (3 km core, 720 m halo, 30 m cell, 240 m slope base, 360 m roughness radius) and the
  same descriptors (`etl_extractors.compute_topography_features`), measured in a local
  azimuthal equidistant grid on the IAU lunar sphere, like the Jezero reference on Mars.
- Lunar-only products (illumination, permanently shadowed regions, Diviner temperatures
  and regolith thermophysics, Mini-RF CPR) go to `enrichment_lunar`. Illumination and PSR
  gate the lunar site; Diviner and Mini-RF are compared with Earth only by within-body rank.

Rows are partitioned by polar stereographic hemisphere (`MOON_SPS` / `MOON_NPS`) because the
LOLA polar products use those projections; only polar sites (|lat| >= 60 deg) are supported.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
import time
from pathlib import Path

import numpy as np
import rasterio
import rasterio.errors
from pyproj import CRS
from rasterio.transform import from_origin
from rasterio.warp import transform_bounds
from rasterio.windows import Window, from_bounds

from pipelines import atlas_sources as sources
from pipelines import etl_extractors as extractors
from pipelines.etl_lunar_schema import (  # noqa: F401  (re-exported)
    ENRICHMENT_LUNAR_SCHEMA, LUNAR_DIMENSIONS, LUNAR_RANGES, LUNAR_SITE_PROFILE, LUNAR_SITE_STATUS_ENUM,
)
from scripts import analizar_primer_caso as terrain

ROOT = Path(__file__).resolve().parents[1]
SPEC_PATH = ROOT / 'specs/sources/luna-polar-sur-v1.json'

MOON_RADIUS_M = 1_737_400.0
RADIUS_TOLERANCE_M = 1.0
PLANETARY_FRAME = 'MOON_ME_DE421'
GRID_VERSION = 'moon-aeqd-v1'
BATCH_PREFIX = 'moon-'
POLAR_MIN_ABS_LAT = 60.0
SOUTH_POLAR_STEREO = CRS.from_proj4(
    f'+proj=stere +lat_0=-90 +lat_ts=-90 +lon_0=0 +x_0=0 +y_0=0 +R={MOON_RADIUS_M:.0f} +units=m +no_defs'
)
NORTH_POLAR_STEREO = CRS.from_proj4(
    f'+proj=stere +lat_0=90 +lat_ts=90 +lon_0=0 +x_0=0 +y_0=0 +R={MOON_RADIUS_M:.0f} +units=m +no_defs'
)
# Elevation needs full support in every 30 m cell (as for Jezero); coarser products such as
# Diviner (240 m) still fill each cell from one native pixel, so the same tolerance applies.
SUPPORT_TOLERANCE = 1e-6
MIN_PRODUCT_SUPPORT = extractors.MIN_COVER_SUPPORT

# ---------------------------------------------------------------------------
# Geometry
# ---------------------------------------------------------------------------
def polar_partition(latitude: float) -> str:
    """Partition key of a lunar window: south or north polar stereographic hemisphere."""
    if abs(latitude) < POLAR_MIN_ABS_LAT:
        raise ValueError(f'Solo se admiten sitios lunares polares (|lat| >= {POLAR_MIN_ABS_LAT}°)')
    return 'MOON_SPS' if latitude < 0 else 'MOON_NPS'


def polar_crs(latitude: float) -> CRS:
    return SOUTH_POLAR_STEREO if polar_partition(latitude) == 'MOON_SPS' else NORTH_POLAR_STEREO


def local_crs(longitude: float, latitude: float) -> CRS:
    """Local azimuthal equidistant grid on the lunar sphere: true distances in the footprint."""
    return CRS.from_proj4(
        f'+proj=aeqd +lat_0={latitude} +lon_0={longitude} +R={MOON_RADIUS_M:.0f} +units=m +no_defs'
    )


def region_id(site_id: str) -> str:
    return f'{GRID_VERSION}:{site_id}'


def check_lunar_crs(crs) -> None:
    """Reject rasters not referenced to the IAU lunar sphere (R = 1737.4 km)."""
    if crs is None:
        raise ValueError('El ráster lunar no declara CRS')
    radius = CRS.from_wkt(crs.to_wkt()).ellipsoid.semi_major_metre
    if abs(radius - MOON_RADIUS_M) > RADIUS_TOLERANCE_M:
        raise ValueError(f'El radio del CRS ({radius} m) no es el lunar ({MOON_RADIUS_M} m)')


@dataclass(frozen=True)
class Footprint:
    """Local 30 m grid of `half_m` around a lunar site (row 0 is north of the site)."""
    longitude: float
    latitude: float
    half_m: int
    cell_m: int = extractors.CELL_M

    @property
    def crs(self) -> CRS:
        return local_crs(self.longitude, self.latitude)

    @property
    def transform(self):
        return from_origin(-self.half_m, self.half_m, self.cell_m, self.cell_m)

    @property
    def shape(self) -> tuple[int, int]:
        n = 2 * self.half_m // self.cell_m
        return n, n


def base_footprint(longitude: float, latitude: float) -> Footprint:
    return Footprint(longitude, latitude, extractors.WINDOW_M // 2 + extractors.HALO_M)


def core_footprint(longitude: float, latitude: float) -> Footprint:
    return Footprint(longitude, latitude, extractors.WINDOW_M // 2)


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------
def source_path(source: dict) -> str:
    """Local path when present (verified copy), otherwise a /vsicurl/ range read of the COG."""
    local = source.get('path')
    if local and (ROOT / local).exists():
        return str(ROOT / local)
    if source.get('url'):
        return f"/vsicurl/{source['url']}"
    raise FileNotFoundError(f"Fuente sin ruta local ni URL: {source.get('id')}")


def source_identity(source: dict, opened: str) -> dict:
    """SHA-256 of a local copy, or ETag/size/date of the remote object read by ranges."""
    if not opened.startswith('/vsicurl/'):
        h = hashlib.sha256()
        with open(opened, 'rb') as f:
            for block in iter(lambda: f.read(1024 * 1024), b''):
                h.update(block)
        return {'access_mode': 'cache', 'sha256_or_etag': h.hexdigest()}
    try:
        info = sources.remote_identity({'url': source['url']})
    except OSError as exc:  # identity is provenance, not a reason to drop a measured window
        info = {'status': f'network_error: {type(exc).__name__}'}
    tag = info.get('etag') or (
        f"len={info.get('bytes')};lm={info.get('last_modified')}" if info.get('status') == 'available' else None
    )
    return {'access_mode': 'range', 'sha256_or_etag': tag}


READ_ATTEMPTS = 4
READ_BACKOFF_S = 3.0


def read_footprint(opened: str, footprint: Footprint, scale: float = 1.0, offset: float = 0.0,
                   valid_range: tuple[float, float] | None = None) -> tuple[np.ndarray, np.ndarray, dict]:
    """Average a lunar raster onto `footprint`; cells without full native support are NaN.

    Returns (values, support, meta). Values are `raw * scale + offset` in SI units. Remote
    range reads that fail mid-tile are retried on a fresh handle; a partial read is never used.
    """
    for attempt in range(1, READ_ATTEMPTS + 1):
        try:
            return _read_footprint_once(opened, footprint, scale, offset, valid_range)
        except rasterio.errors.RasterioIOError:
            if not opened.startswith('/vsicurl/') or attempt == READ_ATTEMPTS:
                raise
            time.sleep(READ_BACKOFF_S * attempt)
    raise AssertionError('unreachable')


def _read_footprint_once(opened: str, footprint: Footprint, scale: float, offset: float,
                         valid_range: tuple[float, float] | None) -> tuple[np.ndarray, np.ndarray, dict]:
    with rasterio.open(opened) as ds:
        if ds.count < 1:
            raise ValueError('El ráster lunar no tiene bandas')
        check_lunar_crs(ds.crs)
        half = footprint.half_m
        bounds = transform_bounds(footprint.crs, ds.crs, -half, -half, half, half, densify_pts=41)
        w = from_bounds(*bounds, ds.transform)
        col, row = math.floor(w.col_off) - 2, math.floor(w.row_off) - 2
        win = Window(col, row, math.ceil(w.col_off + w.width) + 2 - col,
                     math.ceil(w.row_off + w.height) + 2 - row)
        masked = ds.read(1, window=win, boundless=True, masked=True).astype('float64')
        data = masked.filled(np.nan) * scale + offset
        valid = ~np.ma.getmaskarray(masked) & np.isfinite(data)
        if valid_range is not None:
            valid &= (data >= valid_range[0]) & (data <= valid_range[1])
        data[~valid] = np.nan
        values, support = terrain.aggregate(
            data, valid, ds.window_transform(win), ds.crs, footprint.crs, footprint.transform,
            footprint.shape, SUPPORT_TOLERANCE,
        )
        meta = {
            'crs_wkt': ds.crs.to_wkt(),
            'native_resolution_m': float(abs(ds.res[0])),
            'source_window': [int(win.col_off), int(win.row_off), int(win.width), int(win.height)],
            'crop_valid_fraction': float(valid.mean()) if valid.size else 0.0,
        }
    return values, support, meta


def manifest_row(manifest_id: str, source: dict, identity: dict, meta: dict, now: datetime) -> dict:
    return {
        'source_manifest_id': manifest_id,
        'product_id': source['product_id'],
        'asset_id': source['asset_id'],
        'access_mode': identity['access_mode'],
        'sha256_or_etag': identity['sha256_or_etag'],
        'native_resolution_m': meta['native_resolution_m'],
        'effective_resolution_m': float(max(meta['native_resolution_m'], extractors.CELL_M)),
        'observation_period': source.get('observation_period'),
        'created_at': now,
        'crs_wkt': meta['crs_wkt'],
        'planetary_frame': PLANETARY_FRAME,
    }


# ---------------------------------------------------------------------------
# Topography (base_windows)
# ---------------------------------------------------------------------------
def build_base_row(site: dict, topo_feats: dict | None, manifest_id: str, now: datetime) -> dict:
    """A `base_windows` row for a lunar window, with Earth-only fields set to not requested."""
    feats = topo_feats or {}
    rankable = feats.get('relief_p95_p05_m') is not None
    row = {
        'region_id': region_id(site['id']),
        'grid_version': GRID_VERSION,
        'body': 'Moon',
        'utm_zone_band': polar_partition(site['latitude']),
        'batch_id': f"{BATCH_PREFIX}{site['id']}",  # one Parquet part per site
        'longitude': float(site['longitude']),
        'latitude': float(site['latitude']),
        'window_m': extractors.WINDOW_M,
        'cell_m': extractors.CELL_M,
        'slope_base_m': extractors.SLOPE_BASE_M,
        'roughness_radius_m': extractors.ROUGHNESS_RADIUS_M,
        'land_fraction': 1.0,
        'topo_valid_fraction': feats.get('topo_valid_fraction', 0.0),
        'roughness_coverage': feats.get('roughness_coverage', 0.0),
        'relief_p95_p05_m': feats.get('relief_p95_p05_m'),
        'slope_240m_p50_deg': feats.get('slope_240m_p50_deg'),
        'slope_240m_p90_deg': feats.get('slope_240m_p90_deg'),
        'roughness_360m_p50_m': feats.get('roughness_360m_p50_m'),
        **{k: feats.get(k) for k in extractors.SHAPE_FEATURE_KEYS},
        'analog_surface_eligibility': 'moon_reference_surface',
        'eligibility_profile': 'moon_reference',
        'cover_status': 'not_requested',
        **dict.fromkeys(extractors.COVER_FIELDS),
        'qa_status': 'rankable' if rankable else ('insufficient_dem_support' if topo_feats else 'dem_unavailable'),
        'source_manifest_id': manifest_id,
        'updated_at': now,
    }
    return row


def extract_lunar_window(site: dict, dem: dict, now: datetime | None = None) -> tuple[dict, list[dict], dict]:
    """Measure the base topographic contract of a lunar site from a LOLA DEM source.

    Returns (base row, manifest rows, diagnostics with support and native step).
    """
    now = now or datetime.now(timezone.utc)
    footprint = base_footprint(site['longitude'], site['latitude'])
    opened = source_path(dem)
    z, support, meta = read_footprint(opened, footprint, dem.get('scale', 1.0), dem.get('offset', 0.0),
                                      tuple(dem['valid_range_m']) if dem.get('valid_range_m') else None)
    if not np.isfinite(z).any():
        row = build_base_row(site, None, 'none', now)
        return row, [], {'support_mean': float(support.mean()), **meta}
    feats = extractors.compute_topography_features(z, np.ones(z.shape, bool))
    identity = source_identity(dem, opened)
    manifest_id = extractors.make_manifest_id([dem['asset_id']], f"{identity['access_mode']}:{extractors.CELL_M}:moon")
    row = build_base_row(site, feats, manifest_id, now)
    diagnostics = {'support_mean': float(support.mean()), **meta}
    return row, [manifest_row(manifest_id, dem, identity, meta, now)], diagnostics


# ---------------------------------------------------------------------------
# Lunar-only dimensions (enrichment_lunar)
# ---------------------------------------------------------------------------
def _stat(values: np.ndarray, stat: str) -> float:
    if stat == 'mean':
        return float(values.mean())
    if stat.startswith('p'):
        return float(np.percentile(values, float(stat[1:])))
    raise ValueError(f'Estadístico desconocido: {stat}')


def summarize_layers(dim: str, layers: dict[str, dict], arrays: dict[str, np.ndarray]) -> tuple[dict, float]:
    """Column values of one dimension over the core footprint and the shared valid fraction.

    `arrays` maps each source id to its footprint grid. Cells count as valid only when every
    source of the dimension is finite, so all columns share one denominator. Amplitude
    (`diviner_tamp_p50_k`) is the per-cell median of Tmax - Tmin, not a difference of medians.
    """
    stack = [arrays[layer['source']] for layer in layers.values() if layer['source'] in arrays]
    if not stack:
        return dict.fromkeys(LUNAR_DIMENSIONS[dim]), 0.0
    valid = np.logical_and.reduce([np.isfinite(a) for a in stack])
    fraction = float(valid.mean())
    out = dict.fromkeys(LUNAR_DIMENSIONS[dim])
    if fraction < MIN_PRODUCT_SUPPORT:
        return out, fraction
    for column, layer in layers.items():
        if layer.get('stat') == 'derived_difference':
            a, b = arrays[layer['source']], arrays[layer['minus']]
            out[column] = float(np.median((a - b)[valid]))
        else:
            out[column] = _stat(arrays[layer['source']][valid], layer['stat'])
    return out, fraction


def dimension_status(dim: str, values: dict, fraction: float, configured: bool) -> str:
    if not configured:
        return 'on_demand_fetchable'
    if fraction == 0.0:
        return 'no_swath_coverage'
    if fraction < MIN_PRODUCT_SUPPORT:
        return 'insufficient_coverage'
    if dim == 'psr' and values['psr_fraction'] == 0.0:
        return 'measured_absent'
    return 'measured'


def classify_lunar_site(base_row: dict, lunar: dict, thresholds: dict) -> str:
    """Lunar site gate (`lunar_polar_base_v1`): volatile target, illuminated base or exclusion.

    Order: a footprint mostly in permanent shadow is a volatile target; otherwise steep
    terrain is excluded, then illumination decides. Thresholds are initial decisions to be
    validated against published Artemis candidate regions.
    """
    psr = lunar.get('psr_fraction')
    if psr is not None and psr >= thresholds['min_psr_fraction_for_volatile_target']:
        return 'volatile_target_psr'
    slope_p90 = base_row.get('slope_240m_p90_deg')
    if slope_p90 is None:
        return 'pending_topography'
    if slope_p90 > thresholds['max_slope_240m_p90_deg']:
        return 'excluded_steep'
    illumination = lunar.get('illumination_mean_fraction')
    if illumination is None:
        return 'pending_illumination'
    if illumination < thresholds['min_illumination_mean_fraction']:
        return 'excluded_low_illumination'
    return 'base_candidate_illuminated'


def extract_lunar_dimensions(site: dict, base_row: dict, spec: dict,
                             now: datetime | None = None) -> tuple[dict, list[dict], dict]:
    """Measure the configured lunar products over the 3 km core of `site`.

    A dimension whose sources are not `confirmed` in the spec keeps `on_demand_fetchable`;
    nothing is guessed. Returns (enrichment_lunar row, manifest rows, diagnostics).
    """
    now = now or datetime.now(timezone.utc)
    footprint = core_footprint(site['longitude'], site['latitude'])
    srcs = spec['sources']
    arrays: dict[str, np.ndarray] = {}
    used: dict[str, tuple[dict, dict, dict]] = {}
    row: dict = {'region_id': region_id(site['id'])}
    diagnostics: dict = {}
    for dim, dim_spec in spec['dimensions'].items():
        layers = dim_spec['layers']
        needed = {layer['source'] for layer in layers.values()} | {
            layer['minus'] for layer in layers.values() if 'minus' in layer
        }
        configured = all(srcs[s].get('status') == 'confirmed' for s in needed)
        if configured:
            for sid in sorted(needed - arrays.keys()):
                src = {**srcs[sid], 'id': sid}
                opened = source_path(src)
                vr = tuple(src['valid_range']) if src.get('valid_range') else None
                values, _, meta = read_footprint(opened, footprint, src.get('scale', 1.0), src.get('offset', 0.0), vr)
                arrays[sid] = values
                used[sid] = (src, source_identity(src, opened), meta)
        values, fraction = summarize_layers(dim, layers, arrays) if configured else (
            dict.fromkeys(LUNAR_DIMENSIONS[dim]), None)
        row.update(values)
        row[f'{dim}_valid_fraction'] = fraction
        row[f'{dim}_status'] = dimension_status(dim, values, fraction or 0.0, configured)
        diagnostics[dim] = {'configured': configured, 'sources': sorted(needed)}

    row['lunar_site_profile'] = LUNAR_SITE_PROFILE
    row['lunar_site_status'] = classify_lunar_site(base_row, row, spec['site_gate'][LUNAR_SITE_PROFILE])
    manifest_id = extractors.make_manifest_id(
        [s['asset_id'] for s, _, _ in used.values()], f'lunar:{extractors.CELL_M}'
    ) if used else 'none'
    row['source_manifest_id'] = manifest_id
    row['updated_at'] = now
    manifests = [manifest_row(manifest_id, s, ident, meta, now) for s, ident, meta in used.values()]
    return row, manifests, diagnostics


LOCAL_SEARCH_M = 300


def site_position_check(z_core: np.ndarray, psr_core: np.ndarray | None, cell_m: int = extractors.CELL_M) -> dict:
    """Independent check of published coordinates against the DEM (and PSR map) of the footprint.

    A highly illuminated point should sit on locally high ground and outside permanent shadow.
    Reports the elevation percentile of the centre within the 3 km core, the distance from the
    centre to the highest cell within +-300 m, and the PSR value at the centre and over the core.
    It does not move the site: the published coordinates stay the reference.
    """
    n = z_core.shape[0]
    c = n // 2
    centre = z_core[c - 1:c + 1, c - 1:c + 1]
    zc = float(np.nanmean(centre))
    r = LOCAL_SEARCH_M // cell_m
    box = z_core[c - r:c + r, c - r:c + r]
    i, j = np.unravel_index(np.nanargmax(box), box.shape)
    out = {
        'centre_elevation_m': zc,
        'centre_elevation_percentile_in_core': float((z_core[np.isfinite(z_core)] < zc).mean()),
        'distance_to_local_max_m': float(cell_m * np.hypot(i - r + 0.5, j - r + 0.5)),
        'local_search_half_side_m': LOCAL_SEARCH_M,
        'psr_at_centre': None,
        'psr_core_fraction': None,
    }
    if psr_core is not None:
        out['psr_at_centre'] = float(np.nanmean(psr_core[c - 1:c + 1, c - 1:c + 1]))
        out['psr_core_fraction'] = float(np.nanmean(psr_core))
    return out


def check_site_position(site: dict, spec: dict) -> dict:
    """`site_position_check` for a spec site, reading the DEM and, if confirmed, the PSR map."""
    fp = core_footprint(site['longitude'], site['latitude'])
    dem = {**spec['sources'][site['dem_source']], 'id': site['dem_source']}
    z, _, _ = read_footprint(source_path(dem), fp, dem.get('scale', 1.0), dem.get('offset', 0.0))
    psr_src = spec['sources'].get('lola_lpsr_80s_20mpp', {})
    psr = None
    if psr_src.get('status') == 'confirmed':
        psr, _, _ = read_footprint(source_path({**psr_src, 'id': 'lola_lpsr_80s_20mpp'}), fp)
    return site_position_check(z, psr)


def load_spec(path: Path = SPEC_PATH) -> dict:
    spec = json.loads(Path(path).read_text(encoding='utf-8'))
    if spec.get('radius_m') != MOON_RADIUS_M or spec.get('planetary_frame') != PLANETARY_FRAME:
        raise ValueError('La especificación lunar no usa la esfera IAU ni el marco MOON_ME/DE421')
    return spec


def site_by_id(spec: dict, site_id: str) -> dict:
    for site in spec['sites']:
        if site['id'] == site_id:
            return site
    raise KeyError(f'Sitio lunar desconocido: {site_id}')
