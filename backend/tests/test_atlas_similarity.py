"""`/api/atlas/similarity`: the results published with a release, as the frontend consumes them."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app import atlas_store as store
from app.main import app


def result(rank):
    return {'rank': rank, 'region_id': f'w{rank}', 'longitude': 10.0 + rank, 'latitude': 20.0, 'score': 0.1 * rank}


class PublishedSimilarityTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        patcher = patch.object(store, 'ROOT', self.root)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.client = TestClient(app)

    def release(self, version='r1', similarity=True, escape=False):
        path = self.root / version
        (path / 'similarity').mkdir(parents=True)
        manifest = {'version': version, 'cell_m': 30}
        if similarity:
            (path / 'similarity/jezero.json').write_text(json.dumps({
                'engine_id': 'motor-similitud-ml-v1', 'reference': {'id': 'jezero'}, 'results': [result(i) for i in range(1, 8)]}))
            (self.root / 'secreto.json').write_text(json.dumps({'results': [result(1)]}))
            manifest['similarity'] = {'engine_status': 'unsupervised_pending_blind_validation', 'references': {
                'jezero': {'status': 'published', 'file': 'similarity/jezero.json'},
                'haworth-fondo': {'status': 'failed', 'file': 'similarity/haworth-fondo.json'},
                'escape': {'status': 'published', 'file': '../secreto.json'}}}
        (path / 'manifest.json').write_text(json.dumps(manifest))
        (self.root / 'current').write_text(version)

    def test_index_lists_the_published_references(self):
        self.release()
        body = self.client.get('/api/atlas/similarity').json()
        self.assertEqual(body['references']['jezero']['status'], 'published')
        self.assertEqual(body['references']['haworth-fondo']['status'], 'failed')

    def test_reference_is_paged_and_carries_the_release_version(self):
        self.release()
        page = self.client.get('/api/atlas/similarity/jezero?limit=3&offset=2').json()
        self.assertEqual([row['rank'] for row in page['results']], [3, 4, 5])
        self.assertEqual((page['version'], page['limit'], page['offset']), ('r1', 3, 2))
        self.assertEqual(page['engine_id'], 'motor-similitud-ml-v1')  # what the frontend adapter checks
        self.assertEqual(len(self.client.get('/api/atlas/similarity/jezero').json()['results']), 7)

    def test_a_pinned_version_is_served_even_after_promotion(self):
        self.release('first')
        self.release('second', similarity=False)
        self.assertEqual(self.client.get('/api/atlas/similarity/jezero').status_code, 404)
        self.assertEqual(self.client.get('/api/atlas/similarity/jezero?version=first').json()['version'], 'first')

    def test_missing_unpublished_and_unsafe_references_are_404(self):
        self.release()
        for ref in ('de-gerlache-cresta', 'haworth-fondo', 'escape', '..%2Fx', 'a.b'):
            with self.subTest(ref=ref):
                self.assertEqual(self.client.get(f'/api/atlas/similarity/{ref}').status_code, 404)

    def test_release_without_similarity_and_without_release(self):
        self.release(similarity=False)
        self.assertEqual(self.client.get('/api/atlas/similarity').status_code, 404)
        self.assertEqual(self.client.get('/api/atlas/similarity?version=nada').status_code, 404)

    def test_no_active_release_is_503(self):
        self.assertEqual(self.client.get('/api/atlas/similarity/jezero').status_code, 503)

    def test_paging_limits_are_validated(self):
        self.release()
        for query in ('limit=0', 'limit=101', 'offset=-1'):
            self.assertEqual(self.client.get(f'/api/atlas/similarity/jezero?{query}').status_code, 422, query)


if __name__ == '__main__':
    unittest.main()
