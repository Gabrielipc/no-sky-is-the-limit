"""Formal Feature Store contract (PyArrow schemas, QA validation and DuckDB out-of-core views).

Aligns the ETL Parquet store with `specs/analysis/contrato-comun-entrega3.json`
(`contrato-comun-superficie-v1`) and `specs/analysis/feature-store-etl-v1.json`.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

import duckdb
import pyarrow as pa
import pyarrow.compute as pc

ROOT = Path(__file__).resolve().parents[1]
SPEC_PATH = ROOT / 'specs/analysis/feature-store-etl-v1.json'
CONTRACT_SPEC_PATH = ROOT / 'specs/analysis/contrato-comun-entrega3.json'

SPECTRAL_COMPLEXES: tuple[str, ...] = (
    'abs_fe3_oxide_0p53_0p90um',
    'abs_al_oh_2p20um',
    'abs_fe_mg_oh_2p30um',
    'abs_carbonate_2p30_2p50um',
    'abs_hydrated_sioh_so4_1p9_2p26um',
    'abs_mafic_fe2_1p0um',
)

BODY_ENUM = ('Earth', 'Mars')
ELIGIBILITY_ENUM = (
    'mars_reference_surface',
    'eligible_arid_exposed',
    'excluded_dense_canopy',
    'excluded_permanent_water',
    'excluded_urban_or_ice',
    'excluded_insufficient_land',
    'pending_on_demand_cover_check',
)
BASE_QA_ENUM = (
    'rankable',
    'insufficient_dem_support',
    'insufficient_land',
    'dem_unavailable',
)
FEATURE_STATUS_ENUM = (
    'measured',
    'measured_absent',
    'insufficient_coverage',
    'insufficient_complex_sample',
    'unobserved_by_product',
    'on_demand_fetchable',
    'no_swath_coverage',
)

BASE_WINDOWS_SCHEMA = pa.schema([
    pa.field('region_id', pa.string(), nullable=False),
    pa.field('grid_version', pa.string(), nullable=False),
    pa.field('body', pa.string(), nullable=False),
    pa.field('utm_zone_band', pa.string(), nullable=False),
    pa.field('batch_id', pa.string(), nullable=False),
    pa.field('longitude', pa.float64(), nullable=False),
    pa.field('latitude', pa.float64(), nullable=False),
    pa.field('window_m', pa.int32(), nullable=False),
    pa.field('cell_m', pa.int32(), nullable=False),
    pa.field('slope_base_m', pa.int32(), nullable=False),
    pa.field('roughness_radius_m', pa.int32(), nullable=False),
    pa.field('land_fraction', pa.float32(), nullable=False),
    pa.field('topo_valid_fraction', pa.float32(), nullable=False),
    pa.field('roughness_coverage', pa.float32(), nullable=False),
    pa.field('relief_p95_p05_m', pa.float32(), nullable=True),
    pa.field('slope_240m_p50_deg', pa.float32(), nullable=True),
    pa.field('slope_240m_p90_deg', pa.float32(), nullable=True),
    pa.field('roughness_360m_p50_m', pa.float32(), nullable=True),
    pa.field('analog_surface_eligibility', pa.string(), nullable=False),
    pa.field('bare_or_sparse_fraction', pa.float32(), nullable=True),
    pa.field('trees_fraction', pa.float32(), nullable=True),
    pa.field('built_fraction', pa.float32(), nullable=True),
    pa.field('permanent_water_fraction', pa.float32(), nullable=True),
    pa.field('water_occurrence_mean_pct', pa.float32(), nullable=True),
    pa.field('water_extent_gt0_fraction', pa.float32(), nullable=True),
    pa.field('qa_status', pa.string(), nullable=False),
    pa.field('source_manifest_id', pa.string(), nullable=False),
    pa.field('updated_at', pa.timestamp('us', tz='UTC'), nullable=False),
])


def _spectral_fields() -> list[pa.Field]:
    fields: list[pa.Field] = [
        pa.field('region_id', pa.string(), nullable=False),
        pa.field('instrument', pa.string(), nullable=False),
    ]
    for complex_id in SPECTRAL_COMPLEXES:
        fields.extend([
            pa.field(f'{complex_id}_p50', pa.float32(), nullable=True),
            pa.field(f'{complex_id}_p95', pa.float32(), nullable=True),
            pa.field(f'{complex_id}_active_fraction', pa.float32(), nullable=True),
            pa.field(f'{complex_id}_n_samples', pa.int32(), nullable=True),
            pa.field(f'{complex_id}_status', pa.string(), nullable=False),
        ])
    fields.extend([
        pa.field('source_manifest_id', pa.string(), nullable=False),
        pa.field('updated_at', pa.timestamp('us', tz='UTC'), nullable=False),
    ])
    return fields


ENRICHMENT_SPECTRAL_SCHEMA = pa.schema(_spectral_fields())

ENRICHMENT_TEMPORAL_SCHEMA = pa.schema([
    pa.field('region_id', pa.string(), nullable=False),
    pa.field('hls_ndvi_p50', pa.float32(), nullable=True),
    pa.field('hls_valid_fraction', pa.float32(), nullable=True),
    pa.field('hls_status', pa.string(), nullable=False),
    pa.field('landsat_lst_p50_k', pa.float32(), nullable=True),
    pa.field('landsat_valid_fraction', pa.float32(), nullable=True),
    pa.field('thermal_inertia_p50', pa.float32(), nullable=True),
    pa.field('thermal_status', pa.string(), nullable=False),
    pa.field('source_manifest_id', pa.string(), nullable=False),
    pa.field('updated_at', pa.timestamp('us', tz='UTC'), nullable=False),
])

SOURCE_MANIFESTS_SCHEMA = pa.schema([
    pa.field('source_manifest_id', pa.string(), nullable=False),
    pa.field('product_id', pa.string(), nullable=False),
    pa.field('asset_id', pa.string(), nullable=False),
    pa.field('access_mode', pa.string(), nullable=False),
    pa.field('sha256_or_etag', pa.string(), nullable=True),
    pa.field('native_resolution_m', pa.float32(), nullable=False),
    pa.field('effective_resolution_m', pa.float32(), nullable=True),
    pa.field('observation_period', pa.string(), nullable=True),
    pa.field('created_at', pa.timestamp('us', tz='UTC'), nullable=False),
])

TABLE_SCHEMAS: dict[str, pa.Schema] = {
    'base_windows': BASE_WINDOWS_SCHEMA,
    'enrichment_spectral': ENRICHMENT_SPECTRAL_SCHEMA,
    'enrichment_temporal': ENRICHMENT_TEMPORAL_SCHEMA,
    'source_manifests': SOURCE_MANIFESTS_SCHEMA,
}


def load_store_spec() -> dict:
    return json.loads(SPEC_PATH.read_text(encoding='utf-8'))


def _check_enum(table: pa.Table, col: str, allowed: Iterable[str]) -> None:
    allowed_set = set(allowed)
    values = set(pc.unique(table[col]).to_pylist())
    invalid = values - allowed_set
    if invalid:
        raise ValueError(f'Columna {col} contiene valores no permitidos: {sorted(invalid)}')


def _check_range(table: pa.Table, col: str, low: float, high: float) -> None:
    arr = table[col]
    valid = pc.drop_null(arr)
    if len(valid) == 0:
        return
    min_val = pc.min(valid).as_py()
    max_val = pc.max(valid).as_py()
    if min_val < low or max_val > high:
        raise ValueError(f'Columna {col} fuera de rango [{low}, {high}]: [{min_val}, {max_val}]')


def validate_table(table: pa.Table, table_name: str) -> pa.Table:
    """Validate schema, nullability, enums and physical bounds before Parquet write."""
    if table_name not in TABLE_SCHEMAS:
        raise ValueError(f'Tabla desconocida en el contrato: {table_name}')
    expected = TABLE_SCHEMAS[table_name]
    if table.schema != expected:
        table = table.cast(expected, safe=True)
    for field in expected:
        if not field.nullable and table[field.name].null_count > 0:
            raise ValueError(f'Columna no anulable {field.name} en {table_name} contiene nulos')

    if table_name == 'base_windows':
        _check_enum(table, 'body', BODY_ENUM)
        _check_enum(table, 'analog_surface_eligibility', ELIGIBILITY_ENUM)
        _check_enum(table, 'qa_status', BASE_QA_ENUM)
        for frac in (
            'land_fraction', 'topo_valid_fraction', 'roughness_coverage',
            'bare_or_sparse_fraction', 'trees_fraction', 'built_fraction',
            'permanent_water_fraction', 'water_extent_gt0_fraction',
        ):
            _check_range(table, frac, 0.0, 1.0)
        _check_range(table, 'water_occurrence_mean_pct', 0.0, 100.0)
        _check_range(table, 'slope_240m_p50_deg', 0.0, 90.0)
        _check_range(table, 'slope_240m_p90_deg', 0.0, 90.0)
        _check_range(table, 'relief_p95_p05_m', 0.0, 25000.0)
        _check_range(table, 'roughness_360m_p50_m', 0.0, 5000.0)
    elif table_name == 'enrichment_spectral':
        for complex_id in SPECTRAL_COMPLEXES:
            _check_enum(table, f'{complex_id}_status', FEATURE_STATUS_ENUM)
            _check_range(table, f'{complex_id}_active_fraction', 0.0, 1.0)
    elif table_name == 'enrichment_temporal':
        _check_enum(table, 'hls_status', FEATURE_STATUS_ENUM)
        _check_enum(table, 'thermal_status', FEATURE_STATUS_ENUM)
        _check_range(table, 'hls_ndvi_p50', -1.0, 1.0)
        _check_range(table, 'hls_valid_fraction', 0.0, 1.0)
        _check_range(table, 'landsat_valid_fraction', 0.0, 1.0)
        _check_range(table, 'landsat_lst_p50_k', 100.0, 400.0)
    return table


def configure_duckdb(conn: duckdb.DuckDBPyConnection, spill_dir: Path, memory_limit: str = '2GB',
                     threads: int = 4) -> None:
    """Configure DuckDB for bounded out-of-core execution."""
    spill_dir.mkdir(parents=True, exist_ok=True)
    escaped = str(spill_dir).replace("'", "''")
    conn.execute(f"SET memory_limit = '{memory_limit}'")
    conn.execute(f"SET temp_directory = '{escaped}'")
    conn.execute(f'SET threads = {int(threads)}')
    conn.execute('SET preserve_insertion_order = false')


def _empty_view_sql(view_name: str, schema: pa.Schema) -> str:
    type_map = {
        pa.string(): 'VARCHAR',
        pa.int32(): 'INTEGER',
        pa.float32(): 'FLOAT',
        pa.float64(): 'DOUBLE',
        pa.timestamp('us', tz='UTC'): 'TIMESTAMPTZ',
    }
    cols = ', '.join(f'CAST(NULL AS {type_map[f.type]}) AS {f.name}' for f in schema)
    return f'CREATE OR REPLACE VIEW {view_name} AS SELECT {cols} WHERE 1 = 0'


def _has_parquet(directory: Path) -> bool:
    return directory.exists() and any(directory.rglob('*.parquet'))


def register_unified_views(conn: duckdb.DuckDBPyConnection, store_root: Path) -> None:
    """Register base, latest-enrichment, and unified views over the Parquet lakehouse."""
    base_dir = store_root / 'base'
    if _has_parquet(base_dir):
        pattern = str(base_dir / '**' / '*.parquet').replace("'", "''")
        conn.execute(
            f"CREATE OR REPLACE VIEW base_windows AS SELECT * FROM read_parquet('{pattern}', hive_partitioning=true)"
        )
    else:
        conn.execute(_empty_view_sql('base_windows', BASE_WINDOWS_SCHEMA))

    for sub, view_name, schema in (
        ('spectral', 'enrichment_spectral_latest', ENRICHMENT_SPECTRAL_SCHEMA),
        ('temporal', 'enrichment_temporal_latest', ENRICHMENT_TEMPORAL_SCHEMA),
    ):
        edir = store_root / 'enrichment' / sub
        if _has_parquet(edir):
            pattern = str(edir / '*.parquet').replace("'", "''")
            conn.execute(
                f"""
                CREATE OR REPLACE VIEW {view_name} AS
                SELECT * FROM read_parquet('{pattern}')
                QUALIFY row_number() OVER (PARTITION BY region_id ORDER BY updated_at DESC) = 1
                """
            )
        else:
            conn.execute(_empty_view_sql(view_name, schema))

    spectral_cols = []
    for cid in SPECTRAL_COMPLEXES:
        spectral_cols.extend([
            f's.{cid}_p50',
            f's.{cid}_p95',
            f's.{cid}_active_fraction',
            f's.{cid}_n_samples',
            f"COALESCE(s.{cid}_status, CASE WHEN b.body = 'Mars' THEN 'unobserved_by_product' ELSE 'on_demand_fetchable' END) AS {cid}_status",
        ])

    conn.execute(
        f"""
        CREATE OR REPLACE VIEW features_unified AS
        SELECT
            b.*,
            s.instrument AS spectral_instrument,
            {', '.join(spectral_cols)},
            t.hls_ndvi_p50,
            t.hls_valid_fraction,
            COALESCE(t.hls_status, CASE WHEN b.body = 'Mars' THEN 'unobserved_by_product' ELSE 'on_demand_fetchable' END) AS hls_status,
            t.landsat_lst_p50_k,
            t.landsat_valid_fraction,
            t.thermal_inertia_p50,
            COALESCE(t.thermal_status, 'on_demand_fetchable') AS thermal_status
        FROM base_windows b
        LEFT JOIN enrichment_spectral_latest s USING (region_id)
        LEFT JOIN enrichment_temporal_latest t USING (region_id)
        """
    )


def compact_enrichment(conn: duckdb.DuckDBPyConnection, store_root: Path, subset: str) -> Path | None:
    """Out-of-core compaction of enrichment delta files into a single ZSTD Parquet file."""
    if subset not in ('spectral', 'temporal'):
        raise ValueError(f'Subconjunto inválido para compactación: {subset}')
    edir = store_root / 'enrichment' / subset
    files = sorted(edir.glob('*.parquet'))
    if len(files) <= 1:
        return files[0] if files else None
    view_name = f'enrichment_{subset}_latest'
    register_unified_views(conn, store_root)
    staged = edir / '.compacted_staging.parquet'
    escaped = str(staged).replace("'", "''")
    conn.execute(
        f"COPY (SELECT * FROM {view_name}) TO '{escaped}' (FORMAT PARQUET, COMPRESSION ZSTD)"
    )
    target = edir / 'compacted_0000.parquet'
    staged.replace(target)
    for old in files:
        if old != target:
            old.unlink()
    return target
