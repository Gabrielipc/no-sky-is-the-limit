import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import duckdb
from fastapi.testclient import TestClient

from app import atlas_store as store
from app.main import app


class AtlasAPITests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        patcher = patch.object(store, 'ROOT', self.root)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.client = TestClient(app)

    def release(self, version, ids):
        path = self.root / version
        (path / 'windows').mkdir(parents=True)
        with duckdb.connect() as db:
            db.execute('CREATE TABLE ids (region_id VARCHAR)')
            db.executemany('INSERT INTO ids VALUES (?)', [(key,) for key in ids])
            db.execute("""
                COPY (
                  SELECT region_id, 'rankable' AS status, 30 AS cell_m, 0.0 AS longitude, 0.0 AS latitude,
                         'fixture' AS area, 'fixture' AS batch, 10.0 AS relief_m, 2.0 AS roughness_m,
                         2.0 AS slope_p50_deg, 1.0 AS land_fraction, 1.0 AS valid_elevation,
                         1.0 AS valid_slope, 1.0 AS valid_roughness, []::VARCHAR[] AS asset_ids,
                         []::VARCHAR[] AS worldcover_assets, []::VARCHAR[] AS water_assets,
                         0.0 AS bare_fraction, 0.0 AS water_occurrence_pct, list_value(1.0) AS slope_cdf
                  FROM ids
                ) TO ? (FORMAT PARQUET)
            """, [str(path / 'windows/a.parquet')])
        profile = {'profile_id': 'jezero-forma', 'slope_histogram': [10000], 'relief_m': 10, 'roughness_m': 2}
        (path / 'manifest.json').write_text(json.dumps({'version': version, 'cell_m': 30, 'profile': profile,
                                                       'normalization': dict.fromkeys(store.DISTANCES, 1)}))
        (self.root / 'current').write_text(version)

    def test_replay_retains_version_after_promotion(self):
        self.release('first', ['b', 'a'])
        response = self.client.get('/api/atlas/search?limit=1&offset=1')
        self.assertEqual(response.status_code, 200, response.text)
        query = response.json()
        self.assertEqual((query['version'], query['cell_m'], query['matches'][0]['region_id']), ('first', 30, 'b'))
        self.release('second', ['c'])
        replay = self.client.get(f'/api/atlas/search/{query["query_id"]}')
        self.assertEqual([row['region_id'] for row in replay.json()['matches']], ['a', 'b'])
        self.assertEqual(self.client.get('/api/atlas').json()['version'], 'second')
        self.assertEqual(self.client.get('/api/atlas/coverage').json()['bins'][0]['rankable'], 1)
        self.assertEqual(self.client.get('/api/atlas/candidates/c').json()['window']['cell_m'], 30)
        self.assertEqual(self.client.get('/api/atlas/search?slope=0&relief=0&roughness=0').status_code, 422)

    def test_no_active_release(self):
        self.assertEqual(self.client.get('/api/atlas').status_code, 503)
        self.assertEqual(self.client.get('/api/atlas?version=missing').status_code, 404)
