"""`/api/similarity`: the resident engine behind HTTP, its contract and its error handling."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import sys
import tempfile
import unittest

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))

from app.services import similarity_service as similarity  # noqa: E402
from app.main import app  # noqa: E402
from pipelines import contract_check as check  # noqa: E402
from pipelines import similarity_ml as sim  # noqa: E402
from tests import test_similarity_ml as fixtures  # noqa: E402

REF = fixtures.REF

SCHEMA = check.load_motor_schema()
API_SCHEMA_PATH = ROOT / 'specs/api/similitud-api-v1.schema.json'
API_SCHEMA = json.loads(API_SCHEMA_PATH.read_text(encoding='utf-8'))


def conforms(value, definition: str) -> list:
    """Errors of `value` against a definition of the API contract (empty when it conforms)."""
    return check.validate(value, API_SCHEMA['$defs'][definition], root=API_SCHEMA)
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

    def test_catalog_carries_kind_limitations_and_sources(self) -> None:
        refs = {r['id']: r for r in self.client.get('/api/similarity/references').json()['references']}
        for ref in refs.values():
            self.assertIn(ref['kind'], ('landing_site', 'base_candidate', 'control'))
            self.assertTrue(ref['limitations'], ref['id'])  # the analogy's limits are always shown
            self.assertTrue(ref['sources'], ref['id'])
        self.assertEqual(refs['haworth-fondo']['center']['latitude'], -87.45)

    def test_catalog_metadata_matches_the_spec_and_the_mirror(self) -> None:
        from pipelines import etl_mirror
        meta = similarity.load_catalog_meta()
        spec_refs = set(sim.load_spec()['references'])
        self.assertEqual(set(meta), spec_refs)  # no reference without limitations, none orphaned
        mirrored = {p['id']: p for p in etl_mirror.load_manifest()['products']}
        spec = json.loads((ROOT / 'specs/analysis/referencias-v1.json').read_text(encoding='utf-8'))
        for ref_id, entry in meta.items():
            self.assertIn(entry['kind'], spec['kinds'])
            for source in entry['sources']:
                self.assertIn(source, mirrored, f'{ref_id}: {source} no está en el manifiesto de espejo')

    def test_catalog_response_gives_the_defaults_the_interface_needs(self) -> None:
        body = self.client.get('/api/similarity/references').json()
        self.assertEqual(set(body['default_weights']), {'Mars', 'Moon'})
        self.assertEqual(set(body['default_weights']['Mars']), set(ALL_VIEWS))
        self.assertTrue(body['views']['escabrosidad']['fitted'])
        self.assertFalse(body['views']['espectral']['fitted'])
        self.assertEqual(body['engine_status'], 'unsupervised_pending_blind_validation')

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

    def test_every_response_conforms_to_its_definition(self) -> None:
        catalog = self.client.get('/api/similarity/references').json()
        self.assertEqual(conforms(catalog, 'ReferencesResponse'), [])
        for ref in catalog['references']:
            self.assertEqual(conforms(ref, 'ReferenceEntry'), [], ref['id'])
        detail = self.client.get('/api/similarity/references/jezero').json()
        self.assertEqual(conforms(detail, 'ReferenceDetail'), [])
        body = self.post({'reference': 'jezero', 'only_eligible': False, 'limit': 5}).json()
        self.assertEqual(conforms(body, 'SearchEnvelope'), [])
        self.assertEqual(check.validate(body, SCHEMA['$defs']['SearchResponse'], root=SCHEMA), [])  # engine contract
        self.assertRegex(body['query_id'], API_SCHEMA['$defs']['SearchEnvelope']['properties']['query_id']['pattern'])
        self.assertEqual(conforms(self.client.get('/api/similarity/status').json(), 'ServiceStatus'), [])

    def test_status_reports_peak_memory_so_the_vm_can_be_sized(self) -> None:
        self.post({'reference': 'jezero', 'only_eligible': False})
        status = self.client.get('/api/similarity/status').json()
        self.assertGreater(status['peak_rss_mb'], 50)  # at least the interpreter and the libraries
        self.assertEqual(conforms(status, 'ServiceStatus'), [])

    def test_status_conforms_before_the_engine_is_loaded(self) -> None:
        similarity.configure(self.root, self.model_path)
        self.assertEqual(conforms(self.client.get('/api/similarity/status').json(), 'ServiceStatus'), [])

    def test_every_error_has_the_documented_shape(self) -> None:
        cases = {
            404: self.client.get('/api/similarity/references/no-existe'),
            422: self.post({'reference': 'jezero', 'limit': 0}),
        }
        similarity.configure(self.root, Path(self.tmp.name) / 'sin-modelo.joblib')
        cases[503] = self.client.get('/api/similarity/references')
        for code, res in cases.items():
            with self.subTest(code=code):
                self.assertEqual(res.status_code, code)
                self.assertEqual(conforms(res.json(), 'ErrorResponse'), [])
                self.assertIn(str(code), API_SCHEMA['x-errors'])
        self.assertIsInstance(cases[422].json()['detail'], list)  # pydantic: a list of validation errors
        similarity.configure(self.root, self.model_path)
        self.assertIsInstance(self.post({'reference': 'jezero', 'weights': {'zzz': 1}}).json()['detail'], str)

    def test_the_contract_lists_the_routes_the_app_serves(self) -> None:
        # OpenAPI lists the real operations whatever FastAPI version wraps the routers.
        served = {(method.upper(), path) for path, ops in app.openapi()['paths'].items()
                  if path.startswith('/api/similarity') for method in ops}
        documented = {(e['method'], e['path']) for e in API_SCHEMA['x-endpoints']}
        self.assertEqual(served, documented)
        for endpoint in API_SCHEMA['x-endpoints']:
            for code in endpoint['errors']:
                self.assertIn(str(code), API_SCHEMA['x-errors'])

    def test_enums_agree_with_the_engine_and_the_catalogue(self) -> None:
        views = set(API_SCHEMA['$defs']['ViewId']['enum'])
        self.assertEqual(views, set(SCHEMA['$defs']['ViewId']['enum']))
        self.assertEqual(views, set(sim.view_ids(sim.load_spec())))
        kinds = json.loads((ROOT / 'specs/analysis/referencias-v1.json').read_text(encoding='utf-8'))['kinds']
        self.assertEqual(set(kinds), set(API_SCHEMA['$defs']['ReferenceEntry']['properties']['kind']['enum']) - {None})
        seen = {s for r in self.client.get('/api/similarity/references').json()['references'] for s in r['views'].values()}
        self.assertLessEqual(seen, set(API_SCHEMA['$defs']['ViewStatus']['enum']))
        self.assertEqual(set(API_SCHEMA['$defs']['ViewStatus']['enum']), {'reference_has_data', 'reference_missing', 'not_fitted'})


if __name__ == '__main__':
    unittest.main()
