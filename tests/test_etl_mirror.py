"""Verified mirror of the reference rasters (pipelines/etl_mirror.py)."""
from __future__ import annotations

import hashlib
import http.server
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest import mock

from pipelines import etl_mirror as mirror

BODY = bytes(range(256)) * 4000  # ~1 MB, not a repeating block of zeros


class Handler(http.server.BaseHTTPRequestHandler):
    ignore_range = False
    redirect_to = None
    truncate = False

    def log_message(self, *_):
        pass

    def do_GET(self):  # noqa: N802
        if self.path == '/redirect':
            self.send_response(302)
            self.send_header('Location', Handler.redirect_to)
            self.end_headers()
            return
        data, start = BODY, 0
        rng = self.headers.get('Range')
        if rng and not Handler.ignore_range:
            start = int(rng.split('=')[1].split('-')[0])
            self.send_response(206)
            self.send_header('Content-Range', f'bytes {start}-{len(data) - 1}/{len(data)}')
        else:
            self.send_response(200)
        chunk = data[start:len(data) // 2] if Handler.truncate else data[start:]
        self.send_header('Content-Length', str(len(chunk)))
        self.end_headers()
        self.wfile.write(chunk)


class MirrorTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.base = f'http://127.0.0.1:{cls.server.server_address[1]}'

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        Handler.ignore_range, Handler.redirect_to, Handler.truncate = False, None, False
        self.sha = hashlib.sha256(BODY).hexdigest()
        self.item = {'id': 'demo', 'asset_id': 'DEMO.TIF', 'body': 'Moon', 'tier': 1, 'url': f'{self.base}/file',
                     'bytes': len(BODY), 'path': 'moon/demo/DEMO.TIF', 'sha256': self.sha}
        self.manifest = {'products': [self.item]}
        patcher = mock.patch.object(mirror.time, 'sleep')
        patcher.start()
        self.addCleanup(patcher.stop)

    # -- manifest ------------------------------------------------------------
    def test_committed_manifest_is_valid_and_light_enough_to_mirror(self) -> None:
        manifest = mirror.load_manifest()
        ids = [p['id'] for p in manifest['products']]
        self.assertEqual(len(ids), len(set(ids)))
        tier1 = sum(p['bytes'] for p in manifest['products'] if p['tier'] == 1)
        self.assertLess(tier1, 10e9)  # the plan relies on a mirror that fits comfortably on one disk
        for p in manifest['products']:
            self.assertTrue(p['url'].startswith('https://'), p['id'])
            self.assertIn(p['body'], ('Moon', 'Mars'))
            self.assertTrue(p['role'] and p['citation'], p['id'])

    def test_manifest_rejects_unsafe_entries(self) -> None:
        bad = [{**self.item, 'url': 'http://example.org/x'}, {**self.item, 'path': '../fuera'},
               {**self.item, 'path': '/abs/ruta'}, {**self.item, 'bytes': 0}]
        for item in bad:
            with self.subTest(item=item['url'] + item['path']):
                path = self.root / 'm.json'
                path.write_text(json.dumps({'products': [item]}))
                with self.assertRaises(ValueError):
                    mirror.load_manifest(path)
        path = self.root / 'dup.json'
        path.write_text(json.dumps({'products': [self.item, self.item]}))
        with self.assertRaises(ValueError):
            mirror.load_manifest(path)

    # -- fetch ---------------------------------------------------------------
    def test_fetch_downloads_checks_the_hash_and_is_idempotent(self) -> None:
        res = mirror.fetch(self.manifest, self.root)
        self.assertEqual([r['status'] for r in res], ['fetched'])
        self.assertTrue(res[0]['hash_checked'])
        self.assertEqual(mirror.target(self.item, self.root).read_bytes(), BODY)
        self.assertEqual(mirror.fetch(self.manifest, self.root), [])
        self.assertEqual(mirror.plan(self.manifest, self.root)['remaining_bytes'], 0)

    def test_resume_continues_a_partial_file(self) -> None:
        part = mirror.target(self.item, self.root).with_name('DEMO.TIF.part')
        part.parent.mkdir(parents=True)
        part.write_bytes(BODY[:300_000])
        self.assertEqual(mirror.state(self.item, self.root)['status'], 'partial')
        res = mirror.fetch_item(self.item, self.root)
        self.assertEqual(res['status'], 'fetched')
        self.assertEqual(res['downloaded'], len(BODY) - 300_000)
        self.assertEqual(mirror.target(self.item, self.root).read_bytes(), BODY)

    def test_server_that_ignores_range_restarts_cleanly(self) -> None:
        Handler.ignore_range = True
        part = mirror.target(self.item, self.root).with_name('DEMO.TIF.part')
        part.parent.mkdir(parents=True)
        part.write_bytes(BODY[:1000])
        self.assertEqual(mirror.fetch_item(self.item, self.root)['status'], 'fetched')
        self.assertEqual(mirror.target(self.item, self.root).read_bytes(), BODY)

    def test_wrong_hash_discards_the_download(self) -> None:
        item = {**self.item, 'sha256': '0' * 64}
        res = mirror.fetch_item(item, self.root)
        self.assertEqual(res['status'], 'hash_mismatch')
        self.assertFalse(mirror.target(item, self.root).exists())
        self.assertFalse(mirror.target(item, self.root).with_name('DEMO.TIF.part').exists())

    def test_md5_is_supported_and_sha256_is_always_reported(self) -> None:
        item = {k: v for k, v in self.item.items() if k != 'sha256'} | {'md5': hashlib.md5(BODY).hexdigest()}
        res = mirror.fetch_item(item, self.root)
        self.assertEqual((res['status'], res['sha256']), ('fetched', self.sha))
        self.assertTrue(mirror.verify_item(item, self.root)['ok'])

    def test_truncated_response_is_a_failure_not_a_file(self) -> None:
        Handler.truncate = True
        res = mirror.fetch_item(self.item, self.root, attempts=2)
        self.assertEqual(res['status'], 'failed')
        self.assertFalse(mirror.target(self.item, self.root).exists())

    def test_redirect_to_plain_http_is_refused(self) -> None:
        Handler.redirect_to = f'{self.base}/file'
        item = {**self.item, 'url': f'{self.base}/redirect'}
        res = mirror.fetch_item(item, self.root, attempts=1)
        self.assertEqual(res['status'], 'failed')
        self.assertIn('HTTPS', res['error'])

    def test_budget_skips_what_does_not_fit_and_takes_the_lightest_first(self) -> None:
        small = {**self.item, 'id': 'small', 'path': 'moon/demo/S.TIF', 'bytes': 5, 'sha256': None}
        manifest = {'products': [self.item, small]}
        log = []
        res = mirror.fetch(manifest, self.root, max_bytes=len(BODY) // 2, log=log.append)
        self.assertEqual([r['id'] for r in res], ['small'])  # fails its size check: the server sends ~1 MB
        self.assertTrue(any('omitido' in m for m in log))

    # -- verify / local copy -------------------------------------------------
    def test_verify_detects_corruption_and_missing_files(self) -> None:
        self.assertEqual(mirror.verify(self.manifest, self.root)[0]['reason'], 'missing')
        mirror.fetch(self.manifest, self.root)
        self.assertTrue(mirror.verify(self.manifest, self.root)[0]['ok'])
        path = mirror.target(self.item, self.root)
        data = bytearray(path.read_bytes())
        data[10] ^= 0xFF
        path.write_bytes(bytes(data))
        res = mirror.verify(self.manifest, self.root)[0]
        self.assertFalse(res['ok'])
        self.assertIn('mismatch', res['reason'])
        path.write_bytes(b'corto')
        self.assertIn('size', mirror.verify(self.manifest, self.root)[0]['reason'])

    def test_local_copy_only_returns_complete_files(self) -> None:
        self.assertIsNone(mirror.local_copy('DEMO.TIF', self.root, self.manifest))
        mirror.fetch(self.manifest, self.root)
        self.assertEqual(mirror.local_copy('DEMO.TIF', self.root, self.manifest), mirror.target(self.item, self.root))
        self.assertEqual(mirror.local_copy('demo', self.root, self.manifest), mirror.target(self.item, self.root))
        self.assertIsNone(mirror.local_copy('otro', self.root, self.manifest))
        self.assertIsNone(mirror.local_copy(None, self.root, self.manifest))
        mirror.target(self.item, self.root).write_bytes(b'truncado')
        self.assertIsNone(mirror.local_copy('DEMO.TIF', self.root, self.manifest))

    def test_record_hashes_fills_only_missing_ones(self) -> None:
        item = {k: v for k, v in self.item.items() if k != 'sha256'}
        path = self.root / 'm.json'
        path.write_text(json.dumps({'products': [item]}))
        res = mirror.fetch_item(item, self.root)
        self.assertEqual(mirror.record_hashes(path, [res]), 1)
        self.assertEqual(json.loads(path.read_text())['products'][0]['sha256'], self.sha)
        self.assertEqual(mirror.record_hashes(path, [res]), 0)


if __name__ == '__main__':
    unittest.main()
