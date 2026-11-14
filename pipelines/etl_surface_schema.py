"""Contract of the six pending official-source surface dimensions (`enrichment_surface`).

Implements Section 3 of the 2026-11-14 audit:
- `aridity` (IMERG / GSMaP)
- `soil_moisture` (SMAP L3 SPL3SMP_E.006)
- `snow_persistence` (MODIS MOD10A1.061 / SGLI SICE contrast)
- `permafrost` (ESA CCI Permafrost v5.0)
- `thermal_emissivity` (ASTER GED v3, bridging to Diviner CF and THEMIS IR)
- `sar_backscatter` (Sentinel-1 RTC / OPERA-S1, bridging to Mini-RF)
- `apparent_thermal_inertia` (MODIS MOD11A1/MYD11A1 + MCD43A3, audit §2.2, bridging to THEMIS TI
  and Diviner by within-body ranks; units 1/K, never mixed with `thermal_inertia_p50` of THEMIS)

Only depends on PyArrow so `etl_contract` can import it without a cycle; extraction
and raster adapters live in `pipelines.etl_surface_dimensions`.
"""
from __future__ import annotations

import pyarrow as pa

SURFACE_DIMENSIONS: dict[str, tuple[str, ...]] = {
    'aridity': ('precip_mean_annual_mm', 'dry_months_fraction'),
    'soil_moisture': ('smap_sm_p50_m3m3', 'smap_sm_p90_m3m3'),
    'snow_persistence': ('mod10a1_snow_days_fraction', 'mod10a1_clear_days_fraction'),
    'permafrost': ('cci_permafrost_probability', 'cci_active_layer_thickness_m'),
    'thermal_emissivity': ('aster_emissivity_mafic_index', 'aster_christiansen_wb_um'),
    'sar_backscatter': ('s1_rtc_vv_p50_db', 's1_rtc_vh_p50_db', 's1_rtc_vh_vv_ratio_db'),
    'apparent_thermal_inertia': ('modis_ati_p50_per_k', 'modis_ati_iqr_per_k'),
}

# Physical bounds checked before writing (inclusive).
SURFACE_RANGES: dict[str, tuple[float, float]] = {
    'precip_mean_annual_mm': (0.0, 15000.0),
    'dry_months_fraction': (0.0, 1.0),
    'smap_sm_p50_m3m3': (0.0, 0.65),
    'smap_sm_p90_m3m3': (0.0, 0.65),
    'mod10a1_snow_days_fraction': (0.0, 1.0),
    'mod10a1_clear_days_fraction': (0.0, 1.0),
    'cci_permafrost_probability': (0.0, 1.0),
    'cci_active_layer_thickness_m': (0.0, 20.0),
    'aster_emissivity_mafic_index': (0.5, 1.5),
    'aster_christiansen_wb_um': (7.5, 9.5),
    's1_rtc_vv_p50_db': (-35.0, 10.0),
    's1_rtc_vh_p50_db': (-40.0, 5.0),
    's1_rtc_vh_vv_ratio_db': (-25.0, 10.0),
    'modis_ati_p50_per_k': (0.0, 1.0),
    'modis_ati_iqr_per_k': (0.0, 1.0),
}


def _surface_fields() -> list[pa.Field]:
    fields: list[pa.Field] = [pa.field('region_id', pa.string(), nullable=False)]
    for dim, columns in SURFACE_DIMENSIONS.items():
        fields.extend(pa.field(col, pa.float32(), nullable=True) for col in columns)
        fields.append(pa.field(f'{dim}_valid_fraction', pa.float32(), nullable=True))
        fields.append(pa.field(f'{dim}_status', pa.string(), nullable=False))
    fields.extend([
        pa.field('source_manifest_id', pa.string(), nullable=False),
        pa.field('updated_at', pa.timestamp('us', tz='UTC'), nullable=False),
    ])
    return fields


ENRICHMENT_SURFACE_SCHEMA = pa.schema(_surface_fields())


def validate_surface_table(table: pa.Table, check_enum, check_range, feature_status_enum) -> None:
    """Enum and range checks of `enrichment_surface` (called from `etl_contract.validate_table`)."""
    for dim in SURFACE_DIMENSIONS:
        check_enum(table, f'{dim}_status', feature_status_enum)
        check_range(table, f'{dim}_valid_fraction', 0.0, 1.0)
    for col, (low, high) in SURFACE_RANGES.items():
        check_range(table, col, low, high)


def unified_surface_columns_sql(base_alias: str = 'b', surf_alias: str = 'surf') -> str:
    """Official-source surface columns exposed in `features_unified`."""
    cols: list[str] = []
    for dim, columns in SURFACE_DIMENSIONS.items():
        cols.extend(f'{surf_alias}.{col}' for col in (*columns, f'{dim}_valid_fraction'))
        cols.append(
            f"COALESCE({surf_alias}.{dim}_status, CASE WHEN {base_alias}.body = 'Earth' "
            f"THEN 'on_demand_fetchable' ELSE 'unobserved_by_product' END) AS {dim}_status"
        )
    return ', '.join(cols)
