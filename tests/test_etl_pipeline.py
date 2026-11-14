"""End-to-end tests for ETL extractors and DuckDB out-of-core FeatureStore."""
from __future__ import annotations

from datetime import datetime, timezone
import math
from pathlib import Path
import tempfile
import unittest

import numpy as np

from pipelines import etl_contract as contract
from pipelines import etl_extractors as extractors
from pipelines.etl_store import FeatureStore
from scripts.analizar_dimensiones import geometry_descriptors


class TestETLPipeline(unittest.TestCase):
    def test_topography_240m_slope_and_roughness_on_synthetic_plane(self) -> None:
        cell = 30
        size = (3000 + 2 * 720) // cell  # 148 x 148
        # Constant 10-degree eastward slope
        target_deg = 10.0
        grad = math.tan(math.radians(target_deg))
        xs = np.arange(size, dtype='float64') * cell
        elev = np.tile(xs * grad, (size, 1))
        land = np.ones((size, size), dtype=bool)

        feats = extractors.compute_topography_features(elev, land, cell_m=cell, window_m=3000)
        self.assertEqual(feats['land_fraction'], 1.0)
        self.assertAlmostEqual(feats['topo_valid_fraction'], 1.0, places=5)
        self.assertAlmostEqual(feats['slope_240m_p50_deg'], target_deg, places=3)
        self.assertAlmostEqual(feats['slope_240m_p90_deg'], target_deg, places=3)
        self.assertAlmostEqual(feats['roughness_360m_p50_m'], 0.0, places=5)
        self.assertGreater(feats['relief_p95_p05_m'], 400.0)

    def test_separable_roughness_matches_reference(self) -> None:
        rng = np.random.default_rng(7)
        z = rng.normal(1200.0, 18.0, size=(90, 90))
        z[10:13, 20:24] = np.nan
        ref = geometry_descriptors(z, 30, 360)['roughness_rms']
        fast = extractors.roughness_rms_separable(z, 30, 360)
        self.assertTrue(np.array_equal(np.isnan(ref), np.isnan(fast)))
        valid = np.isfinite(ref)
        self.assertTrue(np.allclose(ref[valid], fast[valid], atol=1e-10))

    def test_eligibility_gate(self) -> None:
        self.assertEqual(
            extractors.classify_eligibility(0.95, 0.99, 0.92, 0.01, 0.0, 0.0, 0.0),
            'eligible_arid_exposed',
        )
        self.assertEqual(
            extractors.classify_eligibility(0.95, 0.99, 0.10, 0.80, 0.0, 0.0, 0.0),
            'excluded_dense_canopy',
        )
        self.assertEqual(
            extractors.classify_eligibility(0.95, 0.99, 0.85, 0.0, 0.0, 0.0, 0.05),
            'excluded_permanent_water',
        )
        self.assertEqual(
            extractors.classify_eligibility(0.95, 0.99, 0.90, 0.0, 0.05, 0.0, 0.0),
            'excluded_urban_or_ice',
        )
        self.assertEqual(
            extractors.classify_eligibility(0.60, 0.99, 0.99, 0.0, 0.0, 0.0, 0.0),
            'excluded_insufficient_land',
        )
        self.assertEqual(
            extractors.classify_eligibility(0.95, 0.40, None, None, None, None, None),
            'pending_on_demand_cover_check',
        )

    def test_feature_store_batch_enrich_and_rank_out_of_core(self) -> None:
        now = datetime(2026, 11, 12, 14, 0, tzinfo=timezone.utc)

        def base_row(rid: str, band: str, relief: float, s50: float, s90: float, elig: str) -> dict:
            return {
                'region_id': rid,
                'grid_version': 'utm-ups-v1',
                'body': 'Earth',
                'utm_zone_band': band,
                'batch_id': 'batch-test',
                'longitude': -110.6,
                'latitude': 38.6,
                'window_m': 3000,
                'cell_m': 30,
                'slope_base_m': 240,
                'roughness_radius_m': 360,
                'land_fraction': 1.0,
                'topo_valid_fraction': 1.0,
                'roughness_coverage': 1.0,
                'relief_p95_p05_m': relief,
                'slope_240m_p50_deg': s50,
                'slope_240m_p90_deg': s90,
                'roughness_360m_p50_m': 5.0 if elig == 'eligible_arid_exposed' else None,
                'analog_surface_eligibility': elig,
                'bare_or_sparse_fraction': 0.96 if elig == 'eligible_arid_exposed' else 0.05,
                'trees_fraction': 0.0 if elig == 'eligible_arid_exposed' else 0.90,
                'built_fraction': 0.0,
                'permanent_water_fraction': 0.0,
                'water_occurrence_mean_pct': 0.0,
                'water_extent_gt0_fraction': 0.0,
                'qa_status': 'rankable',
                'source_manifest_id': 'man-01',
                'updated_at': now,
            }

        rows = [
            base_row('win-close', 'N01', 118.0, 3.1, 9.0, 'eligible_arid_exposed'),
            base_row('win-far', 'N01', 450.0, 14.0, 28.0, 'eligible_arid_exposed'),
            base_row('win-forest', 'N01', 120.0, 3.0, 9.2, 'excluded_dense_canopy'),
        ]
        manifests = [{
            'source_manifest_id': 'man-01',
            'product_id': 'copernicus-glo30',
            'asset_id': 'Copernicus_DSM_COG_10_N38_00_W111_00_DEM.tif',
            'access_mode': 'cache',
            'sha256_or_etag': 'abc123',
            'native_resolution_m': 30.0,
            'effective_resolution_m': 30.0,
            'observation_period': 'static',
            'created_at': now,
        }]

        with tempfile.TemporaryDirectory() as tmp:
            store = FeatureStore(Path(tmp) / 'store', memory_limit='512MB', threads=2)
            written = store.write_base_batch('batch-test', rows, manifests)
            self.assertEqual(len(written), 1)

            candidates = store.query_candidates_for_enrichment(limit=10)
            self.assertEqual([c['region_id'] for c in candidates], ['win-close', 'win-far'])

            # Simulate on-demand enrichment of win-close
            spec_row = extractors.build_spectral_record_from_emit_summary(
                region_id='win-close',
                complex_stats={
                    cid: {'p50': 0.04, 'p95': 0.06, 'active_fraction': 0.35, 'n_samples': 120, 'status': 'measured'}
                    for cid in contract.SPECTRAL_COMPLEXES if cid != 'abs_mafic_fe2_1p0um'
                },
                source_manifest_id='man-emit',
                now=now,
            )
            temp_row = extractors.build_temporal_record(
                region_id='win-close',
                hls_ndvi_p50=0.09,
                hls_valid_fraction=0.98,
                hls_status='measured',
                landsat_lst_p50_k=311.2,
                landsat_valid_fraction=0.95,
                thermal_status='measured',
                source_manifest_id='man-temp',
                now=now,
            )
            store.append_enrichment('spectral', [spec_row])
            store.append_enrichment('temporal', [temp_row])

            ranked = store.rank_similar(120.27, 3.07, 9.24, limit=5, only_eligible=True)
            self.assertEqual([r['region_id'] for r in ranked], ['win-close', 'win-far'])
            self.assertEqual(ranked[0]['abs_al_oh_2p20um_status'], 'measured')
            self.assertEqual(ranked[1]['abs_al_oh_2p20um_status'], 'on_demand_fetchable')
            self.assertEqual(ranked[0]['hls_status'], 'measured')

            stats = store.store_stats()
            self.assertEqual(stats['total_windows'], 3)
            self.assertEqual(stats['enriched_spectral_earth'], 1)
            self.assertLess(stats['total_gb'], 100)


if __name__ == '__main__':
    unittest.main()
