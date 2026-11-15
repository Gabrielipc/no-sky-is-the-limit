"""Tests for the six official-source surface dimensions (`enrichment_surface`), audit §3."""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np
import pyarrow as pa

from pipelines import etl_contract as contract
from pipelines import etl_surface_dimensions as surf
from pipelines import etl_surface_schema as surf_schema
from pipelines.etl_store import FeatureStore

NOW = datetime(2026, 11, 14, 12, 0, tzinfo=timezone.utc)


class TestSurfaceExtractors(unittest.TestCase):
    def test_aridity_1d_and_insufficient_coverage(self) -> None:
        # 10 dry months (< 5 mm) + 2 wet months (24 mm) -> annual total 58 mm (mean 4.833 * 12)
        monthly = np.array([0.0] * 8 + [2.0, 2.0, 20.0, 34.0], dtype=float)
        out, frac, status = surf.compute_aridity_metrics(monthly)
        self.assertEqual(status, 'measured')
        self.assertAlmostEqual(frac, 1.0)
        self.assertAlmostEqual(out['precip_mean_annual_mm'], 58.0, places=5)
        self.assertAlmostEqual(out['dry_months_fraction'], 10.0 / 12.0, places=5)

        sparse = monthly.copy()
        sparse[:4] = np.nan  # 8/12 = 66.7% < 80%
        out_low, frac_low, status_low = surf.compute_aridity_metrics(sparse)
        self.assertEqual(status_low, 'insufficient_coverage')
        self.assertAlmostEqual(frac_low, 8.0 / 12.0, places=5)
        self.assertIsNone(out_low['precip_mean_annual_mm'])
        self.assertIsNone(out_low['dry_months_fraction'])

    def test_smap_moisture_qa_filtering(self) -> None:
        sm = np.array([0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.55, 0.60])
        qa = np.array([0, 0, 0, 0, 0, 0, 0, 0, 1, 1], dtype=np.int32)  # last two fail bit-0 QA
        out, frac, status = surf.compute_smap_moisture_metrics(sm, qa)
        self.assertEqual(status, 'measured')
        self.assertAlmostEqual(frac, 0.80)
        self.assertAlmostEqual(out['smap_sm_p50_m3m3'], 0.225, places=5)
        self.assertAlmostEqual(out['smap_sm_p90_m3m3'], float(np.percentile(sm[:8], 90.0)), places=5)

        # Dropping one more pixel -> 70% < 80%
        qa_low = qa.copy()
        qa_low[0] = 3
        out_low, frac_low, status_low = surf.compute_smap_moisture_metrics(sm, qa_low)
        self.assertEqual(status_low, 'insufficient_coverage')
        self.assertAlmostEqual(frac_low, 0.70)
        self.assertIsNone(out_low['smap_sm_p50_m3m3'])

    def test_mod10a1_snow_masks_clouds_and_bad_qa(self) -> None:
        # 10 days: 8 clear (5 snow-covered 25..90, 3 snow-free 0), 2 cloud/fill (250, 255)
        ndsi = np.array([80, 60, 40, 25, 10, 0, 0, 0, 250, 255], dtype=np.float32)
        qa = np.array([0, 0, 1, 1, 0, 0, 1, 0, 0, 255], dtype=np.int32)
        out, frac, status = surf.compute_mod10a1_snow_metrics(ndsi, qa)
        self.assertEqual(status, 'measured')
        self.assertAlmostEqual(frac, 0.80)
        self.assertAlmostEqual(out['mod10a1_clear_days_fraction'], 0.80)
        self.assertAlmostEqual(out['mod10a1_snow_days_fraction'], 5.0 / 8.0)

        # Poor Basic QA (== 2) reduces clear fraction below 0.80
        qa_poor = qa.copy()
        qa_poor[0] = 2
        out_poor, _, status_poor = surf.compute_mod10a1_snow_metrics(ndsi, qa_poor)
        self.assertEqual(status_poor, 'insufficient_coverage')
        self.assertIsNone(out_poor['mod10a1_snow_days_fraction'])

    def test_permafrost_metrics_and_absent_alt(self) -> None:
        pfr = np.array([[90.0, 80.0], [70.0, 0.0]])
        alt = np.array([[0.8, 1.0], [1.2, np.nan]])  # ALT absent where PFR == 0
        out, frac, status = surf.compute_permafrost_metrics(pfr, alt)
        self.assertEqual(status, 'measured')
        self.assertAlmostEqual(frac, 1.0)
        self.assertAlmostEqual(out['cci_permafrost_probability'], 0.60, places=5)
        self.assertAlmostEqual(out['cci_active_layer_thickness_m'], 1.0, places=5)

    def test_aster_ged_separates_felsic_and_mafic(self) -> None:
        # Quartzose felsic spectrum: lower e10-e12 Reststrahlen than e13-e14
        felsic = np.broadcast_to(np.array([0.80, 0.78, 0.82, 0.95, 0.96])[:, None, None], (5, 4, 4)).copy()
        # Basaltic mafic spectrum: higher e10-e11, Reststrahlen shift toward e13-e14
        mafic = np.broadcast_to(np.array([0.96, 0.94, 0.88, 0.82, 0.86])[:, None, None], (5, 4, 4)).copy()
        f_out, _, f_status = surf.compute_aster_ged_emissivity_metrics(felsic)
        m_out, _, m_status = surf.compute_aster_ged_emissivity_metrics(mafic)
        self.assertEqual(f_status, 'measured')
        self.assertEqual(m_status, 'measured')
        self.assertLess(f_out['aster_emissivity_mafic_index'], 1.0)
        self.assertGreater(m_out['aster_emissivity_mafic_index'], 1.0)
        self.assertLess(f_out['aster_christiansen_wb_um'], m_out['aster_christiansen_wb_um'])

    def test_sentinel1_rtc_masks_layover_shadow(self) -> None:
        vv = np.full((5, 5), 0.1)     # -10 dB
        vh = np.full((5, 5), 0.01)    # -20 dB -> VH/VV = -10 dB
        mask = np.zeros((5, 5), dtype=bool)
        mask[0, :5] = True  # 5/25 masked -> 80% valid
        vv[0, :5] = 10.0    # outlier under layover must be ignored
        out, frac, status = surf.compute_sentinel1_rtc_metrics(vv, vh, mask)
        self.assertEqual(status, 'measured')
        self.assertAlmostEqual(frac, 0.80)
        self.assertAlmostEqual(out['s1_rtc_vv_p50_db'], -10.0, places=4)
        self.assertAlmostEqual(out['s1_rtc_vh_p50_db'], -20.0, places=4)
        self.assertAlmostEqual(out['s1_rtc_vh_vv_ratio_db'], -10.0, places=4)

        mask[1, 0] = True  # 6/25 masked -> 76% < 80%
        out_low, frac_low, status_low = surf.compute_sentinel1_rtc_metrics(vv, vh, mask)
        self.assertEqual(status_low, 'insufficient_coverage')
        self.assertAlmostEqual(frac_low, 0.76)
        self.assertIsNone(out_low['s1_rtc_vv_p50_db'])


class TestSurfaceStoreIntegration(unittest.TestCase):
    def test_validation_rejects_out_of_range_and_bad_status(self) -> None:
        row = surf.extract_surface_dimensions_window(
            'earth-utah-1',
            raw_inputs={'aridity': {'monthly_precip_mm': np.full(12, 10.0)}},
            updated_at=NOW,
        )
        self.assertEqual(row['aridity_status'], 'measured')
        self.assertEqual(row['soil_moisture_status'], 'on_demand_fetchable')
        self.assertIsNone(row['smap_sm_p50_m3m3'])

        valid_tbl = pa.Table.from_pylist([row], schema=contract.ENRICHMENT_SURFACE_SCHEMA)
        contract.validate_table(valid_tbl, 'enrichment_surface')

        bad_range = pa.Table.from_pylist(
            [{**row, 'smap_sm_p50_m3m3': 0.95, 'soil_moisture_status': 'measured'}],
            schema=contract.ENRICHMENT_SURFACE_SCHEMA,
        )
        with self.assertRaises(ValueError):
            contract.validate_table(bad_range, 'enrichment_surface')

        bad_status = pa.Table.from_pylist(
            [{**row, 'permafrost_status': 'invalid_status'}],
            schema=contract.ENRICHMENT_SURFACE_SCHEMA,
        )
        with self.assertRaises(ValueError):
            contract.validate_table(bad_status, 'enrichment_surface')

    def test_store_round_trip_and_unified_view(self) -> None:
        base_rows = [
            {
                'region_id': 'earth-utah-1', 'grid_version': 'utm-ups-v1', 'body': 'Earth',
                'utm_zone_band': '32612', 'batch_id': '32612-500000-4200000',
                'longitude': -110.6, 'latitude': 38.6, 'window_m': 3000, 'cell_m': 30,
                'slope_base_m': 240, 'roughness_radius_m': 360, 'land_fraction': 1.0,
                'topo_valid_fraction': 1.0, 'roughness_coverage': 1.0, 'relief_p95_p05_m': 33.6,
                'slope_240m_p50_deg': 1.1, 'slope_240m_p90_deg': 2.8, 'roughness_360m_p50_m': 1.7,
                'analog_surface_eligibility': 'eligible_arid_exposed',
                'eligibility_profile': 'arid_mars_surface_v2', 'cover_status': 'measured',
                'bare_or_sparse_fraction': 0.99, 'trees_fraction': 0.0, 'built_fraction': 0.0,
                'permanent_water_fraction': 0.0, 'water_occurrence_mean_pct': 0.0,
                'water_extent_gt0_fraction': 0.0, 'qa_status': 'rankable',
                'source_manifest_id': 'm-base', 'updated_at': NOW,
            },
            {
                'region_id': 'mars-jezero-1', 'grid_version': 'mars-local-v1', 'body': 'Mars',
                'utm_zone_band': 'mars', 'batch_id': 'jezero-0',
                'longitude': 77.41, 'latitude': 18.49, 'window_m': 3000, 'cell_m': 30,
                'slope_base_m': 240, 'roughness_radius_m': 360, 'land_fraction': 1.0,
                'topo_valid_fraction': 1.0, 'roughness_coverage': 1.0, 'relief_p95_p05_m': 120.2,
                'slope_240m_p50_deg': 3.1, 'slope_240m_p90_deg': 9.2, 'roughness_360m_p50_m': 7.5,
                'analog_surface_eligibility': 'mars_reference_surface',
                'eligibility_profile': 'mars_reference', 'cover_status': 'not_requested',
                'bare_or_sparse_fraction': 1.0, 'trees_fraction': 0.0, 'built_fraction': 0.0,
                'permanent_water_fraction': 0.0, 'water_occurrence_mean_pct': 0.0,
                'water_extent_gt0_fraction': 0.0, 'qa_status': 'rankable',
                'source_manifest_id': 'm-mars', 'updated_at': NOW,
            },
        ]

        surf_row = surf.extract_surface_dimensions_window(
            'earth-utah-1',
            raw_inputs={
                'aridity': {'monthly_precip_mm': np.full(12, 3.0)},
                'soil_moisture': {'sm_m3m3': np.full((4, 4), 0.06)},
                'snow_persistence': {'ndsi_snow_cover': np.zeros((4, 4))},
                'permafrost': {'pfr_pct': np.zeros((4, 4)), 'alt_m': np.zeros((4, 4))},
                'thermal_emissivity': {'emissivity_b10_b14': np.broadcast_to(
                    np.array([0.82, 0.80, 0.84, 0.94, 0.95])[:, None, None], (5, 4, 4)
                )},
                'sar_backscatter': {'sigma0_vv_linear': np.full((4, 4), 0.1), 'sigma0_vh_linear': np.full((4, 4), 0.02)},
            },
            updated_at=NOW,
        )

        with tempfile.TemporaryDirectory() as tmp:
            store = FeatureStore(Path(tmp))
            store.write_base_batch('b1', base_rows)
            store.append_enrichment('surface', [surf_row])
            with store._connect() as conn:
                earth = conn.execute(
                    'SELECT aridity_status, precip_mean_annual_mm, sar_backscatter_status, aster_emissivity_mafic_index '
                    "FROM features_unified WHERE region_id = 'earth-utah-1'"
                ).fetchone()
                mars = conn.execute(
                    "SELECT aridity_status, permafrost_status, sar_backscatter_status FROM features_unified WHERE region_id = 'mars-jezero-1'"
                ).fetchone()
                cols = {r[0] for r in conn.execute('DESCRIBE features_unified').fetchall()}

            self.assertEqual(earth[0], 'measured')
            self.assertAlmostEqual(earth[1], 36.0, places=4)
            self.assertEqual(earth[2], 'measured')
            self.assertLess(earth[3], 1.0)
            self.assertEqual(mars, ('unobserved_by_product', 'unobserved_by_product', 'unobserved_by_product'))
            for expected_col in surf_schema.SURFACE_RANGES:
                self.assertIn(expected_col, cols)

    def test_spec_and_contract_alignment(self) -> None:
        spec = surf.load_surface_spec()
        store_spec = contract.load_store_spec()
        self.assertEqual(set(spec['dimensions'].keys()), set(surf_schema.SURFACE_DIMENSIONS.keys()))
        self.assertIn('enrichment_surface', store_spec['tables'])
        entrega3 = json.loads(contract.CONTRACT_SPEC_PATH.read_text(encoding='utf-8'))
        self.assertEqual(
            [d['id'] for d in entrega3['official_surface_dimensions']['dimensions']],
            list(surf_schema.SURFACE_DIMENSIONS.keys()),
        )

    def test_build_surface_source_manifests(self) -> None:
        rows = surf.build_surface_source_manifests(fetched_at=NOW)
        self.assertGreaterEqual(len(rows), 8)
        table = pa.Table.from_pylist(rows, schema=contract.SOURCE_MANIFESTS_SCHEMA)
        contract.validate_table(table, 'source_manifests')
        self.assertEqual({r['product_id'] for r in rows} >= {
            'GPM_3IMERGDF.07', 'SPL3SMP_E.006', 'MOD10A1.061',
            'ESA_CCI_PERMAFROST_v5.0', 'AG100.003', 'OPERA_L2_RTC-S1_V1',
        }, True)


if __name__ == '__main__':
    unittest.main()
