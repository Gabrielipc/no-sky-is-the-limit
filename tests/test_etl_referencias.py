"""Cloud job that mirrors the reference rasters (scripts/etl_referencias.py)."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from pipelines import etl_mirror as mirror
from scripts import etl_referencias as job

BODY = bytes(range(256)) * 40


class MirrorJobTest(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.sha = hashlib.sha256(BODY).hexdigest()
        self.manifest = {'products': [
            {'id': 'moon-a', 'asset_id': 'A.TIF', 'body': 'Moon', 'tier': 1, 'url': 'https://example.org/a', 'bytes': len(BODY), 'path': 'moon/A.TIF'},
            {'id': 'mars-b', 'asset_id': 'B.TIF', 'body': 'Mars', 'tier': 1, 'url': 'https://example.org/b', 'bytes': len(BODY), 'path': 'mars/B.TIF'},
            {'id': 'mars-ctx', 'asset_id': 'C.TIF', 'body': 'Mars', 'tier': 2, 'url': 'https://example.org/c', 'bytes': len(BODY), 'path': 'mars/C.TIF'}]}

    def fake_fetch(self, manifest, root, ids=None, **_):
        out = []
        for item in mirror.products(manifest, ids=ids):
            path = mirror.target(item, root)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(BODY)
            out.append({'id': item['id'], 'status': 'fetched', 'sha256': self.sha})
        return out

    def run_job(self, body='Moon', tiers=(1,), **patches):
        with mock.patch.object(mirror, 'load_manifest', return_value=self.manifest), \
                mock.patch.object(mirror, 'fetch', side_effect=patches.get('fetch', self.fake_fetch)):
            return job.run_mirror(body, list(tiers), 2, root=self.tmp / 'espejo', evidence_dir=self.tmp / 'ev')

    def test_each_body_only_mirrors_its_own_products_and_tier(self) -> None:
        self.assertEqual(job.body_ids(self.manifest, 'Moon', [1]), ['moon-a'])
        self.assertEqual(job.body_ids(self.manifest, 'Mars', [1]), ['mars-b'])
        self.assertEqual(job.body_ids(self.manifest, 'Mars', [1, 2]), ['mars-b', 'mars-ctx'])

    def test_real_manifest_splits_cleanly_between_the_two_bodies(self) -> None:
        manifest = mirror.load_manifest()
        moon, mars = job.body_ids(manifest, 'Moon', [1]), job.body_ids(manifest, 'Mars', [1])
        self.assertTrue(moon and mars)
        self.assertFalse(set(moon) & set(mars))  # what lets the two jobs run on two clouds at once

    def test_job_verifies_and_leaves_hash_evidence(self) -> None:
        checked = self.run_job('Moon')
        self.assertEqual([r['id'] for r in checked], ['moon-a'])
        doc = json.loads((self.tmp / 'ev/moon.json').read_text())
        self.assertEqual(doc['spec_id'], 'espejo-evidencia-v1')
        self.assertEqual(doc['products']['moon-a']['sha256'], self.sha)
        self.assertNotIn('mars-b', doc['products'])

    def test_a_failed_download_stops_the_job_without_evidence(self) -> None:
        bad = lambda manifest, root, ids=None, **_: [{'id': 'moon-a', 'status': 'failed', 'error': 'x'}]  # noqa: E731
        with self.assertRaises(SystemExit):
            self.run_job('Moon', fetch=bad)
        self.assertFalse((self.tmp / 'ev/moon.json').exists())

    def test_a_corrupt_copy_fails_verification(self) -> None:
        self.manifest['products'][0]['sha256'] = '0' * 64
        with self.assertRaises(SystemExit):
            self.run_job('Moon')
        self.assertFalse((self.tmp / 'ev/moon.json').exists())

    def test_no_products_for_the_tier_is_an_error(self) -> None:
        with self.assertRaises(SystemExit):
            self.run_job('Moon', tiers=(3,))

    def test_evidence_is_adopted_into_the_manifest_without_overwriting(self) -> None:
        self.run_job('Moon')
        path = self.tmp / 'manifest.json'
        path.write_text(json.dumps(self.manifest))
        result = mirror.adopt_hashes(path, [self.tmp / 'ev/moon.json'])
        self.assertEqual((result['added'], result['conflicts']), (['moon-a'], []))
        self.assertEqual(json.loads(path.read_text())['products'][0]['sha256'], self.sha)
        again = mirror.adopt_hashes(path, [self.tmp / 'ev/moon.json'])
        self.assertEqual((again['added'], again['unchanged']), ([], ['moon-a']))
        evidence = json.loads((self.tmp / 'ev/moon.json').read_text())
        evidence['products']['moon-a']['sha256'] = 'f' * 64
        (self.tmp / 'ev/otro.json').write_text(json.dumps(evidence))
        clash = mirror.adopt_hashes(path, [self.tmp / 'ev/otro.json'])
        self.assertIn('sha256', clash['conflicts'][0]['reason'])
        self.assertEqual(json.loads(path.read_text())['products'][0]['sha256'], self.sha)  # untouched

    def test_adopt_rejects_other_sizes_unknown_products_and_foreign_files(self) -> None:
        self.run_job('Moon')
        path = self.tmp / 'manifest.json'
        path.write_text(json.dumps(self.manifest))
        doc = json.loads((self.tmp / 'ev/moon.json').read_text())
        doc['products']['moon-a']['bytes'] += 1
        doc['products']['fantasma'] = {'sha256': 'a' * 64, 'bytes': 1, 'url': 'https://example.org/x'}
        (self.tmp / 'ev/malo.json').write_text(json.dumps(doc))
        result = mirror.adopt_hashes(path, [self.tmp / 'ev/malo.json'])
        self.assertEqual(sorted(c['id'] for c in result['conflicts']), ['fantasma', 'moon-a'])
        self.assertEqual(result['added'], [])
        (self.tmp / 'ev/ajeno.json').write_text(json.dumps({'spec_id': 'otra-cosa', 'products': {}}))
        with self.assertRaises(ValueError):
            mirror.adopt_hashes(path, [self.tmp / 'ev/ajeno.json'])


if __name__ == '__main__':
    unittest.main()
