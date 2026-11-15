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

    def test_regional_tiles_are_continuous_and_keep_real_relief(self):
        regional = self.manifest['mola']['regional']
        keys = set(regional['tiles'])
        self.assertEqual(regional['pixels_per_degree'], 128)
        self.assertEqual(regional['source_bytes'], 8847360)
        for key in keys:
            level,x,y = map(int,key.split('/'))
            a=read(ASSETS/f'mola/{key}.png')
            for neighbor,edge,other in [(f'{level}/{x+1}/{y}',a[:,:,-1],(slice(None),slice(None),0)),(f'{level}/{x}/{y+1}',a[:,-1,:],(slice(None),0,slice(None)))]:
                if neighbor in keys:
                    b=read(ASSETS/f'mola/{neighbor}.png')
                    np.testing.assert_array_equal(edge,b[other])
        # Jezero's crater and surroundings must retain hundreds of metres of relief.
        level=8; x=int((77.41+180)/360*2**(level+1)); y=int((90-18.49)/180*2**level)
        a=read(ASSETS/f'mola/{level}/{x}/{y}.png').astype(float)
        z=a[0]*256+a[1]-32768
        self.assertGreater(float(z.max()-z.min()), 500)
