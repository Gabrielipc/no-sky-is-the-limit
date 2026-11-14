"""Producer-Consumer async streaming ETL: Prefetch raw tiles -> CPU process -> Immediate cleanup."""
from __future__ import annotations

from collections import Counter
from concurrent.futures import FIRST_COMPLETED, Future, ProcessPoolExecutor, ThreadPoolExecutor, wait
from contextlib import ExitStack
from datetime import datetime, timezone
from pathlib import Path
import shutil
import time
from typing import Callable

import httpx
import rasterio

from pipelines import atlas_sources as sources
from pipelines import atlas_topography as topo
from pipelines import etl_extractors as extractors
from pipelines.etl_store import FeatureStore


class StreamRasters(topo.Rasters):
    """Rasters reader that checks ephemeral stream files before permanent local cache."""

    def __init__(self, stack: ExitStack, local_overrides: dict[str, Path]) -> None:
        super().__init__(stack, mode='cache')
        self.local_overrides = local_overrides

    def get(self, entry: dict):
        key = entry['id']
        if key in self.opened or key in self.unavailable:
            return self.opened.get(key)
        override = self.local_overrides.get(key)
        if override is not None and override.is_file():
            self.opened[key] = self.stack.enter_context(rasterio.open(str(override)))
            self.identities[key] = {'id': key, 'status': 'stream_temp', 'bytes': override.stat().st_size}
            return self.opened[key]
        return super().get(entry)


_WORKER_LAND: topo.Land | None = None
_WORKER_INVENTORY: dict | None = None


def _init_worker() -> None:
    global _WORKER_LAND, _WORKER_INVENTORY
    _WORKER_LAND = topo.Land()
    _WORKER_INVENTORY = sources.glo_inventory()


def download_tile_to_temp(
    entry: dict,
    tmp_dir: Path,
    timeout_s: float = 60.0,
    client: httpx.Client | None = None,
) -> tuple[str, Path | None, int]:
    """Download a single remote tile atomically into ephemeral tmp_dir."""
    target = tmp_dir / entry['id']
    if target.is_file():
        return entry['id'], target, target.stat().st_size
    part = tmp_dir / f'.{entry["id"]}.part'
    try:
        ctx = (
            client.stream('GET', entry['url'], follow_redirects=True, timeout=timeout_s)
            if client is not None
            else httpx.stream('GET', entry['url'], follow_redirects=True, timeout=timeout_s)
        )
        with ctx as resp:
            if resp.status_code != 200:
                return entry['id'], None, 0
            written = 0
            with part.open('wb') as fh:
                for chunk in resp.iter_bytes(chunk_size=1024 * 256):
                    fh.write(chunk)
                    written += len(chunk)
        part.replace(target)
        return entry['id'], target, written
    except (httpx.HTTPError, OSError):
        part.unlink(missing_ok=True)
        return entry['id'], None, 0


def _process_stream_batch(
    batch: topo.Batch,
    stride: int,
    include_cover: bool,
    store_dir: str,
    memory_limit: str,
    threads: int,
    local_overrides: dict[str, str],
) -> tuple[str, str, int, int, float]:
    started = time.perf_counter()
    land = _WORKER_LAND if _WORKER_LAND is not None else topo.Land()
    inventory = _WORKER_INVENTORY if _WORKER_INVENTORY is not None else sources.glo_inventory()
    store = FeatureStore(Path(store_dir), memory_limit=memory_limit, threads=threads)
    override_paths = {k: Path(v) for k, v in local_overrides.items()}
    rows = []
    manifests = []
    with ExitStack() as stack:
        stack.enter_context(rasterio.Env(
            GDAL_DISABLE_READDIR_ON_OPEN='EMPTY_DIR',
            GDAL_CACHEMAX=256 * 1024 ** 2,
        ))
        rasters = StreamRasters(stack, override_paths)
        for site in topo.windows(batch, stride):
            row, m_rows = extractors.extract_base_window(
                site, land, rasters, inventory, include_cover=include_cover
            )
            rows.append(row)
            manifests.extend(m_rows)
    written = store.write_base_batch(batch.id, rows, manifests)
    store.mark_batch_completed(batch.id, {
        'batch_id': batch.id,
        'label': batch.label,
        'windows': len(rows),
        'partitions': len(written),
        'mode': 'stream',
        'completed_at': datetime.now(timezone.utc).isoformat(),
    })
    return batch.label, batch.id, len(rows), len(written), time.perf_counter() - started


def _dir_bytes(path: Path) -> int:
    return sum(p.stat().st_size for p in path.iterdir() if p.is_file()) if path.exists() else 0


def run_stream(
    batches: list[topo.Batch],
    store_dir: Path,
    stride: int = 10000,
    include_cover: bool = True,
    cpu_workers: int = 8,
    io_workers: int = 12,
    max_temp_gb: float = 4.0,
    memory_limit: str = '6GB',
    threads: int = 4,
    downloader: Callable[[dict, Path], tuple[str, Path | None, int]] | None = None,
) -> dict:
    """Stream remote tiles into ephemeral cache, process in parallel, and delete immediately."""
    if not batches:
        return {'processed_batches': 0, 'downloaded_tiles': 0, 'downloaded_bytes': 0, 'deleted_tiles': 0}

    # Spatial sort maximizes contiguous tile reuse before deletion.
    ordered = sorted(batches, key=lambda b: (b.zone, b.south, b.west))
    inventory = sources.glo_inventory()
    tmp_dir = store_dir / '.stream_tmp'
    tmp_dir.mkdir(parents=True, exist_ok=True)

    fetch_fn = downloader or download_tile_to_temp
    max_temp_bytes = int(max_temp_gb * (1024 ** 3))
    prefetch_limit = max(cpu_workers * 2, io_workers)

    # Precompute needed non-cached assets per batch and reference counts.
    batch_needs: dict[str, list[dict]] = {}
    ref_counts: Counter[str] = Counter()
    for batch in ordered:
        entries, _ = topo.batch_assets(batch, inventory, context=include_cover)
        needed = [e for e in entries if sources.local_identity(e) is None]
        batch_needs[batch.id] = needed
        for e in needed:
            ref_counts[e['id']] += 1

    download_futures: dict[str, Future] = {}
    local_paths: dict[str, Path | None] = {}
    cpu_futures: dict[Future, tuple[topo.Batch, list[str]]] = {}
    pending_download: list[tuple[topo.Batch, list[dict]]] = []

    next_idx = 0
    downloaded_tiles = 0
    downloaded_bytes = 0
    deleted_tiles = 0
    processed_batches = 0

    try:
        limits = httpx.Limits(max_connections=io_workers, max_keepalive_connections=io_workers)
        with httpx.Client(limits=limits) as http_client, \
             ThreadPoolExecutor(max_workers=io_workers) as io_pool, \
             ProcessPoolExecutor(max_workers=cpu_workers, initializer=_init_worker) as cpu_pool:

            def submit_download(entry: dict) -> Future:
                if downloader is not None:
                    return io_pool.submit(downloader, entry, tmp_dir)
                return io_pool.submit(download_tile_to_temp, entry, tmp_dir, 60.0, http_client)

            while next_idx < len(ordered) or pending_download or cpu_futures:
                # 1. Enqueue prefetch downloads while respecting temp disk budget & in-flight limit.
                while (
                    next_idx < len(ordered)
                    and len(pending_download) + len(cpu_futures) < prefetch_limit
                    and _dir_bytes(tmp_dir) < max_temp_bytes
                ):
                    batch = ordered[next_idx]
                    next_idx += 1
                    needed = batch_needs[batch.id]
                    for entry in needed:
                        aid = entry['id']
                        if aid not in local_paths and aid not in download_futures:
                            download_futures[aid] = submit_download(entry)
                    pending_download.append((batch, needed))

                # 2. Collect completed downloads without blocking if CPU can start.
                done_aids = [aid for aid, fut in download_futures.items() if fut.done()]
                for aid in done_aids:
                    fut = download_futures.pop(aid)
                    _, path, nbytes = fut.result()
                    local_paths[aid] = path
                    if path is not None:
                        downloaded_tiles += 1
                        downloaded_bytes += nbytes

                # 3. Promote ready batches to CPU worker pool.
                still_waiting: list[tuple[topo.Batch, list[dict]]] = []
                for batch, needed in pending_download:
                    if all(e['id'] in local_paths for e in needed):
                        overrides = {
                            e['id']: str(local_paths[e['id']])
                            for e in needed
                            if local_paths[e['id']] is not None
                        }
                        cpu_fut = cpu_pool.submit(
                            _process_stream_batch,
                            batch, stride, include_cover, str(store_dir),
                            memory_limit, threads, overrides,
                        )
                        cpu_futures[cpu_fut] = (batch, [e['id'] for e in needed])
                    else:
                        still_waiting.append((batch, needed))
                pending_download = still_waiting

                # 4. Wait for either a CPU batch or a download to finish.
                wait_set: list[Future] = list(cpu_futures.keys()) + list(download_futures.values())
                if not wait_set:
                    if next_idx < len(ordered):
                        # Evict idle temp tiles held for far-future batches so backpressure never stalls.
                        active_ids = {
                            e['id'] for _, needs in pending_download for e in needs
                        } | {
                            aid for _, aids in cpu_futures.values() for aid in aids
                        }
                        evicted = 0
                        for aid in list(local_paths.keys()):
                            if aid not in active_ids:
                                path = local_paths.pop(aid, None)
                                if path is not None and path.exists():
                                    path.unlink(missing_ok=True)
                                    evicted += 1
                        if evicted > 0:
                            continue
                        # Force-enqueue at least one batch if temp dir still exceeds cap.
                        batch = ordered[next_idx]
                        next_idx += 1
                        needed = batch_needs[batch.id]
                        for entry in needed:
                            aid = entry['id']
                            if aid not in local_paths and aid not in download_futures:
                                download_futures[aid] = submit_download(entry)
                        pending_download.append((batch, needed))
                        continue
                    break
                done, _ = wait(wait_set, return_when=FIRST_COMPLETED)

                for fut in done:
                    if fut in cpu_futures:
                        batch, used_ids = cpu_futures.pop(fut)
                        label, bid, n_rows, n_parts, elapsed = fut.result()
                        processed_batches += 1
                        for aid in used_ids:
                            ref_counts[aid] -= 1
                            if ref_counts[aid] <= 0:
                                path = local_paths.pop(aid, None)
                                if path is not None and path.exists():
                                    path.unlink(missing_ok=True)
                                    deleted_tiles += 1
                        print(
                            f'[stream] {label} {bid}: {n_rows} ventanas -> {n_parts} part ({elapsed:.2f} s) | '
                            f'tmp={_dir_bytes(tmp_dir) / (1024**2):.1f} MB',
                            flush=True,
                        )
                    else:
                        # Download finished; will be collected at top of loop.
                        pass
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    return {
        'processed_batches': processed_batches,
        'downloaded_tiles': downloaded_tiles,
        'downloaded_bytes': downloaded_bytes,
        'deleted_tiles': deleted_tiles,
    }
