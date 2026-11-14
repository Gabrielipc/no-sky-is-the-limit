"""Scientific edge cases for the exploratory reader, independent of local originals."""
import unittest
import numpy as np
from rasterio.io import MemoryFile
from rasterio.transform import from_origin
from shapely.geometry import box, mapping

from scripts.explorar_fuentes_atlas import (
    hls_mask, landsat_mask, native_crop, physical, read_crop, stats,
)


class SourceExplorationTest(unittest.TestCase):
    def test_jrc_zero_is_observed_and_255_is_missing(self):
        values = physical([0, 40, 100, 255, np.nan], 'jrc', '')
        result = stats(values, 5)
        self.assertEqual(result['n'], 3)
        self.assertEqual(result['min'], 0)
        self.assertEqual(result['valid_fraction'], .6)

    def test_hls_policies_keep_snow_and_water_explicit(self):
        qa = np.array([0, 16, 32, 2, 4, 8, 192, 255, np.nan])
        np.testing.assert_array_equal(hls_mask(qa), [1,1,1,0,0,0,1,0,0])
        np.testing.assert_array_equal(hls_mask(qa, 'legacy'), [1,1,0,0,0,0,1,0,0])
        np.testing.assert_array_equal(hls_mask(qa, 'dry_land'), [1,0,0,0,0,0,1,0,0])

    def test_landsat_snow_and_water_are_not_fill(self):
        qa = np.array([0, 32, 128, 1, 2, 4, 8, 16, np.nan])
        np.testing.assert_array_equal(landsat_mask(qa), [1,0,1,0,0,0,0,0,0])
        np.testing.assert_array_equal(landsat_mask(qa, True), [1,1,1,0,0,0,0,0,0])

    def test_scaling_excludes_fill_before_offset(self):
        a = physical([0, 44947], 'landsat', 'ST_B10')
        self.assertTrue(np.isnan(a[0]))
        self.assertAlmostEqual(a[1], 302.62974494)
        np.testing.assert_allclose(physical([-9999,100], 'landsat','ST_QA'), [np.nan,1],equal_nan=True)

    def test_partial_raster_preserves_whole_footprint_denominator(self):
        with MemoryFile() as mem:
            with mem.open(driver='GTiff',width=2,height=2,count=1,dtype='float32',
                          crs='EPSG:32612',transform=from_origin(0,2,1,1),nodata=-9999) as d:
                d.write(np.ones((2,2), dtype='float32'),1)
            with mem.open() as d:
                win,inside = native_crop(d,mapping(box(-1,0,2,2)), 'EPSG:32612')
                values = read_crop(d,1,win)
                self.assertEqual(int(inside.sum()),6)
                self.assertEqual(stats(values[inside],inside.sum())['n'],4)
                self.assertAlmostEqual(stats(values[inside],inside.sum())['valid_fraction'],2/3)


if __name__=='__main__': unittest.main()
