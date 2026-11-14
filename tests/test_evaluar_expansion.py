"""Boundaries for the conditional source/scale expansion."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import rasterio
from rasterio.transform import from_origin

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import evaluar_expansion as m


class ExpansionScienceTests(unittest.TestCase):
    def test_stratified_selection_is_deterministic_and_contains_excluded_controls(self):
        release = json.loads((m.PREVIOUS/'candidatas.json').read_text())
        cfg = m.load_config()
        local = lambda plan: all(t['filename'] in ('N38W111.tif', 'S24W068.tif') for t in plan['tiles'])
        a, strata = m.select_cohort(release, cfg, local)
        b, strata_b = m.select_cohort(release, cfg, local)
        self.assertEqual(a, b)
        self.assertEqual(strata, strata_b)
        self.assertEqual(len(a), 10)
        self.assertEqual(sum(s['role'] == 'control' for s, _ in a), 3)
        self.assertEqual(sum(s['pool_count'] for s in strata), 970)
        self.assertEqual(len(strata), 6)
        for stratum in strata:
            self.assertEqual(len(stratum['selected_ids']), 1)
        self.assertIn('utah-010-007', [s['id'] for s, _ in a])
        with self.assertRaises(ValueError):
            m.select_cohort(release, {**cfg, 'max_candidates': 2}, local)

    def test_source_comparison_zero_signed_deltas_and_inclusive_thresholds(self):
        old = {'cell_m': 300, 'elevation_coverage': 1, 'slope_coverage': 1,
               'slope_wasserstein_deg': 2, 'candidate_minus_reference_relief_m': -60}
        new = {**old, 'slope_wasserstein_deg': 2.1, 'candidate_minus_reference_relief_m': -59}
        profile = {'base': {'slope_distance_max_deg': 2, 'abs_relief_difference_max_m': 60}}
        arrays = {300: np.array([0., 1., 2.])}
        contrast = m.source_contrast([old], [new], arrays, arrays, [old], profile, .95)[0]
        self.assertEqual(contrast['candidate_source_wasserstein_deg'], 0)
        self.assertAlmostEqual(contrast['slope_distance_delta_deg'], .1)
        self.assertEqual(contrast['relief_difference_delta_m'], 1)
        self.assertTrue(contrast['filter_decisions']['base']['changed'])
        self.assertEqual(contrast['filter_decisions']['base']['gmted_reasons'], [])

    def test_insufficient_reference_or_candidate_is_not_a_filter_change(self):
        metric = {'cell_m': 600, 'elevation_coverage': 1, 'slope_coverage': 1,
                  'slope_wasserstein_deg': 0, 'candidate_minus_reference_relief_m': 0}
        profiles = {'base': {'slope_distance_max_deg': 2, 'abs_relief_difference_max_m': 60}}
        arrays = {600: np.array([0.])}
        for candidate, ref in (({**metric, 'slope_coverage': .94}, metric),
                               (metric, {**metric, 'elevation_coverage': .94}),
                               ({**metric, 'slope_wasserstein_deg': None}, metric)):
            row = m.source_contrast([metric], [candidate], arrays, arrays, [ref], profiles, .95)[0]
            self.assertIsNone(row['slope_distance_delta_deg'])
            self.assertIsNone(row['candidate_source_wasserstein_deg'])
            self.assertIsNone(row['filter_decisions']['base']['changed'])

    def test_detail_plan_covers_coarsest_stencil(self):
        cfg = m.load_config()
        release = json.loads((m.PREVIOUS/'candidatas.json').read_text())
        site = next(s for s in release['candidates'] if s['id'] == 'utah-010-007')
        plan = m.detail_plan(site, cfg)
        old = site['detail_plan']['bbox']
        w, s, e, n = plan['bbox']
        self.assertTrue(w < old[0] and s < old[1] and e > old[2] and n > old[3])
        self.assertEqual(plan['margin_m'], 600)

    def test_native_pixel_origin_and_fully_covered_slope_are_preserved(self):
        # A planar native SRTM grid should retain complete support on all scales.
        site = {'body': 'Earth', 'latitude': 38.6, 'longitude': -110.6}
        cfg = {**m.regional.load_config(), **m.load_config()}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'srtm.tif'
            transform = from_origin(-111-1/7200, 39+1/7200, 1/3600, 1/3600)
            with rasterio.open(path, 'w', driver='GTiff', height=3601, width=3601,
                               count=1, dtype='int16', crs='EPSG:4326', transform=transform,
                               nodata=-32768, compress='deflate') as ds:
                ds.write(np.zeros((3601, 3601), dtype='int16'), 1)
            crop = m.read_detail([path], site, cfg)
            self.assertAlmostEqual((crop[2].c-transform.c)/transform.a,
                                   round((crop[2].c-transform.c)/transform.a), places=7)
            stats, _ = m.regional.measurements(crop, cfg)
            for metric in stats:
                self.assertEqual(metric['slope_coverage'], 1)
                self.assertEqual(metric['relief_p95_p5_m'], 0)
            with self.assertRaises(ValueError):
                m.read_detail([path, path], site, cfg)

    def test_changed_upstream_fails_before_any_download(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder/'manifest-local.json').write_text(json.dumps({'files': [
                {'file': '../../specs/search/busqueda-regional-v1.json', 'bytes': 1, 'sha256': 'bad'}]}))
            with patch.object(m, 'PREVIOUS', folder), patch('urllib.request.urlopen') as network:
                with self.assertRaises((OSError, ValueError)):
                    m.run()
                network.assert_not_called()


if __name__ == '__main__':
    unittest.main()
