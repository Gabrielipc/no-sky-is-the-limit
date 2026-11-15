"""Análogos en Nicaragua: geometría, densificación, deduplicación y el precálculo versionado."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))

import analogos_nicaragua as nic  # noqa: E402


class GeometryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.boundary = nic.load_boundary()
        cls.volcanoes = json.loads(nic.VOLCANOES_PATH.read_text(encoding='utf-8'))['volcanoes']
        cls.sites = json.loads(nic.SITES_PATH.read_text(encoding='utf-8'))['sites']

    def test_haversine_one_degree_of_latitude(self):
        self.assertAlmostEqual(nic.haversine_km(-86, 12, -86, 13), 111.2, delta=0.2)

    def test_boundary_keeps_nicaragua_and_drops_neighbours(self):
        self.assertTrue(nic.inside(self.boundary, -86.25, 12.13))   # Managua
        self.assertTrue(nic.inside(self.boundary, -86.70, 12.506))  # Cerro Negro
        self.assertFalse(nic.inside(self.boundary, -87.21, 14.07))  # Tegucigalpa, Honduras
        self.assertFalse(nic.inside(self.boundary, -84.09, 9.93))   # San José, Costa Rica

    def test_every_volcano_and_known_site_is_inside(self):
        for item in self.volcanoes + self.sites:
            self.assertTrue(nic.inside(self.boundary, item['longitude'], item['latitude']), item['name'])

    def test_known_sites_cite_declared_sources(self):
        sources = json.loads(nic.SITES_PATH.read_text(encoding='utf-8'))['sources']
        for site in self.sites:
            self.assertTrue(site['sources'])
            for sid in site['sources']:
                self.assertIn(sid, sources)
                self.assertTrue(sources[sid]['url'].startswith('https://'))

    def test_nearest_volcano(self):
        v, d = nic.nearest_volcano(-86.70, 12.51, self.volcanoes)
        self.assertEqual(v['name'], 'Negro, Cerro')
        self.assertLess(d, 1)

    def test_dense_sites_cover_known_sites_summits_and_a_grid_inside_the_radius(self):
        sites = nic.dense_sites(self.boundary, self.volcanoes, self.sites, radius_km=5, stride_m=3000)
        ids = {s['region_id'] for s in sites}
        for s in self.sites:
            self.assertIn(f"{nic.DENSE_PREFIX}-sitio-{s['id']}", ids)
        for v in self.volcanoes:
            self.assertIn(f"{nic.DENSE_PREFIX}-volcan-{v['id']}", ids)
        grid = [s for s in sites if s['label'] == 'grid']
        self.assertTrue(grid)
        for s in grid:
            _, d = nic.nearest_volcano(s['longitude'], s['latitude'], self.volcanoes)
            self.assertLessEqual(d, 5.1)
            self.assertTrue(nic.inside(self.boundary, s['longitude'], s['latitude']))
            self.assertEqual(s['x'] % 3000, 0)
            self.assertEqual(s['y'] % 3000, 0)

    def test_dedupe_keeps_atlas_window_and_site_windows(self):
        atlas = [{'region_id': 'a', 'longitude': -86.5, 'latitude': 12.4}]
        dense = [{'region_id': 'g1', 'source': 'grid', 'longitude': -86.5001, 'latitude': 12.4001},
                 {'region_id': 'g2', 'source': 'grid', 'longitude': -86.45, 'latitude': 12.4},
                 {'region_id': 's', 'source': 'known_site', 'longitude': -86.5, 'latitude': 12.4}]
        self.assertEqual([w['region_id'] for w in nic.dedupe_dense(dense, atlas)], ['g2', 's'])

    def test_global_rank(self):
        import numpy as np
        scores = np.array([0.1, 0.2, 0.3])
        self.assertEqual(nic.global_rank(scores, 0.05), 1)
        self.assertEqual(nic.global_rank(scores, 0.25), 3)
        self.assertIsNone(nic.global_rank(scores, None))


@unittest.skipUnless(nic.OUT_PATH.is_file(), 'sin precálculo')
class PublishedOutputTest(unittest.TestCase):
    """El JSON que lee la vista: columnas alineadas, sin NaN y con lo que la interfaz promete."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.data = json.loads(nic.OUT_PATH.read_text(encoding='utf-8'))

    def test_rankings_are_aligned_with_windows(self):
        n = len(self.data['windows']['rows'])
        self.assertGreater(n, 1000)
        for row in self.data['windows']['rows']:
            self.assertEqual(len(row), len(self.data['windows']['columns']))
        for rid, ranking in self.data['rankings'].items():
            for key in ('score', 'coverage', 'global_rank'):
                self.assertEqual(len(ranking[key]), n, f'{rid}.{key}')

    def test_references_include_planets_and_known_sites(self):
        ids = {r['id'] for r in self.data['references']}
        self.assertTrue(set(nic.PLANETARY_REFERENCES) <= ids)
        self.assertIn('sitio:cerro-negro', ids)

    def test_volcanic_zone_is_densified(self):
        cols = self.data['windows']['columns']
        windows = [dict(zip(cols, r)) for r in self.data['windows']['rows']]
        volcanic = [w for w in windows if w['volcanic']]
        self.assertGreater(len(volcanic), 500)
        self.assertTrue(all(w['source'] != 'grid' or w['volcanic'] for w in windows))
        ids = {w['region_id'] for w in windows}
        self.assertEqual(len(ids), len(windows))

    def test_water_and_reference_neighbourhood_are_not_ranked(self):
        cols = self.data['windows']['columns']
        windows = [dict(zip(cols, r)) for r in self.data['windows']['rows']]
        for rid, ranking in self.data['rankings'].items():
            for w, s in zip(windows, ranking['score']):
                if w['water_dominated']:
                    self.assertIsNone(s)
                if s is not None:
                    self.assertGreaterEqual(s, 0)
        site = next(s for s in self.data['known_sites']['sites'] if s['id'] == 'cerro-negro')
        cn = self.data['rankings']['sitio:cerro-negro']['score']
        for w, s in zip(windows, cn):
            if nic.haversine_km(w['longitude'], w['latitude'], site['longitude'], site['latitude']) < nic.SELF_EXCLUSION_KM:
                self.assertIsNone(s)


if __name__ == '__main__':
    unittest.main()
