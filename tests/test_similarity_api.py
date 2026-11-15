"""`/api/similarity`: the resident engine behind HTTP, its contract and its error handling."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sys
import tempfile
import unittest

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))

from app import similarity  # noqa: E402
from app.main import app  # noqa: E402
from pipelines import contract_check as check  # noqa: E402
from pipelines import similarity_ml as sim  # noqa: E402
from tests import test_similarity_ml as fixtures  # noqa: E402

REF = fixtures.REF

SCHEMA = check.load_motor_schema()
ALL_VIEWS = SCHEMA['$defs']['ViewId']['enum']


class SimilarityAPITest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        fixtures.TestEngineOnStore.setUpClass()  # synthetic Earth store + fitted model
        cls.tmp = tempfile.TemporaryDirectory()
        cls.model_path = Path(cls.tmp.name) / 'modelo.joblib'
        sim.save_model(fixtures.TestEngineOnStore.model, cls.model_path)
        cls.root = fixtures.TestEngineOnStore.root
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls) -> None:
        similarity.configure(cls.root, cls.model_path).close()
        cls.tmp.cleanup()
        fixtures.TestEngineOnStore.tearDownClass()

    def setUp(self) -> None:
        similarity.configure(self.root, self.model_path)

    def post(self, body: dict):
        return self.client.post('/api/similarity/search', json=body)

    # -- catalog -----------------------------------------------------------
    def test_catalog_lists_resolvable_and_unavailable_references(self) -> None:
        res = self.client.get('/api/similarity/references')
        self.assertEqual(res.status_code, 200)
        refs = {r['id']: r for r in res.json()['references']}
        self.assertTrue(refs['jezero']['available'])
        self.assertEqual(refs['jezero']['body'], 'Mars')
        self.assertEqual(refs['jezero']['views']['escabrosidad'], 'reference_has_data')
        self.assertEqual(refs['jezero']['views']['espectral'], 'not_fitted')
        # The fixture store has no Haworth window: it is reported, not hidden and not invented.
        self.assertFalse(refs['haworth-fondo']['available'])
        self.assertIn('reason', refs['haworth-fondo'])

    def test_reference_detail(self) -> None:
        res = self.client.get('/api/similarity/references/jezero')
        self.assertEqual(res.status_code, 200)
        self.assertIn('relief_p95_p05_m', res.json()['features'])
        self.assertEqual(self.client.get('/api/similarity/references/no-existe').status_code, 404)

    # -- search ------------------------------------------------------------
    def test_named_reference_answers_with_the_published_contract(self) -> None:
        res = self.post({'reference': 'jezero', 'only_eligible': False, 'limit': 5})
        self.assertEqual(res.status_code, 200, res.text)
        body = res.json()
        self.assertEqual(check.validate(body, SCHEMA['$defs']['SearchResponse'], root=SCHEMA), [])
        self.assertEqual(len(body['results']), 5)
        self.assertEqual(len(body['query_id']), 64)
        self.assertFalse(body['timings']['cache_hit'])
        self.assertGreaterEqual(body['timings']['total_ms'], body['timings']['engine_ms'])

    def test_api_matches_the_engine(self) -> None:
        direct = fixtures.TestEngineOnStore.engine.search(self.root, {'id': 'e', 'body': 'Mars', 'features': REF},
                                                 only_eligible=False, limit=20, memory_limit='512MB', threads=2)
        res = self.post({'reference': {'id': 'e', 'body': 'Mars', 'features': REF}, 'only_eligible': False,
                         'limit': 20}).json()
        self.assertEqual([r['region_id'] for r in res['results']], [r['region_id'] for r in direct['results']])
        self.assertEqual([r['score'] for r in res['results']], [r['score'] for r in direct['results']])

    def test_repeated_and_equivalent_requests_share_the_query_id_and_hit_the_cache(self) -> None:
        first = self.post({'reference': 'jezero', 'only_eligible': False, 'limit': 10}).json()
        again = self.post({'reference': 'jezero', 'only_eligible': False, 'limit': 10}).json()
        self.assertTrue(again['timings']['cache_hit'])
        self.assertEqual(again['query_id'], first['query_id'])
        self.assertEqual(again['results'], first['results'])
        # The weights are renormalised by the engine, so a scaled copy is the same query.
        equal = {v: 1.0 for v in ALL_VIEWS}
        a = self.post({'reference': 'jezero', 'only_eligible': False, 'weights': equal}).json()
        b = self.post({'reference': 'jezero', 'only_eligible': False,
                       'weights': {v: 2.0 for v in ALL_VIEWS}}).json()
        self.assertEqual(a['query_id'], b['query_id'])
        c = self.post({'reference': 'jezero', 'only_eligible': False, 'weights': {'escabrosidad': 5.0}}).json()
        self.assertNotEqual(a['query_id'], c['query_id'])

    def test_weights_change_the_ranking(self) -> None:
        rug = self.post({'reference': {'body': 'Mars', 'features': REF}, 'only_eligible': False, 'limit': 5,
                         'weights': {'escabrosidad': 1, 'forma_hipsometrica': 0, 'organizacion': 0,
                                     'regimen_morfologico': 0}}).json()
        shape = self.post({'reference': {'body': 'Mars', 'features': REF}, 'only_eligible': False, 'limit': 5,
                           'weights': {'escabrosidad': 0, 'forma_hipsometrica': 1, 'organizacion': 0.2,
                                       'regimen_morfologico': 0}}).json()
        self.assertNotEqual([r['region_id'] for r in rug['results']], [r['region_id'] for r in shape['results']])

    def test_null_features_are_ignored_and_missing_views_are_reported(self) -> None:
        res = self.post({'reference': {'body': 'Mars', 'features': {**REF, 'hypsometric_integral': None}},
                         'only_eligible': False, 'limit': 3})
        self.assertEqual(res.status_code, 200, res.text)
        self.assertNotIn('hypsometric_integral', res.json()['reference']['features'])

    def test_concurrent_queries_agree(self) -> None:
        body = {'reference': 'jezero', 'only_eligible': False, 'limit': 15, 'fusion': 'rrf'}
        similarity.service().ensure()
        with ThreadPoolExecutor(6) as ex:
            out = list(ex.map(lambda _: self.post(body).json()['results'], range(12)))
        self.assertTrue(all(o == out[0] for o in out))

    def test_other_profile_builds_its_own_pool(self) -> None:
        res = self.post({'reference': 'jezero', 'profile': 'polar_cold_v1', 'only_eligible': False, 'limit': 3})
        self.assertEqual(res.status_code, 200, res.text)
        self.assertEqual(res.json()['profile'], 'polar_cold_v1')
        self.assertIn('polar_cold_v1', similarity.service().status()['profiles_loaded'])

    # -- errors ------------------------------------------------------------
    def test_validation_errors_are_422(self) -> None:
        bad = [
            {'reference': 'jezero', 'weights': {'vista_inventada': 1.0}},
            {'reference': 'jezero', 'weights': {'escabrosidad': -1.0}},
            {'reference': 'jezero', 'weights': {v: 0.0 for v in ALL_VIEWS}},
            {'reference': 'jezero', 'limit': 0},
            {'reference': 'jezero', 'limit': 5000},
            {'reference': 'jezero', 'fusion': 'otra'},
            {'reference': 'jezero', 'profile': 'no_existe'},
            {'reference': 'jezero', 'campo_extra': 1},
            {'reference': 'jezero', 'bbox': [10, 0, 5, 20]},
            {'reference': 'jezero', 'bbox': [0, 0, 1]},
            {'reference': {'body': 'Venus', 'features': {}}},
            {'reference': {'body': 'Mars', 'features': {'inventada': 1.0}}},
            {'reference': {'body': 'Mars', 'features': REF, 'percentiles': {'cpr_p50': 1.5}}},
            {'reference': {'body': 'Mars', 'features': REF, 'percentiles': {'relief_p95_p05_m': 0.5}}},
            {},
        ]
        for body in bad:
            with self.subTest(body=body):
                self.assertEqual(self.post(body).status_code, 422)

    def test_unknown_or_unavailable_reference_is_404(self) -> None:
        self.assertEqual(self.post({'reference': 'no-existe'}).status_code, 404)
        res = self.post({'reference': 'haworth-fondo'})
        self.assertEqual(res.status_code, 404)
        self.assertIn('no disponible', res.json()['detail'])

    def test_missing_model_or_store_is_503(self) -> None:
        similarity.configure(self.root, Path(self.tmp.name) / 'no-hay-modelo.joblib')
        self.assertEqual(self.client.get('/api/similarity/references').status_code, 503)
        self.assertEqual(self.post({'reference': 'jezero'}).status_code, 503)
        similarity.configure(Path(self.tmp.name) / 'no-hay-almacen', self.model_path)
        self.assertEqual(self.post({'reference': 'jezero'}).status_code, 503)
        self.assertFalse(self.client.get('/api/similarity/status').json()['loaded'])

    def test_status_reports_the_loaded_engine(self) -> None:
        self.post({'reference': 'jezero', 'only_eligible': False})
        status = self.client.get('/api/similarity/status').json()
        self.assertTrue(status['loaded'])
        self.assertEqual(status['engine_status'], 'unsupervised_pending_blind_validation')
        self.assertGreater(status['profiles_loaded'][similarity.DEFAULT_PROFILE], 400)
        self.assertGreaterEqual(status['cached_queries'], 1)


if __name__ == '__main__':
    unittest.main()
