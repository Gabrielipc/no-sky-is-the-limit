"""Contract of the global coarse surface layer (`enrichment_global`) and of `enrichment_selection`.

Plan: docs/01-vigentes/etapa-actual-armonizacion/Plan de mitigacion del sesgo de seleccion topografica.md

`enrichment_global` holds, for every Earth window, surface context sampled from global climatological
rasters built once per product (`pipelines/etl_global_layers.py`). Every column carries the `_cmg`
suffix and the `context_coarse` tier: the support is the native cell (0.05°-9 km, larger than the
3 km window, except AG1km at 1 km) and the values are never mixed with the fine per-window columns of
`enrichment_surface` (`modis_ati_p50_per_k`, AG100 emissivity, ...).

`enrichment_selection` records why a window was enriched (`candidate`, `background`, `retrieval`, ...)
and, for the stratified background sample, its inclusion probability, so the similarity engine can
fit the bridge views on an unbiased, weighted population.

Only depends on PyArrow so `etl_contract` can import it without a cycle.
"""
from __future__ import annotations

import pyarrow as pa

GLOBAL_LAYERS_VERSION = 'global-layers-v1'

# layer -> (columns, product ids, support)
GLOBAL_LAYERS: dict[str, dict] = {
    'imerg': {
        'columns': ('precip_annual_mm_cmg', 'dry_months_fraction_cmg'),
        'products': ('GPM_3IMERGM.07',),
        'support_m': 11_100.0,
    },
    'snow': {
        'columns': ('snow_cover_mean_pct_cmg', 'snow_months_fraction_cmg'),
        'products': ('MOD10CM.061',),
        'support_m': 5_550.0,
    },
    'ati': {
        'columns': ('lst_day_night_delta_k_cmg', 'albedo_wsa_cmg', 'ati_cmg_per_k'),
        'products': ('MYD11C3.061', 'MCD43C3.061'),
        'support_m': 5_550.0,
    },
    'emissivity': {
        'columns': ('emis_mean_b10_b14_cmg', 'emis_quartz_index_cmg', 'emis_carbonate_index_cmg',
                    'emis_mafic_index_cmg'),
        'products': ('AG1km.003',),
        'support_m': 3_000.0,  # mean of the 1 km cells whose centre falls in the 3 km footprint
    },
    'soil_moisture': {
        'columns': ('soil_moisture_mean_cmg', 'soil_moisture_obs_fraction_cmg'),
        'products': ('SPL3SMP_E.006',),
        'support_m': 9_008.0,
    },
    'permafrost': {
        'columns': ('permafrost_fraction_cmg',),
        'products': ('ESA_CCI_PERMAFROST_v5.0',),
        'support_m': 1_000.0,
    },
}

GLOBAL_RANGES: dict[str, tuple[float, float]] = {
    'precip_annual_mm_cmg': (0.0, 15000.0),
    'dry_months_fraction_cmg': (0.0, 1.0),
    'snow_cover_mean_pct_cmg': (0.0, 100.0),
    'snow_months_fraction_cmg': (0.0, 1.0),
    'lst_day_night_delta_k_cmg': (0.0, 80.0),
    'albedo_wsa_cmg': (0.0, 1.0),
    'ati_cmg_per_k': (0.0, 1.0),
    'emis_mean_b10_b14_cmg': (0.5, 1.0),
    'emis_quartz_index_cmg': (0.5, 1.5),
    'emis_carbonate_index_cmg': (0.5, 1.5),
    'emis_mafic_index_cmg': (0.5, 1.5),
    'soil_moisture_mean_cmg': (0.0, 0.65),
    'soil_moisture_obs_fraction_cmg': (0.0, 1.0),
    'permafrost_fraction_cmg': (0.0, 1.0),
}

GLOBAL_COLUMNS: tuple[str, ...] = tuple(c for layer in GLOBAL_LAYERS.values() for c in layer['columns'])


def _global_fields() -> list[pa.Field]:
    fields: list[pa.Field] = [pa.field('region_id', pa.string(), nullable=False)]
    for name, layer in GLOBAL_LAYERS.items():
        fields.extend(pa.field(col, pa.float32(), nullable=True) for col in layer['columns'])
        fields.append(pa.field(f'{name}_cmg_status', pa.string(), nullable=False))
    fields.extend([
        pa.field('global_layers_version', pa.string(), nullable=False),
        pa.field('source_manifest_id', pa.string(), nullable=False),
        pa.field('updated_at', pa.timestamp('us', tz='UTC'), nullable=False),
    ])
    return fields


ENRICHMENT_GLOBAL_SCHEMA = pa.schema(_global_fields())

SELECTION_REASONS = ('candidate', 'background', 'background_cluster', 'retrieval', 'control', 'explicit')

ENRICHMENT_SELECTION_SCHEMA = pa.schema([
    pa.field('region_id', pa.string(), nullable=False),
    pa.field('design_id', pa.string(), nullable=False),
    pa.field('selection_reason', pa.string(), nullable=False),
    pa.field('view', pa.string(), nullable=True),
    pa.field('stratum', pa.string(), nullable=True),
    pa.field('inclusion_probability', pa.float64(), nullable=True),
    pa.field('seed', pa.int64(), nullable=True),
    pa.field('updated_at', pa.timestamp('us', tz='UTC'), nullable=False),
])


def validate_global_table(table: pa.Table, check_enum, check_range, feature_status_enum) -> None:
    for name in GLOBAL_LAYERS:
        check_enum(table, f'{name}_cmg_status', feature_status_enum)
    for col, (low, high) in GLOBAL_RANGES.items():
        check_range(table, col, low, high)


def validate_selection_table(table: pa.Table, check_enum, check_range) -> None:
    check_enum(table, 'selection_reason', SELECTION_REASONS)
    check_range(table, 'inclusion_probability', 0.0, 1.0)


def unified_global_columns_sql(base_alias: str = 'b', alias: str = 'g') -> str:
    """Global coarse columns exposed in `features_unified`."""
    cols: list[str] = []
    for name, layer in GLOBAL_LAYERS.items():
        cols.extend(f'{alias}.{col}' for col in layer['columns'])
        cols.append(
            f"COALESCE({alias}.{name}_cmg_status, CASE WHEN {base_alias}.body = 'Earth' "
            f"THEN 'on_demand_fetchable' ELSE 'unobserved_by_product' END) AS {name}_cmg_status"
        )
    return ', '.join(cols)
