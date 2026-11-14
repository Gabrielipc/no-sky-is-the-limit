"""Contract of the laser-altimetry and polarimetric-radar bridges (audit 2026-11-14, section 3).

Two enrichment tables, keyed by `region_id` like the rest of the store:

- `enrichment_altimetry`: along-track slopes and differential slopes from ICESat-2 ATL08
  terrain segments over the 3 km core, plus the same along-track slopes and heights from
  GLO-30 at the same segments. Laser profiles do not depend on DEM interpolation, so they
  validate the DEM features and share the measurement principle of LOLA and MOLA.
- `enrichment_radar`: circular polarization ratio (CPR), total power and degree of
  polarization from RCM compact polarimetry (CEOS-ARD, gamma-0), the Earth side of the
  Mini-RF CPR. C band (5.6 cm) and S band (12.6 cm) differ, so bodies are compared by
  within-body rank, never by absolute value.

Only depends on PyArrow so `etl_contract` can import it without a cycle.
"""
from __future__ import annotations

import pyarrow as pa

ALTIMETRY_INSTRUMENT = 'ICESat-2/ATLAS ATL08'
RADAR_INSTRUMENT = 'RCM/SAR-C compact polarimetry'

# Metric columns -> physical bounds (inclusive), checked before writing.
ALTIMETRY_METRICS: dict[str, tuple[float, float]] = {
    'laser_slope_20m_p50_deg': (0.0, 90.0),
    'laser_slope_20m_p90_deg': (0.0, 90.0),
    'laser_slope_100m_p50_deg': (0.0, 90.0),
    'laser_slope_100m_p90_deg': (0.0, 90.0),
    'laser_diff_slope_200m_p50_deg': (0.0, 90.0),
    'laser_diff_slope_600m_p50_deg': (0.0, 90.0),
    'dem_slope_100m_p50_deg': (0.0, 90.0),
    'dem_slope_100m_p90_deg': (0.0, 90.0),
    'dem_diff_slope_200m_p50_deg': (0.0, 90.0),
    'dem_diff_slope_600m_p50_deg': (0.0, 90.0),
    'dem_minus_laser_median_m': (-500.0, 500.0),
    'dem_minus_laser_nmad_m': (0.0, 500.0),
    'snow_flag_fraction': (0.0, 1.0),
}
ALTIMETRY_COUNTS = (
    'granules_found', 'granules_with_data', 'n_tracks', 'n_segments', 'n_pairs_20m', 'n_pairs_100m',
    'n_diff_200m', 'n_diff_600m',
)
RADAR_METRICS: dict[str, tuple[float, float]] = {
    'rcm_cpr_p50': (0.0, 10.0),
    'rcm_cpr_p90': (0.0, 10.0),
    'rcm_s1_p50_db': (-60.0, 20.0),
    'rcm_dop_p50': (0.0, 1.0),
    'rcm_local_incidence_p50_deg': (0.0, 90.0),
    'rcm_valid_fraction': (0.0, 1.0),
}
RADAR_COUNTS = ('scenes_found', 'n_scenes')


def _schema(counts: tuple[str, ...], metrics: dict, status: str) -> pa.Schema:
    return pa.schema(
        [pa.field('region_id', pa.string(), nullable=False),
         pa.field('instrument', pa.string(), nullable=False),
         pa.field('product_id', pa.string(), nullable=False),
         pa.field('observation_period', pa.string(), nullable=True)]
        + [pa.field(c, pa.int32(), nullable=False) for c in counts]
        + [pa.field(m, pa.float32(), nullable=True) for m in metrics]
        + [pa.field(status, pa.string(), nullable=False),
           pa.field('source_manifest_id', pa.string(), nullable=False),
           pa.field('updated_at', pa.timestamp('us', tz='UTC'), nullable=False)]
    )


ENRICHMENT_ALTIMETRY_SCHEMA = _schema(ALTIMETRY_COUNTS, ALTIMETRY_METRICS, 'altimetry_status')
ENRICHMENT_RADAR_SCHEMA = _schema(RADAR_COUNTS, RADAR_METRICS, 'radar_status')


def validate_bridge_table(table: pa.Table, table_name: str, check_enum, check_range, feature_status_enum) -> None:
    """Enum and range checks (called from `etl_contract.validate_table`)."""
    if table_name == 'enrichment_altimetry':
        status, metrics, counts = 'altimetry_status', ALTIMETRY_METRICS, ALTIMETRY_COUNTS
    else:
        status, metrics, counts = 'radar_status', RADAR_METRICS, RADAR_COUNTS
    check_enum(table, status, feature_status_enum)
    for col, (low, high) in metrics.items():
        check_range(table, col, low, high)
    for col in counts:
        check_range(table, col, 0, 2**31 - 1)


def unified_bridge_columns_sql(base_alias: str = 'b', alt_alias: str = 'a', radar_alias: str = 'r') -> str:
    """Bridge columns of `features_unified`. Neither product observes Mars or the Moon."""
    cols = [f'{alt_alias}.{m}' for m in ('n_tracks', 'n_pairs_100m', *ALTIMETRY_METRICS)]
    cols.append(
        f"COALESCE({alt_alias}.altimetry_status, CASE WHEN {base_alias}.body = 'Earth' "
        f"THEN 'on_demand_fetchable' ELSE 'unobserved_by_product' END) AS altimetry_status"
    )
    cols.extend(f'{radar_alias}.{m}' for m in ('n_scenes', *RADAR_METRICS))
    cols.append(
        f"COALESCE({radar_alias}.radar_status, CASE WHEN {base_alias}.body = 'Earth' "
        f"THEN 'on_demand_fetchable' ELSE 'unobserved_by_product' END) AS radar_status"
    )
    return ', '.join(cols)
