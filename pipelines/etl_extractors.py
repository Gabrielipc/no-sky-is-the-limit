"""Raw-to-Feature extractors aligned with contrato-comun-superficie-v1 (Entrega 3).

Produces records conforming to `pipelines.etl_contract`:
  - Base window (3x3 km, 30 m cell, 720 m halo, 240 m slope base, 360 m roughness radius)
  - WorldCover + JRC surface eligibility gate
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

CELL_M = 30
WINDOW_M = 3000
HALO_M = 720
SLOPE_BASE_M = 240
ROUGHNESS_RADIUS_M = 360
MIN_LAND_FRACTION = 0.80
MIN_VALID_TOPO = 0.95
MIN_COVER_SUPPORT = 0.80


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
) -> str:
    """Apply the Entrega 3 hard surface eligibility gate."""
    if land_fraction < MIN_LAND_FRACTION:
        return 'excluded_insufficient_land'
    if cover_valid_fraction is None or cover_valid_fraction < MIN_COVER_SUPPORT:
        return 'pending_on_demand_cover_check'
    if permanent_water is not None and permanent_water > 0.0:
        return 'excluded_permanent_water'
    if trees is not None and trees > 0.05:
        return 'excluded_dense_canopy'
    if (built is not None and built > 0.02) or (ice is not None and ice > 0.05):
        return 'excluded_urban_or_ice'
    if bare_or_sparse is not None and bare_or_sparse >= 0.85:
        return 'eligible_arid_exposed'
    return 'excluded_dense_canopy'


def center_crop(array: np.ndarray, side_m: int, cell_m: int) -> np.ndarray:
    n = side_m // cell_m
    start = (array.shape[0] - n) // 2
    return array[start:start + n, start:start + n]


def slope_fixed_base(elevation: np.ndarray, cell_m: int, base_m: int) -> np.ndarray:
    """Central differences requiring finite samples along both axes at fixed physical base."""
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
    angles = np.degrees(np.arctan(np.hypot(dx, dy)))
    return np.pad(np.where(valid, angles, np.nan), step, constant_values=np.nan)


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
    slp_240 = slope_fixed_base(masked, cell_m, slope_base_m)
    rgh_360 = roughness_rms_separable(masked, cell_m, roughness_radius_m)

    z_core = center_crop(masked, window_m, cell_m)
    s_core = center_crop(slp_240, window_m, cell_m)
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

    return {
        'land_fraction': land_frac,
        'topo_valid_fraction': topo_valid,
        'roughness_coverage': r_cov,
        'relief_p95_p05_m': relief,
        'slope_240m_p50_deg': slope_p50,
        'slope_240m_p90_deg': slope_p90,
        'roughness_360m_p50_m': roughness_p50,
    }


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
    half = WINDOW_M // 2 + HALO_M
    x, y, crs = site['x'], site['y'], site['zone']
    bounds = topo.geographic_boxes(crs, (x - half, y - half, x + half, y + half))
    size = (WINDOW_M + HALO_M * 2) // CELL_M
    shape = (size, size)
    affine = from_origin(x - half, y + half, CELL_M, CELL_M)
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
        'analog_surface_eligibility': 'excluded_insufficient_land',
        'bare_or_sparse_fraction': None,
        'trees_fraction': None,
        'built_fraction': None,
        'permanent_water_fraction': None,
        'water_occurrence_mean_pct': None,
        'water_extent_gt0_fraction': None,
        'qa_status': 'insufficient_land',
        'source_manifest_id': 'none',
        'updated_at': now,
    }
    if land_fraction < MIN_LAND_FRACTION:
        return base_row, []

    dem_entries = [inventory[key] for key in topo.tile_keys(bounds, 1) if key in inventory]
    z, dem_ids = topo.mosaic(rasters, dem_entries, crs, bounds, affine, shape, Resampling.average)
    if not dem_ids:
        base_row['qa_status'] = 'dem_unavailable'
        base_row['analog_surface_eligibility'] = 'pending_on_demand_cover_check'
        return base_row, []

    topo_feats = compute_topography_features(z, land_mask)
    base_row.update(topo_feats)
    rankable = topo_feats['relief_p95_p05_m'] is not None
    base_row['qa_status'] = 'rankable' if rankable else 'insufficient_dem_support'

    all_ids = list(dem_ids)
    cover_valid_frac = None
    ice_frac = None
    if include_cover and rankable:
        wc_entries = [sources.worldcover_asset(*key) for key in topo.tile_keys(bounds, 3)]
        jrc_entries = [sources.jrc_asset(*key) for key in topo.tile_keys(bounds, 10)]
        cover, wc_ids = topo.mosaic(rasters, wc_entries, crs, bounds, affine, shape, Resampling.nearest, (10, 100))
        water, jrc_ids = topo.mosaic(rasters, jrc_entries, crs, bounds, affine, shape, Resampling.average, (0, 100))
        all_ids.extend(wc_ids)
        all_ids.extend(jrc_ids)

        wc_core = center_crop(cover, WINDOW_M, CELL_M)[core_land]
        jrc_core = center_crop(water, WINDOW_M, CELL_M)[core_land]
        wc_valid = np.isin(wc_core, [10, 20, 30, 40, 50, 60, 70, 80, 90, 95, 100])
        cover_valid_frac = float(wc_valid.mean()) if wc_core.size else 0.0
        if cover_valid_frac >= MIN_COVER_SUPPORT:
            valid_wc = wc_core[wc_valid]
            base_row['bare_or_sparse_fraction'] = float(np.isin(valid_wc, [60]).mean())
            base_row['trees_fraction'] = float(np.isin(valid_wc, [10]).mean())
            base_row['built_fraction'] = float(np.isin(valid_wc, [50]).mean())
            base_row['permanent_water_fraction'] = float(np.isin(valid_wc, [80]).mean())
            ice_frac = float(np.isin(valid_wc, [70]).mean())

        jrc_valid = np.isfinite(jrc_core)
        if jrc_core.size and float(jrc_valid.mean()) >= MIN_COVER_SUPPORT:
            valid_jrc = jrc_core[jrc_valid]
            base_row['water_occurrence_mean_pct'] = float(valid_jrc.mean())
            base_row['water_extent_gt0_fraction'] = float((valid_jrc > 0.0).mean())

    eligibility = classify_eligibility(
        land_fraction=base_row['land_fraction'],
        cover_valid_fraction=cover_valid_frac,
        bare_or_sparse=base_row['bare_or_sparse_fraction'],
        trees=base_row['trees_fraction'],
        built=base_row['built_fraction'],
        ice=ice_frac,
        permanent_water=base_row['permanent_water_fraction'],
    )
    base_row['analog_surface_eligibility'] = eligibility
    if eligibility == 'excluded_dense_canopy':
        # Entrega 3: roughness is conditional on trees_fraction <= 0.05
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
