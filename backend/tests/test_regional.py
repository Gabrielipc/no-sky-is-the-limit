import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from app.main import app
from app import regional


class RegionalAPITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client=TestClient(app)
        cls.stored=json.loads((regional.EVIDENCE/'candidatas.json').read_text())

    def test_counts_and_metrics_match_release_for_all_profiles_and_scales(self):
        for cell in (300,600):
            for profile in ('strict','baseline','relaxed'):
                response=self.client.get('/api/regional-search/candidates',params={'area_id':'utah','cell_m':cell,'profile':profile})
                self.assertEqual(response.status_code,200,response.text)
                result=response.json()
                expected=next(s for s in self.stored['sensitivity'] if s['area_id']=='utah' and s['cell_m']==cell and s['profile']==profile)
                self.assertEqual(result['generated'],expected['generated'])
                self.assertEqual(result['accepted'],expected['accepted'])
                self.assertEqual(result['total'],expected['accepted'])
                for row in result['items']:
                    self.assertTrue(row['passes_filter']); self.assertEqual(row['filter_reasons'],[])
                    site=next(s for s in self.stored['candidates'] if s['id']==row['id'])
                    self.assertEqual(row['metric'],next(m for m in site['metrics'] if m['cell_m']==cell))
                    self.assertNotIn('score',row)

    def test_exclusions_pagination_and_export_are_consistent(self):
        result=self.client.get('/api/regional-search/candidates?area_id=mojave&profile=strict&include_excluded=true&limit=100').json()
        self.assertEqual(result['total'],result['generated'])
        self.assertEqual(len(result['items']),100)
        next_page=self.client.get('/api/regional-search/candidates?area_id=mojave&profile=strict&include_excluded=true&limit=100&offset=100').json()
        self.assertTrue(set(r['id'] for r in result['items']).isdisjoint(r['id'] for r in next_page['items']))
        export=self.client.get('/api/regional-search/export?area_id=mojave&profile=strict&include_excluded=true')
        self.assertEqual(export.status_code,200)
        self.assertIn('application/geo+json',export.headers['content-type'])
        self.assertEqual(len(export.json()['features']),result['total'])
        self.assertTrue(any(not f['properties']['passes_filter'] for f in export.json()['features']))

    def test_known_controls_retained_even_when_excluded(self):
        summary=self.client.get('/api/regional-search').json()
        self.assertEqual(len(summary['control_filter_outcomes']),3)
        control=self.client.get('/api/regional-search/candidates/control-utah').json()
        self.assertEqual(control['role'],'control')
        self.assertEqual(control['phase2_site_id'],'earth-utah')
        self.assertTrue(control['metrics'][0]['filter_outcomes']['baseline'])
        self.assertFalse(control['metrics'][0]['filter_outcomes']['relaxed'])
        self.assertEqual(control['local_detail']['evaluation_status'],'pending_detail')
        self.assertIsNone(control['local_detail']['metrics'])

    def test_detail_and_pending_are_separate(self):
        summary=self.client.get('/api/regional-search').json()
        self.assertIn('utah-010-007',summary['local_evaluations'])
        response=self.client.get('/api/regional-search/candidates/utah-010-007')
        self.assertEqual(response.status_code,200,response.text)
        detail=response.json()['local_detail']
        self.assertEqual(detail['evaluation_status'],'locally_evaluated_exploratory')
        self.assertEqual([m['cell_m'] for m in detail['metrics']],[60,120])
        self.assertEqual(detail['window_m'],3000)
        self.assertEqual(self.client.get('/api/regional-search/candidates/missing').status_code,404)

    def test_invalid_filters_and_page_sizes_rejected(self):
        for query in ('area_id=global','cell_m=60','profile=validated','limit=101','limit=0','offset=-1'):
            self.assertEqual(self.client.get('/api/regional-search/candidates?'+query).status_code,422,query)

    def test_changed_or_missing_release_returns_503(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)
            (path/'manifest-local.json').write_bytes((regional.EVIDENCE/'manifest-local.json').read_bytes())
            (path/'candidatas.json').write_text('{}')
            with patch.object(regional,'EVIDENCE',path):
                self.assertEqual(self.client.get('/api/regional-search').status_code,503)
                self.assertEqual(self.client.get('/api/regional-search/evidence/candidatas.json').status_code,503)
                (path/'candidatas.json').unlink()
                self.assertEqual(self.client.get('/api/regional-search').status_code,503)

    def test_only_allowlisted_evidence_is_served(self):
        for filename in ('auditoria-gmted.json','procesamiento.json','manifiesto-gmted.json'):
            self.assertEqual(self.client.get('/api/regional-search/evidence/'+filename).status_code,200)
        for filename in ('.env','mn75_grd.zip','..%2F..%2F.env'):
            self.assertEqual(self.client.get('/api/regional-search/evidence/'+filename).status_code,404)


if __name__=='__main__':unittest.main()
