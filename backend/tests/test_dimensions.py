from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from app.main import app
from app.routers import dimensions_router as dimensions


class DimensionsTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_candidates_and_scales_have_real_descriptors(self):
        for site in ('earth-utah', 'earth-atacama'):
            for cell in (60, 120):
                response = self.client.get('/api/multidimensional', params={'candidate_id': site, 'cell_m': cell})
                self.assertEqual(response.status_code, 200, response.text)
                data = response.json()
                self.assertEqual(data['candidate']['id'], site)
                self.assertEqual(data['reference']['scale']['cell_m'], cell)
                self.assertIsNone(data['combined_score'])
                for key in data['metrics']:
                    self.assertEqual(data['comparison']['metrics'][key]['status'], 'comparable')
                    self.assertIsInstance(data['comparison']['metrics'][key]['wasserstein'], float)
                    grid = data['reference']['scale']['grids'][key]
                    self.assertEqual(len(grid['values']), (1800//cell)**2)

    def test_thermal_never_becomes_an_earth_comparison(self):
        data = self.client.get('/api/multidimensional').json()
        self.assertEqual(data['reference']['thermal']['summary']['valid_cells'], 342)
        self.assertEqual(data['reference']['thermal']['status'], 'measured')
        self.assertEqual(data['candidate']['thermal']['status'], 'not_acquired')
        self.assertIsNone(data['candidate']['thermal']['summary'])
        self.assertEqual(data['comparison']['thermal']['status'], 'not_comparable')
        self.assertIsNone(data['comparison']['thermal']['wasserstein'])
        for dimension in data['candidate']['pending_dimensions']:
            self.assertEqual(dimension['status'], 'not_evaluated')
            self.assertIsNone(dimension['value'])

    def test_scenario_and_direct_routes_match(self):
        direct = self.client.get('/api/multidimensional?candidate_id=earth-atacama&cell_m=120')
        other = self.client.get('/api/scenarios/superficie-multidimensional/comparison?candidate_id=earth-atacama&cell_m=120')
        self.assertEqual(direct.json(), other.json())

    def test_bad_reference_site_and_scale_return_422(self):
        for query in ('cell_m=30', 'cell_m=abc', 'reference_id=moon', 'candidate_id=unknown'):
            self.assertEqual(self.client.get('/api/multidimensional?'+query).status_code, 422)

    def test_evidence_resolves_and_raw_files_are_private(self):
        data = self.client.get('/api/multidimensional').json()
        for url in data['evidence'].values():
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers['x-content-type-options'], 'nosniff')
        for name in ('Jezero_Thermal_Inertia_v1.tiff', '.env', '..%2F.env'):
            self.assertEqual(self.client.get('/api/multidimensional/evidence/'+name).status_code, 404)
        self.assertEqual(len(self.client.get('/api/multidimensional/sources').json()['sources']), 16)

    def test_missing_or_changed_release_is_503(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(dimensions, 'EVIDENCE', Path(folder)):
                self.assertEqual(self.client.get('/api/multidimensional').status_code, 503)
                self.assertEqual(self.client.get('/api/multidimensional/evidence/resultados.json').status_code, 503)
        with patch.object(dimensions, 'digest', return_value='changed'):
            self.assertEqual(self.client.get('/api/multidimensional').status_code, 503)


if __name__ == '__main__':
    unittest.main()
