"""Tests for footprint shape/organisation descriptors of the topographic contract."""
from __future__ import annotations

import math
import unittest

import numpy as np

from pipelines import etl_extractors as extractors

CELL = 30
SIZE = (3000 + 2 * 720) // CELL
COORDS = (np.arange(SIZE, dtype='float64') - (SIZE - 1) / 2) * CELL
X, Y = np.meshgrid(COORDS, -COORDS)  # row 0 is north
LAND = np.ones((SIZE, SIZE), dtype=bool)


def features(elevation: np.ndarray) -> dict:
    return extractors.compute_topography_features(elevation, LAND, cell_m=CELL, window_m=3000)


class TestShapeFeatures(unittest.TestCase):
    def test_tilted_plane(self) -> None:
        f = features(X * math.tan(math.radians(10.0)))
        self.assertAlmostEqual(f['hypsometric_integral'], 0.5, places=2)
        self.assertAlmostEqual(f['elevation_skew_p95_p05'], 0.0, places=6)
        self.assertAlmostEqual(f['aspect_240m_resultant_length'], 1.0, places=6)
        self.assertEqual(f['slope_240m_gt15_fraction'], 0.0)
        self.assertEqual(f['slope_240m_gt25_fraction'], 0.0)

    def test_steep_plane_fractions(self) -> None:
        f = features(X * math.tan(math.radians(20.0)))
        self.assertEqual(f['slope_240m_gt15_fraction'], 1.0)
        self.assertEqual(f['slope_240m_gt25_fraction'], 0.0)

    def test_bowl_has_low_integral_and_positive_skew(self) -> None:
        r = np.hypot(X, Y)
        bowl = 1e-4 * r ** 2  # flat floor, steep rim: crater/playa-like
        f = features(bowl)
        self.assertLess(f['hypsometric_integral'], 0.5)
        self.assertGreater(f['elevation_skew_p95_p05'], 0.0)
        # A symmetric bowl faces every direction equally.
        self.assertLess(f['aspect_240m_resultant_length'], 0.05)

    def test_dome_has_high_integral_and_negative_skew(self) -> None:
        dome = -1e-4 * np.hypot(X, Y) ** 2
        f = features(dome)
        self.assertGreater(f['hypsometric_integral'], 0.5)
        self.assertLess(f['elevation_skew_p95_p05'], 0.0)

    def test_fan_is_more_organised_than_isotropic_bumps(self) -> None:
        fan = -0.02 * Y - 2e-6 * X ** 2  # descends south, gently convex across: a fan apron
        bumps = 20.0 * np.sin(X / 300.0) * np.sin(Y / 300.0)
        self.assertGreater(features(fan)['aspect_240m_resultant_length'], 0.9)
        self.assertLess(features(bumps)['aspect_240m_resultant_length'], 0.2)

    def test_flat_window_reports_no_elevation_shape_or_aspect(self) -> None:
        f = features(np.zeros((SIZE, SIZE)) + 0.0005 * X)
        self.assertIsNone(f['hypsometric_integral'])
        self.assertIsNone(f['elevation_skew_p95_p05'])
        self.assertIsNone(f['aspect_240m_resultant_length'])
        self.assertEqual(f['slope_240m_gt15_fraction'], 0.0)

    def test_slope_matches_gradient(self) -> None:
        z = 0.3 * X + 0.1 * Y
        dx, dy = extractors.gradient_fixed_base(z, CELL, 240)
        valid = np.isfinite(dx)
        self.assertTrue(np.allclose(dx[valid], 0.3))
        self.assertTrue(np.allclose(dy[valid], 0.1))
        self.assertTrue(np.allclose(extractors.slope_fixed_base(z, CELL, 240)[valid],
                                    math.degrees(math.atan(math.hypot(0.3, 0.1)))))


if __name__ == '__main__':
    unittest.main()
