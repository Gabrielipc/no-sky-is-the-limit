import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch
import io
import urllib.request

spec = importlib.util.spec_from_file_location('surface_acquisition', Path(__file__).resolve().parents[1]/'scripts/adquirir_dimensiones.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class AcquisitionTests(unittest.TestCase):
    @staticmethod
    def response(status, headers, body=b'x'):
        response = MagicMock()
        response.status = status
        response.headers = headers
        response.read.side_effect = io.BytesIO(body).read
        response.__enter__.return_value = response
        return response

    def test_emit_preflight_uses_get_and_total_range_size_not_one_byte_length(self):
        response = self.response(206, {'Content-Range': 'bytes 0-0/45656544', 'Content-Length': '1',
                                      'Content-Type': 'application/x-netcdf', 'ETag': '"version"'})
        entry = {'url': 'https://'+m.EARTHDATA_HOST+'/file.nc', 'bytes': None}
        with patch.object(m, 'request', return_value=response) as request, patch.object(m.transport, 'inspect_url') as head:
            m.inspect(entry)
            request.assert_called_once_with(entry['url'], headers={'Range': 'bytes=0-0'})
            head.assert_not_called()
        self.assertEqual(entry['bytes'], 45656544)
        self.assertEqual(entry['etag'], '"version"')
        self.assertEqual(entry['status'], 'ready')
        response.read.assert_called_once_with(2)

    def test_emit_preflight_rejects_wrong_unknown_and_incomplete_ranges(self):
        for headers, body in [({'Content-Range': 'bytes 0-0/*'}, b'x'),
                              ({'Content-Range': 'bytes 0-15/100'}, b'x'),
                              ({'Content-Range': 'bytes 0-0/100', 'Content-Length': '16'}, b'x'),
                              ({'Content-Range': 'bytes 0-0/100'}, b'')]:
            with self.subTest(headers=headers, body=body), patch.object(m, 'request', return_value=self.response(206, headers, body)):
                with self.assertRaisesRegex(ValueError, 'rango'):
                    m.inspect_remote('https://'+m.EARTHDATA_HOST+'/file.nc')

    def test_ignored_range_closes_without_reading_full_file_and_public_head_is_unchanged(self):
        response = self.response(200, {'Content-Length': '50000000', 'Content-Type': 'application/x-netcdf'})
        with patch.object(m, 'request', return_value=response):
            self.assertEqual(m.inspect_remote('https://'+m.EARTHDATA_HOST+'/file.nc')['bytes'], 50000000)
            response.read.assert_not_called()
            response.__exit__.assert_called_once()
        with patch.object(m.transport, 'inspect_url', return_value={'bytes': 3}) as head:
            self.assertEqual(m.inspect_remote('https://zenodo.org/file.tif'), {'bytes': 3})
            head.assert_called_once()

    def test_discovery_offline_does_not_download_and_keeps_pair_files(self):
        with patch.dict(m.os.environ, {}, clear=True), patch.object(m, 'request', side_effect=AssertionError('network')):
            plan = m.discover(['themis', 'emit'])
        emit = [e for e in plan['files'] if e['source'] == 'emit']
        self.assertEqual(len(emit), 4)
        self.assertTrue(all(e['status'] == 'awaiting_auth' for e in emit))
        self.assertTrue(all(e['bytes'] is None for e in emit))
        self.assertEqual({e['site_id'] for e in emit}, {'utah', 'atacama'})

    def test_image_acquisition_includes_its_pds_label(self):
        catalog = json.loads(m.CATALOG.read_text())
        files = m.selected_products(catalog, ['hirise-ortho'])
        self.assertEqual(len(files), 2)
        self.assertTrue(files[0]['path'].endswith('.JP2'))
        self.assertTrue(files[1]['path'].endswith('.LBL'))

    def test_token_is_never_sent_to_public_host_or_stored(self):
        opener = MagicMock()
        with patch.dict(m.os.environ, {'EARTHDATA_TOKEN': 'test-secret'}), patch.object(m.urllib.request, 'build_opener', return_value=opener):
            m.request('https://zenodo.org/api/records/4931348')
            self.assertIsNone(opener.open.call_args.args[0].get_header('Authorization'))
            m.request('https://'+m.EARTHDATA_HOST+'/file.nc')
            self.assertEqual(opener.open.call_args.args[0].get_header('Authorization'), 'Bearer test-secret')
            plan = m.discover(['emit'])
            self.assertNotIn('test-secret', json.dumps(plan))
            self.assertNotIn('test-secret', m.error_message(ValueError('test-secret')))

    def test_redirect_strips_authorization_across_hosts(self):
        handler = m.SafeRedirect()
        req = urllib.request.Request('https://'+m.EARTHDATA_HOST+'/file', headers={'Authorization': 'Bearer secret'})
        redirected = handler.redirect_request(req, None, 302, 'Found', {}, 'https://example.amazonaws.com/file')
        self.assertIsNone(redirected.get_header('Authorization'))
        with self.assertRaises(ValueError):
            handler.redirect_request(req, None, 302, 'Found', {}, 'http://example.com/file')

    def test_missing_auth_and_invalid_host_fail_before_network(self):
        with patch.dict(m.os.environ, {}, clear=True), patch.object(m.urllib.request, 'build_opener') as opener:
            with self.assertRaisesRegex(ValueError, 'EARTHDATA_TOKEN'):
                m.request('https://'+m.EARTHDATA_HOST+'/file.nc')
            with self.assertRaises(ValueError):
                m.request('https://unrelated.example/file')
            opener.assert_not_called()

    def test_budget_preflight_prevents_partially_downloading_oversized_batch(self):
        files = [{'source': 'themis', 'path': 'x/a.tif', 'url': 'unused', 'bytes': 60, 'status': 'ready'},
                 {'source': 'themis', 'path': 'x/b.tif', 'url': 'unused', 'bytes': 60, 'status': 'ready'}]
        with tempfile.TemporaryDirectory() as folder, patch.object(m.transport, 'RAW', Path(folder)), patch.object(m, 'inspect'), patch.object(m.transport, 'fetch_with_retries') as download:
            with self.assertRaisesRegex(ValueError, 'presupuesto'):
                m.fetch({'files': files}, ['themis'], 100/1e9)
            download.assert_not_called()

    def test_existing_mismatched_original_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(m.transport, 'RAW', Path(folder)):
            p = Path(folder)/'old.tif'; p.write_bytes(b'old')
            plan = {'files': [{'source': 'themis', 'path': 'old.tif', 'bytes': 3, 'sha256': hashlib.sha256(b'new').hexdigest()}]}
            self.assertEqual(m.fetch(plan, ['themis'], 1), 1)
            self.assertEqual(p.read_bytes(), b'old')

    def test_verify_detects_missing_or_modified_files(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(m.transport, 'RAW', Path(folder)):
            p = Path(folder)/'ok.tif'; p.write_bytes(b'ok')
            plan = {'files': [{'source': 'themis', 'path': 'ok.tif', 'bytes': 2, 'sha256': hashlib.sha256(b'ok').hexdigest()}]}
            self.assertEqual(m.verify(plan, ['themis']), 0)
            p.write_bytes(b'no')
            self.assertEqual(m.verify(plan, ['themis']), 1)
            with self.assertRaises(ValueError):
                m.verify(plan, ['emit'])

    def test_completed_file_identity_is_persisted_before_next_download(self):
        files = [{'source': 'themis', 'path': 'a.tif', 'url': 'unused', 'bytes': 2},
                 {'source': 'themis', 'path': 'b.tif', 'url': 'unused', 'bytes': 2}]
        snapshots = []
        def download(entry, ceiling):
            if entry['path'] == 'b.tif':
                raise KeyboardInterrupt('simulated interruption')
            entry.update(status='downloaded', sha256='first-file-identity')
        with tempfile.TemporaryDirectory() as folder, patch.object(m.transport, 'RAW', Path(folder)), patch.object(m, 'inspect'), patch.object(m.transport, 'fetch_with_retries', side_effect=download):
            with self.assertRaises(KeyboardInterrupt):
                m.fetch({'files': files}, ['themis'], 1, lambda: snapshots.append(json.loads(json.dumps(files))))
        self.assertTrue(any(s[0].get('sha256') == 'first-file-identity' for s in snapshots))


if __name__ == '__main__':
    unittest.main()
