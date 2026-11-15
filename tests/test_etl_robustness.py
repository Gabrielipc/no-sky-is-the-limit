"""Tests for failure causes, retries, cover status and identity-aware resume of the sweep."""
from __future__ import annotations

import argparse
from contextlib import ExitStack
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import httpx
import numpy as np
import rasterio
from rasterio.transform import from_origin

from pipelines import atlas_sources as sources
from pipelines import atlas_topography as topo
from pipelines import etl_extractors as ex
from pipelines import etl_stream as stream_engine
from pipelines.etl_store import FeatureStore
from scripts import etl_pipeline as cli

DESERT = topo.Batch(zone=32612, west=484000, south=4222000, label='desierto')


def synthetic_dem(path: Path) -> None:
    lon = np.linspace(0, 1, 120, dtype='float32')
    data = 1500.0 + 300.0 * np.tile(lon, (120, 1))
    with rasterio.open(path, 'w', driver='GTiff', height=120, width=120, count=1, dtype='float32',
                       crs='EPSG:4326', transform=from_origin(-111.0, 39.0, 1 / 120, 1 / 120)) as dst:
        dst.write(data.astype('float32'), 1)


class FakeRasters(topo.Rasters):
    """DEM from a synthetic file; every other asset fails with `cover_cause` (or DEM with `dem_cause`)."""

    def __init__(self, stack, dem_path, dem_cause=None, cover_cause='http_404'):
        super().__init__(stack, 'cache')
        self.dem_path, self.dem_cause, self.cover_cause = dem_path, dem_cause, cover_cause

    def get(self, entry):
        key = entry['id']
        if key in self.opened or key in self.unavailable:
            return self.opened.get(key)
        cause = self.dem_cause if entry['source'] == 'glo30' else self.cover_cause
        if entry['source'] == 'glo30' and cause is None:
            self.opened[key] = self.stack.enter_context(rasterio.open(self.dem_path))
            self.identities[key] = {'status': 'synthetic'}
            return self.opened[key]
        self.unavailable.add(key)
        self.failures[key] = cause
        return None


def first_site():
    """A window whose footprint and halo lie inside the synthetic 1° DEM tile."""
    return next(s for s in topo.windows(DESERT, 10000)
                if -110.9 < s['longitude'] < -110.1 and 38.1 < s['latitude'] < 38.9)


class TestFailureCauses(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        cls.dem = Path(cls.tmp.name) / 'dem.tif'
        synthetic_dem(cls.dem)
        cls.land = topo.Land()
        cls.inventory = sources.glo_inventory()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def extract(self, **kwargs) -> tuple[dict, FakeRasters]:
        with ExitStack() as stack:
            rasters = FakeRasters(stack, str(self.dem), **kwargs)
            row, _ = ex.extract_base_window(first_site(), self.land, rasters, self.inventory, include_cover=True)
            return row, rasters

    def test_dem_access_failure_is_not_a_catalogue_gap(self) -> None:
        row, rasters = self.extract(dem_cause='network_error: ConnectError')
        self.assertEqual(row['qa_status'], 'dem_fetch_failed')
        outcome = ex.batch_outcome([row], rasters, ex.run_identity(10000))
        self.assertEqual(outcome['status'], 'incomplete')
        self.assertIn('network_error: ConnectError', outcome['failed_assets'].values())

    def test_missing_dem_tile_is_a_catalogue_gap(self) -> None:
        row, rasters = self.extract(dem_cause='http_404')
        self.assertEqual(row['qa_status'], 'dem_unavailable')
        self.assertEqual(ex.batch_outcome([row], rasters, ex.run_identity(10000))['status'], 'complete')

    def test_missing_cover_tile_and_cover_failure(self) -> None:
        row, rasters = self.extract(cover_cause='http_404')
        self.assertEqual(row['qa_status'], 'rankable')
        self.assertEqual(row['cover_status'], 'no_cover_tile')
        self.assertEqual(row['analog_surface_eligibility'], 'pending_on_demand_cover_check')
        self.assertEqual(ex.batch_outcome([row], rasters, ex.run_identity(10000))['status'], 'complete')

        row, rasters = self.extract(cover_cause='read_error: timeout')
        self.assertEqual(row['cover_status'], 'cover_fetch_failed')
        self.assertIsNone(row['cover_valid_fraction'])
        self.assertIsNone(row['bare_or_sparse_fraction'])
        self.assertEqual(ex.batch_outcome([row], rasters, ex.run_identity(10000))['status'], 'incomplete')


class TestStreamFallback(unittest.TestCase):
    def test_missing_tile_after_failed_download_stays_a_catalogue_gap(self) -> None:
        with ExitStack() as stack:
            rasters = stream_engine.StreamRasters(stack, {}, {'wc.tif': 'http_404', 'jrc.tif': 'http_503'})
            # Replace the range attempt of the base class with known outcomes (no network).
            original = topo.Rasters.get

            def fake_get(self, entry):
                self.unavailable.add(entry['id'])
                self.failures[entry['id']] = 'http_404' if entry['id'] == 'wc.tif' else 'network_error: Timeout'
                return None

            topo.Rasters.get = fake_get
            try:
                rasters.get({'id': 'wc.tif', 'source': 'worldcover', 'url': 'u'})
                rasters.get({'id': 'jrc.tif', 'source': 'jrc', 'url': 'u'})
            finally:
                topo.Rasters.get = original
            self.assertEqual(rasters.failures['wc.tif'], 'http_404')
            self.assertEqual(rasters.failures['jrc.tif'], 'http_503; range: network_error: Timeout')
            self.assertEqual(ex.asset_failures(rasters, [{'id': 'wc.tif'}, {'id': 'jrc.tif'}]),
                             {'jrc.tif': 'http_503; range: network_error: Timeout'})


class TestDownloadRetries(unittest.TestCase):
    def client(self, statuses: list) -> tuple[httpx.Client, list]:
        calls = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(request.url)
            status = statuses[min(len(calls) - 1, len(statuses) - 1)]
            if status == 'error':
                raise httpx.ConnectError('down', request=request)
            return httpx.Response(status, content=b'tile' if status == 200 else b'')

        return httpx.Client(transport=httpx.MockTransport(handler)), calls

    def download(self, statuses: list) -> tuple[tuple, list]:
        client, calls = self.client(statuses)
        with tempfile.TemporaryDirectory() as tmp:
            result = stream_engine.download_tile_to_temp(
                {'id': 't.tif', 'url': 'https://example.invalid/t.tif'}, Path(tmp),
                client=client, sleep=lambda s: None)
            return (result[0], result[1] is not None, result[2], result[3]), calls

    def test_transient_error_is_retried(self) -> None:
        result, calls = self.download([503, 'error', 200])
        self.assertEqual(result, ('t.tif', True, 4, None))
        self.assertEqual(len(calls), 3)

    def test_missing_tile_is_not_retried(self) -> None:
        result, calls = self.download([404])
        self.assertEqual(result, ('t.tif', False, 0, 'http_404'))
        self.assertEqual(len(calls), 1)

    def test_persistent_failure_reports_cause(self) -> None:
        result, calls = self.download(['error'])
        self.assertEqual(result[3], 'network_error: ConnectError')
        self.assertEqual(len(calls), 3)


class TestDirBytes(unittest.TestCase):
    def test_file_vanishing_mid_scan_is_skipped(self) -> None:
        from pipelines import etl_stream
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'a.tif').write_bytes(b'x' * 10)
            gone = root / '.b.tif.part'
            gone.write_bytes(b'y' * 5)
            real_iterdir = Path.iterdir

            def iterdir_then_delete(self):
                items = list(real_iterdir(self))
                gone.unlink()
                return iter(items)

            with mock.patch.object(Path, 'iterdir', iterdir_then_delete):
                self.assertEqual(etl_stream._dir_bytes(root), 10)
            self.assertEqual(etl_stream._dir_bytes(root / 'missing'), 0)


class TestResume(unittest.TestCase):
    def test_identity_and_incomplete_batches(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = FeatureStore(Path(tmp) / 'store')
            batches = list(topo.benchmark_batches())
            legacy, complete, incomplete, other_stride = (b.id for b in batches[:4])
            store.mark_batch_completed(legacy, {'batch_id': legacy})
            store.mark_batch_completed(complete, {'status': 'complete', 'identity': ex.run_identity(10000)})
            store.mark_batch_completed(incomplete, {'status': 'incomplete', 'identity': ex.run_identity(10000)})
            store.mark_batch_completed(other_stride, {'status': 'complete', 'identity': ex.run_identity(3000)})

            # Legacy records predate the shape descriptors and cover_status: always reprocessed.
            self.assertEqual(store.completed_batch_ids(ex.run_identity(10000)), {complete})
            self.assertEqual(store.completed_batch_ids(ex.LEGACY_RUN_IDENTITY), {legacy})
            self.assertEqual(store.completed_batch_ids(ex.run_identity(3000)), {other_stride})
            self.assertEqual(store.incomplete_batch_ids(), {incomplete})

            args = argparse.Namespace(scope='pilot', mode='auto', start=0, max_batches=0, overwrite=False,
                                      stride=10000)
            pending = {b.id for b in cli._select_batches(args, store)}
            self.assertEqual(pending, {legacy, incomplete, other_stride, batches[4].id})


if __name__ == '__main__':
    unittest.main()
