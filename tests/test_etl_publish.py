"""Tests for publishing the ETL store as an Atlas release read by the API."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest

from backend.app import atlas_store
from pipelines import etl_publish as publish
from pipelines.etl_store import FeatureStore
from tests.test_etl_eligibility import SCENARIOS, base_row

NOW = datetime(2026, 11, 14, 12, 0, tzinfo=timezone.utc)


def window(name: str, scenario: str, relief: float, s50: float, s90: float, qa: str = 'rankable') -> dict:
    row = base_row(f'utm-ups-v1-10000-32612-420-{48 + len(name)}-{name}', SCENARIOS[scenario])
    row.update({'relief_p95_p05_m': relief, 'slope_240m_p50_deg': s50, 'slope_240m_p90_deg': s90,
                'roughness_360m_p50_m': 7.0, 'qa_status': qa, 'source_manifest_id': 'm1'})
    return row


class TestPublish(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.store = FeatureStore(root / 'store', memory_limit='512MB', threads=2)
        rows = [window('near', 'desert', 121.0, 3.1, 9.3), window('far', 'desert', 400.0, 12.0, 25.0),
                window('trees', 'forest', 120.0, 3.0, 9.2), window('gap', 'desert', 0, 0, 0, 'dem_fetch_failed')]
        rows[-1].update({'relief_p95_p05_m': None, 'slope_240m_p50_deg': None, 'slope_240m_p90_deg': None,
                         'roughness_360m_p50_m': None, 'analog_surface_eligibility': 'pending_on_demand_cover_check'})
        manifests = [{'source_manifest_id': 'm1', 'product_id': pid, 'asset_id': aid, 'access_mode': 'cache',
                      'sha256_or_etag': 'x', 'native_resolution_m': 30.0, 'effective_resolution_m': 30.0,
                      'observation_period': 'static', 'created_at': NOW}
                     for pid, aid in (('copernicus-glo30', 'dem.tif'), ('esa-worldcover-2021', 'wc.tif'),
                                      ('jrc-gsw-v1_5', 'jrc.tif'))]
        self.store.write_base_batch('b1', rows, manifests)
        self.store.mark_batch_completed('b1', {'status': 'complete'})
        self.releases = root / 'releases'
        self.releases.mkdir()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_release_is_searchable_by_the_api(self) -> None:
        manifest = publish.publish_release(self.store, 'etl-test-r1', root=self.releases, set_current=True)
        self.assertEqual(manifest['ranking_method'], atlas_store.QUANTILE_METHOD)
        self.assertEqual(manifest['counts'], {'rankable': 3, 'dem_fetch_failed': 1})
        self.assertEqual(manifest['coverage_status'], 'partial')
        self.assertEqual((self.releases / 'current').read_text().strip(), 'etl-test-r1')

        release, loaded = atlas_store.load_release(self.releases)
        total, matches = atlas_store.search(release, loaded)
        self.assertEqual(total, 2)  # the forest window is not eligible under the arid profile
        self.assertEqual([m['region_id'].split('-')[-1] for m in matches], ['near', 'far'])
        near = matches[0]
        self.assertAlmostEqual(near['slope_distance_deg'],
                               (abs(3.1 - publish.JEZERO_PROFILE['slope_p50_deg'])
                                + abs(9.3 - publish.JEZERO_PROFILE['slope_p90_deg'])) / 2, places=4)

        bins = atlas_store.coverage(release)
        self.assertEqual(sum(b['gaps'] for b in bins), 1)
        found = atlas_store.candidate(release, near['region_id'])
        self.assertEqual((found['asset_ids'], found['worldcover_assets'], found['water_assets']),
                         (['dem.tif'], ['wc.tif'], ['jrc.tif']))
        self.assertEqual(atlas_store.context_counts(release)['bare'], 3)

    def test_existing_version_is_not_overwritten(self) -> None:
        publish.publish_release(self.store, 'etl-test-r1', root=self.releases)
        with self.assertRaises(FileExistsError):
            publish.publish_release(self.store, 'etl-test-r1', root=self.releases)
        with self.assertRaises(ValueError):
            publish.publish_release(self.store, '../escape', root=self.releases)


if __name__ == '__main__':
    unittest.main()
