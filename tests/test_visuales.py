"""Check visual derivatives against the reviewed grids, including orientation."""
import hashlib
import json
from pathlib import Path
import unittest

import numpy as np
import rasterio
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
VISUAL = ROOT / 'frontend/public/analysis'


class VisualDerivativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.layers = json.loads((VISUAL / 'terrain.json').read_text())
        cls.manifest = json.loads((VISUAL / 'manifest.json').read_text())

    def test_visual_assets_are_bound_to_reviewed_results_and_have_valid_identities(self):
        expected = hashlib.sha256((ROOT / 'docs/evidencia-fase-2/resultados.json').read_bytes()).hexdigest()
        self.assertEqual(self.layers['results_sha256'], expected)
        self.assertEqual(self.manifest['scientific_results_sha256'], expected)
        for item in self.manifest['files']:
            path = VISUAL / item['file']
            self.assertEqual(path.stat().st_size, item['bytes'])
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), item['sha256'])
        entries = {e['file']: e for e in json.loads((ROOT / 'docs/evidencia-fase-2/manifest-local.json').read_text())['files']}
        for item in self.layers['inputs']:
            self.assertEqual(item['sha256'], entries[Path(item['file']).name]['sha256'])

    def test_cells_preserve_north_up_order_mask_scale_and_median_relative_height(self):
        for site, scales in self.layers['sites'].items():
            for cell, grid in scales.items():
                for variable, limits in [('slope', 'slope_range'), ('elevation', 'height_range')]:
                    with rasterio.open(ROOT / f'docs/evidencia-fase-2/{site}-{cell}m-{variable}.tif') as src:
                        a = src.read(1, masked=True)
                        self.assertLess(src.transform.e, 0, 'Row zero must be the northern edge')
                        self.assertEqual((grid['rows'], grid['columns']), a.shape)
                        if variable == 'elevation':
                            a = a - np.ma.median(a)
                        expected = a.filled(np.nan)
                        actual = np.array([np.nan if v is None else v for v in grid[variable]]).reshape(a.shape)
                        np.testing.assert_allclose(actual, expected, atol=.000051, rtol=0, equal_nan=True)
                        lo, hi = self.layers[limits]
                        self.assertGreaterEqual(float(a.min()), lo)
                        self.assertLessEqual(float(a.max()), hi)

    def test_regional_backgrounds_have_exact_catalog_extents_and_are_only_context(self):
        cfg = json.loads((ROOT / 'specs/search/busqueda-regional-v1.json').read_text())
        self.assertEqual(self.manifest['regional_source'], next(s for s in cfg['sources'] if s['id'] == 'mn75_grd'))
        for background in self.manifest['backgrounds']:
            area = next(a for a in cfg['areas'] if a['id'] == background['area_id'])
            self.assertEqual(background['bbox'], area['bbox'])
            self.assertIn('not a measured layer', background['role'])
            with Image.open(VISUAL / background['file']) as image:
                self.assertEqual(image.size, (512, 512))
                self.assertEqual(image.mode, 'RGBA')


if __name__ == '__main__':
    unittest.main()
