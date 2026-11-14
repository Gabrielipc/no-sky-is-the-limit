"""Unit and integrity checks for the surface-dimension harmonization pilot."""
import json
from pathlib import Path
import sys
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))
import armonizar_dimensiones_superficie as surf


class SurfaceHarmonizationTests(unittest.TestCase):
    def test_earth_crs_defaults_to_equal_area(self):
        crs = surf.earth_crs((-110.6, 38.6))
        self.assertIn('+proj=laea', crs.to_proj4())

    def test_hls_feature_returns_high_aerosol_filtered_arrays_for_pairing(self):
        # First pixel has normal aerosol (0), second has high aerosol (3 << 6 = 192).
        green = np.array([[2000., 2000.]])
        red = np.array([[1000., 1000.]])
        nir = np.array([[3000., 3000.]])
        swir = np.array([[1500., 1500.]])
        qa = np.array([[0., 192.]])
        inside = np.array([[True, True]])
        profile, selected = surf.hls_feature([green, red, nir, swir, qa], inside, 'HLS.L30.T12SWH.2024184T180142.v2.0')
        self.assertEqual(profile['policies']['0.01_all_aerosol']['ndvi']['n'], 2)
        self.assertEqual(profile['policies']['0.01_exclude_high_aerosol']['ndvi']['n'], 1)
        self.assertTrue(np.isfinite(selected['ndvi'][0, 0]))
        self.assertTrue(np.isnan(selected['ndvi'][0, 1]))

    def test_emit_family_aggregation_unifies_hematite_and_preserves_mixtures(self):
        classes = [
            {'id': 2, 'name': 'fe3+_hematite.fine.gr.gds76', 'label': 'Hematita · 2'},
            {'id': 31, 'name': 'fe3+_hematite.thincoat', 'label': 'Hematita · 31'},
            {'id': 47, 'name': 'fe3+_hematite.nano.BR34b2b', 'label': 'Hematita · 47'},
            {'id': 126, 'name': 'calcite.33+kaol.33+mus-AMXr2', 'label': 'Mezcla de biblioteca: Calcita · 126'},
            {'id': 100, 'name': 'organic_plastic-vinyl', 'label': 'organic_plastic-vinyl · 100'},
        ]
        counts_by_id = {'2': 226, '31': 1810, '47': 25, '126': 5, '100': 10}
        families = surf.aggregate_emit_families(counts_by_id, classes)
        self.assertEqual(families['Hematita'], 2061)
        self.assertEqual(families['Mezcla de biblioteca: Calcita'], 5)
        self.assertEqual(families['Orgánico o sintético'], 10)
        self.assertEqual(surf.shannon_entropy_bits({'Hematita': 2061}), 0.0)
        self.assertGreater(surf.shannon_entropy_bits({'2': 226, '31': 1810, '47': 25}), 0.5)

    def test_select_pilot_values_applies_uniform_coverage_and_sample_thresholds(self):
        synthetic = {
            'cover_and_water': [],
            'optical_and_landsat': [],
            'themis': [{
                'site': 'mars-jezero-fan', 'window_m': 3000, 'path': 'themis.tif',
                'offset_native_m': [0, 0], 'grid_step_m': [100.0, 100.0],
                'inertia': {'n': 930, 'denominator': 930, 'valid_fraction': 1.0, 'p50': 239.76, 'iqr': 32.67},
            }],
            'crism': [
                {
                    'site': 'mars-jezero-fan', 'window_m': 1800, 'paths': ['sr.img', 'in.img'],
                    'in_swath_centers': 9806, 'outside_swath_centers': 394,
                    'indicators': {
                        'D2300': {
                            'mask_0': {'n': 8897, 'denominator': 10200, 'valid_fraction': 8897 / 10200, 'p50': 0.0058, 'p95': 0.0121},
                            'in_swath_mask_0': {'n': 8897, 'denominator': 9806, 'valid_fraction': 8897 / 9806, 'p50': 0.0058, 'p95': 0.0121},
                        },
                    },
                },
                {
                    'site': 'mars-jezero-fan', 'window_m': 3000, 'paths': ['sr.img', 'in.img'],
                    'in_swath_centers': 22074, 'outside_swath_centers': 6316,
                    'indicators': {
                        'D2300': {
                            'mask_0': {'n': 20514, 'denominator': 28390, 'valid_fraction': 20514 / 28390, 'p50': 0.0064, 'p95': 0.0126},
                            'in_swath_mask_0': {'n': 20514, 'denominator': 22074, 'valid_fraction': 20514 / 22074, 'p50': 0.0064, 'p95': 0.0126},
                        },
                    },
                },
            ],
            'emit': [{
                'site': 'desierto', 'window_m': 3000, 'scene': 'EMIT_TEST', 'date': '2023-06-09',
                'unique_source_samples': 2061, 'paths': ['min.nc', 'unc.nc'],
                'groups': {
                    '1': {
                        'sample_ids_valid': 2061, 'no_match_unique': 0,
                        'classes': [{'id': 2, 'name': 'fe3+_hematite', 'label': 'Hematita · 2'}],
                        'sensitivity': {
                            '0.8': {'unique_samples': 2057, 'counts_unique': {'2': 2057}, 'family_counts_unique': {'Hematita': 2057},
                                    'library_entropy_bits': 0.0, 'family_entropy_bits': 0.0},
                            '0.9': {'unique_samples': 10, 'counts_unique': {'2': 10}, 'family_counts_unique': {'Hematita': 10},
                                    'library_entropy_bits': 0.0, 'family_entropy_bits': 0.0},
                        },
                    },
                },
            }],
        }
        pilot = surf.select_pilot_values(synthetic)
        by_key = {(r['feature_id'], r['window_m'], r.get('fit_min')): r for r in pilot['records']}
        self.assertEqual(by_key[('crism_d2300_p95', 1800, None)]['status'], 'measured')
        self.assertAlmostEqual(by_key[('crism_d2300_p95', 1800, None)]['value'], 0.0121)
        self.assertEqual(by_key[('crism_d2300_p95', 3000, None)]['status'], 'insufficient_coverage')
        self.assertIsNone(by_key[('crism_d2300_p95', 3000, None)]['value'])
        self.assertAlmostEqual(by_key[('crism_d2300_p95', 3000, None)]['unmasked_p95'], 0.0126)
        self.assertEqual(by_key[('emit_mineral_family_fraction', 3000, 0.8)]['status'], 'measured')
        self.assertEqual(by_key[('emit_mineral_family_fraction', 3000, 0.8)]['value'], {'Hematita': 1.0})
        self.assertEqual(by_key[('emit_mineral_family_fraction', 3000, 0.9)]['status'], 'insufficient_sample')
        self.assertIsNone(by_key[('emit_mineral_family_fraction', 3000, 0.9)]['value'])

    def test_published_evidence_matches_manifest_and_invariants(self):
        manifest = json.loads((ROOT / 'docs/evidencia-armonizacion-superficie/manifest.json').read_text())
        for item in manifest['files']:
            path = ROOT / item['path']
            self.assertTrue(path.is_file(), item['path'])
            self.assertEqual(surf.eda.digest(path), item['sha256'], item['path'])
        measurements = json.loads((ROOT / 'docs/evidencia-armonizacion-superficie/mediciones.json').read_text())
        crism_3km = next(r for r in measurements['crism'] if r['window_m'] == 3000)
        self.assertEqual(crism_3km['footprint_centers'], 28390)
        self.assertEqual(crism_3km['in_swath_centers'], 22074)
        self.assertEqual(crism_3km['outside_swath_centers'], 6316)


if __name__ == '__main__':
    unittest.main()
