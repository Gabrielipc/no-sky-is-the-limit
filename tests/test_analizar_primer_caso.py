"""Controles científicos mínimos de máscaras, escala y magnitudes."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

import numpy as np
import rasterio
from rasterio.transform import from_origin

spec = importlib.util.spec_from_file_location('first_case', Path(__file__).resolve().parents[1] / 'scripts/analizar_primer_caso.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class TerrainTests(unittest.TestCase):
    def test_plane_known_slope_and_vertical_offset(self):
        y, x = np.mgrid[:12, :12] * 60
        z = .1*x + .2*y
        expected = np.degrees(np.arctan(np.hypot(.1,.2)))
        np.testing.assert_allclose(m.slopes(z,60), expected, atol=1e-12)
        np.testing.assert_allclose(m.slopes(z+10000,60), expected, atol=1e-12)
        a = m.describe(z,m.slopes(z,60),[0,90])
        b = m.describe(z+10000,m.slopes(z+10000,60),[0,90])
        self.assertAlmostEqual(a['relief_p95_p5_m'], b['relief_p95_p5_m'])

    def test_zero_elevation_valid_but_invalid_center_masks_slope(self):
        z = np.zeros((5,5))
        np.testing.assert_array_equal(m.slopes(z,60),0)
        z[2,2] = np.nan
        slopes=m.slopes(z,60)
        self.assertEqual(int(np.isnan(slopes).sum()),5)

    def test_missing_data_are_not_renormalized_to_complete_support(self):
        data=np.arange(16,dtype=float).reshape(4,4)
        valid=np.ones_like(data,dtype=bool); valid[0,0]=False
        src=from_origin(0,4,1,1); dst=from_origin(0,4,2,2)
        a,s=m.aggregate(data,valid,src,'EPSG:3857','EPSG:3857',dst,(2,2),1e-6)
        self.assertAlmostEqual(s[0,0],.75)
        self.assertTrue(np.isnan(a[0,0]))
        self.assertAlmostEqual(a[1,1],12.5)
        _,complete=m.aggregate(data,np.ones_like(valid),src,'EPSG:3857','EPSG:3857',dst,(2,2),1e-6)
        np.testing.assert_array_equal(complete,1)

    def test_all_missing_metrics_are_unknown(self):
        d=m.describe(np.full((3,3),np.nan),np.full((3,3),np.nan),[0,90])
        self.assertIsNone(d['relief_p95_p5_m'])
        self.assertIsNone(d['slope_quantiles_deg'])
        self.assertEqual(d['status'],'insufficient_data')

    def test_same_terrain_is_invariant_to_aggregation_scale(self):
        # Block averages of a plane preserve its gradient at 60 and 120 m.
        y,x=np.mgrid[:24,:24]*30
        z=.1*x+.2*y
        for cell in [60,120]:
            n=720//cell
            a,s=m.aggregate(z,np.ones_like(z,dtype=bool),from_origin(0,720,30,30),
                            'EPSG:3857','EPSG:3857',from_origin(0,720,cell,cell),(n,n),1e-6)
            np.testing.assert_allclose(m.slopes(a,cell),np.degrees(np.arctan(np.hypot(.1,.2))),atol=1e-10)

    def test_mismatched_original_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'wrong.img'; p.write_bytes(b'abc')
            with self.assertRaisesRegex(ValueError,'no se sobrescribe'):
                m.acquire({'input':str(p),'bytes':3,'sha256':'wrong'},True)
            self.assertEqual(p.read_bytes(),b'abc')

    def test_window_outside_source_retains_invalid_padding(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'small.tif'
            with rasterio.open(p,'w',driver='GTiff',width=3,height=3,count=1,
                               dtype='int16',crs='EPSG:4326',transform=from_origin(-.0005,.0005,.0003,.0003),nodata=-32768) as ds:
                ds.write(np.ones((3,3),dtype='int16'),1)
            site={'id':'partial','body':'Earth','latitude':0,'longitude':0,'input':str(p),
                  'product_id':'small','url':'unused','vertical_reference':'test','limitations':[]}
            data,valid,*_=m.read_crop(p,site,{'window_m':1800,'margin_m':240})
            self.assertTrue(valid.any())
            self.assertTrue((~valid).any())
            self.assertTrue(np.isnan(data[~valid]).all())


if __name__=='__main__':
    unittest.main()
