#!/usr/bin/env python3
"""Acquire, index and publish the offline 30 m atlas."""
import argparse
import hashlib
import json
import math
import os
import shutil
import sys
import time
from collections import Counter
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from backend.app import atlas_store as store
from pipelines import atlas_sources as sources
from pipelines import atlas_topography as topography

WORK = sources.ROOT / 'data/features/atlas30'
DAY = 86400
SCHEMA = pa.schema([
    ('region_id', pa.string()), ('batch', pa.string()), ('area', pa.string()), ('zone', pa.int32()),
    ('x', pa.int32()), ('y', pa.int32()), ('longitude', pa.float64()), ('latitude', pa.float64()),
    ('cell_m', pa.int32()), ('status', pa.string()), ('asset_ids', pa.list_(pa.string())),
    ('worldcover_assets', pa.list_(pa.string())), ('water_assets', pa.list_(pa.string())),
    ('land_fraction', pa.float32()), ('valid_elevation', pa.float32()), ('valid_slope', pa.float32()),
    ('valid_roughness', pa.float32()), ('relief_m', pa.float64()), ('roughness_m', pa.float64()),
    ('slope_p50_deg', pa.float64()), ('slope_histogram', pa.list_(pa.int32())), ('slope_cdf', pa.list_(pa.float64())),
    ('bare_fraction', pa.float32()), ('vegetation_fraction', pa.float32()), ('urban_fraction', pa.float32()),
    ('ice_fraction', pa.float32()), ('worldcover_water_fraction', pa.float32()),
    ('worldcover_valid_fraction', pa.float32()), ('water_occurrence_pct', pa.float32()),
    ('water_valid_fraction', pa.float32()),
])


def batch_path(options):
    return WORK / f'{topography.GRID_VERSION}-{options.scope}-{options.stride}-{options.mode}-context{int(options.context)}'


def batches(scope, land=None):
    if scope == 'pilot':
        return list(topography.benchmark_batches())
    identity = land.identity if land is not None else sources.local_identity(sources.inventory_assets()[0])
    if identity is None:
        raise ValueError('Falta la máscara terrestre. Ejecuta atlas30.py inventory')
    stamp = {'grid_version': topography.GRID_VERSION, 'batch_size_m': topography.BATCH_SIZE,
             'land_sha256': identity['sha256']}
    path = sources.MANIFESTS / f'world-batches-{topography.GRID_VERSION}.json'
    try:
        cached = json.loads(path.read_text())
        if cached['stamp'] == stamp and cached['batches']:
            return [topography.Batch(*coords, 'mundial') for coords in cached['batches']]
    except (FileNotFoundError, ValueError, KeyError, TypeError):
        pass
    if land is None:
        land = topography.Land()
    # Preserve the dispersed order and existing --start offsets across invocations.
    ordered = sorted(topography.world_batches(land), key=lambda batch: hashlib.sha256(batch.id.encode()).digest())
    sources.atomic_json(path, {'stamp': stamp, 'batches': [[b.zone, b.west, b.south] for b in ordered]})
    return ordered


def acquire(options, selected):
    inventory = sources.glo_inventory()
    entries, seen = {}, {}
    for batch in selected:
        assets, missing = topography.batch_assets(batch, inventory, options.context)
        seen[batch.id] = {'assets': [entry['id'] for entry in assets], 'glo30_missing': missing}
        entries.update((entry['id'], entry) for entry in assets)
    if options.plan_only:
        results = [sources.local_identity(entry) or sources.remote_identity(entry) for entry in entries.values()]
    else:
        results = sources.fetch(entries.values(), int(options.max_gb * 10**9))
    planned = {'scope': options.scope, 'batches': seen, 'assets': results,
               'estimated_new_bytes': sum(entry['bytes'] or 0 for entry in results if entry['status'] == 'available'),
               'cdse_followup': 'https://dataspace.copernicus.eu/explore-data/data-collections/copernicus-contributing-missions/collections-description/COP-DEM'}
    if options.check_cdse:
        gaps = sorted({tuple(key) for batch in seen.values() for key in batch['glo30_missing']})
        planned['cdse_lookup'] = [sources.cdse_lookup(*key) for key in gaps]
    summary = {'scope': options.scope, 'batch_count': len(seen)}
    if options.plan_only:
        summary['estimated_new_bytes'] = planned['estimated_new_bytes']
    else:
        summary['newly_verified_bytes'] = sum(entry.get('newly_verified_bytes', 0) for entry in results)
        summary['new_files'] = sum('newly_verified_bytes' in entry for entry in results)
    summary['reused_files'] = sum(entry['status'] == 'verified_local' and 'newly_verified_bytes' not in entry
                                  for entry in results)
    summary['unavailable_files'] = sum(entry['status'] not in ('verified_local', 'available') for entry in results)
    sources.atomic_json(sources.MANIFESTS / f'{options.scope}-acquisition.json', {**planned, **summary})
    print(json.dumps(summary, ensure_ascii=False), flush=True)


def run(options, land, selected):
    inventory = sources.glo_inventory()
    path = batch_path(options)
    path.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    completed = 0
    for batch in selected:
        parquet = path / (batch.id + '.parquet')
        marker = path / (batch.id + '.json')
        if marker.exists() and parquet.exists() and json.loads(marker.read_text())['sha256'] == sources.digest(parquet):
            continue
        if completed == options.max_batches or time.monotonic() - started >= options.max_hours * 3600:
            break
        rows, measured = topography.process(batch, options.stride, land, inventory, options.mode, options.context)
        for row in rows:
            counts = row['slope_histogram']
            row['slope_cdf'] = (np.cumsum(counts) / sum(counts)).tolist() if counts else None
        with TemporaryDirectory(dir=path) as work:
            pending = Path(work) / parquet.name
            pq.write_table(pa.Table.from_pylist(rows, schema=SCHEMA), pending, compression='zstd')
            measured.update(batch=batch.id, label=batch.label, bounds=batch.bounds, zone=batch.zone,
                            counts=dict(Counter(row['status'] for row in rows)), sha256=sources.digest(pending))
            pending.replace(parquet)
            sources.atomic_json(marker, measured)
        print(f'{batch.label} {batch.id}: {len(rows)} ventanas en {measured["seconds"]:.2f} s', flush=True)
        completed += 1


def publish(options, land, selected):
    if not store.TOKEN.fullmatch(options.version):
        raise ValueError('Nombre de versión inválido')
    path = batch_path(options)
    root = store.ROOT
    root.mkdir(parents=True, exist_ok=True)
    release = root / options.version
    if release.exists():
        raise FileExistsError(f'Versión ya publicada: {release}')
    with TemporaryDirectory(dir=root) as folder:
        staging = Path(folder) / options.version
        (staging / 'windows').mkdir(parents=True)
        reports = []
        identities = {}
        for batch in selected:
            parquet, marker = path / (batch.id + '.parquet'), path / (batch.id + '.json')
            if not marker.exists() or not parquet.exists():
                continue
            measured = json.loads(marker.read_text())
            if measured['sha256'] != sources.digest(parquet):
                raise ValueError(f'Lote alterado: {parquet}')
            shutil.copyfile(parquet, staging / 'windows' / parquet.name)
            for identity in measured.pop('assets'):
                prior = identities.get(identity['id'])
                if prior and (prior.get('etag'), prior.get('last_modified'), prior['bytes']) != (
                        identity.get('etag'), identity.get('last_modified'), identity['bytes']):
                    raise ValueError(f'El original cambió entre lotes: {identity["id"]}')
                identities[identity['id']] = identity
            reports.append(measured)
        if not reports:
            raise ValueError('No hay lotes completos para publicar')
        profile, _ = topography.reference()
        with store.connect(staging) as db:
            count, unique, off_scale = db.execute(
                'SELECT count(*), count(DISTINCT region_id), count(*) FILTER (WHERE cell_m != 30) FROM windows'
            ).fetchone()
            counts = dict(db.execute('SELECT status, count(*) FROM windows GROUP BY status').fetchall())
        if count != unique or off_scale:
            raise ValueError('IDs duplicados o escala inesperada en la publicación')
        manifest = {'version': options.version, 'scope': options.scope,
                    'coverage_status': 'complete_sample' if options.scope == 'world' and len(reports) == len(selected) else 'partial',
                    'window_m': topography.WINDOW, 'cell_m': topography.CELL, 'stride_m': options.stride,
                    'grid_version': topography.GRID_VERSION, 'min_land_fraction': topography.MIN_LAND,
                    'min_valid_fraction': topography.MIN_VALID, 'profile': profile, 'counts': counts,
                    'batch_count': len(reports), 'planned_batches': len(selected),
                    'normalization': store.normalization(staging, profile),
                    'normalization_method': 'Percentil 75 de cada distancia del release con mínimos de 0.25°, 5 m y 0.1 m.',
                    'source_catalog': sources.CATALOG, 'land_asset': land.identity}
        sources.atomic_json(staging / 'manifest.json', manifest)
        sources.atomic_json(staging / 'sources.json', identities)
        sources.atomic_json(staging / 'batches.json', reports)
        if options.refine:
            from pipelines.atlas_refinement import refine
            refine(staging, manifest, land, sources.glo_inventory(), options.mode)
        staging.rename(release)
    pending = root / f'.current-{os.getpid()}'
    try:
        pending.write_text(options.version + '\n')
        pending.replace(root / 'current')
    finally:
        pending.unlink(missing_ok=True)
    print(f'Publicación {options.version}: {count} ventanas, {counts.get("rankable", 0)} clasificables', flush=True)


def benchmark(options, selected):
    path = batch_path(options)
    reports = [json.loads((path / (batch.id + '.json')).read_text()) for batch in selected
               if (path / (batch.id + '.json')).exists()]
    world_count = len(batches('world'))
    if not reports:
        raise ValueError('El benchmark requiere lotes medidos')
    seconds = [report['seconds'] for report in reports if report['assets']] or [report['seconds'] for report in reports]
    assets = {asset['id']: asset for report in reports for asset in report['assets']}
    summary = {'mode': options.mode, 'scope': options.scope, 'context': options.context,
               'cell_m': 30, 'stride_m': options.stride, 'reports': reports,
               'full_asset_bytes': sum(asset['bytes'] or 0 for asset in assets.values()),
               'full_asset_bytes_note': 'Tamaño de archivos completos, no tráfico HTTP de rangos.',
               'uncompressed_source_bytes_read': sum(report['uncompressed_source_bytes_read'] for report in reports),
               'world_batches': world_count,
               'world_estimated_days': [min(seconds) * world_count / DAY, max(seconds) * world_count / DAY]}
    sources.atomic_json(sources.MANIFESTS / f'benchmark-{options.scope}-{options.mode}-{options.stride}-context{int(options.context)}.json', summary)
    print(json.dumps({key: value for key, value in summary.items() if key != 'reports'}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('inventory')
    temporal = commands.add_parser('temporal')
    temporal.add_argument('--max-areas', type=int, choices=range(1, 6), default=5)
    context = commands.add_parser('context', help='Inventariar o descargar contexto sin procesar')
    context.add_argument('--layers', nargs='+', choices=('worldcover', 'jrc', 'hls', 'landsat'),
                         default=['worldcover', 'jrc'])
    context.add_argument('--areas', nargs='+', choices=tuple(topography.BENCHMARK), default=list(topography.BENCHMARK))
    context.add_argument('--fetch', action='store_true')
    context.add_argument('--max-gb', type=float, default=2.)
    for command in ('acquire', 'run', 'publish', 'benchmark'):
        sub = commands.add_parser(command)
        sub.add_argument('--scope', choices=('pilot', 'world'), default='pilot')
        sub.add_argument('--stride', choices=(3000, 10000), default=10000, type=int)
        sub.add_argument('--mode', choices=('cache', 'range', 'auto'), default='cache')
        sub.add_argument('--context', action='store_true')
        if command in ('acquire', 'run'):
            sub.add_argument('--max-batches', type=int, default=5)
            sub.add_argument('--start', type=int, default=0)
        if command == 'acquire':
            sub.add_argument('--max-gb', type=float, default=2.)
            sub.add_argument('--plan-only', action='store_true')
            sub.add_argument('--check-cdse', action='store_true')
        if command == 'run':
            sub.add_argument('--max-hours', type=float, default=168.)
        if command == 'publish':
            sub.add_argument('version')
            sub.add_argument('--refine', action='store_true')
    options = parser.parse_args()
    if options.command == 'inventory':
        for entry in sources.fetch(sources.inventory_assets(), 10_000_000):
            print(entry['status'], entry['id'], entry['bytes'])
        return
    if options.command == 'temporal':
        from pipelines.atlas_temporal import run as run_temporal
        run_temporal(options.max_areas)
        return
    if options.command == 'context':
        if not math.isfinite(options.max_gb) or options.max_gb <= 0:
            parser.error('--max-gb debe ser finito y positivo')
        from pipelines.atlas_context import prepare
        report = prepare(list(dict.fromkeys(options.layers)), list(dict.fromkeys(options.areas)),
                         options.fetch, options.max_gb)
        print(json.dumps({key: report[key] for key in ('layers', 'gaps', 'path')}, ensure_ascii=False, indent=2))
        return
    land = None if options.command in ('acquire', 'benchmark') else topography.Land()
    selected = batches(options.scope, land)
    if options.command in ('acquire', 'run'):
        if options.start < 0 or options.max_batches < 1:
            parser.error('--start debe ser ≥ 0 y --max-batches ≥ 1')
        selected = selected[options.start:]
    if options.command == 'acquire':
        acquire(options, selected[:options.max_batches])
    elif options.command == 'run':
        run(options, land, selected)
    elif options.command == 'publish':
        publish(options, land, selected)
    elif options.command == 'benchmark':
        benchmark(options, selected)


if __name__ == '__main__':
    main()
