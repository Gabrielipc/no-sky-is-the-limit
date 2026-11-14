import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))

import contrato_comun_y_seleccion as entrega3
import explorar_fuentes_atlas as eda


class TestContratoComunEntrega3(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.out_dir = ROOT / 'docs/evidencia-entrega-3'
        cls.spec = json.loads((ROOT / 'specs/analysis/contrato-comun-entrega3.json').read_text())
        cls.contract = json.loads((cls.out_dir / 'contrato-features.json').read_text())
        cls.selection = json.loads((cls.out_dir / 'seleccion-y-redundancia.json').read_text())
        cls.manifest = json.loads((cls.out_dir / 'manifest.json').read_text())

    def test_common_contract_sites_and_topography_parity(self):
        sites = {s['site_id']: s for s in self.contract['sites']}
        self.assertEqual(len(sites), 11)
        self.assertIn('mars-jezero-fan', sites)
        self.assertIn('desierto', sites)
        self.assertIn('atacama-materiales', sites)

        # Both Mars and Earth must expose identical topographic contract keys at 30, 60, 120 m and 1800, 3000 m
        mars_30 = sites['mars-jezero-fan']['topography_contract']['3000']['30']
        utah_30 = sites['desierto']['topography_contract']['3000']['30']
        for key in ('relief_p95_p05_m', 'slope_240m_p50_deg', 'slope_240m_p90_deg', 'roughness_360m_p50_m'):
            self.assertIsNotNone(mars_30[key], f'Missing {key} in Mars 30m contract')
            self.assertIsNotNone(utah_30[key], f'Missing {key} in Utah 30m contract')

        # Eligibility gate must classify arid exposed vs negative controls accurately
        self.assertEqual(sites['desierto']['eligibility_and_water_contract']['analog_surface_eligibility'], 'eligible_arid_exposed')
        self.assertEqual(sites['costa']['eligibility_and_water_contract']['analog_surface_eligibility'], 'eligible_arid_exposed')
        self.assertEqual(sites['bosque-oregon']['eligibility_and_water_contract']['analog_surface_eligibility'], 'excluded_dense_canopy')
        self.assertEqual(sites['costa-carolina']['eligibility_and_water_contract']['analog_surface_eligibility'], 'excluded_permanent_water')

    def test_independent_spectral_adapters_share_canonical_complexes(self):
        sites = {s['site_id']: s for s in self.contract['sites']}
        expected_ids = {c['complex_id'] for c in self.spec['spectral_absorption_complexes']}

        crism_1800 = sites['mars-jezero-fan']['spectral_absorption_contract']['by_window']['1800']
        crism_3000 = sites['mars-jezero-fan']['spectral_absorption_contract']['by_window']['3000']
        self.assertEqual(crism_1800['status'], 'measured')
        self.assertEqual(crism_3000['status'], 'insufficient_coverage')
        self.assertEqual(set(crism_1800['complexes'].keys()), expected_ids)

        # At 1800 m (87.23% footprint coverage), CRISM complexes must have measured values; at 3000 m (72.26%), masked to None
        for cid, comp in crism_1800['complexes'].items():
            self.assertIsNotNone(comp['strength_p95'], f'CRISM 1800m {cid} should be measured')
        for cid, comp in crism_3000['complexes'].items():
            self.assertIsNone(comp['strength_p95'], f'CRISM 3000m {cid} should be None due to 72.26% footprint coverage')
            self.assertIsNotNone(comp['unmasked_strength_p95'])

        # EMIT adapter must map onto the exact same 6 complex IDs, exclude organic/synthetic, and enforce n >= 30
        atacama_3000 = sites['atacama-materiales']['spectral_absorption_contract']['by_window']['3000']['primary_scene']
        self.assertEqual(set(atacama_3000['complexes'].keys()), expected_ids)
        self.assertEqual(atacama_3000['group_2_summary']['n_organic_or_synthetic'], 861)
        self.assertEqual(atacama_3000['group_2_summary']['n_qualified_mineral'], 707)

        # Carbonate (n=305), Al-OH (n=211), Hydrated silica/sulfate (n=178) have >=30 samples -> measured
        self.assertEqual(atacama_3000['complexes']['abs_carbonate_2p30_2p50um']['status'], 'measured')
        self.assertEqual(atacama_3000['complexes']['abs_carbonate_2p30_2p50um']['sample_count'], 305)
        self.assertEqual(atacama_3000['complexes']['abs_al_oh_2p20um']['status'], 'measured')
        self.assertEqual(atacama_3000['complexes']['abs_hydrated_sioh_so4_1p9_2p26um']['status'], 'measured')

        # Fe/Mg-OH in Atacama has n=13 (<30) -> insufficient_complex_sample with strength_p95=None
        fe_mg = atacama_3000['complexes']['abs_fe_mg_oh_2p30um']
        self.assertEqual(fe_mg['status'], 'insufficient_complex_sample')
        self.assertIsNone(fe_mg['strength_p95'])
        self.assertIsNotNone(fe_mg['unmasked_strength_p95'])

        # Mafic 1.0 um in EMIT L2B is explicitly unobserved_by_product
        mafic = atacama_3000['complexes']['abs_mafic_fe2_1p0um']
        self.assertEqual(mafic['status'], 'unobserved_by_product')

    def test_on_demand_window_evaluator_modes(self):
        # Local cache hit for Utah
        hit = entrega3.evaluate_on_demand_window_contract(-110.6, 38.6, 3000, mode='auto')
        self.assertEqual(hit['resolution_strategy'], 'verified_local_cache_hit')
        self.assertEqual(hit['matched_site_id'], 'desierto')
        self.assertFalse(hit['requires_full_globe_download'])

        # Uncached coordinate in 'auto' or 'range' mode resolves via HTTP 206 COG range streaming
        stream = entrega3.evaluate_on_demand_window_contract(-75.25, -14.80, 3000, mode='auto')
        self.assertEqual(stream['resolution_strategy'], 'http_206_cog_range_stream')
        self.assertFalse(stream['requires_full_globe_download'])
        self.assertIn('glo30_cog_vsicurl', stream['stages'])

        # Uncached coordinate in strict 'cache' mode defers cleanly without network
        miss = entrega3.evaluate_on_demand_window_contract(-75.25, -14.80, 3000, mode='cache')
        self.assertEqual(miss['resolution_strategy'], 'cache_miss_deferred')

    def test_spatial_partition_and_feature_selection(self):
        part = self.selection['spatial_partition']
        self.assertEqual(part['total_screening_windows'], 973)
        self.assertEqual(part['development_windows_count'] + part['holdout_windows_count'], 973)
        self.assertGreaterEqual(part['min_inter_basin_distance_km'], 250.0)

        dev_blocks = {b['block_id'] for b in part['blocks'] if b['split'] == 'development'}
        hold_blocks = {b['block_id'] for b in part['blocks'] if b['split'] == 'holdout'}
        self.assertTrue(dev_blocks.isdisjoint(hold_blocks), 'Development and holdout blocks must be disjoint')

        # Verify all slope 240m sensor discrepancy reductions are > 50%
        for row in self.selection['sensor_and_scale_stability']:
            self.assertGreater(row['slope_discrepancy_reduction_240m_vs_60m_pct'], 50.0)

    def test_manifest_integrity(self):
        self.assertGreaterEqual(len(self.manifest['files']), 9)
        for item in self.manifest['files']:
            p = ROOT / item['path']
            self.assertTrue(p.is_file(), f"Missing tracked file: {item['path']}")
            self.assertEqual(p.stat().st_size, item['bytes'])
            self.assertEqual(eda.digest(p), item['sha256'])


if __name__ == '__main__':
    unittest.main()
