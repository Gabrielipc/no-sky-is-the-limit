"""Tests for the Parquet Feature Store ETL contract and DuckDB out-of-core views."""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq

from pipelines import etl_contract as contract


class TestETLContract(unittest.TestCase):
    def test_spec_alignment_with_entrega3(self) -> None:
        store_spec = contract.load_store_spec()
        entrega3_spec = json.loads(contract.CONTRACT_SPEC_PATH.read_text(encoding='utf-8'))
        self.assertEqual(store_spec['contract_ref'], entrega3_spec['contract_id'])
        self.assertEqual(store_spec['storage_budget']['max_store_gb'], 100)
        spec_complexes = tuple(c['complex_id'] for c in entrega3_spec['spectral_absorption_complexes'])
        self.assertEqual(contract.SPECTRAL_COMPLEXES, spec_complexes)

    def test_validation_rejects_invalid_enum_and_range(self) -> None:
        now = datetime(2026, 11, 12, 12, 0, tzinfo=timezone.utc)
        valid_row = {
            'region_id': 'utm-ups-v1-3000-32612-10-20',
            'grid_version': 'utm-ups-v1',
            'body': 'Earth',
            'utm_zone_band': '32612',
            'batch_id': '32612-500000-4200000',
            'longitude': -110.6,
            'latitude': 38.6,
            'window_m': 3000,
            'cell_m': 30,
            'slope_base_m': 240,
            'roughness_radius_m': 360,
            'land_fraction': 1.0,
            'topo_valid_fraction': 1.0,
            'roughness_coverage': 1.0,
            'relief_p95_p05_m': 33.65,
            'slope_240m_p50_deg': 1.14,
            'slope_240m_p90_deg': 2.81,
            'roughness_360m_p50_m': 1.68,
            'analog_surface_eligibility': 'eligible_arid_exposed',
            'eligibility_profile': 'arid_mars_surface_v2',
            'cover_status': 'measured',
            'bare_or_sparse_fraction': 0.997,
            'trees_fraction': 0.0,
            'built_fraction': 0.0,
            'permanent_water_fraction': 0.0,
            'water_occurrence_mean_pct': 0.0,
            'water_extent_gt0_fraction': 0.0,
            'qa_status': 'rankable',
            'source_manifest_id': 'manifest-001',
            'updated_at': now,
        }
        table = pa.Table.from_pylist([valid_row], schema=contract.BASE_WINDOWS_SCHEMA)
        validated = contract.validate_table(table, 'base_windows')
        self.assertEqual(validated.num_rows, 1)

        bad_enum = pa.Table.from_pylist([{**valid_row, 'body': 'Venus'}], schema=contract.BASE_WINDOWS_SCHEMA)
        with self.assertRaises(ValueError):
            contract.validate_table(bad_enum, 'base_windows')

        bad_range = pa.Table.from_pylist([{**valid_row, 'bare_or_sparse_fraction': 1.25}],
                                        schema=contract.BASE_WINDOWS_SCHEMA)
        with self.assertRaises(ValueError):
            contract.validate_table(bad_range, 'base_windows')

    def test_duckdb_unified_view_and_compaction(self) -> None:
        t0 = datetime(2026, 11, 12, 10, 0, tzinfo=timezone.utc)
        t1 = datetime(2026, 11, 12, 11, 0, tzinfo=timezone.utc)
        t2 = datetime(2026, 11, 12, 12, 0, tzinfo=timezone.utc)

        base_rows = [
            {
                'region_id': 'earth-utah-1',
                'grid_version': 'utm-ups-v1',
                'body': 'Earth',
                'utm_zone_band': '32612',
                'batch_id': '32612-500000-4200000',
                'longitude': -110.6,
                'latitude': 38.6,
                'window_m': 3000,
                'cell_m': 30,
                'slope_base_m': 240,
                'roughness_radius_m': 360,
                'land_fraction': 1.0,
                'topo_valid_fraction': 1.0,
                'roughness_coverage': 1.0,
                'relief_p95_p05_m': 33.65,
                'slope_240m_p50_deg': 1.14,
                'slope_240m_p90_deg': 2.81,
                'roughness_360m_p50_m': 1.68,
                'analog_surface_eligibility': 'eligible_arid_exposed',
                'eligibility_profile': 'arid_mars_surface_v2',
                'cover_status': 'measured',
            'eligibility_profile': 'arid_mars_surface_v2',
                'bare_or_sparse_fraction': 0.997,
                'trees_fraction': 0.0,
                'built_fraction': 0.0,
                'permanent_water_fraction': 0.0,
                'water_occurrence_mean_pct': 0.0,
                'water_extent_gt0_fraction': 0.0,
                'qa_status': 'rankable',
                'source_manifest_id': 'm-base',
                'updated_at': t0,
            },
            {
                'region_id': 'mars-jezero-1',
                'grid_version': 'mars-local-v1',
                'body': 'Mars',
                'utm_zone_band': 'mars',
                'batch_id': 'jezero-0',
                'longitude': 77.41,
                'latitude': 18.49,
                'window_m': 3000,
                'cell_m': 30,
                'slope_base_m': 240,
                'roughness_radius_m': 360,
                'land_fraction': 1.0,
                'topo_valid_fraction': 1.0,
                'roughness_coverage': 1.0,
                'relief_p95_p05_m': 120.27,
                'slope_240m_p50_deg': 3.07,
                'slope_240m_p90_deg': 9.24,
                'roughness_360m_p50_m': 7.57,
                'analog_surface_eligibility': 'mars_reference_surface',
                'eligibility_profile': 'mars_reference',
                'cover_status': 'not_requested',
                'bare_or_sparse_fraction': 1.0,
                'trees_fraction': 0.0,
                'built_fraction': 0.0,
                'permanent_water_fraction': 0.0,
                'water_occurrence_mean_pct': 0.0,
                'water_extent_gt0_fraction': 0.0,
                'qa_status': 'rankable',
                'source_manifest_id': 'm-mars',
                'updated_at': t0,
            },
        ]

        def spectral_row(region_id: str, al_oh_p50: float, status: str, ts: datetime) -> dict:
            row = {
                'region_id': region_id,
                'instrument': 'EMIT_L2B',
                'source_manifest_id': 'm-emit',
                'updated_at': ts,
            }
            for cid in contract.SPECTRAL_COMPLEXES:
                row[f'{cid}_p50'] = al_oh_p50 if cid == 'abs_al_oh_2p20um' else None
                row[f'{cid}_p95'] = (al_oh_p50 + 0.01) if cid == 'abs_al_oh_2p20um' else None
                row[f'{cid}_active_fraction'] = 0.5 if cid == 'abs_al_oh_2p20um' else None
                row[f'{cid}_n_samples'] = 100 if cid == 'abs_al_oh_2p20um' else None
                row[f'{cid}_status'] = status if cid == 'abs_al_oh_2p20um' else 'on_demand_fetchable'
            return row

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'store'
            (root / 'base' / 'utm_zone_band=32612').mkdir(parents=True)
            (root / 'base' / 'utm_zone_band=mars').mkdir(parents=True)
            (root / 'enrichment' / 'spectral').mkdir(parents=True)

            t_earth = contract.validate_table(
                pa.Table.from_pylist([base_rows[0]], schema=contract.BASE_WINDOWS_SCHEMA),
                'base_windows',
            )
            t_mars = contract.validate_table(
                pa.Table.from_pylist([base_rows[1]], schema=contract.BASE_WINDOWS_SCHEMA),
                'base_windows',
            )
            pq.write_table(t_earth.drop(['utm_zone_band']), root / 'base' / 'utm_zone_band=32612' / 'part_0.parquet',
                           compression='zstd')
            pq.write_table(t_mars.drop(['utm_zone_band']), root / 'base' / 'utm_zone_band=mars' / 'part_0.parquet',
                           compression='zstd')

            with duckdb.connect() as conn:
                contract.configure_duckdb(conn, Path(tmp) / 'spill', memory_limit='512MB', threads=2)
                contract.register_unified_views(conn, root)

                # Before on-demand enrichment: typed statuses reflect body defaults.
                statuses = dict(conn.execute(
                    'SELECT region_id, abs_al_oh_2p20um_status FROM features_unified'
                ).fetchall())
                self.assertEqual(statuses['earth-utah-1'], 'on_demand_fetchable')
                self.assertEqual(statuses['mars-jezero-1'], 'unobserved_by_product')

                # Append two on-demand spectral deltas; latest timestamp must win.
                d1 = contract.validate_table(
                    pa.Table.from_pylist([spectral_row('earth-utah-1', 0.02, 'measured', t1)],
                                         schema=contract.ENRICHMENT_SPECTRAL_SCHEMA),
                    'enrichment_spectral',
                )
                d2 = contract.validate_table(
                    pa.Table.from_pylist([spectral_row('earth-utah-1', 0.035, 'measured', t2)],
                                         schema=contract.ENRICHMENT_SPECTRAL_SCHEMA),
                    'enrichment_spectral',
                )
                pq.write_table(d1, root / 'enrichment' / 'spectral' / 'delta_001.parquet', compression='zstd')
                pq.write_table(d2, root / 'enrichment' / 'spectral' / 'delta_002.parquet', compression='zstd')
                contract.register_unified_views(conn, root)

                p50, status = conn.execute(
                    "SELECT abs_al_oh_2p20um_p50, abs_al_oh_2p20um_status FROM features_unified WHERE region_id = 'earth-utah-1'"
                ).fetchone()
                self.assertEqual(status, 'measured')
                self.assertAlmostEqual(p50, 0.035, places=4)

                compacted = contract.compact_enrichment(conn, root, 'spectral')
                self.assertIsNotNone(compacted)
                self.assertEqual(len(list((root / 'enrichment' / 'spectral').glob('*.parquet'))), 1)

                p50_after, _ = conn.execute(
                    "SELECT abs_al_oh_2p20um_p50, abs_al_oh_2p20um_status FROM features_unified WHERE region_id = 'earth-utah-1'"
                ).fetchone()
                self.assertAlmostEqual(p50_after, 0.035, places=4)


if __name__ == '__main__':
    unittest.main()


class TestBaseDeduplication(unittest.TestCase):
    def test_window_in_two_batches_appears_once_with_latest_row(self) -> None:
        from datetime import datetime, timezone
        from pipelines.etl_store import FeatureStore
        from tests.test_similarity_ml import base_row, REF
        with tempfile.TemporaryDirectory() as tmp:
            store = FeatureStore(Path(tmp) / 'store', memory_limit='256MB', threads=1)
            old = base_row('w1', 1.0, 1.0, dict(REF)) | {'batch_id': 'pilot', 'relief_p95_p05_m': 1.0,
                                                          'updated_at': datetime(2026, 11, 14, 22, tzinfo=timezone.utc)}
            new = base_row('w1', 1.0, 1.0, dict(REF)) | {'batch_id': 'world', 'relief_p95_p05_m': 2.0,
                                                          'updated_at': datetime(2026, 11, 15, 2, tzinfo=timezone.utc)}
            store.write_base_batch('pilot', [old])
            store.write_base_batch('world', [new, base_row('w2', 2.0, 2.0, dict(REF))])
            with store._connect() as conn:
                rows = conn.execute('SELECT region_id, relief_p95_p05_m FROM features_unified ORDER BY 1').fetchall()
            self.assertEqual(rows, [('w1', 2.0), ('w2', REF['relief_p95_p05_m'])])
