"""Analytic controls for shape, support and physical-unit comparisons."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
import numpy as np
from pyproj import CRS
import rasterio
from rasterio.transform import from_origin

spec = importlib.util.spec_from_file_location('surface_analysis', Path(__file__).resolve().parents[1]/'scripts/analizar_dimensiones.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class SurfaceTests(unittest.TestCase):
    def test_inclined_plane_has_zero_roughness_position_and_curvature(self):
        y, x = np.mgrid[:21, :21]*60
        for offset in (0, 100000):
            arrays = m.geometry_descriptors(.1*x+.2*y+offset, 60, 120)
            for values in arrays.values():
                np.testing.assert_allclose(values[3:-3, 3:-3], 0, atol=1e-9)

    def test_paraboloid_has_known_laplacian_tpi_and_plane_residual(self):
        y, x = (np.mgrid[:15, :15]-7)*60
        a = .0001
        arrays = m.geometry_descriptors(a*(x*x+y*y), 60, 60)
        self.assertAlmostEqual(arrays['laplacian'][7, 7], 4*a)
        self.assertAlmostEqual(arrays['topographic_position'][7, 7], -2*a*(2*60**2/3))
        expected_rms = a*np.sqrt(2*np.var(np.array([-60, 0, 60])**2))
        self.assertAlmostEqual(arrays['roughness_rms'][7, 7], expected_rms)

    def test_hole_invalidates_full_neighborhood_and_axial_curvature(self):
        z = np.zeros((21, 21)); z[10, 10] = np.nan
        arrays = m.geometry_descriptors(z, 60, 120)
        for key in ('roughness_rms', 'topographic_position'):
            self.assertEqual(np.isnan(arrays[key][2:-2, 2:-2]).sum(), 25)
            self.assertTrue(np.isnan(arrays[key][:2]).all())
        self.assertEqual(np.isnan(arrays['laplacian'][1:-1, 1:-1]).sum(), 5)

    def test_no_data_and_insufficient_support_never_become_matches(self):
        a = np.full((10, 10), np.nan)
        self.assertIsNone(m.describe(a, .95)['quantiles'])
        self.assertIsNone(m.compare(a, a, .95)['wasserstein'])
        a = np.zeros((10, 10)); a.flat[:6] = np.nan
        result = m.compare(a, np.zeros_like(a), .95)
        self.assertEqual(result['status'], 'insufficient_quality')
        self.assertIsNone(result['wasserstein'])
        self.assertIsNone(result['candidate_minus_reference_median'])

    def test_wasserstein_retains_units_and_signed_delta(self):
        a = np.arange(25).reshape(5, 5).astype(float)
        result = m.compare(a, a-3, .95)
        self.assertEqual(result['wasserstein'], 3)
        self.assertEqual(result['candidate_minus_reference_median'], -3)
        self.assertEqual(m.compare(a, a, .95)['wasserstein'], 0)

    def test_neighborhood_keeps_physical_radius_at_both_scales(self):
        for cell in (60, 120):
            yy, xx = np.mgrid[:25, :25]*cell
            values = m.geometry_descriptors(.2*xx+.1*yy, cell, 360)
            radius = 360//cell
            self.assertEqual(np.isfinite(values['roughness_rms']).sum(), (25-2*radius)**2)
        with self.assertRaises(ValueError):
            m.geometry_descriptors(np.zeros((10, 10)), 120, 350)

    def test_thermal_preserves_native_sampling_and_excludes_zero_nodata(self):
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder)/'thermal.tif'
            radius = 3396190
            crs = CRS.from_proj4(f'+proj=eqc +R={radius} +units=m')
            a = np.full((3, 3), 250, dtype='float32'); a[1, 1] = 0
            with rasterio.open(p, 'w', driver='GTiff', width=3, height=3, count=1, dtype='float32',
                               crs=crs, transform=from_origin(0, 300, 100, 100), nodata=0) as ds:
                ds.write(a, 1)
            ts = dict(input=str(p), product_id='test', url='unused', doi='unused', license='test', units='TI',
                      bytes=p.stat().st_size, sha256=m.terrain.digest(p), nodata=0, sphere_radius_m=radius)
            delta = np.degrees(300/radius)
            area = {'geometry': {'type': 'Polygon', 'coordinates': [[[0, 0], [delta, 0], [delta, delta], [0, delta], [0, 0]]]}}
            result = m.inspect_thermal(ts, area, .95)
            self.assertEqual(result['summary']['valid_cells'], 8)
            self.assertEqual(result['summary']['total_cells'], 9)
            self.assertEqual(result['summary']['quantiles']['p50'], 250)
            self.assertEqual(result['status'], 'insufficient_quality')
            self.assertEqual(result['native_step_projected_m'], [100, 100])
            self.assertEqual(sum(v is not None for v in result['grid']['values']), 8)
            ts['sha256'] = 'wrong'
            with self.assertRaisesRegex(ValueError, 'identidad'):
                m.inspect_thermal(ts, area, .95)

    def test_invalid_margin_rejected_before_reading_rasters(self):
        config = dict(neighborhood_radius_m=360, margin_m=240, window_m=1800, scales_m=[60, 120],
                      min_coverage=.95, support_tolerance=1e-6)
        with self.assertRaises(ValueError):
            m.validate_config(config)


if __name__ == '__main__':
    unittest.main()
