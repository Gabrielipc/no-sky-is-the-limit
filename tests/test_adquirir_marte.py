import copy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch
import urllib.request

spec = importlib.util.spec_from_file_location('mars_acquisition', Path(__file__).resolve().parents[1] / 'scripts/adquirir_marte.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class Response(io.BytesIO):
    def __init__(self, body=b'x', status=206, headers=None):
        super().__init__(body)
        self.status = status
        self.headers = headers or {'Content-Range': 'bytes 0-0/3', 'Content-Length': '1', 'ETag': '"v1"'}


class MarsAcquisitionTests(unittest.TestCase):
    def tiny_plan(self):
        plan = m.discover()
        entry = {'url': m.DIRECTORY + 'frt000047a3_07_sr166j_mtr3.img',
                 'path': m.FOLDER + '/frt000047a3_07_sr166j_mtr3.img', 'bytes': 3,
                 'role': 'refined_spectral_summary_parameters', 'expected_sha256': None, 'status': 'planned'}
        plan['files'] = [entry]
        return plan

    def test_discovery_is_offline_bounded_and_preserves_required_metadata(self):
        with patch.object(m, 'request', side_effect=AssertionError('network')):
            plan, full = m.discover(), m.discover('full')
        self.assertEqual(len(plan['files']), 7)
        self.assertEqual(len(full['files']), 13)
        self.assertEqual(sum(e['bytes'] for e in plan['files']), 188972526)
        self.assertEqual(sum(e['bytes'] for e in full['files']) - sum(e['bytes'] for e in plan['files']), 1338694468)
        self.assertTrue(all(e['expected_sha256'] for e in plan['files'] if e['role'] == 'metadata'))
        self.assertFalse(any('_if166j_' in e['path'] for e in plan['files']))

    def test_plan_rejects_tampered_sources_inventory_urls_sizes_and_paths(self):
        original = m.discover()
        changes = [('source_sha256', 'bad'), ('metadata_sha256', 'bad'), ('package', 'other')]
        for key, value in changes:
            plan = copy.deepcopy(original); plan[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                m.validate_plan(plan)
        for key, value in [('path', '../escape'), ('url', 'https://example.com/file'), ('bytes', 1), ('expected_sha256', None)]:
            plan = copy.deepcopy(original); plan['files'][0][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                m.validate_plan(plan)
        plan = copy.deepcopy(original); plan['files'].append(plan['files'][0])
        with self.assertRaises(ValueError):
            m.validate_plan(plan)

    def test_public_requests_never_load_tokens_and_reject_credentials_or_foreign_hosts(self):
        opener = MagicMock()
        url = m.discover()['files'][0]['url']
        with patch.dict(os.environ, {'EARTHDATA_TOKEN': 'test-secret'}), patch.object(m.urllib.request, 'build_opener', return_value=opener):
            m.request(url)
            self.assertIsNone(opener.open.call_args.args[0].get_header('Authorization'))
            for unsafe in ('http://example.com/x', url + '?token=test-secret', url.replace('pds-geosciences.wustl.edu', 'example.com')):
                with self.assertRaises(ValueError):
                    m.request(unsafe)
            with self.assertRaises(ValueError):
                m.request(url, headers={'Authorization': 'Bearer test-secret'})
            self.assertNotIn('test-secret', json.dumps(m.discover()))
        with self.assertRaises(ValueError):
            m.PublicRedirect().redirect_request(urllib.request.Request(url), None, 302, 'Found', {}, 'https://example.com/file')

    def test_probe_reads_one_byte_and_uses_total_size(self):
        plan = self.tiny_plan()
        with patch.object(m, 'request', return_value=Response()) as request:
            m.inspect(plan['files'][0])
        request.assert_called_once_with(plan['files'][0]['url'], headers={'Range': 'bytes=0-0'})
        self.assertEqual(plan['files'][0]['bytes'], 3)
        self.assertEqual(plan['files'][0]['etag'], '"v1"')

    def test_probe_rejects_unknown_changed_or_invalid_ranges_and_html(self):
        responses = [Response(headers={'Content-Range': 'bytes 0-0/*'}),
                     Response(headers={'Content-Range': 'bytes 0-0/4'}),
                     Response(headers={'Content-Range': 'bytes 0-1/3'}),
                     Response(body=b''), Response(headers={'Content-Type': 'text/html'}),
                     Response(headers={'Content-Encoding': 'gzip'})]
        for response in responses:
            with self.subTest(headers=response.headers), patch.object(m, 'request', return_value=response), self.assertRaises(ValueError):
                m.inspect(self.tiny_plan()['files'][0])

    def test_ignored_range_does_not_read_whole_image(self):
        response = Response(status=200, headers={'Content-Length': '3'})
        with patch.object(response, 'read', side_effect=AssertionError('must not read')), patch.object(m, 'request', return_value=response):
            m.inspect(self.tiny_plan()['files'][0])
        self.assertTrue(response.closed)

    def test_budget_and_disk_preflight_prevent_all_network_and_downloads(self):
        for budget in (.0001, float('nan'), float('inf'), 0, 11):
            with self.subTest(budget=budget), patch.object(m, 'request') as request, self.assertRaises(ValueError):
                m.fetch(m.discover('full'), budget)
            request.assert_not_called()
        with patch.object(m.shutil, 'disk_usage', return_value=MagicMock(free=1)), patch.object(m, 'request') as request:
            with self.assertRaisesRegex(ValueError, 'Espacio'):
                m.fetch(m.discover(), .25)
            request.assert_not_called()

    def test_unavailable_product_prevents_partial_package_transfer(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(m.transport, 'RAW', Path(folder)), patch.object(m, 'inspect', side_effect=ValueError('unavailable')), patch.object(m.transport, 'fetch_with_retries') as download:
            self.assertEqual(m.fetch(m.discover(), .25), 7)
            download.assert_not_called()

    def test_fetch_verify_report_repeat_and_changed_original(self):
        plan = self.tiny_plan()
        expected = copy.deepcopy(plan['files'])
        def request(url, method='GET', headers=None):
            if headers and headers.get('Range') == 'bytes=0-0':
                return Response()
            return Response(b'abc', 200, {'ETag': '"v1"', 'Content-Length': '3'})
        with tempfile.TemporaryDirectory() as folder, patch.object(m.transport, 'RAW', Path(folder)), patch.object(m, 'selected_files', return_value=expected), patch.object(m, 'request', request), patch.object(m.transport, 'request', request):
            self.assertEqual(m.fetch(plan), 0)
            report = Path(folder) / 'report.json'
            self.assertEqual(m.verify(plan, report), 0)
            self.assertTrue(json.loads(report.read_text())['complete'])
            with patch.object(m, 'request', side_effect=AssertionError('network')):
                self.assertEqual(m.fetch(plan), 0)
            path = m.transport.safe_path(plan['files'][0]['path'])
            path.write_bytes(b'bad')
            self.assertEqual(m.fetch(plan), 1)
            self.assertEqual(path.read_bytes(), b'bad')
            self.assertEqual(m.verify(plan, report), 1)
            self.assertFalse(json.loads(report.read_text())['complete'])

    def test_failed_redownload_keeps_previous_science_hash_binding(self):
        plan = self.tiny_plan(); expected = copy.deepcopy(plan['files'])
        sha = hashlib.sha256(b'abc').hexdigest()
        plan['files'][0]['sha256'] = sha
        def download(entry, ceiling):
            self.assertEqual(entry['expected_sha256'], sha)
            entry.pop('sha256', None)
            raise ValueError('checksum differs')
        with tempfile.TemporaryDirectory() as folder, patch.object(m.transport, 'RAW', Path(folder)), patch.object(m, 'selected_files', return_value=expected), patch.object(m, 'inspect'), patch.object(m.transport, 'fetch_with_retries', side_effect=download):
            self.assertEqual(m.fetch(plan), 1)
            self.assertEqual(plan['files'][0]['sha256'], sha)
            self.assertIsNone(plan['files'][0]['expected_sha256'])

    def test_completed_transfer_persists_identity_before_return(self):
        plan = self.tiny_plan(); expected = copy.deepcopy(plan['files'])
        snapshots = []
        def download(entry, ceiling):
            entry.update(status='downloaded', sha256=hashlib.sha256(b'abc').hexdigest())
        with tempfile.TemporaryDirectory() as folder, patch.object(m.transport, 'RAW', Path(folder)), patch.object(m, 'selected_files', return_value=expected), patch.object(m, 'inspect'), patch.object(m.transport, 'fetch_with_retries', side_effect=download):
            m.fetch(plan, on_update=lambda: snapshots.append(copy.deepcopy(plan)))
        self.assertTrue(any(s['files'][0].get('sha256') for s in snapshots))

    def test_reuse_plan_requires_validated_inventory_and_matching_local_bytes(self):
        plan = self.tiny_plan(); expected = copy.deepcopy(plan['files'])
        plan['files'][0]['sha256'] = hashlib.sha256(b'abc').hexdigest()
        with tempfile.TemporaryDirectory() as folder, patch.object(m.transport, 'RAW', Path(folder)), patch.object(m, 'selected_files', side_effect=lambda package: copy.deepcopy(expected)):
            path = m.transport.safe_path(plan['files'][0]['path'])
            path.parent.mkdir(parents=True); path.write_bytes(b'abc')
            reused = m.discover('full', plan)
            self.assertEqual(reused['files'][0]['sha256'], plan['files'][0]['sha256'])
            path.write_bytes(b'bad')
            clean = m.discover('full', plan)
            self.assertNotIn('sha256', clean['files'][0])
            plan['source_sha256'] = 'changed'
            with self.assertRaises(ValueError):
                m.discover('full', plan)

    def test_interrupted_stream_resumes_exact_range_with_validator(self):
        plan = self.tiny_plan(); plan['files'][0]['bytes'] = 6
        expected = copy.deepcopy(plan['files']); calls = []
        class Broken(Response):
            def read(self, n=-1):
                chunk = super().read(n)
                if not chunk:
                    raise OSError('interrupted')
                return chunk
        def request(url, method='GET', headers=None):
            calls.append(headers)
            if headers and headers.get('Range') == 'bytes=0-0':
                return Response(headers={'Content-Range': 'bytes 0-0/6', 'ETag': '"v1"'})
            if headers and headers.get('Range') == 'bytes=3-':
                self.assertEqual(headers['If-Range'], '"v1"')
                return Response(b'def', 206, {'Content-Range': 'bytes 3-5/6', 'ETag': '"v1"'})
            return Broken(b'abc', 200, {'ETag': '"v1"'})
        with tempfile.TemporaryDirectory() as folder, patch.object(m.transport, 'RAW', Path(folder)), patch.object(m, 'selected_files', return_value=expected), patch.object(m, 'request', request), patch.object(m.transport, 'request', request), patch.object(m.transport.time, 'sleep'):
            self.assertEqual(m.fetch(plan), 0)
            self.assertEqual(m.transport.safe_path(plan['files'][0]['path']).read_bytes(), b'abcdef')
            self.assertTrue(any(h and h.get('Range') == 'bytes=3-' for h in calls))


if __name__ == '__main__':
    unittest.main()
