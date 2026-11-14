"""Published surface assets must preserve geographic seams, identity and height masks."""
import hashlib
import json
from pathlib import Path
import unittest
import warnings
import numpy as np
import rasterio

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / 'frontend/public/surface'


def read(path):
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', rasterio.errors.NotGeoreferencedWarning)
        with rasterio.open(path) as src:
            return src.read()


class SurfaceAssetsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads((ASSETS/'manifest.json').read_text())

    def test_published_identities_and_real_source_crops(self):
        for entry in self.manifest['files']:
            data = (ASSETS/entry['file']).read_bytes()
            self.assertEqual(len(data), entry['bytes'])
            self.assertEqual(hashlib.sha256(data).hexdigest(), entry['sha256'])
        for site in self.manifest['sites']:
            self.assertEqual(hashlib.sha256((ROOT/site['source_file']).read_bytes()).hexdigest(), site['source_sha256'])

    def test_tiles_share_edges_and_wrap_at_antimeridian(self):
        for level in range(self.manifest['mola']['max_level']+1):
            nx, ny = 2**(level+1), 2**level
            for y in range(ny):
                for x in range(nx):
                    a=read(ASSETS/f'mola/{level}/{x}/{y}.png')
                    b=read(ASSETS/f'mola/{level}/{(x+1)%nx}/{y}.png')
                    np.testing.assert_array_equal(a[:,:,-1], b[:,:,0])
                    if y+1<ny:
                        c=read(ASSETS/f'mola/{level}/{x}/{y+1}.png')
                        np.testing.assert_array_equal(a[:,-1,:], c[:,0,:])

    def test_local_height_encoding_and_texture_mask(self):
        for site in self.manifest['sites']:
            gray=read(ASSETS/site['heightmap'])[0]
            self.assertEqual(gray.shape,(site['height'],site['width']))
            valid=gray!=site['nodata']
            self.assertAlmostEqual(float(valid.mean()),site['coverage'])
            z=gray[valid].astype(float)*site['scale_m']+site['offset_m']
            self.assertAlmostEqual(float(z.min()),site['min_m'],places=3)
            self.assertAlmostEqual(float(z.max()),site['max_m'],places=3)
            np.testing.assert_array_equal(read(ASSETS/site['texture'])[3]>0,valid)
            self.assertEqual((site['width']-1)*site['cell_m'],1800)
            self.assertLess(site['scale_m']/2,1)
