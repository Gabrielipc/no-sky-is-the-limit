"""Tests for skip/resume batch tracking and async producer-consumer streaming cleanup."""
from __future__ import annotations

import argparse
from pathlib import Path
import tempfile
import unittest

import numpy as np
import rasterio
from rasterio.transform import from_origin

from pipelines import atlas_sources as sources
from pipelines import atlas_topography as topo
from pipelines import etl_extractors as ex
from pipelines import etl_stream as stream_engine
from pipelines.etl_store import FeatureStore
from scripts import etl_pipeline as cli


class TestETLStreamAndSkip(unittest.TestCase):
    def test_skip_resume_filters_completed_batches(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = FeatureStore(Path(tmp) / 'store')
            batches = list(topo.benchmark_batches())[:2]
            store.mark_batch_completed(batches[0].id, {'batch_id': batches[0].id, 'status': 'complete',
                                                       'identity': ex.run_identity(10000)})
            self.assertIn(batches[0].id, store.completed_batch_ids())

            args_skip = argparse.Namespace(
                scope='pilot', mode='auto', start=0, max_batches=0, overwrite=False
            )
            pending = cli._select_batches(args_skip, store)
            self.assertNotIn(batches[0].id, [b.id for b in pending])
            self.assertIn(batches[1].id, [b.id for b in pending])

            args_overwrite = argparse.Namespace(
                scope='pilot', mode='auto', start=0, max_batches=0, overwrite=True
            )
            all_selected = cli._select_batches(args_overwrite, store)
            self.assertEqual(len(all_selected), 5)

    def test_stream_downloads_processes_and_cleans_temp_files(self) -> None:
        # Use a batch that has no local cache or fake a synthetic tile via downloader.
        batch = topo.Batch(zone=32612, west=484000, south=4222000, label='desierto')
        downloads: list[str] = []

        def fake_downloader(entry: dict, tmp_dir: Path) -> tuple[str, Path | None, int]:
            downloads.append(entry['id'])
            target = tmp_dir / entry['id']
            data = np.full((120, 120), 1500.0, dtype='float32')
            transform = from_origin(-111.0, 39.0, 1.0 / 120.0, 1.0 / 120.0)
            with rasterio.open(
                target, 'w', driver='GTiff', height=120, width=120, count=1,
                dtype='float32', crs='EPSG:4326', transform=transform,
            ) as dst:
                dst.write(data, 1)
            return entry['id'], target, target.stat().st_size

        # Temporarily pretend no local tile cache exists (keeping inventory/land) so fake_downloader runs.
        orig_local_id = sources.local_identity
        sources.local_identity = (
            lambda entry: None if entry.get('id', '').endswith(('.tif', '.TIF')) else orig_local_id(entry)
        )
        try:
            with tempfile.TemporaryDirectory() as tmp:
                store_dir = Path(tmp) / 'store'
                summary = stream_engine.run_stream(
                    batches=[batch],
                    store_dir=store_dir,
                    stride=10000,
                    include_cover=False,
                    cpu_workers=1,
                    io_workers=2,
                    max_temp_gb=1.0,
                    memory_limit='512MB',
                    threads=2,
                    downloader=fake_downloader,
                )
                self.assertEqual(summary['processed_batches'], 1)
                self.assertGreater(summary['downloaded_tiles'], 0)
                self.assertEqual(summary['deleted_tiles'], summary['downloaded_tiles'])
                self.assertFalse((store_dir / '.stream_tmp').exists())

                store = FeatureStore(store_dir)
                self.assertIn(batch.id, store.completed_batch_ids())
                stats = store.store_stats()
                self.assertEqual(stats['total_windows'], 100)
        finally:
            sources.local_identity = orig_local_id

    def test_stream_evicts_and_never_stalls_when_temp_budget_is_tiny(self) -> None:
        batches = [
            topo.Batch(zone=32612, west=484000, south=4222000, label='b1'),
            topo.Batch(zone=32613, west=484000, south=4222000, label='b2'),
        ]

        def fake_downloader(entry: dict, tmp_dir: Path) -> tuple[str, Path | None, int]:
            target = tmp_dir / entry['id']
            data = np.full((60, 60), 1500.0, dtype='float32')
            transform = from_origin(-111.0, 39.0, 1.0 / 60.0, 1.0 / 60.0)
            with rasterio.open(
                target, 'w', driver='GTiff', height=60, width=60, count=1,
                dtype='float32', crs='EPSG:4326', transform=transform,
            ) as dst:
                dst.write(data, 1)
            return entry['id'], target, target.stat().st_size

        orig_local_id = sources.local_identity
        sources.local_identity = (
            lambda entry: None if entry.get('id', '').endswith(('.tif', '.TIF')) else orig_local_id(entry)
        )
        try:
            with tempfile.TemporaryDirectory() as tmp:
                store_dir = Path(tmp) / 'store'
                summary = stream_engine.run_stream(
                    batches=batches,
                    store_dir=store_dir,
                    stride=10000,
                    include_cover=False,
                    cpu_workers=1,
                    io_workers=2,
                    max_temp_gb=0.00001,  # ~10 KB: smaller than a single synthetic GeoTIFF
                    memory_limit='512MB',
                    threads=2,
                    downloader=fake_downloader,
                )
                self.assertEqual(summary['processed_batches'], 2)
                self.assertFalse((store_dir / '.stream_tmp').exists())
        finally:
            sources.local_identity = orig_local_id


if __name__ == '__main__':
    unittest.main()
