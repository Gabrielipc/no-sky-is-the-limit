import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from backend.app import atlas_store as store
from pipelines import atlas_sources as sources, atlas_topography as topography
from scripts.atlas30 import SCHEMA, batches


class AtlasTopographyTests(unittest.TestCase):
    def test_fixed_zones_and_antimeridian(self):
        self.assertEqual(topography.owner(-180, 0), 32601)
        self.assertEqual(topography.owner(179.999, 10), 32660)
        self.assertEqual(topography.owner(0, 84), 32661)
        self.assertEqual(topography.owner(0, -81), 32761)
        self.assertEqual(topography.tile_keys(topography.split((179.5, 0, -179.5, 1)), 1),
                         [(0, -180), (0, 179)])
        for batch in topography.benchmark_batches():
            sites = list(topography.windows(batch, 10_000))
            self.assertEqual(len({row['region_id'] for row in sites}), len(sites))
            self.assertTrue(all(topography.owner(row['longitude'], row['latitude']) == batch.zone
                                for row in sites))

    def test_flat_zero_is_a_measurement_and_missing_support_excludes(self):
        size = (topography.WINDOW + topography.HALO * 2) // topography.CELL
        elevation = np.zeros((size, size))
        land = np.ones_like(elevation, dtype=bool)
        flat, arrays = topography.metrics(elevation, land, topography.CELL)
        self.assertEqual(arrays['slope'].shape, (100, 100))
        self.assertEqual(flat['relief_m'], 0)
        self.assertEqual(flat['roughness_m'], 0)
        self.assertEqual(sum(flat['slope_histogram']), 10_000)
        elevation[:, size // 2] = np.nan
        missing, _ = topography.metrics(elevation, land, topography.CELL)
        self.assertAlmostEqual(missing['valid_elevation'], .99)
        self.assertLess(missing['valid_roughness'], .95)
        self.assertIsNone(missing['relief_m'])

    def test_mosaic_preserves_zero_and_does_not_fill_gap(self):
        rasters = Mock()
        rasters.sample.side_effect = [
            [(np.array([[0., np.nan, np.nan]]), np.array([[1., 0., 0.]]))],
            [(np.array([[np.nan, 99., 10.]]), np.array([[0., .5, 1.]]))],
        ]
        entries = [{'id': 'west'}, {'id': 'east'}]
        result, ids = topography.mosaic(rasters, entries, 32601, [], None, (1, 3), None)
        np.testing.assert_equal(result, np.array([[0., np.nan, 10.]]))
        self.assertEqual(ids, ['east', 'west'])

    def test_world_plan_reuses_cached_order_until_mask_changes(self):
        sample = list(topography.benchmark_batches())[:3]
        with tempfile.TemporaryDirectory() as tmp, patch.object(sources, 'MANIFESTS', Path(tmp)), \
                patch.object(sources, 'local_identity', return_value={'sha256': 'first'}) as identity, \
                patch.object(topography, 'Land'), patch.object(topography, 'world_batches', return_value=sample) as generate:
            first = batches('world')
            self.assertEqual([b.id for b in first], [b.id for b in batches('world')])
            generate.assert_called_once()
            identity.return_value = {'sha256': 'next'}
            self.assertEqual([b.id for b in first], [b.id for b in batches('world')])
            self.assertEqual(generate.call_count, 2)

    def test_fetch_distinguishes_new_verified_bytes_from_reuse(self):
        asset = sources.asset('glo30', 'fixture.tif', 'https://example.test/fixture.tif')
        reused = {**asset, 'status': 'verified_local', 'bytes': 8}
        pending = {**asset, 'status': 'available', 'bytes': 12}
        with tempfile.TemporaryDirectory() as tmp, patch.object(sources, 'CACHE', Path(tmp)), \
                patch.object(sources, 'local_identity', side_effect=[reused, None]):
            old, new = sources.fetch([asset, asset], 100, inspect=lambda _: pending,
                                     download=lambda entry: {**entry, 'status': 'verified_local'})
        self.assertNotIn('newly_verified_bytes', old)
        self.assertEqual(new['newly_verified_bytes'], 12)

    def test_budget_stops_before_transfer(self):
        entry = sources.asset('glo30', 'fixture.tif', 'https://example.test/fixture.tif')
        with tempfile.TemporaryDirectory() as tmp, patch.object(sources, 'CACHE', Path(tmp)), \
                patch.object(sources, 'remote_identity', return_value={**entry, 'status': 'available', 'bytes': 8}), \
                patch.object(sources, 'transfer') as transfer:
            with self.assertRaisesRegex(ValueError, 'presupuesto'):
                sources.fetch([entry], 7)
            transfer.assert_not_called()

    def test_release_query_distances_and_missing_filters(self):
        with tempfile.TemporaryDirectory() as tmp:
            release = Path(tmp)
            (release / 'windows').mkdir()
            base = {'longitude': 0, 'latitude': 0, 'status': 'rankable', 'cell_m': 30, 'relief_m': 10,
                    'roughness_m': 2, 'slope_cdf': [1] * 90, 'bare_fraction': 0, 'water_occurrence_pct': 0}
            profiles = {'slope_histogram': [10] + [0] * 89, 'relief_m': 10, 'roughness_m': 2}
            rows = [{**base, 'region_id': 'b'}, {**base, 'region_id': 'a'},
                    {**base, 'region_id': 'c', 'status': 'insufficient_dem_support'},
                    {**base, 'region_id': 'd', 'slope_cdf': [0] + [1] * 89, 'bare_fraction': None}]
            pq.write_table(pa.Table.from_pylist(rows, schema=SCHEMA), release / 'windows/a.parquet')
            manifest = {'profile': profiles, 'normalization': store.normalization(release, profiles)}
            total, results = store.search(release, manifest)
            self.assertEqual(total, 3)
            self.assertEqual([row['region_id'] for row in results], ['a', 'b', 'd'])
            self.assertEqual(results[2]['slope_distance_deg'], 1)
            total, results = store.search(release, manifest, bare_min=0, water_max=0, limit=1, offset=1)
            self.assertEqual((total, results[0]['region_id']), (2, 'b'))
