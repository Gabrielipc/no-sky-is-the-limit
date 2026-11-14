from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from app.main import app
from app.routers import minerals_router as minerals


class MineralAPITests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_both_candidates_expose_real_groups_quality_and_no_mars_score(self):
        for site in ('earth-utah', 'earth-atacama'):
            response = self.client.get('/api/minerals', params={'candidate_id': site})
            self.assertEqual(response.status_code, 200, response.text)
            result = response.json()
            self.assertEqual(result['candidate']['id'], site)
            self.assertEqual(result['candidate']['status'], 'measured')
            self.assertEqual(result['mars']['status'], 'indicators_available')
            self.assertEqual(result['mars']['endpoint'], '/api/minerals/jezero')
            grid = result['candidate']['grid']
            self.assertEqual(set(grid['groups']), {'1', '2'})
            self.assertGreater(grid['available_classification_cells'], 0)
            self.assertNotIn('score', result)
            self.assertNotIn('similarity', result)

    def test_unknown_candidate_and_non_allowlisted_files_are_rejected(self):
        self.assertEqual(self.client.get('/api/minerals?candidate_id=moon').status_code, 422)
        for name in ('.env', 'file.nc', '..%2F.env'):
            self.assertEqual(self.client.get('/api/minerals/evidence/' + name).status_code, 404)
        self.assertEqual(self.client.get('/api/minerals/evidence/procesamiento.json').status_code, 200)

    def test_changed_or_missing_release_fails_closed(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)
            (path / 'manifest-local.json').write_bytes((minerals.EVIDENCE / 'manifest-local.json').read_bytes())
            with patch.object(minerals, 'EVIDENCE', path):
                self.assertEqual(self.client.get('/api/minerals').status_code, 503)
        with patch.object(minerals.hashlib, 'sha256') as sha:
            sha.return_value.hexdigest.return_value = 'altered'
            self.assertEqual(self.client.get('/api/minerals').status_code, 503)

    def test_jezero_preserves_signed_values_and_masked_cells(self):
        response = self.client.get('/api/minerals/jezero')
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()
        grid = result['grid']
        self.assertEqual(result['coverage'], {'total': 10200, 'supported': 8897, 'excluded': 909, 'missing': 394})
        self.assertEqual(grid['step_m'], [18, 18])
        self.assertEqual(sum(grid['inside']), result['coverage']['total'])
        self.assertEqual(grid['mask'].count(0), result['coverage']['supported'])
        self.assertEqual(grid['mask'].count(1), result['coverage']['excluded'])
        for layer in result['layers']:
            self.assertEqual(len(layer['values']), grid['rows'] * grid['columns'])
            self.assertEqual(layer['valid_cells'], sum(value is not None for value in layer['values']))
            self.assertTrue(all(value is None for value, mask in zip(layer['values'], grid['mask']) if mask != 0))
        d2300 = next(layer for layer in result['layers'] if layer['id'] == 'D2300')
        self.assertLess(d2300['p02'], 0)
        self.assertNotIn('score', result)
        self.assertEqual(self.client.get(result['evidence']['manifest-local.json']).status_code, 200)
        self.assertEqual(self.client.get('/api/minerals/jezero/evidence/frt000047a3.img').status_code, 404)

    def test_unavailable_jezero_evidence_keeps_earth_available(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(minerals, 'JEZERO_EVIDENCE', Path(folder)):
            self.assertEqual(self.client.get('/api/minerals/jezero').status_code, 503)
            response = self.client.get('/api/minerals')
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()['mars']['status'], 'unavailable')


if __name__ == '__main__':
    unittest.main()
