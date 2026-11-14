"""Extractors and adapters for the six official-source surface dimensions (`enrichment_surface`).

Covers Section 3 of the 2026-11-14 audit:
1. Aridity (NASA IMERG / JAXA GSMaP)
2. Soil moisture (NASA SMAP SPL3SMP_E.006)
3. Snow persistence (NASA MODIS MOD10A1.061 / JAXA SGLI SICE contrast)
4. Permafrost (ESA CCI Permafrost v5.0 from ESA Open Science Catalog)
5. Silicate thermal-IR emissivity (NASA ASTER GED v3, functional bridge to Diviner CF & THEMIS IR)
6. Decimetric SAR backscatter (Copernicus Sentinel-1 RTC / OPERA-S1, functional bridge to Mini-RF)
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

import numpy as np
from pyproj import CRS

from pipelines import etl_extractors as extractors
from pipelines.etl_surface_schema import SURFACE_DIMENSIONS

ROOT = Path(__file__).resolve().parents[1]
SURFACE_SPEC_PATH = ROOT / 'specs/sources/dimensiones-superficie-oficiales-v1.json'
MIN_VALID_FRACTION = 0.80
ASTER_TIR_WAVELENGTHS_UM = (8.29, 8.63, 9.08, 10.66, 11.32)
EARTH_CRS_WKT = CRS.from_epsg(4326).to_wkt()


def load_surface_spec() -> dict[str, Any]:
    return json.loads(SURFACE_SPEC_PATH.read_text(encoding='utf-8'))


def _parse_timestamp(value: datetime | str | None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    text = value.replace('Z', '+00:00')
    parsed = datetime.fromisoformat(text)
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


def compute_aridity_metrics(
    monthly_precip_mm: np.ndarray,
    *,
    min_valid_fraction: float = MIN_VALID_FRACTION,
    dry_month_threshold_mm: float = 5.0,
) -> tuple[dict[str, float | None], float, str]:
    """Compute annualized precipitation (mm/yr) and dry-month fraction from monthly totals.

    `monthly_precip_mm` has shape `(n_months,)` or `(n_months, ...)` in mm/month.
    """
    arr = np.asarray(monthly_precip_mm, dtype=np.float64)
    out: dict[str, float | None] = dict.fromkeys(SURFACE_DIMENSIONS['aridity'])
    if arr.size == 0:
        return out, 0.0, 'no_swath_coverage'
    valid = np.isfinite(arr) & (arr >= 0.0) & (arr <= 5000.0)
    valid_fraction = float(valid.mean())
    if valid_fraction == 0.0:
        return out, 0.0, 'no_swath_coverage'
    if valid_fraction < min_valid_fraction:
        return out, valid_fraction, 'insufficient_coverage'

    if arr.ndim == 1:
        monthly_means = arr[valid]
    else:
        masked = np.where(valid, arr, np.nan)
        spatial_axes = tuple(range(1, arr.ndim))
        raw_means = np.nanmean(masked, axis=spatial_axes)
        monthly_means = raw_means[np.isfinite(raw_means)]

    if monthly_means.size == 0:
        return out, 0.0, 'no_swath_coverage'
    out['precip_mean_annual_mm'] = float(np.clip(np.mean(monthly_means) * 12.0, 0.0, 15000.0))
    out['dry_months_fraction'] = float(np.mean(monthly_means < dry_month_threshold_mm))
    return out, valid_fraction, 'measured'


def compute_smap_moisture_metrics(
    sm_m3m3: np.ndarray,
    qa_flag: np.ndarray | None = None,
    *,
    min_valid_fraction: float = MIN_VALID_FRACTION,
) -> tuple[dict[str, float | None], float, str]:
    """Compute SMAP L3 surface soil moisture P50 and P90 (m^3/m^3) with QA filtering.

    If `qa_flag` is integer, bit 0 == 0 indicates recommended retrieval quality (SPL3SMP_E).
    If `qa_flag` is boolean, True indicates recommended quality.
    """
    sm = np.asarray(sm_m3m3, dtype=np.float64)
    out: dict[str, float | None] = dict.fromkeys(SURFACE_DIMENSIONS['soil_moisture'])
    if sm.size == 0:
        return out, 0.0, 'no_swath_coverage'

    valid = np.isfinite(sm) & (sm >= 0.0) & (sm <= 0.65)
    if qa_flag is not None:
        qa = np.asarray(qa_flag)
        if qa.shape != sm.shape:
            raise ValueError('qa_flag debe tener la misma forma que sm_m3m3')
        qa_ok = qa if qa.dtype == np.bool_ else ((qa.astype(np.int64) & 1) == 0)
        valid &= qa_ok

    valid_fraction = float(valid.mean())
    if valid_fraction == 0.0:
        return out, 0.0, 'no_swath_coverage'
    if valid_fraction < min_valid_fraction:
        return out, valid_fraction, 'insufficient_coverage'

    vals = sm[valid]
    out['smap_sm_p50_m3m3'] = float(np.percentile(vals, 50.0))
    out['smap_sm_p90_m3m3'] = float(np.percentile(vals, 90.0))
    return out, valid_fraction, 'measured'


def compute_mod10a1_snow_metrics(
    ndsi_snow_cover: np.ndarray,
    qa_flag: np.ndarray | None = None,
    *,
    min_valid_fraction: float = MIN_VALID_FRACTION,
) -> tuple[dict[str, float | None], float, str]:
    """Compute MOD10A1.061 snow persistence and clear-sky coverage over a footprint series.

    Valid clear observations have `0 <= NDSI_Snow_Cover <= 100` (and `Basic_QA <= 1` when
    integer QA is supplied, or `True` when boolean QA is supplied). Values > 100 represent
    clouds (250), night (211), ocean/water (237/239) or fill (255).
    """
    ndsi = np.asarray(ndsi_snow_cover, dtype=np.float64)
    out: dict[str, float | None] = dict.fromkeys(SURFACE_DIMENSIONS['snow_persistence'])
    if ndsi.size == 0:
        return out, 0.0, 'no_swath_coverage'

    clear = np.isfinite(ndsi) & (ndsi >= 0.0) & (ndsi <= 100.0)
    if qa_flag is not None:
        qa = np.asarray(qa_flag)
        if qa.shape != ndsi.shape:
            raise ValueError('qa_flag debe tener la misma forma que ndsi_snow_cover')
        qa_ok = qa if qa.dtype == np.bool_ else ((qa >= 0) & (qa <= 1))
        clear &= qa_ok

    clear_fraction = float(clear.mean())
    if clear_fraction == 0.0:
        return out, 0.0, 'no_swath_coverage'
    if clear_fraction < min_valid_fraction:
        return out, clear_fraction, 'insufficient_coverage'

    vals = ndsi[clear]
    out['mod10a1_snow_days_fraction'] = float(np.mean((vals >= 1.0) & (vals <= 100.0)))
    out['mod10a1_clear_days_fraction'] = clear_fraction
    return out, clear_fraction, 'measured'


def compute_permafrost_metrics(
    pfr_pct: np.ndarray,
    alt_m: np.ndarray | None = None,
    *,
    min_valid_fraction: float = MIN_VALID_FRACTION,
) -> tuple[dict[str, float | None], float, str]:
    """Compute ESA CCI Permafrost probability [0, 1] and median active-layer thickness (m)."""
    pfr = np.asarray(pfr_pct, dtype=np.float64)
    out: dict[str, float | None] = dict.fromkeys(SURFACE_DIMENSIONS['permafrost'])
    if pfr.size == 0:
        return out, 0.0, 'no_swath_coverage'

    pfr_valid = np.isfinite(pfr) & (pfr >= 0.0) & (pfr <= 100.0)
    valid_fraction = float(pfr_valid.mean())
    if valid_fraction == 0.0:
        return out, 0.0, 'no_swath_coverage'
    if valid_fraction < min_valid_fraction:
        return out, valid_fraction, 'insufficient_coverage'

    out['cci_permafrost_probability'] = float(np.clip(np.mean(pfr[pfr_valid]) / 100.0, 0.0, 1.0))

    if alt_m is not None:
        alt = np.asarray(alt_m, dtype=np.float64)
        if alt.shape != pfr.shape:
            raise ValueError('alt_m debe tener la misma forma que pfr_pct')
        alt_valid = pfr_valid & np.isfinite(alt) & (alt >= 0.0) & (alt <= 20.0)
        pf_present = pfr_valid & (pfr > 0.0)
        if pf_present.any() and float(alt_valid[pf_present].mean()) >= min_valid_fraction:
            out['cci_active_layer_thickness_m'] = float(np.median(alt[alt_valid]))
        elif (not pf_present.any()) and float(alt_valid.mean()) >= min_valid_fraction:
            out['cci_active_layer_thickness_m'] = float(np.median(alt[alt_valid]))
    return out, valid_fraction, 'measured'


def compute_aster_ged_emissivity_metrics(
    emissivity_b10_b14: np.ndarray,
    *,
    min_valid_fraction: float = MIN_VALID_FRACTION,
) -> tuple[dict[str, float | None], float, str]:
    """Compute ASTER GED v3 mafic-felsic emissivity index and estimated Christiansen feature (µm).

    `emissivity_b10_b14` has shape `(5, ...)` for ASTER TIR bands 10–14
    (nominal centers: 8.29, 8.63, 9.08, 10.66, 11.32 µm) in normalized units `[0, 1]`.
    """
    bands = np.asarray(emissivity_b10_b14, dtype=np.float64)
    out: dict[str, float | None] = dict.fromkeys(SURFACE_DIMENSIONS['thermal_emissivity'])
    if bands.ndim < 1 or bands.shape[0] != 5 or bands[0].size == 0:
        return out, 0.0, 'no_swath_coverage'

    valid = np.all(np.isfinite(bands) & (bands >= 0.4) & (bands <= 1.05), axis=0)
    e10, e11, e12, e13, _e14 = bands
    denom = e12 + e13
    valid &= denom > 0.2
    valid_fraction = float(valid.mean())
    if valid_fraction == 0.0:
        return out, 0.0, 'no_swath_coverage'
    if valid_fraction < min_valid_fraction:
        return out, valid_fraction, 'insufficient_coverage'

    mafic_index = (e10[valid] + e11[valid]) / denom[valid]
    out['aster_emissivity_mafic_index'] = float(np.clip(np.median(mafic_index), 0.5, 1.5))

    # Estimate Christiansen feature wavelength in [7.5, 9.5] um across 8.29, 8.63, 9.08 um.
    # Quartzose felsic rocks exhibit lower e10 than e13 due to the ~8.3 um Reststrahlen doublet,
    # placing CF shortward (< 8.29 um); mafic/ultramafic rocks peak across b10-b12.
    short_wl = np.array(ASTER_TIR_WAVELENGTHS_UM[:3], dtype=np.float64)
    e_short = np.stack([e10[valid], e11[valid], e12[valid]], axis=0)
    e_min = np.min(e_short, axis=0, keepdims=True)
    weights = np.maximum(e_short - e_min, 0.0)
    w_sum = np.sum(weights, axis=0)
    centroid_wl = np.where(
        w_sum > 1e-6,
        np.sum(weights * short_wl[:, None], axis=0) / np.maximum(w_sum, 1e-6),
        ASTER_TIR_WAVELENGTHS_UM[0],
    )
    felsic_shift = np.maximum(0.0, e13[valid] - e10[valid]) / np.maximum(e13[valid], 0.1)
    cf_est = np.where(e13[valid] > e10[valid], ASTER_TIR_WAVELENGTHS_UM[0] - 0.5 * felsic_shift, centroid_wl)
    out['aster_christiansen_wb_um'] = float(np.clip(np.median(cf_est), 7.5, 9.5))
    return out, valid_fraction, 'measured'


def compute_sentinel1_rtc_metrics(
    sigma0_vv_linear: np.ndarray,
    sigma0_vh_linear: np.ndarray,
    layover_shadow_mask: np.ndarray | None = None,
    *,
    min_valid_fraction: float = MIN_VALID_FRACTION,
) -> tuple[dict[str, float | None], float, str]:
    """Compute Sentinel-1 RTC median VV/VH sigma0 (dB) and VH/VV ratio (dB).

    Inputs are linear radar backscatter power (`sigma0 > 0`). Optional `layover_shadow_mask`
    uses `True`/nonzero to mark excluded layover or shadow pixels.
    """
    vv = np.asarray(sigma0_vv_linear, dtype=np.float64)
    vh = np.asarray(sigma0_vh_linear, dtype=np.float64)
    if vv.shape != vh.shape:
        raise ValueError('sigma0_vv_linear y sigma0_vh_linear deben tener la misma forma')
    out: dict[str, float | None] = dict.fromkeys(SURFACE_DIMENSIONS['sar_backscatter'])
    if vv.size == 0:
        return out, 0.0, 'no_swath_coverage'

    valid = np.isfinite(vv) & np.isfinite(vh) & (vv > 0.0) & (vh > 0.0)
    if layover_shadow_mask is not None:
        mask = np.asarray(layover_shadow_mask)
        if mask.shape != vv.shape:
            raise ValueError('layover_shadow_mask debe tener la misma forma que sigma0_vv_linear')
        valid &= ~mask.astype(bool)

    vv_db_all = np.where(valid, 10.0 * np.log10(np.maximum(vv, 1e-12)), np.nan)
    vh_db_all = np.where(valid, 10.0 * np.log10(np.maximum(vh, 1e-12)), np.nan)
    ratio_db_all = vh_db_all - vv_db_all
    valid &= (
        (vv_db_all >= -35.0) & (vv_db_all <= 10.0)
        & (vh_db_all >= -40.0) & (vh_db_all <= 5.0)
        & (ratio_db_all >= -25.0) & (ratio_db_all <= 10.0)
    )

    valid_fraction = float(valid.mean())
    if valid_fraction == 0.0:
        return out, 0.0, 'no_swath_coverage'
    if valid_fraction < min_valid_fraction:
        return out, valid_fraction, 'insufficient_coverage'

    out['s1_rtc_vv_p50_db'] = float(np.median(vv_db_all[valid]))
    out['s1_rtc_vh_p50_db'] = float(np.median(vh_db_all[valid]))
    out['s1_rtc_vh_vv_ratio_db'] = float(np.median(ratio_db_all[valid]))
    return out, valid_fraction, 'measured'


def extract_surface_dimensions_window(
    region_id: str,
    *,
    raw_inputs: dict[str, dict[str, Any]] | None = None,
    source_manifest_id: str = 'surface-official-v1',
    updated_at: datetime | str | None = None,
    min_valid_fraction: float = MIN_VALID_FRACTION,
) -> dict[str, Any]:
    """Assemble an `enrichment_surface` row for one window.

    Any dimension missing from `raw_inputs` receives `status = 'on_demand_fetchable'` with
    null metrics and null valid fraction; nothing is guessed or imputed.
    """
    inputs = raw_inputs or {}
    row: dict[str, Any] = {
        'region_id': region_id,
        'source_manifest_id': source_manifest_id,
        'updated_at': _parse_timestamp(updated_at),
    }
    extractors_map = {
        'aridity': lambda cfg: compute_aridity_metrics(
            cfg['monthly_precip_mm'],
            min_valid_fraction=min_valid_fraction,
            dry_month_threshold_mm=cfg.get('dry_month_threshold_mm', 5.0),
        ),
        'soil_moisture': lambda cfg: compute_smap_moisture_metrics(
            cfg['sm_m3m3'],
            cfg.get('qa_flag'),
            min_valid_fraction=min_valid_fraction,
        ),
        'snow_persistence': lambda cfg: compute_mod10a1_snow_metrics(
            cfg['ndsi_snow_cover'],
            cfg.get('qa_flag'),
            min_valid_fraction=min_valid_fraction,
        ),
        'permafrost': lambda cfg: compute_permafrost_metrics(
            cfg['pfr_pct'],
            cfg.get('alt_m'),
            min_valid_fraction=min_valid_fraction,
        ),
        'thermal_emissivity': lambda cfg: compute_aster_ged_emissivity_metrics(
            cfg['emissivity_b10_b14'],
            min_valid_fraction=min_valid_fraction,
        ),
        'sar_backscatter': lambda cfg: compute_sentinel1_rtc_metrics(
            cfg['sigma0_vv_linear'],
            cfg['sigma0_vh_linear'],
            cfg.get('layover_shadow_mask'),
            min_valid_fraction=min_valid_fraction,
        ),
    }

    for dim, cols in SURFACE_DIMENSIONS.items():
        if dim in inputs and inputs[dim] is not None:
            metrics, valid_fraction, status = extractors_map[dim](inputs[dim])
            row.update(metrics)
            row[f'{dim}_valid_fraction'] = valid_fraction
            row[f'{dim}_status'] = status
        else:
            row.update(dict.fromkeys(cols))
            row[f'{dim}_valid_fraction'] = None
            row[f'{dim}_status'] = 'on_demand_fetchable'
    return row


def build_surface_source_manifests(
    fetched_at: datetime | str | None = None,
    *,
    manifest_id_prefix: str = 'surface-official-v1',
) -> list[dict[str, Any]]:
    """Build `source_manifests` rows with official DOIs and versions from the surface spec."""
    spec = load_surface_spec()
    created_at = _parse_timestamp(fetched_at)
    rows: list[dict[str, Any]] = []
    for dim, dim_spec in spec['dimensions'].items():
        for role, src in dim_spec['sources'].items():
            product_id = src['product_id']
            manifest_id = extractors.make_manifest_id([product_id], f'{manifest_id_prefix}:{dim}')
            rows.append({
                'source_manifest_id': manifest_id,
                'product_id': product_id,
                'asset_id': f'{dim}:{role}:{product_id}',
                'access_mode': src.get('access_mode', 'on_demand'),
                'sha256_or_etag': None,
                'native_resolution_m': float(src['native_resolution_m']),
                'effective_resolution_m': float(src['native_resolution_m']),
                'observation_period': None,
                'created_at': created_at,
                'crs_wkt': EARTH_CRS_WKT,
                'planetary_frame': 'EARTH_WGS84',
                'doi': src.get('doi'),
                'product_version': src.get('product_version'),
            })
    return rows
