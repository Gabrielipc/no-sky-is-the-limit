import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from app.main import app
from app.routers import expansion_router as expansion
from app.routers import regional_router as regional


class ExpansionTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_release_matches_evidence_and_preserves_pending(self):
        response = self.client.get('/api/expansion')
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()
        stored = json.loads((expansion.EVIDENCE/'resultados.json').read_text())
        self.assertEqual(result['candidates'], stored['candidates'])
        self.assertEqual(len(result['candidates']), 10)
        pending = [r for r in result['candidates'] if r['status'] == 'pending_detail']
        self.assertEqual(len(pending), 3)
        for row in pending:
            self.assertIsNone(row['local_metrics'])
            self.assertIsNone(row['source_contrasts'])
            self.assertTrue(row['missing_tiles'])
        self.assertNotIn('score', result)
        self.assertEqual(result['processing']['resources']['network_requests'], 0)

    def test_only_regional_scales_have_filter_decisions(self):
        result = self.client.get('/api/expansion').json()
        for row in result['candidates']:
            if row['source_contrasts'] is None:
                continue
            self.assertEqual([m['cell_m'] for m in row['local_metrics']], [60, 120, 300, 600])
            self.assertEqual([m['cell_m'] for m in row['source_contrasts']], [300, 600])
        for summary in result['summary']:
            expected = [c['filter_decisions'][summary['profile']]['changed']
                        for row in result['candidates'] for c in row['source_contrasts'] or []
                        if c['cell_m'] == summary['cell_m']]
            self.assertEqual(summary['paired_count'], sum(c is not None for c in expected))
            self.assertEqual(summary['changed_count'], sum(c is True for c in expected))

    def test_second_scenario_is_queryable_and_rejects_unknown_parameters(self):
        route = '/api/scenarios/estabilidad-topografica/comparison'
        for cell in (60, 120, 300, 600):
            response = self.client.get(route, params={'cell_m': cell})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()['cell_m'], cell)
        self.assertEqual(self.client.get(route+'?cell_m=500').status_code, 422)
        self.assertEqual(self.client.get(route+'?reference_id=moon').status_code, 422)

    def test_changed_and_missing_phase5_records_fail_closed(self):
        for name in ('resultados.json', 'procesamiento.json', 'manifest-local.json'):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                folder = Path(tmp)
                for path in expansion.EVIDENCE.glob('*.json'):
                    shutil.copyfile(path, folder/path.name)
                with patch.object(expansion, 'EVIDENCE', folder):
                    (folder/name).write_text('{}')
                    self.assertEqual(self.client.get('/api/expansion').status_code, 503)
                    self.assertEqual(self.client.get('/api/expansion/evidence/resultados.json').status_code, 503)
                    (folder/name).unlink()
                    self.assertEqual(self.client.get('/api/expansion').status_code, 503)

    def test_changed_config_or_upstream_release_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            cfg = folder/'config.json'
            cfg.write_text('{}')
            with patch.object(expansion, 'CONFIG', cfg):
                self.assertEqual(self.client.get('/api/expansion').status_code, 503)
            with patch.object(regional, 'EVIDENCE', folder):
                self.assertEqual(self.client.get('/api/expansion').status_code, 503)

    def test_only_allowlisted_evidence_is_served(self):
        for name in expansion.FILES:
            response = self.client.get('/api/expansion/evidence/'+name)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers['x-content-type-options'], 'nosniff')
        for name in ('N38W111.tif', '.env', '..%2F..%2F.env', 'verificacion.json'):
            self.assertEqual(self.client.get('/api/expansion/evidence/'+name).status_code, 404)


if __name__ == '__main__':
    unittest.main()
