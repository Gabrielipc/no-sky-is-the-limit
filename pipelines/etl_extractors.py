"""Raw-to-Feature extractors aligned with contrato-comun-superficie-v1 (Entrega 3).

Produces records conforming to `pipelines.etl_contract`:
  - Base window (3x3 km, 30 m cell, 720 m halo, 240 m slope base, 360 m roughness radius)
  - WorldCover + JRC surface eligibility gate, versioned per scenario (`pipelines.etl_eligibility`)
  - Conditional on-demand spectral (EMIT L2B) and temporal/thermal (HLS + Landsat ST) adapters
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import uuid

import numpy as np
from rasterio.transform import from_origin
from rasterio.warp import Resampling
from scipy.ndimage import correlate1d

from pipelines import atlas_sources as sources
from pipelines import atlas_topography as topo
from pipelines import etl_contract as contract
from pipelines import etl_eligibility as eligibility

CELL_M = 30
WINDOW_M = 3000
HALO_M = 720
SLOPE_BASE_M = 240
ROUGHNESS_RADIUS_M = 360
MIN_LAND_FRACTION = eligibility.MIN_LAND_FRACTION
MIN_VALID_TOPO = 0.95
MIN_COVER_SUPPORT = eligibility.MIN_COVER_SUPPORT


def utm_zone_band(zone: int) -> str:
    """Coarse partition key (~60 UTM/UPS buckets) to avoid millions of tiny folders."""
    if zone in (32661, 32761):
        return str(zone)
    hemi = 'N' if zone < 32700 else 'S'
    band = ((zone % 100) - 1) // 6
    return f'{hemi}{band:02d}'


def make_manifest_id(asset_ids: list[str], extra: str = '') -> str:
    payload = '|'.join(sorted(asset_ids)) + ('|' + extra if extra else '')
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()[:16]


def classify_eligibility(
    land_fraction: float,
    cover_valid_fraction: float | None,
    bare_or_sparse: float | None,
    trees: float | None,
    built: float | None,
    ice: float | None,
    permanent_water: float | None,
    *,
    water_occurrence_ge50: float | None = None,
    moss_lichen: float | None = None,
    profile: str = eligibility.DEFAULT_PROFILE,
) -> str:
    """Apply the scenario surface eligibility gate (see `pipelines.etl_eligibility`)."""
    return eligibility.classify(
        {
            'bare_or_sparse_fraction': bare_or_sparse,
            'trees_fraction': trees,
            'built_fraction': built,
            'snow_ice_fraction': ice,
            'permanent_water_fraction': permanent_water,
            'moss_lichen_fraction': moss_lichen,
            'water_occurrence_ge50_fraction': water_occurrence_ge50,
        },
        land_fraction=land_fraction,
        cover_valid_fraction=cover_valid_fraction,
        profile_id=profile,
    )


def center_crop(array: np.ndarray, side_m: int, cell_m: int) -> np.ndarray:
    n = side_m // cell_m
    start = (array.shape[0] - n) // 2
    return array[start:start + n, start:start + n]


def gradient_fixed_base(elevation: np.ndarray, cell_m: int, base_m: int) -> tuple[np.ndarray, np.ndarray]:
    """East and north elevation gradients (m/m) by central differences at a fixed physical base.

    Cells without finite samples along both axes of the base are NaN; the output keeps
    the input shape (row 0 is north).
    """
    if base_m < 2 * cell_m or base_m % (2 * cell_m):
        raise ValueError('Slope base must be an even multiple of the cell size')
    step = base_m // (2 * cell_m)
    height, width = elevation.shape
    center = elevation[step:-step, step:-step]
    valid = np.isfinite(center)
    for offset in range(-step, step + 1):
        valid &= np.isfinite(elevation[step + offset:height - step + offset, step:-step])
        valid &= np.isfinite(elevation[step:-step, step + offset:width - step + offset])
    dx = (elevation[step:-step, 2 * step:] - elevation[step:-step, :-2 * step]) / base_m
    dy = (elevation[:-2 * step, step:-step] - elevation[2 * step:, step:-step]) / base_m

    def pad(values: np.ndarray) -> np.ndarray:
        return np.pad(np.where(valid, values, np.nan), step, constant_values=np.nan)

    return pad(dx), pad(dy)


def slope_fixed_base(elevation: np.ndarray, cell_m: int, base_m: int) -> np.ndarray:
    """Slope angle (degrees) from `gradient_fixed_base`."""
    dx, dy = gradient_fixed_base(elevation, cell_m, base_m)
    return np.degrees(np.arctan(np.hypot(dx, dy)))


SHAPE_FEATURE_KEYS = (
    'hypsometric_integral',
    'elevation_skew_p95_p05',
    'aspect_240m_resultant_length',
    'slope_240m_gt15_fraction',
    'slope_240m_gt25_fraction',
)
MIN_RELIEF_FOR_SHAPE_M = 2.0
MIN_ASPECT_SLOPE_DEG = 1.0
MIN_ASPECT_CELL_FRACTION = 0.10


def shape_features(z_valid: np.ndarray, dx_valid: np.ndarray, dy_valid: np.ndarray) -> dict:
    """Shape/organisation descriptors of one footprint (audit 2026-11-14, section 1.1).

    - `hypsometric_integral`: (mean - P5) / (P95 - P5); low in infilled basins/fans, high on plateaus.
    - `elevation_skew_p95_p05`: (P95 + P5 - 2 P50) / (P95 - P5), bounded in [-1, 1]; positive
      when a flat floor is bordered by higher ground (crater, playa).
    - `aspect_240m_resultant_length`: mean resultant length of downslope unit vectors for cells
      steeper than 1 deg; 1 = one dominant facing (fan, escarpment), 0 = isotropic relief.
    - `slope_240m_gt15/25_fraction`: share of valid cells steeper than 15 / 25 deg.

    Elevation-based descriptors are None when P95 - P5 < 2 m, where quantisation and
    datum noise dominate; aspect is None when fewer than 10 % of cells exceed 1 deg.
    """
    out = dict.fromkeys(SHAPE_FEATURE_KEYS)
    if z_valid.size:
        p5, p50, p95 = np.percentile(z_valid, [5, 50, 95])
        span = p95 - p5
        if span >= MIN_RELIEF_FOR_SHAPE_M:
            out['hypsometric_integral'] = float(np.clip((z_valid.mean() - p5) / span, 0.0, 1.0))
            out['elevation_skew_p95_p05'] = float((p95 + p5 - 2.0 * p50) / span)
    if dx_valid.size:
        slope = np.degrees(np.arctan(np.hypot(dx_valid, dy_valid)))
        out['slope_240m_gt15_fraction'] = float((slope > 15.0).mean())
        out['slope_240m_gt25_fraction'] = float((slope > 25.0).mean())
        inclined = slope > MIN_ASPECT_SLOPE_DEG
        if inclined.mean() >= MIN_ASPECT_CELL_FRACTION:
            norm = np.hypot(dx_valid[inclined], dy_valid[inclined])
            ux, uy = -dx_valid[inclined] / norm, -dy_valid[inclined] / norm
            out['aspect_240m_resultant_length'] = float(np.hypot(ux.mean(), uy.mean()))
    return out


def roughness_rms_separable(elevation: np.ndarray, cell_m: int, radius_m: int) -> np.ndarray:
    """Fast O(k) separable 1D plane-detrended RMS roughness matching geometry_descriptors."""
    if cell_m <= 0 or radius_m < cell_m or radius_m % cell_m:
        raise ValueError('Radio positivo y múltiplo del tamaño de celda')
    z = np.asarray(elevation, dtype=float)
    radius = int(radius_m // cell_m)
    k = 2 * radius + 1
    good = np.isfinite(z)
    offset = float(np.median(z[good])) if good.any() else 0.0
    a = np.where(good, z - offset, 0.0)

    ones = np.ones(k, dtype=float)
    ramp = np.arange(-radius, radius + 1, dtype=float) * cell_m

    def sep(arr: np.ndarray, kx: np.ndarray, ky: np.ndarray) -> np.ndarray:
        return correlate1d(
            correlate1d(arr, kx, axis=1, mode='constant', cval=0.0),
            ky,
            axis=0,
            mode='constant',
            cval=0.0,
        )

    count = sep(good.astype(float), ones, ones)
    total = sep(a, ones, ones)
    total2 = sep(a * a, ones, ones)
    sx = sep(a, ramp, ones)
    sy = sep(a, ones, ramp)
    n = k * k
    sum_r2 = k * float(np.sum(ramp * ramp))
    residual = (total2 - total * total / n - sx * sx / sum_r2 - sy * sy / sum_r2) / n
    roughness = np.sqrt(np.maximum(residual, 0.0))
    roughness[residual <= np.finfo(float).eps * np.maximum(total2 / n, 1.0) * 64] = 0.0
    roughness[count != n] = np.nan
    return roughness


def compute_topography_features(
    elevation: np.ndarray,
    land_mask: np.ndarray,
    cell_m: int = CELL_M,
    window_m: int = WINDOW_M,
    slope_base_m: int = SLOPE_BASE_M,
    roughness_radius_m: int = ROUGHNESS_RADIUS_M,
) -> dict:
    """Compute Entrega 3 topographic contract metrics from an elevation grid with halo."""
    masked = np.where(land_mask, elevation, np.nan)
    dx_240, dy_240 = gradient_fixed_base(masked, cell_m, slope_base_m)
    slp_240 = np.degrees(np.arctan(np.hypot(dx_240, dy_240)))
    rgh_360 = roughness_rms_separable(masked, cell_m, roughness_radius_m)

    z_core = center_crop(masked, window_m, cell_m)
    s_core = center_crop(slp_240, window_m, cell_m)
    dx_core = center_crop(dx_240, window_m, cell_m)
    dy_core = center_crop(dy_240, window_m, cell_m)
    r_core = center_crop(rgh_360, window_m, cell_m)
    area_core = center_crop(land_mask.astype('float64'), window_m, cell_m) > 0.5

    denom = int(area_core.sum())
    land_frac = float(area_core.mean())
    if denom == 0:
        return {
            'land_fraction': land_frac,
            'topo_valid_fraction': 0.0,
            'roughness_coverage': 0.0,
            'relief_p95_p05_m': None,
            'slope_240m_p50_deg': None,
            'slope_240m_p90_deg': None,
            'roughness_360m_p50_m': None,
            **dict.fromkeys(SHAPE_FEATURE_KEYS),
        }

    z_valid = z_core[area_core & np.isfinite(z_core)]
    s_valid = s_core[area_core & np.isfinite(s_core)]
    r_valid = r_core[area_core & np.isfinite(r_core)]

    z_cov = float(z_valid.size / denom)
    s_cov = float(s_valid.size / denom)
    r_cov = float(r_valid.size / denom)
    topo_valid = min(z_cov, s_cov)

    enough = topo_valid >= MIN_VALID_TOPO and z_valid.size > 0 and s_valid.size > 0
    relief = float(np.ptp(np.percentile(z_valid, [5, 95]))) if enough else None
    slope_p50 = float(np.median(s_valid)) if enough else None
    slope_p90 = float(np.percentile(s_valid, 90)) if enough else None
    roughness_p50 = float(np.median(r_valid)) if (enough and r_cov >= MIN_COVER_SUPPORT and r_valid.size > 0) else None
    s_mask = area_core & np.isfinite(s_core)
    shape = (
        shape_features(z_valid, dx_core[s_mask], dy_core[s_mask]) if enough
        else dict.fromkeys(SHAPE_FEATURE_KEYS)
    )

    return {
        'land_fraction': land_frac,
        'topo_valid_fraction': topo_valid,
        'roughness_coverage': r_cov,
        'relief_p95_p05_m': relief,
        'slope_240m_p50_deg': slope_p50,
        'slope_240m_p90_deg': slope_p90,
        'roughness_360m_p50_m': roughness_p50,
        **shape,
    }


MISSING_TILE_CAUSES = ('http_404', 'http_403')
COVER_FIELDS = (
    'cover_valid_fraction', 'bare_or_sparse_fraction', 'trees_fraction', 'built_fraction',
    'permanent_water_fraction', 'snow_ice_fraction', 'moss_lichen_fraction',
    'water_occurrence_mean_pct', 'water_extent_gt0_fraction', 'water_occurrence_ge50_fraction',
)


# Bump when the columns or values a batch writes change, so resume reprocesses older batches.
# 2: footprint shape descriptors, cover_status and versioned eligibility gate (2026-11-14).
FEATURE_VERSION = 2


def run_identity(stride_m: int) -> dict:
    """Parameters that change the result of a batch; resume only skips matching runs."""
    return {
        'grid_version': topo.GRID_VERSION, 'stride_m': int(stride_m), 'window_m': WINDOW_M, 'cell_m': CELL_M,
        'halo_m': HALO_M, 'slope_base_m': SLOPE_BASE_M, 'roughness_radius_m': ROUGHNESS_RADIUS_M,
        'feature_version': FEATURE_VERSION,
    }


# Batches written before run identities existed: same grid parameters, feature version 1
# (no shape descriptors nor cover_status), so they never match a current identity.
LEGACY_RUN_IDENTITY = {k: v for k, v in run_identity(10000).items() if k != 'feature_version'}


def asset_failures(rasters: topo.Rasters, entries: list[dict]) -> dict[str, str]:
    """Failures among `entries` that are access problems, not tiles absent from the catalogue."""
    return {
        e['id']: rasters.failures[e['id']] for e in entries
        if e['id'] in rasters.failures and rasters.failures[e['id']] not in MISSING_TILE_CAUSES
    }


def compute_cover_fields(
    rasters: topo.Rasters, crs: int, bounds: list, affine, shape: tuple[int, int], core_land: np.ndarray,
) -> tuple[dict, list[str], dict[str, str]]:
    """WorldCover/JRC fractions over the land part of the 3 km core.

    Returns the cover fields (with `cover_status`), the asset ids read and the access
    failures. `cover_status` separates a measurement from a missing tile (catalogue gap),
    an access failure and insufficient valid support.
    """
    wc_entries = [sources.worldcover_asset(*key) for key in topo.tile_keys(bounds, 3)]
    jrc_entries = [sources.jrc_asset(*key) for key in topo.tile_keys(bounds, 10)]
    cover, wc_ids = topo.mosaic(rasters, wc_entries, crs, bounds, affine, shape, Resampling.nearest, (10, 100))
    water, jrc_ids = topo.mosaic(rasters, jrc_entries, crs, bounds, affine, shape, Resampling.average, (0, 100))
    failures = asset_failures(rasters, wc_entries + jrc_entries)

    fields = dict.fromkeys(COVER_FIELDS)
    wc_core = center_crop(cover, WINDOW_M, CELL_M)[core_land]
    jrc_core = center_crop(water, WINDOW_M, CELL_M)[core_land]
    wc_valid = np.isin(wc_core, eligibility.WORLDCOVER_VALID)
    cover_valid_frac = float(wc_valid.mean()) if wc_core.size else 0.0
    fields['cover_valid_fraction'] = cover_valid_frac
    if cover_valid_frac >= MIN_COVER_SUPPORT:
        valid_wc = wc_core[wc_valid]
        for column, classes in eligibility.WORLDCOVER_CLASSES.items():
            fields[column] = float(np.isin(valid_wc, classes).mean())
    jrc_valid = np.isfinite(jrc_core)
    if jrc_core.size and float(jrc_valid.mean()) >= MIN_COVER_SUPPORT:
        valid_jrc = jrc_core[jrc_valid]
        fields['water_occurrence_mean_pct'] = float(valid_jrc.mean())
        fields['water_extent_gt0_fraction'] = float((valid_jrc > 0.0).mean())
        fields['water_occurrence_ge50_fraction'] = float((valid_jrc >= 50.0).mean())

    if failures:
        # Partial reads must not feed the gate (nor its SQL re-evaluation): keep only the cause.
        fields = dict.fromkeys(COVER_FIELDS)
        status = 'cover_fetch_failed'
    elif cover_valid_frac >= MIN_COVER_SUPPORT:
        status = 'measured'
    elif all(rasters.failures.get(e['id']) in MISSING_TILE_CAUSES for e in wc_entries):
        status = 'no_cover_tile'
    else:
        status = 'insufficient_cover_support'
    fields['cover_status'] = status
    return fields, wc_ids + jrc_ids, failures


def gate_cover_support(row: dict) -> float | None:
    """Cover support passed to the eligibility gate; None (pending) unless cover was actually read."""
    if row.get('cover_status') in ('measured', 'insufficient_cover_support'):
        return row['cover_valid_fraction']
    return None


def window_grid(zone: int, x: float, y: float, half_m: int, cell_m: int = CELL_M):
    """CRS, geographic read boxes, affine and shape of a square grid centred on (x, y)."""
    bounds = topo.geographic_boxes(zone, (x - half_m, y - half_m, x + half_m, y + half_m))
    size = 2 * half_m // cell_m
    return zone, bounds, from_origin(x - half_m, y + half_m, cell_m, cell_m), (size, size)


def extract_base_window(
    site: dict,
    land: topo.Land,
    rasters: topo.Rasters,
    inventory: dict,
    include_cover: bool = True,
    now: datetime | None = None,
) -> tuple[dict, list[dict]]:
    """Extract a single `base_windows` contract row and its source manifest entries."""
    now = now or datetime.now(timezone.utc)
    crs, bounds, affine, shape = window_grid(site['zone'], site['x'], site['y'], WINDOW_M // 2 + HALO_M)
    land_mask = land.mask(crs, bounds, affine, shape)

    core_land = center_crop(land_mask.astype('float64'), WINDOW_M, CELL_M) > 0.5
    land_fraction = float(core_land.mean())

    base_row = {
        'region_id': site['region_id'],
        'grid_version': topo.GRID_VERSION,
        'body': 'Earth',
        'utm_zone_band': utm_zone_band(crs),
        'batch_id': site['batch'],
        'longitude': float(site['longitude']),
        'latitude': float(site['latitude']),
        'window_m': WINDOW_M,
        'cell_m': CELL_M,
        'slope_base_m': SLOPE_BASE_M,
        'roughness_radius_m': ROUGHNESS_RADIUS_M,
        'land_fraction': land_fraction,
        'topo_valid_fraction': 0.0,
        'roughness_coverage': 0.0,
        'relief_p95_p05_m': None,
        'slope_240m_p50_deg': None,
        'slope_240m_p90_deg': None,
        'roughness_360m_p50_m': None,
        **dict.fromkeys(SHAPE_FEATURE_KEYS),
        'analog_surface_eligibility': 'excluded_insufficient_land',
        'eligibility_profile': eligibility.DEFAULT_PROFILE,
        'cover_status': 'not_requested',
        'cover_valid_fraction': None,
        'bare_or_sparse_fraction': None,
        'trees_fraction': None,
        'built_fraction': None,
        'permanent_water_fraction': None,
        'snow_ice_fraction': None,
        'moss_lichen_fraction': None,
        'water_occurrence_mean_pct': None,
        'water_extent_gt0_fraction': None,
        'water_occurrence_ge50_fraction': None,
        'qa_status': 'insufficient_land',
        'source_manifest_id': 'none',
        'updated_at': now,
    }
    if land_fraction < MIN_LAND_FRACTION:
        return base_row, []

    dem_entries = [inventory[key] for key in topo.tile_keys(bounds, 1) if key in inventory]
    z, dem_ids = topo.mosaic(rasters, dem_entries, crs, bounds, affine, shape, Resampling.average)
    dem_failures = asset_failures(rasters, dem_entries)
    if dem_failures:
        # Even a partial mosaic would bias the descriptors; the batch must be retried.
        base_row['qa_status'] = 'dem_fetch_failed'
        base_row['analog_surface_eligibility'] = 'pending_on_demand_cover_check'
        return base_row, []
    if not dem_ids:
        # No inventory tile, or tiles without data over the window: a catalogue gap.
        base_row['qa_status'] = 'dem_unavailable'
        base_row['analog_surface_eligibility'] = 'pending_on_demand_cover_check'
        return base_row, []

    topo_feats = compute_topography_features(z, land_mask)
    base_row.update(topo_feats)
    rankable = topo_feats['relief_p95_p05_m'] is not None
    base_row['qa_status'] = 'rankable' if rankable else 'insufficient_dem_support'

    all_ids = list(dem_ids)
    if include_cover and rankable:
        cover_fields, cover_ids, _ = compute_cover_fields(rasters, crs, bounds, affine, shape, core_land)
        base_row.update(cover_fields)
        all_ids.extend(cover_ids)

    base_row['analog_surface_eligibility'] = eligibility.classify(
        base_row,
        land_fraction=base_row['land_fraction'],
        cover_valid_fraction=gate_cover_support(base_row),
    )
    trees = base_row['trees_fraction']
    if trees is not None and trees > eligibility.MAX_TREES_FOR_ROUGHNESS:
        # Entrega 3: roughness is conditional on trees_fraction <= 0.05, regardless of the gate label.
        base_row['roughness_360m_p50_m'] = None

    manifest_id = make_manifest_id(all_ids, f'{rasters.mode}:{CELL_M}')
    base_row['source_manifest_id'] = manifest_id
    manifests = [
        {
            'source_manifest_id': manifest_id,
            'product_id': 'copernicus-glo30' if aid.startswith('Copernicus_') else (
                'esa-worldcover-2021' if aid.startswith('ESA_WorldCover') else 'jrc-gsw-v1_5'
            ),
            'asset_id': aid,
            'access_mode': rasters.mode,
            'sha256_or_etag': (rasters.identities.get(aid) or {}).get('sha256')
            or (rasters.identities.get(aid) or {}).get('etag'),
            'native_resolution_m': 10.0 if aid.startswith('ESA_WorldCover') else 30.0,
            'effective_resolution_m': 30.0,
            'observation_period': '2021' if aid.startswith('ESA_WorldCover') else (
                '1984-2024' if aid.startswith('occurrence_') else 'static'
            ),
            'created_at': now,
        }
        for aid in sorted(set(all_ids))
    ]
    return base_row, manifests


def batch_outcome(rows: list[dict], rasters: topo.Rasters, identity: dict) -> dict:
    """Completion record for a batch: complete only without DEM or cover access failures."""
    qa = {}
    cover = {}
    for row in rows:
        qa[row['qa_status']] = qa.get(row['qa_status'], 0) + 1
        cover[row['cover_status']] = cover.get(row['cover_status'], 0) + 1
    failed = qa.get('dem_fetch_failed', 0) + cover.get('cover_fetch_failed', 0)
    return {
        'status': 'incomplete' if failed else 'complete',
        'identity': identity,
        'windows': len(rows),
        'qa_counts': qa,
        'cover_counts': cover,
        'failed_assets': {k: v for k, v in sorted(rasters.failures.items()) if v not in MISSING_TILE_CAUSES},
    }


def build_spectral_record_from_emit_summary(
    region_id: str,
    complex_stats: dict[str, dict],
    source_manifest_id: str,
    now: datetime | None = None,
) -> dict:
    """Convert adapter output for the 6 spectral complexes into an `enrichment_spectral` row."""
    now = now or datetime.now(timezone.utc)
    row: dict = {
        'region_id': region_id,
        'instrument': 'EMIT_L2B',
        'source_manifest_id': source_manifest_id,
        'updated_at': now,
    }
    for cid in contract.SPECTRAL_COMPLEXES:
        item = complex_stats.get(cid, {})
        row[f'{cid}_p50'] = item.get('p50')
        row[f'{cid}_p95'] = item.get('p95')
        row[f'{cid}_active_fraction'] = item.get('active_fraction')
        row[f'{cid}_n_samples'] = item.get('n_samples')
        row[f'{cid}_status'] = item.get('status', 'unobserved_by_product')
    return row


def build_temporal_record(
    region_id: str,
    hls_ndvi_p50: float | None,
    hls_valid_fraction: float | None,
    hls_status: str,
    landsat_lst_p50_k: float | None,
    landsat_valid_fraction: float | None,
    thermal_status: str,
    source_manifest_id: str,
    thermal_inertia_p50: float | None = None,
    now: datetime | None = None,
) -> dict:
    """Build an `enrichment_temporal` row ready for delta append."""
    now = now or datetime.now(timezone.utc)
    return {
        'region_id': region_id,
        'hls_ndvi_p50': hls_ndvi_p50,
        'hls_valid_fraction': hls_valid_fraction,
        'hls_status': hls_status,
        'landsat_lst_p50_k': landsat_lst_p50_k,
        'landsat_valid_fraction': landsat_valid_fraction,
        'thermal_inertia_p50': thermal_inertia_p50,
        'thermal_status': thermal_status,
        'source_manifest_id': source_manifest_id,
        'updated_at': now,
    }


def make_delta_filename(prefix: str = 'delta') -> str:
    ts = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    return f'{prefix}_{ts}_{uuid.uuid4().hex[:8]}.parquet'
