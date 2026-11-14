import unittest
from contextlib import nullcontext
from io import BytesIO
from types import SimpleNamespace
from urllib.request import Request

from pipelines import atlas_context as context, atlas_sources as sources


class AtlasContextTests(unittest.TestCase):
    def test_temporal_selection_pins_scene_bands_and_preserves_polar_gaps(self):
        assets, gaps = context.inputs(['hls', 'landsat'], ['desierto', 'polar'])
        self.assertEqual(len(assets), 26)
        self.assertEqual({tuple(item['areas']) for item in assets}, {('desierto',)})
        self.assertEqual({item['source'] for item in gaps}, {'hls', 'landsat'})
        self.assertTrue(all('?' not in item['url'] for item in assets))
        self.assertTrue(any(item['id'].endswith('.Fmask.tif') for item in assets))
        self.assertTrue(any(item['id'].endswith('_ST_QA.TIF') for item in assets))

    def test_public_layers_are_independent_of_dem_and_temporal_assets(self):
        assets, gaps = context.inputs(['worldcover'], ['desierto'])
        self.assertTrue(assets)
        self.assertEqual({item['source'] for item in assets}, {'worldcover'})
        self.assertEqual(gaps, [])

    def test_ranged_preflight_records_total_not_body_size(self):
        response = SimpleNamespace(status=206, headers={'Content-Range': 'bytes 0-0/1000', 'Content-Length': '1'})
        entry = context.scene_assets('hls', 'HLS.L30.T12SWH.2024080T180233.v2.0')[0]
        result = sources.remote_identity(entry, lambda *args: nullcontext(response), ranged=True)
        self.assertEqual(result['bytes'], 1000)

    def test_earthdata_credentials_are_stripped_on_cross_host_redirect(self):
        req = Request(f'https://{context.EARTHDATA}/asset', headers={'Authorization': 'Bearer example'})
        redirected = context.EarthdataRedirect().redirect_request(
            req, BytesIO(), 302, '', {}, 'https://example.test/file')
        self.assertNotIn('Authorization', redirected.headers)
