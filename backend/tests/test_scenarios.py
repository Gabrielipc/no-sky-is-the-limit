import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app import scenarios


class ScenarioTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def comparison(self, cell=60):
        return self.client.get('/api/scenarios/relieve-regional/comparison',
                               params={'reference_id': 'mars-jezero-fan', 'cell_m': cell})

    def test_complete_case_matches_reviewed_results_at_both_scales(self):
        stored = json.loads((scenarios.EVIDENCE / 'resultados.json').read_text())
        for cell in (60, 120):
            with self.subTest(cell=cell):
                response = self.comparison(cell)
                self.assertEqual(response.status_code, 200, response.text)
                case = response.json()
                self.assertEqual(case['case_id'], stored['case_id'])
                self.assertEqual(case['evidence_identity'], scenarios.digest(scenarios.EVIDENCE / 'resultados.json'))
                self.assertEqual(case['cell_m'], cell)
                self.assertEqual(len(case['candidates']), 2)
                self.assertEqual(case['reference']['id'], 'mars-jezero-fan')
                self.assertNotIn('score', case)
                sites = [case['reference'], *(c['site'] for c in case['candidates'])]
                for site in sites:
                    expected = next(r for r in stored['results'] if r['site_id'] == site['id'] and r['cell_m'] == cell)
                    self.assertEqual(site['measurements'], expected)
                    self.assertEqual(site['area']['properties']['side_m'], 1800)
                    self.assertEqual(site['area']['properties']['body'], site['body'])
                    self.assertEqual(len(site['source']['sha256']), 64)
                for candidate in case['candidates']:
                    expected = next(c for c in stored['comparisons'] if c['candidate'] == candidate['site']['id'] and c['cell_m'] == cell)
                    self.assertEqual(candidate['comparison'], expected)
                    self.assertEqual(len(candidate['sensitivity']), 2)
                    self.assertNotIn('score', candidate)

    def test_missing_dimensions_remain_null_and_explicit(self):
        case = self.comparison().json()
        self.assertEqual(len(case['not_evaluated']), 5)
        for dimension in case['not_evaluated']:
            self.assertIsNone(dimension['value'])
            self.assertEqual(dimension['status'], 'not_evaluated')

    def test_unknown_scenario_reference_and_scale_rejected(self):
        for url, code in (
            ('/api/scenarios/lunar/comparison', 404),
            ('/api/scenarios/relieve-regional/comparison?reference_id=moon', 422),
            ('/api/scenarios/relieve-regional/comparison?reference_id=earth-utah', 422),
            ('/api/scenarios/relieve-regional/comparison?cell_m=500', 422),
            ('/api/scenarios/relieve-regional/comparison?cell_m=abc', 422),
        ):
            self.assertEqual(self.client.get(url).status_code, code, url)

    def test_changed_or_missing_evidence_never_falls_back_to_prototype(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'manifest-local.json').write_bytes((scenarios.EVIDENCE / 'manifest-local.json').read_bytes())
            (root / 'resultados.json').write_text('{"case_id": "tampered"}')
            with patch.object(scenarios, 'EVIDENCE', root):
                self.assertEqual(self.comparison().status_code, 503)
                self.assertEqual(self.client.get('/api/evidence/resultados.json').status_code, 503)
                (root / 'resultados.json').unlink()
                self.assertEqual(self.comparison().status_code, 503)

    def test_changed_config_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            config = Path(folder) / 'config.json'
            config.write_text('{}')
            with patch.object(scenarios, 'CONFIG', config):
                self.assertEqual(self.comparison().status_code, 503)

    def test_links_resolve_and_raw_files_are_not_exposed(self):
        case = self.comparison().json()
        urls = list(case['evidence'].values()) + [case['distributions_figure'], case['orthoimage_figure']]
        for site in [case['reference'], *(c['site'] for c in case['candidates'])]:
            urls.extend(site['figures'].values())
        for url in urls:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200, url)
            self.assertEqual(response.headers['x-content-type-options'], 'nosniff')
            if url.endswith('.png'):
                self.assertTrue(response.content.startswith(b'\x89PNG'))
        for url in ('/api/evidence/N38W111.tif', '/api/evidence/.env', '/api/evidence/..%2F..%2F.env'):
            self.assertEqual(self.client.get(url).status_code, 404)

    def test_catalog_advertises_implemented_scenarios(self):
        response = self.client.get('/api/scenarios')
        self.assertEqual(response.status_code, 200)
        # Additional scenarios must preserve these two existing contracts.
        self.assertEqual([s['id'] for s in response.json()][:2], ['relieve-regional', 'estabilidad-topografica'])
        self.assertEqual(response.json()[0]['scales_m'], [60, 120])
        self.assertEqual(response.json()[1]['scales_m'], [60, 120, 300, 600])


if __name__ == '__main__':
    unittest.main()
