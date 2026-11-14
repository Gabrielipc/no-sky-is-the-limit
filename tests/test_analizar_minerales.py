"""Categorical geolocation, fill values and provenance checks for local EMIT."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

import h5py
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('mineral_analysis', ROOT / 'scripts/analizar_minerales.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class MineralAnalysisTests(unittest.TestCase):
    def test_library_mixtures_are_never_presented_as_pure_minerals(self):
        self.assertIn('Mezcla de biblioteca', m.mineral_label('calcite+0.2Na-mont', 225))
        self.assertNotIn('Mezcla', m.mineral_label('fe3+_hematite.thincoat', 31))

    def test_glt_is_one_based_and_missing_or_outside_never_reads_last_pixel(self):
        raw = np.array([[0, 12], [21, 22]])
        ix = np.array([[1, 2, 0, 3]])
        iy = np.array([[1, 2, 1, 1]])
        result = m.apply_glt(raw, ix, iy)
        np.testing.assert_allclose(result, [[0, 22, np.nan, np.nan]], equal_nan=True)
        with self.assertRaisesRegex(ValueError, 'negativos'):
            m.apply_glt(raw, np.array([[-1]]), np.array([[1]]))

    def test_reader_masks_fill_before_scaling_and_preserves_no_match_zero(self):
        with tempfile.TemporaryDirectory() as folder:
            with h5py.File(Path(folder) / 'test.nc', 'w') as file:
                dataset = file.create_dataset('values', data=np.array([[0., -9999., 4.], [6., 8., 10.]]))
                dataset.attrs['_FillValue'] = [-9999.]
                ix, iy = np.array([[1, 2, 3], [1, 2, 3]]), np.array([[1, 1, 1], [2, 2, 2]])
                inside = np.array([[True, True, True], [True, False, True]])
                a = m.read_variable(dataset, ix, iy, inside)
                np.testing.assert_allclose(a, [[0, np.nan, 4], [6, np.nan, 10]], equal_nan=True)
                dataset.attrs['scale_factor'] = [.5]
                dataset.attrs['add_offset'] = [1.]
                np.testing.assert_allclose(m.read_variable(dataset, ix, iy, inside), [[1, np.nan, 3], [4, np.nan, 6]], equal_nan=True)

    def test_published_grids_keep_groups_separate_and_fill_distinct_from_no_match(self):
        result = json.loads((ROOT / 'docs/evidencia-minerales/resultados.json').read_text())
        for site in result['sites']:
            grid = site['grid']
            total = grid['rows'] * grid['columns']
            self.assertEqual(len(grid['inside']), total)
            self.assertEqual(sum(grid['inside']), grid['footprint_cells'])
            self.assertLessEqual(grid['unique_raw_samples'], grid['glt_cells'])
            for key, group in grid['groups'].items():
                self.assertEqual(len(group['ids']), total)
                self.assertEqual(sum(group['usable']), group['matched_cells'])
                self.assertEqual(sum(i == 0 for i in group['ids']), group['no_match_cells'])
                self.assertTrue(all(c['group'] == int(key) for c in group['classes']))
                self.assertTrue(all(i is None or i >= 0 for i in group['ids']))
        atacama = next(s for s in result['sites'] if s['id'] == 'earth-atacama')
        self.assertGreater(atacama['grid']['groups']['2']['no_match_cells'], 0)
        self.assertTrue(any(not a['selected'] and a['available_classification_cells'] == 0 for a in atacama['scene_audits']))

    def test_published_sources_match_original_hashes_and_bad_identity_does_not_open(self):
        cfg = json.loads(m.CONFIG.read_text())
        for scene in cfg['scenes']:
            for key in ('mineral', 'uncertainty'):
                m.verify(ROOT / scene[key]['input'], scene[key])
        bad = {**cfg['scenes'][0], 'mineral': {**cfg['scenes'][0]['mineral'], 'sha256': 'wrong'}}
        with self.assertRaisesRegex(ValueError, 'Identidad'):
            m.read_scene(bad, {'coordinates': []})


if __name__ == '__main__':
    unittest.main()
