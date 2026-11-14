import importlib.util
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('retrieval', Path(__file__).resolve().parents[1] / 'scripts/recolectar_datos.py')
r = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)


class Response(io.BytesIO):
    def __init__(self, data, headers=None):
        super().__init__(data)
        self.headers = headers or {}


class RetrievalTests(unittest.TestCase):
    def test_discovery_only_selects_relevant_files(self):
        html = b'<a href="megt44n000hb.img">x</a><a href="megr44n000hb.img">x</a><a href="megc44n000hb.xml">x</a>'
        def fake(url, method='GET', headers=None):
            return Response(html if method == 'GET' else b'', {'Content-Length': '10'})
        with patch.object(r, 'request', fake):
            plan = r.discover(['mola'])
        self.assertEqual(len(plan['files']), 2)
        self.assertTrue(all(x['bytes'] == 10 for x in plan['files']))

    def test_pds_absolute_links_and_safe_filtering(self):
        base = r.LOLA
        html = (f'<A HREF="{base}ldem_64_float.img">image</A>'
                f'<a href="{base}ldem_64_float.lbl">label</a>'
                f'<a href="/lro/lro-l-lola-3-rdr-v1/lrolol_1xxx/data/lola_gdr/cylindrical/float_img/ldem_64_float.xml">xml</a>'
                '<a href="https://untrusted.example/ldem_64_float.img">bad</a>')
        urls = r.index_urls(html, base, r.SOURCES['lola']['pattern'])
        self.assertEqual(len(urls), 3)
        self.assertTrue(all(u.startswith(base) for u in urls))

    def test_fetch_verify_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(r, 'RAW', Path(tmp)), patch.object(r, 'request', return_value=Response(b'abc', {'Content-Type': 'application/octet-stream'})):
                entry = {'path': 'lola/file.img', 'url': 'https://example.test/file', 'bytes': 3}
                r.fetch_one(entry, 10000)
                self.assertEqual(entry['sha256'], r.digest(Path(tmp) / 'lola/file.img'))
                r.fetch_one(entry, 10000)
                self.assertEqual(entry['status'], 'verified_local')
                (Path(tmp) / 'lola/file.img').write_bytes(b'bad')
                with self.assertRaisesRegex(ValueError, 'no se sobrescribe'):
                    r.fetch_one(entry, 10000)

    def test_incomplete_and_budget_are_not_published(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(r, 'RAW', Path(tmp)), patch.object(r, 'request', return_value=Response(b'ab')):
                entry = {'path': 'x/file', 'url': 'https://example.test/file', 'bytes': 3}
                with self.assertRaisesRegex(ValueError, 'límite'):
                    r.fetch_one(entry, 2)
                with self.assertRaisesRegex(OSError, 'incompleta'):
                    r.fetch_one(entry, 10000)
                self.assertFalse((Path(tmp) / 'x/file').exists())
                self.assertTrue((Path(tmp) / 'x/file.part').exists())

    def test_resumes_legacy_partial_after_comparison(self):
        class Ranged(Response):
            status = 206
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'file.part').write_bytes(b'abc')
            entry = {'path': 'file', 'url': 'https://example.test/file', 'bytes': 6, 'etag': '"v1"'}
            requests = []
            def fake(url, method='GET', headers=None):
                requests.append(headers)
                if headers['Range'] == 'bytes=0-2':
                    return Ranged(b'abc', {'Content-Range': 'bytes 0-2/6', 'ETag': '"v1"'})
                return Ranged(b'def', {'Content-Range': 'bytes 3-5/6', 'ETag': '"v1"'})
            with patch.object(r, 'RAW', root), patch.object(r, 'request', fake):
                r.fetch_one(entry, 10000)
            self.assertEqual((root / 'file').read_bytes(), b'abcdef')
            self.assertEqual(requests[1]['If-Range'], '"v1"')

    def test_rejects_ignored_range_without_modifying_partial(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'file.part').write_bytes(b'abc')
            entry = {'path': 'file', 'url': 'https://example.test/file', 'bytes': 6, 'etag': '"v1"'}
            with patch.object(r, 'RAW', root), patch.object(r, 'request', return_value=Response(b'abcdef', {'ETag': '"v1"'})):
                with self.assertRaisesRegex(ValueError, 'rango'):
                    r.fetch_one(entry, 10000)
            self.assertEqual((root / 'file.part').read_bytes(), b'abc')

    def test_rejects_changed_partial(self):
        class Ranged(Response):
            status = 206
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'file.part').write_bytes(b'bad')
            entry = {'path': 'file', 'url': 'https://example.test/file', 'bytes': 6, 'etag': '"v1"'}
            res = Ranged(b'abc', {'Content-Range': 'bytes 0-2/6', 'ETag': '"v1"'})
            with patch.object(r, 'RAW', root), patch.object(r, 'request', return_value=res):
                with self.assertRaisesRegex(ValueError, 'difiere'):
                    r.fetch_one(entry, 10000)
            self.assertEqual((root / 'file.part').read_bytes(), b'bad')

    def test_retry_after_interrupted_stream(self):
        class Broken(Response):
            def read(self, n=-1):
                chunk = super().read(n)
                if not chunk:
                    raise OSError('conexión caída')
                return chunk
        class Ranged(Response):
            status = 206
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            entry = {'path': 'file', 'url': 'https://example.test/file', 'bytes': 6, 'etag': '"v1"'}
            def fake(url, method='GET', headers=None):
                if not headers:
                    return Broken(b'abc', {'ETag': '"v1"'})
                self.assertEqual(headers['Range'], 'bytes=3-')
                return Ranged(b'def', {'ETag': '"v1"', 'Content-Range': 'bytes 3-5/6'})
            with patch.object(r, 'RAW', root), patch.object(r, 'request', fake), patch.object(r.time, 'sleep'):
                r.fetch_with_retries(entry, 10000)
            self.assertEqual((root / 'file').read_bytes(), b'abcdef')

    def test_rejects_paths_outside_raw(self):
        with self.assertRaises(ValueError):
            r.safe_path('../outside')


if __name__ == '__main__':
    unittest.main()
