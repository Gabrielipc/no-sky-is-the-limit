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

from pipelines import etl_bridges_schema as bridges_schema
from pipelines import etl_global_schema as global_schema
from pipelines import etl_eligibility as eligibility
from pipelines import etl_lunar_schema as lunar_schema
from pipelines import etl_surface_schema as surface_schema

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

BODY_ENUM = ('Earth', 'Mars', 'Moon')
# Planetary frame of each manifest asset (audit 2026-11-14, section 2.1).
PLANETARY_FRAME_ENUM = ('EARTH_WGS84', 'IAU_MARS', 'MOON_ME_DE421')
# `excluded_urban_or_ice` is kept only to read rows written before the scenario
# profiles split built-up from snow/ice; new rows never use it.
LEGACY_ELIGIBILITY_STATUSES = ('excluded_urban_or_ice',)
ELIGIBILITY_ENUM = (
    'mars_reference_surface',
    'moon_reference_surface',
    *eligibility.ELIGIBLE_STATUSES,
    *eligibility.EXCLUSION_STATUSES,
    *LEGACY_ELIGIBILITY_STATUSES,
)
ELIGIBILITY_PROFILE_ENUM = tuple(eligibility.PROFILES) + ('mars_reference', 'moon_reference')
BASE_QA_ENUM = (
    'rankable',
    'insufficient_dem_support',
    'insufficient_land',
    'dem_unavailable',   # catalogue gap: no inventory tile or no data over the window
    'dem_fetch_failed',  # access failure on an inventory tile; the batch is reopened on resume
)
COVER_STATUS_ENUM = (
    'measured',
    'insufficient_cover_support',
    'no_cover_tile',
    'cover_fetch_failed',
    'not_requested',
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
    pa.field('hypsometric_integral', pa.float32(), nullable=True),
    pa.field('elevation_skew_p95_p05', pa.float32(), nullable=True),
    pa.field('aspect_240m_resultant_length', pa.float32(), nullable=True),
    pa.field('slope_240m_gt15_fraction', pa.float32(), nullable=True),
    pa.field('slope_240m_gt25_fraction', pa.float32(), nullable=True),
    pa.field('analog_surface_eligibility', pa.string(), nullable=False),
    pa.field('eligibility_profile', pa.string(), nullable=False),
    pa.field('cover_status', pa.string(), nullable=False),
    pa.field('cover_valid_fraction', pa.float32(), nullable=True),
    pa.field('bare_or_sparse_fraction', pa.float32(), nullable=True),
    pa.field('trees_fraction', pa.float32(), nullable=True),
    pa.field('built_fraction', pa.float32(), nullable=True),
    pa.field('permanent_water_fraction', pa.float32(), nullable=True),
    pa.field('snow_ice_fraction', pa.float32(), nullable=True),
    pa.field('moss_lichen_fraction', pa.float32(), nullable=True),
    pa.field('water_occurrence_mean_pct', pa.float32(), nullable=True),
    pa.field('water_extent_gt0_fraction', pa.float32(), nullable=True),
    pa.field('water_occurrence_ge50_fraction', pa.float32(), nullable=True),
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

ENRICHMENT_FRAMING_SCHEMA = pa.schema([
    pa.field('region_id', pa.string(), nullable=False),
    pa.field('reference_id', pa.string(), nullable=False),
    pa.field('reference_hypsometric_integral', pa.float32(), nullable=False),
    # Rows written before joint selection lack these: the best framing matched the integral only.
    pa.field('reference_relief_m', pa.float32(), nullable=True),
    pa.field('framing_criterion', pa.string(), nullable=True),
    pa.field('lattice_step_m', pa.int32(), nullable=False),
    pa.field('max_offset_m', pa.int32(), nullable=False),
    pa.field('framings_evaluated', pa.int32(), nullable=False),
    pa.field('framings_valid', pa.int32(), nullable=False),
    pa.field('hi_center', pa.float32(), nullable=True),
    pa.field('hi_best', pa.float32(), nullable=True),
    pa.field('hi_min', pa.float32(), nullable=True),
    pa.field('hi_max', pa.float32(), nullable=True),
    pa.field('best_offset_east_m', pa.int32(), nullable=True),
    pa.field('best_offset_north_m', pa.int32(), nullable=True),
    pa.field('best_at_lattice_edge', pa.bool_(), nullable=True),
    pa.field('best_distance_score', pa.float32(), nullable=True),
    pa.field('center_distance_score', pa.float32(), nullable=True),
    pa.field('best_relief_p95_p05_m', pa.float32(), nullable=True),
    pa.field('best_slope_240m_p50_deg', pa.float32(), nullable=True),
    pa.field('best_slope_240m_p90_deg', pa.float32(), nullable=True),
    pa.field('best_aspect_240m_resultant_length', pa.float32(), nullable=True),
    pa.field('framing_status', pa.string(), nullable=False),
    pa.field('source_manifest_id', pa.string(), nullable=False),
    pa.field('updated_at', pa.timestamp('us', tz='UTC'), nullable=False),
])

# Cover backfill: WorldCover/JRC fields measured after the topographic sweep. The
# base_windows view overlays the latest row per window onto the stored base row.
COVER_OVERLAY_FIELDS = (
    'cover_status', 'cover_valid_fraction', 'bare_or_sparse_fraction', 'trees_fraction', 'built_fraction',
    'permanent_water_fraction', 'snow_ice_fraction', 'moss_lichen_fraction', 'water_occurrence_mean_pct',
    'water_extent_gt0_fraction', 'water_occurrence_ge50_fraction', 'analog_surface_eligibility',
    'eligibility_profile',
)
ENRICHMENT_COVER_SCHEMA = pa.schema(
    [pa.field('region_id', pa.string(), nullable=False)]
    + [BASE_WINDOWS_SCHEMA.field(name) for name in COVER_OVERLAY_FIELDS]
    + [pa.field('source_manifest_id', pa.string(), nullable=False),
       pa.field('updated_at', pa.timestamp('us', tz='UTC'), nullable=False)]
)

ENRICHMENT_LUNAR_SCHEMA = lunar_schema.ENRICHMENT_LUNAR_SCHEMA
ENRICHMENT_ALTIMETRY_SCHEMA = bridges_schema.ENRICHMENT_ALTIMETRY_SCHEMA
ENRICHMENT_RADAR_SCHEMA = bridges_schema.ENRICHMENT_RADAR_SCHEMA
ENRICHMENT_SURFACE_SCHEMA = surface_schema.ENRICHMENT_SURFACE_SCHEMA
ENRICHMENT_GLOBAL_SCHEMA = global_schema.ENRICHMENT_GLOBAL_SCHEMA
ENRICHMENT_SELECTION_SCHEMA = global_schema.ENRICHMENT_SELECTION_SCHEMA

ENRICHMENT_SUBSETS = ('spectral', 'temporal', 'framing', 'cover', 'lunar', 'altimetry', 'radar', 'surface',
                      'global', 'selection')
# Latest row per key of each subset; `selection` keeps one row per window and sampling design.
ENRICHMENT_KEYS = {subset: ('region_id',) for subset in ENRICHMENT_SUBSETS} | {'selection': ('region_id', 'design_id')}

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
    # Native CRS of the asset and its planetary frame. Null only in manifests written before
    # the Moon entered the contract; those are Earth assets in EPSG:4326.
    pa.field('crs_wkt', pa.string(), nullable=True),
    pa.field('planetary_frame', pa.string(), nullable=True),
    # DOI and product version from ESA Open Science Catalog / NASA DAACs (audit §4).
    pa.field('doi', pa.string(), nullable=True),
    pa.field('product_version', pa.string(), nullable=True),
])

TABLE_SCHEMAS: dict[str, pa.Schema] = {
    'base_windows': BASE_WINDOWS_SCHEMA,
    'enrichment_spectral': ENRICHMENT_SPECTRAL_SCHEMA,
    'enrichment_temporal': ENRICHMENT_TEMPORAL_SCHEMA,
    'enrichment_framing': ENRICHMENT_FRAMING_SCHEMA,
    'enrichment_cover': ENRICHMENT_COVER_SCHEMA,
    'enrichment_lunar': ENRICHMENT_LUNAR_SCHEMA,
    'enrichment_altimetry': ENRICHMENT_ALTIMETRY_SCHEMA,
    'enrichment_radar': ENRICHMENT_RADAR_SCHEMA,
    'enrichment_surface': ENRICHMENT_SURFACE_SCHEMA,
    'enrichment_global': ENRICHMENT_GLOBAL_SCHEMA,
    'enrichment_selection': ENRICHMENT_SELECTION_SCHEMA,
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
        _check_enum(table, 'eligibility_profile', ELIGIBILITY_PROFILE_ENUM)
        _check_enum(table, 'cover_status', COVER_STATUS_ENUM)
        _check_enum(table, 'qa_status', BASE_QA_ENUM)
        for frac in (
            'land_fraction', 'topo_valid_fraction', 'roughness_coverage',
            'bare_or_sparse_fraction', 'trees_fraction', 'built_fraction',
            'permanent_water_fraction', 'water_extent_gt0_fraction',
            'cover_valid_fraction', 'snow_ice_fraction', 'moss_lichen_fraction',
            'water_occurrence_ge50_fraction', 'hypsometric_integral',
            'aspect_240m_resultant_length', 'slope_240m_gt15_fraction', 'slope_240m_gt25_fraction',
        ):
            _check_range(table, frac, 0.0, 1.0)
        _check_range(table, 'elevation_skew_p95_p05', -1.0, 1.0)
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
    elif table_name == 'enrichment_cover':
        _check_enum(table, 'cover_status', COVER_STATUS_ENUM)
        _check_enum(table, 'analog_surface_eligibility', ELIGIBILITY_ENUM)
        _check_enum(table, 'eligibility_profile', ELIGIBILITY_PROFILE_ENUM)
        for col in COVER_OVERLAY_FIELDS:
            if col.endswith('_fraction'):
                _check_range(table, col, 0.0, 1.0)
        _check_range(table, 'water_occurrence_mean_pct', 0.0, 100.0)
    elif table_name == 'enrichment_lunar':
        lunar_schema.validate_lunar_table(table, _check_enum, _check_range, FEATURE_STATUS_ENUM)
    elif table_name in ('enrichment_altimetry', 'enrichment_radar'):
        bridges_schema.validate_bridge_table(table, table_name, _check_enum, _check_range, FEATURE_STATUS_ENUM)
    elif table_name == 'enrichment_surface':
        surface_schema.validate_surface_table(table, _check_enum, _check_range, FEATURE_STATUS_ENUM)
    elif table_name == 'enrichment_global':
        global_schema.validate_global_table(table, _check_enum, _check_range, FEATURE_STATUS_ENUM)
    elif table_name == 'enrichment_selection':
        global_schema.validate_selection_table(table, _check_enum, _check_range)
    elif table_name == 'source_manifests':
        _check_enum(table, 'planetary_frame', (*PLANETARY_FRAME_ENUM, None))
    elif table_name == 'enrichment_framing':
        _check_enum(table, 'framing_status', FEATURE_STATUS_ENUM)
        _check_enum(table, 'framing_criterion', ('hi_only_v1', 'joint_relief_hi_v2', None))
        for col in ('reference_hypsometric_integral', 'hi_center', 'hi_best', 'hi_min', 'hi_max',
                    'best_aspect_240m_resultant_length'):
            _check_range(table, col, 0.0, 1.0)
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


_SQL_TYPES = {
    pa.string(): 'VARCHAR',
    pa.int32(): 'INTEGER',
    pa.int64(): 'BIGINT',
    pa.float32(): 'FLOAT',
    pa.float64(): 'DOUBLE',
    pa.timestamp('us', tz='UTC'): 'TIMESTAMPTZ',
    pa.bool_(): 'BOOLEAN',
}


def _empty_view_sql(view_name: str, schema: pa.Schema) -> str:
    cols = ', '.join(f'CAST(NULL AS {_SQL_TYPES[f.type]}) AS {f.name}' for f in schema)
    return f'CREATE OR REPLACE VIEW {view_name} AS SELECT {cols} WHERE 1 = 0'


def _has_parquet(directory: Path) -> bool:
    return directory.exists() and any(directory.rglob('*.parquet'))


def register_unified_views(conn: duckdb.DuckDBPyConnection, store_root: Path) -> None:
    """Register base, latest-enrichment, and unified views over the Parquet lakehouse."""
    base_dir = store_root / 'base'
    if _has_parquet(base_dir):
        pattern = str(base_dir / '**' / '*.parquet').replace("'", "''")
        conn.execute(
            f"CREATE OR REPLACE VIEW base_windows_files AS "
            f"SELECT * FROM read_parquet('{pattern}', hive_partitioning=true, union_by_name=true)"
        )
        # Files written before a column existed lack it entirely; expose it as NULL.
        present = {r[0] for r in conn.execute('DESCRIBE base_windows_files').fetchall()}
        missing = ', '.join(f'CAST(NULL AS {_SQL_TYPES[f.type]}) AS {f.name}'
                            for f in BASE_WINDOWS_SCHEMA if f.name not in present)
        # A window measured by two batches (e.g. a pilot batch and the world sweep share the grid)
        # appears in two parts: keep the latest row per region_id.
        conn.execute(f"CREATE OR REPLACE VIEW base_windows_raw AS SELECT *{', ' + missing if missing else ''} "
                     "FROM base_windows_files "
                     "QUALIFY row_number() OVER (PARTITION BY region_id ORDER BY updated_at DESC, batch_id DESC) = 1")
    else:
        conn.execute(_empty_view_sql('base_windows_raw', BASE_WINDOWS_SCHEMA))

    cover_dir = store_root / 'enrichment' / 'cover'
    if _has_parquet(cover_dir):
        pattern = str(cover_dir / '*.parquet').replace("'", "''")
        conn.execute(f"""
            CREATE OR REPLACE VIEW enrichment_cover_latest AS
            SELECT * FROM read_parquet('{pattern}')
            QUALIFY row_number() OVER (PARTITION BY region_id ORDER BY updated_at DESC) = 1
        """)
        overlay = ', '.join(f'CASE WHEN c.region_id IS NOT NULL THEN c.{f} ELSE b.{f} END AS {f}'
                            for f in COVER_OVERLAY_FIELDS)
        conn.execute(f"""
            CREATE OR REPLACE VIEW base_windows AS
            SELECT b.* REPLACE ({overlay})
            FROM base_windows_raw b LEFT JOIN enrichment_cover_latest c ON b.region_id = c.region_id
        """)
    else:
        conn.execute(_empty_view_sql('enrichment_cover_latest', ENRICHMENT_COVER_SCHEMA))
        conn.execute('CREATE OR REPLACE VIEW base_windows AS SELECT * FROM base_windows_raw')

    for sub, view_name, schema in (
        ('spectral', 'enrichment_spectral_latest', ENRICHMENT_SPECTRAL_SCHEMA),
        ('temporal', 'enrichment_temporal_latest', ENRICHMENT_TEMPORAL_SCHEMA),
        ('framing', 'enrichment_framing_latest', ENRICHMENT_FRAMING_SCHEMA),
        ('lunar', 'enrichment_lunar_latest', ENRICHMENT_LUNAR_SCHEMA),
        ('altimetry', 'enrichment_altimetry_latest', ENRICHMENT_ALTIMETRY_SCHEMA),
        ('radar', 'enrichment_radar_latest', ENRICHMENT_RADAR_SCHEMA),
        ('surface', 'enrichment_surface_latest', ENRICHMENT_SURFACE_SCHEMA),
        ('global', 'enrichment_global_latest', ENRICHMENT_GLOBAL_SCHEMA),
        ('selection', 'enrichment_selection_latest', ENRICHMENT_SELECTION_SCHEMA),
    ):
        edir = store_root / 'enrichment' / sub
        if _has_parquet(edir):
            pattern = str(edir / '*.parquet').replace("'", "''")
            keys = ', '.join(ENRICHMENT_KEYS[sub])
            conn.execute(
                f"""
                CREATE OR REPLACE VIEW {view_name} AS
                SELECT * FROM read_parquet('{pattern}', union_by_name=true)
                QUALIFY row_number() OVER (PARTITION BY {keys} ORDER BY updated_at DESC) = 1
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
            f"COALESCE(s.{cid}_status, CASE WHEN b.body <> 'Earth' THEN 'unobserved_by_product' ELSE 'on_demand_fetchable' END) AS {cid}_status",
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
            COALESCE(t.hls_status, CASE WHEN b.body <> 'Earth' THEN 'unobserved_by_product' ELSE 'on_demand_fetchable' END) AS hls_status,
            t.landsat_lst_p50_k,
            t.landsat_valid_fraction,
            t.thermal_inertia_p50,
            COALESCE(t.thermal_status, CASE WHEN b.body = 'Moon' THEN 'unobserved_by_product' ELSE 'on_demand_fetchable' END) AS thermal_status,
            f.reference_id AS framing_reference_id,
            f.lattice_step_m AS framing_step_m,
            f.max_offset_m AS framing_max_offset_m,
            f.reference_hypsometric_integral AS framing_reference_hi,
            f.reference_relief_m AS framing_reference_relief_m,
            COALESCE(f.framing_criterion, CASE WHEN f.reference_id IS NOT NULL THEN 'hi_only_v1' END) AS framing_criterion,
            f.best_distance_score,
            f.center_distance_score,
            f.framings_valid,
            f.hi_center,
            f.hi_best,
            f.hi_min,
            f.hi_max,
            f.best_offset_east_m,
            f.best_offset_north_m,
            f.best_at_lattice_edge,
            f.best_relief_p95_p05_m,
            f.best_aspect_240m_resultant_length,
            COALESCE(f.framing_status, 'on_demand_fetchable') AS framing_status,
            {lunar_schema.unified_lunar_columns_sql('b', 'l')},
            {bridges_schema.unified_bridge_columns_sql('b', 'a', 'r')},
            {surface_schema.unified_surface_columns_sql('b', 'surf')},
            {global_schema.unified_global_columns_sql('b', 'g')}
        FROM base_windows b
        LEFT JOIN enrichment_spectral_latest s USING (region_id)
        LEFT JOIN enrichment_temporal_latest t USING (region_id)
        LEFT JOIN enrichment_framing_latest f USING (region_id)
        LEFT JOIN enrichment_lunar_latest l USING (region_id)
        LEFT JOIN enrichment_altimetry_latest a USING (region_id)
        LEFT JOIN enrichment_radar_latest r USING (region_id)
        LEFT JOIN enrichment_surface_latest surf USING (region_id)
        LEFT JOIN enrichment_global_latest g USING (region_id)
        """
    )


def compact_enrichment(conn: duckdb.DuckDBPyConnection, store_root: Path, subset: str) -> Path | None:
    """Out-of-core compaction of enrichment delta files into a single ZSTD Parquet file."""
    if subset not in ENRICHMENT_SUBSETS:
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
