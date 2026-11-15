"""Contract of the lunar enrichment table (`enrichment_lunar`), audit 2026-11-14 section 2.1.

Only depends on PyArrow so that `etl_contract` can import it without a cycle; the
extraction lives in `pipelines.etl_lunar`.
"""
from __future__ import annotations

import pyarrow as pa

# ---------------------------------------------------------------------------
LUNAR_SITE_PROFILE = 'lunar_polar_base_v1'
LUNAR_SITE_STATUS_ENUM = (
    'base_candidate_illuminated',
    'volatile_target_psr',
    'excluded_steep',
    'excluded_low_illumination',
    'pending_illumination',
    'pending_topography',
)
LUNAR_DIMENSIONS: dict[str, tuple[str, ...]] = {
    'illumination': ('illumination_mean_fraction', 'illumination_p10_fraction'),
    'psr': ('psr_fraction',),
    'diviner_temperature': ('diviner_tmax_p50_k', 'diviner_tmin_p50_k', 'diviner_tamp_p50_k'),
    'diviner_regolith': ('diviner_rock_abundance_p50', 'diviner_h_parameter_p50_m'),
    'minirf': ('minirf_cpr_p50', 'minirf_cpr_p90', 'minirf_s1_p50_db'),
}
# Physical bounds checked before writing (inclusive).
LUNAR_RANGES: dict[str, tuple[float, float]] = {
    'illumination_mean_fraction': (0.0, 1.0),
    'illumination_p10_fraction': (0.0, 1.0),
    'psr_fraction': (0.0, 1.0),
    'diviner_tmax_p50_k': (10.0, 450.0),
    'diviner_tmin_p50_k': (10.0, 450.0),
    'diviner_tamp_p50_k': (0.0, 440.0),
    'diviner_rock_abundance_p50': (0.0, 1.0),
    'diviner_h_parameter_p50_m': (0.0, 1.0),
    'minirf_cpr_p50': (0.0, 10.0),
    'minirf_cpr_p90': (0.0, 10.0),
    'minirf_s1_p50_db': (-60.0, 20.0),
}


def _lunar_fields() -> list[pa.Field]:
    fields = [pa.field('region_id', pa.string(), nullable=False)]
    for dim, columns in LUNAR_DIMENSIONS.items():
        fields.extend(pa.field(c, pa.float32(), nullable=True) for c in columns)
        fields.append(pa.field(f'{dim}_valid_fraction', pa.float32(), nullable=True))
        fields.append(pa.field(f'{dim}_status', pa.string(), nullable=False))
    fields.extend([
        pa.field('lunar_site_status', pa.string(), nullable=False),
        pa.field('lunar_site_profile', pa.string(), nullable=False),
        pa.field('source_manifest_id', pa.string(), nullable=False),
        pa.field('updated_at', pa.timestamp('us', tz='UTC'), nullable=False),
    ])
    return fields


ENRICHMENT_LUNAR_SCHEMA = pa.schema(_lunar_fields())


def validate_lunar_table(table: pa.Table, check_enum, check_range, feature_status_enum) -> None:
    """Enum and range checks of `enrichment_lunar` (called from `etl_contract.validate_table`)."""
    check_enum(table, 'lunar_site_status', LUNAR_SITE_STATUS_ENUM)
    check_enum(table, 'lunar_site_profile', (LUNAR_SITE_PROFILE,))
    for dim in LUNAR_DIMENSIONS:
        check_enum(table, f'{dim}_status', feature_status_enum)
        check_range(table, f'{dim}_valid_fraction', 0.0, 1.0)
    for col, (low, high) in LUNAR_RANGES.items():
        check_range(table, col, low, high)


def unified_lunar_columns_sql(base_alias: str = 'b', lunar_alias: str = 'l') -> str:
    """Lunar columns of `features_unified`; not applicable (unobserved) outside the Moon."""
    cols = []
    for dim, columns in LUNAR_DIMENSIONS.items():
        cols.extend(f'{lunar_alias}.{c}' for c in (*columns, f'{dim}_valid_fraction'))
        cols.append(
            f"COALESCE({lunar_alias}.{dim}_status, CASE WHEN {base_alias}.body = 'Moon' "
            f"THEN 'on_demand_fetchable' ELSE 'unobserved_by_product' END) AS {dim}_status"
        )
    cols.append(
        f"COALESCE({lunar_alias}.lunar_site_status, CASE WHEN {base_alias}.body = 'Moon' "
        f"THEN 'pending_illumination' END) AS lunar_site_status"
    )
    cols.append(f'{lunar_alias}.lunar_site_profile')
    return ', '.join(cols)
