"""Spatial batches, 30 m metrics and provenance for the offline atlas."""
import math
import resource
import sys
import time
from contextlib import ExitStack
from dataclasses import dataclass
from functools import lru_cache

import geopandas as gpd
import numpy as np
import rasterio
from pyproj import CRS, Transformer
from rasterio.features import rasterize
from rasterio.transform import from_origin
from rasterio.warp import Resampling, reproject, transform_bounds
from rasterio.windows import Window, from_bounds
from shapely import box, get_parts, segmentize, union_all
from shapely.ops import transform
from shapely.strtree import STRtree

from pipelines import atlas_sources as sources
from scripts import analizar_primer_caso as terrain
from scripts.analizar_dimensiones import geometry_descriptors

CELL = 30
WINDOW = 3000
HALO = 480
RADIUS = 360
MIN_LAND = .8
MIN_VALID = .95
GRID_VERSION = 'utm-ups-v1'
BATCH_SIZE = 100_000
WGS84 = CRS.from_epsg(4326)
EDGES = np.arange(91)
BENCHMARK = {
    'desierto': (38.6, -110.6),
    'montana': (46.6, 11.2),
    'costa': (-23.65, -70.1),
    'tropico': (0.6, 114.6),
    'polar': (-80.7, 0.2),
}


@dataclass(frozen=True)
class Batch:
    zone: int
    west: int
    south: int
    label: str

    @property
    def id(self):
        return f'{self.zone}-{self.west}-{self.south}'

    @property
    def bounds(self):
        return self.west, self.south, self.west + BATCH_SIZE, self.south + BATCH_SIZE


@lru_cache(maxsize=260)
def projection(source, target):
    return Transformer.from_crs(source, target, always_xy=True)


def owner(lon, lat):
    if lat >= 84:
        return 32661
    if lat < -80:
        return 32761
    return (32600 if lat >= 0 else 32700) + (math.floor((lon + 180) % 360 / 6) + 1)


def split(bounds):
    west, south, east, north = bounds
    if east < west:
        return [(west, south, 180, north), (-180, south, east, north)]
    return [bounds]


def geographic_boxes(crs, bounds):
    return split(transform_bounds(crs, WGS84, *bounds, densify_pts=41))


def tile_keys(bounds_list, step):
    keys = set()
    for west, south, east, north in bounds_list:
        for lat in range(max(-90, math.floor(south / step) * step), min(90, math.ceil(north / step) * step), step):
            for lon in range(max(-180, math.floor(west / step) * step), min(180, math.ceil(east / step) * step), step):
                keys.add((lat, lon))
    return sorted(keys)


class Land:
    def __init__(self):
        entry = sources.inventory_assets()[0]
        self.identity = sources.local_identity(entry)
        if self.identity is None:
            raise ValueError('Falta la máscara terrestre. Ejecuta atlas30.py inventory')
        layer = gpd.read_file(f'zip://{sources.cached(entry)}')
        if layer.crs.to_epsg() != 4326:
            raise ValueError('La máscara terrestre debe usar EPSG:4326')
        self.tree = STRtree(get_parts(layer.geometry.to_numpy()))

    def parts(self, bounds_list):
        for bounds in bounds_list:
            clip = box(*bounds)
            for index in self.tree.query(clip, predicate='intersects'):
                part = self.tree.geometries[index].intersection(clip)
                if part.area > 0:
                    yield part

    def mask(self, crs, bounds_list, affine, shape):
        project = projection(WGS84, crs).transform
        parts = [transform(project, segmentize(part, .02)) for part in self.parts(bounds_list)]
        return rasterize(parts, out_shape=shape, transform=affine, dtype='uint8').astype(bool) if parts else np.zeros(shape, bool)


def benchmark_batches():
    for label, (lat, lon) in BENCHMARK.items():
        zone = owner(lon, lat)
        x, y = projection(WGS84, zone).transform(lon, lat)
        yield Batch(zone, math.floor((x - BATCH_SIZE / 2) / 1000) * 1000,
                    math.floor((y - BATCH_SIZE / 2) / 1000) * 1000, label)


def world_batches(land):
    domains = [(32661, (-180, 84, 180, 90)), (32761, (-180, -90, 180, -80))]
    for i in range(60):
        west = i * 6 - 180
        domains.extend([(32601 + i, (west, 0, west + 6, 84)), (32701 + i, (west, -80, west + 6, 0))])
    for zone, bounds in sorted(domains):
        projected = [transform(projection(WGS84, zone).transform, segmentize(part, .1))
                     for part in land.parts([bounds])]
        if not projected:
            continue
        tree = STRtree(projected)
        xmin, ymin, xmax, ymax = union_all(projected).bounds
        for y in range(math.floor(ymin / BATCH_SIZE) * BATCH_SIZE, math.ceil(ymax / BATCH_SIZE) * BATCH_SIZE, BATCH_SIZE):
            for x in range(math.floor(xmin / BATCH_SIZE) * BATCH_SIZE, math.ceil(xmax / BATCH_SIZE) * BATCH_SIZE, BATCH_SIZE):
                batch = Batch(zone, x, y, 'mundial')
                if tree.query(box(*batch.bounds).buffer(WINDOW / 2), predicate='intersects').size:
                    yield batch


def windows(batch, stride):
    w, s, e, n = batch.bounds
    inverse = projection(batch.zone, WGS84)
    for row in range(math.ceil(s / stride), math.ceil(n / stride)):
        for col in range(math.ceil(w / stride), math.ceil(e / stride)):
            x, y = col * stride, row * stride
            lon, lat = inverse.transform(x, y)
            if owner(lon, lat) == batch.zone:
                yield {'region_id': f'{GRID_VERSION}-{stride}-{batch.zone}-{row}-{col}',
                       'batch': batch.id, 'area': batch.label, 'zone': batch.zone, 'x': x, 'y': y,
                       'longitude': lon, 'latitude': lat}


def batch_assets(batch, inventory, context=False):
    w, s, e, n = batch.bounds
    margin = WINDOW / 2 + HALO + CELL
    bounds = geographic_boxes(batch.zone, (w - margin, s - margin, e + margin, n + margin))
    keys = tile_keys(bounds, 1)
    entries = [inventory[key] for key in keys if key in inventory]
    missing = [list(key) for key in keys if key not in inventory]
    if context:
        entries += [sources.worldcover_asset(*key) for key in tile_keys(bounds, 3)]
        entries += [sources.jrc_asset(*key) for key in tile_keys(bounds, 10)]
    return entries, missing


class Rasters:
    def __init__(self, stack, mode):
        self.stack = stack
        self.mode = mode
        self.opened = {}
        self.identities = {}
        self.unavailable = set()
        self.read_bytes = 0

    def get(self, entry):
        key = entry['id']
        if key not in self.opened and key not in self.unavailable:
            identity = sources.local_identity(entry) if self.mode != 'range' else None
            if identity is None and self.mode != 'cache':
                identity = sources.remote_identity(entry)
                if identity['status'] != 'available':
                    identity = None
            if identity is None:
                self.unavailable.add(key)
                return None
            path = str(sources.cached(entry)) if identity['status'] == 'verified_local' else '/vsicurl/' + entry['url']
            self.opened[key] = self.stack.enter_context(rasterio.open(path))
            self.identities[key] = identity
        return self.opened.get(key)

    def sample(self, entry, crs, bounds_list, affine, shape, method, valid_range=None):
        ds = self.get(entry)
        if ds is None:
            return []
        results = []
        for west, south, east, north in bounds_list:
            if ds.crs.to_epsg() != 4326:
                west, south, east, north = transform_bounds(WGS84, ds.crs, west, south, east, north)
            w = max(west, ds.bounds.left)
            s = max(south, ds.bounds.bottom)
            e = min(east, ds.bounds.right)
            n = min(north, ds.bounds.top)
            if w >= e or s >= n:
                continue
            raw = from_bounds(w, s, e, n, ds.transform)
            col, row = max(0, math.floor(raw.col_off) - 2), max(0, math.floor(raw.row_off) - 2)
            window = Window(col, row, min(ds.width, math.ceil(raw.col_off + raw.width) + 2) - col,
                            min(ds.height, math.ceil(raw.row_off + raw.height) + 2) - row)
            src = ds.read(1, window=window, masked=True).astype('float64')
            self.read_bytes += src.size * np.dtype(ds.dtypes[0]).itemsize
            data = src.filled(np.nan)
            valid = np.isfinite(data)
            if valid_range:
                valid &= (data >= valid_range[0]) & (data <= valid_range[1])
            args = dict(src_transform=ds.window_transform(window), src_crs=ds.crs, dst_transform=affine,
                        dst_crs=crs, resampling=method, num_threads=1)
            out = np.full(shape, np.nan)
            # Invalid source samples remain invalid even when valid neighbours contribute to the mean.
            support = np.zeros(shape)
            reproject(np.where(valid, data, np.nan), out, src_nodata=np.nan, dst_nodata=np.nan, **args)
            reproject(valid.astype('float64'), support, dst_nodata=0, **args)
            results.append((out, support))
        return results


def mosaic(rasters, entries, crs, bounds_list, affine, shape, method, valid_range=None):
    result = np.full(shape, np.nan)
    provenance = []
    for entry in entries:
        for data, support in rasters.sample(entry, crs, bounds_list, affine, shape, method, valid_range):
            take = np.isnan(result) & (support >= 1 - 1e-6) & np.isfinite(data)
            if take.any():
                result[take] = data[take]
                provenance.append(entry['id'])
    return result, sorted(set(provenance))


def metrics(elevation, land, cell):
    size = WINDOW // cell
    start = (len(elevation) - size) // 2
    core = slice(start, start + size)
    slope_core = slice(start - 1, start + size - 1)
    masked = np.where(land, elevation, np.nan)
    z = masked[core, core]
    slope = terrain.slopes(masked, cell)[slope_core, slope_core]
    roughness = geometry_descriptors(masked, cell, RADIUS)['roughness_rms'][core, core]
    area = land[core, core]
    denominator = int(area.sum())
    arrays = {'elevation': z, 'slope': slope, 'roughness': roughness}
    valid = {name: float(np.isfinite(array).sum() / denominator) if denominator else 0.
             for name, array in arrays.items()}
    values = slope[np.isfinite(slope)]
    enough = min(valid.values()) >= MIN_VALID
    return {'cell_m': cell, 'land_fraction': float(area.mean()), 'valid_elevation': valid['elevation'],
            'valid_slope': valid['slope'], 'valid_roughness': valid['roughness'],
            'relief_m': float(np.ptp(np.nanpercentile(z, [5, 95]))) if enough else None,
            'roughness_m': float(np.nanmedian(roughness)) if enough else None,
            'slope_p50_deg': float(np.median(values)) if enough else None,
            'slope_histogram': np.histogram(values, EDGES)[0].tolist() if enough else None}, arrays


def measure(site, land, rasters, inventory, context=False, cell=CELL):
    half = WINDOW // 2 + HALO
    x, y, crs = site['x'], site['y'], site['zone']
    bounds = geographic_boxes(crs, (x - half, y - half, x + half, y + half))
    size = (WINDOW + HALO * 2) // cell
    shape = (size, size)
    affine = from_origin(x - half, y + half, cell, cell)
    land_mask = land.mask(crs, bounds, affine, shape)
    core = slice(HALO // cell, HALO // cell + WINDOW // cell)
    fraction = float(land_mask[core, core].mean())
    row = {**site, 'cell_m': cell, 'land_fraction': fraction, 'asset_ids': [], 'worldcover_assets': [],
           'water_assets': [], 'valid_elevation': 0., 'valid_slope': 0., 'valid_roughness': 0.,
           'relief_m': None, 'roughness_m': None, 'slope_p50_deg': None, 'slope_histogram': None,
           'bare_fraction': None, 'vegetation_fraction': None, 'urban_fraction': None, 'ice_fraction': None,
           'worldcover_water_fraction': None, 'worldcover_valid_fraction': None,
           'water_occurrence_pct': None, 'water_valid_fraction': None}
    if fraction < MIN_LAND:
        return {**row, 'status': 'insufficient_land'}, {}
    entries = [inventory[key] for key in tile_keys(bounds, 1) if key in inventory]
    z, ids = mosaic(rasters, entries, crs, bounds, affine, shape, Resampling.average)
    if not ids:
        return {**row, 'status': 'dem_unavailable'}, {}
    result, arrays = metrics(z, land_mask, cell)
    row.update(result, asset_ids=ids, status='rankable' if result['relief_m'] is not None else 'insufficient_dem_support')
    if context and row['status'] == 'rankable':
        cover, cover_ids = mosaic(rasters, [sources.worldcover_asset(*key) for key in tile_keys(bounds, 3)],
                                  crs, bounds, affine, shape, Resampling.nearest, (10, 100))
        water, water_ids = mosaic(rasters, [sources.jrc_asset(*key) for key in tile_keys(bounds, 10)],
                                  crs, bounds, affine, shape, Resampling.average, (0, 100))
        land_core = land_mask[core, core]
        cover, water = cover[core, core][land_core], water[core, core][land_core]
        cover_valid = np.isin(cover, [10, 20, 30, 40, 50, 60, 70, 80, 90, 95, 100])
        water_valid = np.isfinite(water)
        row.update(worldcover_assets=cover_ids, water_assets=water_ids,
                   worldcover_valid_fraction=float(cover_valid.mean()), water_valid_fraction=float(water_valid.mean()))
        if cover_valid.mean() >= MIN_VALID:
            for name, codes in {'bare': [60], 'vegetation': [10, 20, 30, 40, 90, 95, 100],
                                'urban': [50], 'ice': [70], 'worldcover_water': [80]}.items():
                row[f'{name}_fraction'] = float(np.isin(cover[cover_valid], codes).mean())
        if water_valid.mean() >= MIN_VALID:
            row['water_occurrence_pct'] = float(water[water_valid].mean())
    return row, arrays


def reference(cell=CELL):
    import json

    site = json.loads(terrain.DEFAULT_CONFIG.read_text())['sites'][0]
    path = terrain.acquire(site, False)
    config = {'window_m': WINDOW, 'margin_m': HALO}
    data, valid, transform_, src, dst, meta = terrain.read_crop(path, site, config)
    size = (WINDOW + HALO * 2) // cell
    half = WINDOW / 2 + HALO
    z, _ = terrain.aggregate(data, valid, transform_, src, dst, from_origin(-half, half, cell, cell),
                             (size, size), 1e-6)
    values, arrays = metrics(z, np.ones(z.shape, bool), cell)
    if values['relief_m'] is None:
        raise ValueError(f'Cobertura de Jezero insuficiente a {cell} m')
    return {**values, 'profile_id': 'jezero-forma', 'site': site['name'], 'body': 'Mars',
            'longitude': site['longitude'], 'latitude': site['latitude'],
            'product': meta['product_id'], 'source': meta, 'window_m': WINDOW,
            'slope_baseline_m': 2 * cell, 'roughness_radius_m': RADIUS}, arrays


def process(batch, stride, land, inventory, mode, context):
    started = time.perf_counter()
    with ExitStack() as stack:
        stack.enter_context(rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN='EMPTY_DIR',
                                         GDAL_HTTP_MAX_RETRY=2, GDAL_HTTP_TIMEOUT=30, GDAL_CACHEMAX=128 * 1024**2))
        rasters = Rasters(stack, mode)
        rows = [measure(site, land, rasters, inventory, context)[0] for site in windows(batch, stride)]
        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return rows, {'seconds': time.perf_counter() - started,
                      'process_peak_ram_bytes': peak if sys.platform == 'darwin' else peak * 1024,
                      'uncompressed_source_bytes_read': rasters.read_bytes,
                      'assets': list(rasters.identities.values()), 'unavailable': sorted(rasters.unavailable)}
