"""Tests for scenario-specific surface eligibility profiles (Python and DuckDB SQL)."""
from __future__ import annotations

from datetime import datetime, timezone
import itertools
from pathlib import Path
import tempfile
import unittest

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq

from pipelines import etl_contract as contract
from pipelines import etl_eligibility as eligibility
from pipelines.etl_store import FeatureStore, eligibility_expression

NOW = datetime(2026, 11, 14, 12, 0, tzinfo=timezone.utc)


def cover(**overrides: float) -> dict:
    fractions = {
        'bare_or_sparse_fraction': 0.0,
        'trees_fraction': 0.0,
        'built_fraction': 0.0,
        'snow_ice_fraction': 0.0,
        'permanent_water_fraction': 0.0,
        'moss_lichen_fraction': 0.0,
        'water_occurrence_ge50_fraction': 0.0,
    }
    fractions.update(overrides)
    return fractions


SCENARIOS = {
    'desert': cover(bare_or_sparse_fraction=0.97, permanent_water_fraction=0.01),
    'playa_margin': cover(bare_or_sparse_fraction=0.72, permanent_water_fraction=0.18,
                          water_occurrence_ge50_fraction=0.16),
    'arctic_barren': cover(bare_or_sparse_fraction=0.55, snow_ice_fraction=0.25, moss_lichen_fraction=0.12),
    'steppe': cover(bare_or_sparse_fraction=0.30, trees_fraction=0.01),
    'forest': cover(bare_or_sparse_fraction=0.02, trees_fraction=0.90),
    'town': cover(bare_or_sparse_fraction=0.90, built_fraction=0.06),
    'jrc_wet_desert': cover(bare_or_sparse_fraction=0.97, water_occurrence_ge50_fraction=0.04),
}

EXPECTED = {
    'arid_mars_surface_v2': {
        'desert': 'eligible_arid_exposed',
        'playa_margin': 'excluded_permanent_water',
        'arctic_barren': 'excluded_snow_ice',
        'steppe': 'excluded_vegetated_non_tree',
        'forest': 'excluded_dense_canopy',
        'town': 'excluded_built',
        'jrc_wet_desert': 'excluded_permanent_water',
    },
    'paleolake_margin_v1': {
        'desert': 'eligible_paleolake_margin',
        'playa_margin': 'eligible_paleolake_margin',
        'arctic_barren': 'excluded_snow_ice',
        'steppe': 'excluded_vegetated_non_tree',
        'forest': 'excluded_dense_canopy',
        'town': 'excluded_built',
        'jrc_wet_desert': 'eligible_paleolake_margin',
    },
    # Without the global layers the cold-climate gate has no evidence: nothing is declared eligible.
    'polar_cold_v1': {
        'desert': 'pending_climate_check',
        'playa_margin': 'excluded_permanent_water',
        'arctic_barren': 'pending_climate_check',
        'steppe': 'excluded_vegetated_non_tree',
        'forest': 'excluded_dense_canopy',
        'town': 'excluded_built',
        'jrc_wet_desert': 'pending_climate_check',
    },
}


def base_row(region_id: str, fractions: dict, profile: str | None = 'arid_mars_surface_v2',
             cover_valid: float | None = 1.0) -> dict:
    status = (
        eligibility.classify(fractions, 1.0, cover_valid, profile)
        if profile else 'pending_on_demand_cover_check'
    )
    return {
        'region_id': region_id, 'grid_version': 'utm-ups-v1', 'body': 'Earth', 'utm_zone_band': 'N01',
        'batch_id': 'b', 'longitude': 0.0, 'latitude': 0.0, 'window_m': 3000, 'cell_m': 30,
        'slope_base_m': 240, 'roughness_radius_m': 360, 'land_fraction': 1.0, 'topo_valid_fraction': 1.0,
        'roughness_coverage': 1.0, 'relief_p95_p05_m': 100.0, 'slope_240m_p50_deg': 3.0,
        'slope_240m_p90_deg': 9.0, 'roughness_360m_p50_m': 5.0,
        'analog_surface_eligibility': status, 'eligibility_profile': profile,
        'cover_status': 'measured' if cover_valid is not None else 'not_requested',
        'cover_valid_fraction': cover_valid, 'water_occurrence_mean_pct': 0.0,
        'water_extent_gt0_fraction': 0.0, 'qa_status': 'rankable', 'source_manifest_id': 'm',
        'updated_at': NOW, **fractions,
    }


class TestEligibilityProfiles(unittest.TestCase):
    def test_scenarios_per_profile(self) -> None:
        for profile_id, expected in EXPECTED.items():
            for name, fractions in SCENARIOS.items():
                with self.subTest(profile=profile_id, scenario=name):
                    self.assertEqual(eligibility.classify(fractions, 1.0, 1.0, profile_id), expected[name])

    def test_polar_profile_needs_a_cold_climate(self) -> None:
        def polar(climate: dict) -> str:
            return eligibility.classify({**SCENARIOS['desert'], **climate}, 1.0, 1.0, 'polar_cold_v1')

        snow, perm = eligibility.SNOW_MONTHS_COLUMN, eligibility.PERMAFROST_COLUMN
        self.assertEqual(polar({snow: 0.0, perm: None}), 'excluded_warm_climate')  # Sahara, Arabia
        self.assertEqual(polar({snow: 0.02, perm: None}), 'excluded_warm_climate')  # Utah
        self.assertEqual(polar({snow: 0.24, perm: 0.09}), 'excluded_warm_climate')
        self.assertEqual(polar({snow: 0.25, perm: None}), 'eligible_polar_cold_exposed')
        self.assertEqual(polar({snow: 1.0, perm: None}), 'eligible_polar_cold_exposed')  # Devon, Peary Land
        self.assertEqual(polar({snow: 0.12, perm: 1.0}), 'eligible_polar_cold_exposed')  # Tibetan plateau
        self.assertEqual(polar({snow: None, perm: 0.1}), 'eligible_polar_cold_exposed')
        self.assertEqual(polar({snow: None, perm: None}), 'pending_climate_check')
        # Climate never rescues a window that fails the cover gates.
        forest = {**SCENARIOS['forest'], snow: 1.0, perm: 1.0}
        self.assertEqual(eligibility.classify(forest, 1.0, 1.0, 'polar_cold_v1'), 'excluded_dense_canopy')
        # The other profiles ignore climate.
        warm = {**SCENARIOS['desert'], snow: 0.0, perm: None}
        self.assertEqual(eligibility.classify(warm, 1.0, 1.0, 'arid_mars_surface_v2'), 'eligible_arid_exposed')

    def test_support_gates_precede_cover(self) -> None:
        for profile_id in eligibility.PROFILES:
            self.assertEqual(eligibility.classify(SCENARIOS['desert'], 0.5, 1.0, profile_id),
                             'excluded_insufficient_land')
            self.assertEqual(eligibility.classify(SCENARIOS['desert'], 1.0, None, profile_id),
                             'pending_on_demand_cover_check')
            self.assertEqual(eligibility.classify(SCENARIOS['desert'], 1.0, 0.5, profile_id),
                             'pending_on_demand_cover_check')

    def test_statuses_are_in_contract_enum(self) -> None:
        produced = {s for exp in EXPECTED.values() for s in exp.values()}
        self.assertTrue(produced <= set(contract.ELIGIBILITY_ENUM))
        self.assertNotIn('excluded_urban_or_ice', eligibility.EXCLUSION_STATUSES)
        self.assertEqual(contract.load_store_spec()['enums']['eligibility_status'], list(contract.ELIGIBILITY_ENUM))

    def test_unknown_profile_rejected(self) -> None:
        with self.assertRaises(ValueError):
            eligibility.classify(SCENARIOS['desert'], 1.0, 1.0, 'lunar_v9')

    def test_sql_matches_python(self) -> None:
        values = (0.0, 0.01, 0.03, 0.1, 0.3, 0.6, 0.9)
        rows = []
        for i, (bare, trees, built, snow, water, ge50) in enumerate(
            itertools.product(values, (0.0, 0.1), (0.0, 0.05), (0.0, 0.1, 0.4), (0.0, 0.03, 0.2), (0.0, 0.1))
        ):
            rows.append({'id': i, 'land_fraction': 1.0, 'cover_valid_fraction': 1.0,
                         **cover(bare_or_sparse_fraction=bare, trees_fraction=trees, built_fraction=built,
                                 snow_ice_fraction=snow, permanent_water_fraction=water,
                                 moss_lichen_fraction=0.1, water_occurrence_ge50_fraction=ge50)})
        conn = duckdb.connect()
        conn.register('base_windows', pa.Table.from_pylist(rows))
        for profile_id in eligibility.PROFILES:
            sql = f'SELECT id, {eligibility.sql_case(profile_id, climate=False)} FROM base_windows ORDER BY id'
            got = dict(conn.execute(sql).fetchall())
            for row in rows:
                with self.subTest(profile=profile_id, row=row['id']):
                    self.assertEqual(got[row['id']], eligibility.classify(row, 1.0, 1.0, profile_id))

    def test_sql_climate_gate_matches_python(self) -> None:
        levels = (None, 0.0, 0.02, 0.24, 0.25, 0.5, 1.0)
        rows = [{'id': i, 'land_fraction': 1.0, 'cover_valid_fraction': 1.0,
                 **SCENARIOS['desert'], eligibility.SNOW_MONTHS_COLUMN: snow, eligibility.PERMAFROST_COLUMN: perm}
                for i, (snow, perm) in enumerate(itertools.product(levels, (None, 0.0, 0.09, 0.1, 1.0)))]
        conn = duckdb.connect()
        schema = pa.schema([('id', pa.int64()), ('land_fraction', pa.float64()), ('cover_valid_fraction', pa.float64()),
                            *[(k, pa.float64()) for k in SCENARIOS['desert']],
                            (eligibility.SNOW_MONTHS_COLUMN, pa.float64()), (eligibility.PERMAFROST_COLUMN, pa.float64())])
        conn.register('base_windows', pa.Table.from_pylist(rows, schema=schema))
        got = dict(conn.execute(
            f"SELECT id, {eligibility.sql_case('polar_cold_v1')} FROM base_windows ORDER BY id").fetchall())
        for row in rows:
            with self.subTest(row=row['id']):
                self.assertEqual(got[row['id']], eligibility.classify(row, 1.0, 1.0, 'polar_cold_v1'))

    def test_store_ranks_by_profile_and_flags_legacy_rows(self) -> None:
        rows = [base_row(name, fractions) for name, fractions in SCENARIOS.items()]
        with tempfile.TemporaryDirectory() as tmp:
            store = FeatureStore(Path(tmp) / 'store', memory_limit='512MB', threads=2)
            store.write_base_batch('b', rows)
            # A pre-profile Parquet file lacks the new columns and uses the legacy label.
            legacy_schema = pa.schema([f for f in contract.BASE_WINDOWS_SCHEMA if f.name not in (
                'eligibility_profile', 'cover_status', 'cover_valid_fraction', 'snow_ice_fraction',
                'moss_lichen_fraction', 'water_occurrence_ge50_fraction')])
            legacy = {k: v for k, v in base_row('legacy', SCENARIOS['desert']).items() if k in legacy_schema.names}
            legacy_dir = Path(tmp) / 'store' / 'base' / 'utm_zone_band=N01'
            pq.write_table(pa.Table.from_pylist([{**legacy, 'utm_zone_band': 'N01'}],
                                                schema=legacy_schema).drop(['utm_zone_band']),
                           legacy_dir / 'part_legacy.parquet')

            def ranked(profile: str) -> set[str]:
                return {r['region_id'] for r in store.rank_similar(100.0, 3.0, 9.0, limit=50, profile=profile)}

            self.assertEqual(ranked('arid_mars_surface_v2'), {'desert'})
            self.assertEqual(ranked('paleolake_margin_v1'), {'desert', 'playa_margin', 'jrc_wet_desert'})
            self.assertEqual(ranked('polar_cold_v1'), set())  # no global layers in this store

            everything = store.rank_similar(100.0, 3.0, 9.0, limit=50, only_eligible=False,
                                            profile='polar_cold_v1')
            by_id = {r['region_id']: r['scenario_eligibility'] for r in everything}
            self.assertEqual(by_id['legacy'], 'pending_on_demand_cover_check')
            self.assertEqual(by_id['forest'], 'excluded_dense_canopy')
            self.assertEqual(by_id['desert'], 'pending_climate_check')

            stats = store.store_stats()
            self.assertEqual(stats['legacy_rows_needing_reextraction'], 1)
            self.assertNotIn('eligible_polar_cold_exposed', stats['by_scenario_profile']['polar_cold_v1'])
            self.assertEqual(stats['by_scenario_profile']['polar_cold_v1']['pending_climate_check'], 3)

    def test_expression_rejects_unknown_profile(self) -> None:
        with self.assertRaises(ValueError):
            eligibility_expression("x' OR 1=1 --")


if __name__ == '__main__':
    unittest.main()
