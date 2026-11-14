"""Bounded 2024 reflectance and temperature pilots over benchmark windows."""
import json
import os
from contextlib import ExitStack
from functools import lru_cache
from urllib.parse import quote, urlencode, urlsplit

import numpy as np
import rasterio
from rasterio.transform import from_origin
from rasterio.warp import Resampling

from pipelines import atlas_sources as sources, atlas_topography as topo

NASA = 'https://cmr.earthdata.nasa.gov/stac/LPCLOUD/search'
USGS = 'https://landsatlook.usgs.gov/stac-server/search'
PC = 'https://planetarycomputer.microsoft.com/api'
PERIODS = ('2024-01-01T00:00:00Z/2024-04-01T00:00:00Z',
           '2024-07-01T00:00:00Z/2024-10-01T00:00:00Z')
HLS = {'HLSL30.v2.0': ('B03', 'B04', 'B05', 'B06', 'Fmask'),
       'HLSS30.v2.0': ('B03', 'B04', 'B8A', 'B11', 'Fmask')}



def catalog(endpoint, **params):
    with sources.request(endpoint + '?' + urlencode(params)) as response:
        return json.load(response)['features']


def representative(items, bands):
    valid = [item for item in items if all(band in item['assets'] for band in bands)]
    return min(valid, key=lambda item: (item['properties'].get('eo:cloud_cover') or 0, item['id']), default=None)


@lru_cache(maxsize=1)
def landsat_token():
    with sources.request(PC + '/sas/v1/token/landsat-c2-l2') as response:
        return json.load(response)['token']


def landsat_mirror(item):
    # The USGS ID adds processing date and an ST suffix. Match the mirror to the full product basename.
    platform, level, pathrow, date, _processing, collection, tier, _st = item['id'].split('_')
    mirror_id = '_'.join((platform, level, pathrow, date, collection, tier))
    matches = catalog(PC + '/stac/v1/search', collections='landsat-c2-l2', ids=mirror_id, limit=1)
    if not matches:
        return None
    asset = matches[0]['assets'].get('lwir11', {})
    return matches[0] if item['id'].removesuffix('_ST') in asset.get('href', '') else None


def read_band(rasters, item, band, grid, *, hls=False):
    url = item['assets'][band]['href']
    host = urlsplit(url).hostname
    if hls and host != 'data.lpdaac.earthdatacloud.nasa.gov':
        raise ValueError('Host de banda HLS no reconocido')
    if not hls and host != 'landsateuwest.blob.core.windows.net':
        raise ValueError('Host de banda Landsat no reconocido')
    # Credentials remain in the environment or memory. Only the unsigned href is persisted.
    entry = sources.asset('hls' if hls else 'landsat', f'{item["id"]}/{band}', url)
    method = Resampling.nearest
    if hls:
        # Earthdata serves ranged GETs but rejects HEAD on these assets.
        target = '/vsicurl?use_head=no&list_dir=no&url=' + quote(url, safe='')
        options = {'GDAL_HTTP_HEADERS': 'Authorization: Bearer ' + os.environ['EARTHDATA_TOKEN'],
                   'CPL_VSIL_CURL_AUTHORIZATION_HEADER_ALLOWED_IF_REDIRECT': 'NO'}
    else:
        target, options = '/vsicurl/' + url + '?' + landsat_token(), {}
    with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN='EMPTY_DIR', **options), rasterio.open(target) as dataset:
        rasters.opened[entry['id']] = dataset
        try:
            arrays = rasters.sample(entry, *grid, method)
        finally:
            rasters.opened.pop(entry['id'])
    result = np.full(grid[-1], np.nan)
    for data, support in arrays:
        take = np.isnan(result) & (support >= 1 - 1e-6)
        result[take] = data[take]
    return result, url


def ratios(a, b):
    return np.divide(a - b, a + b, out=np.full(a.shape, np.nan), where=np.abs(a + b) > 1e-6)


def hls_values(rasters, item, bands, grid):
    results = [read_band(rasters, item, band, grid, hls=True) for band in bands]
    green, red, nir, swir, mask = (pair[0] for pair in results)
    valid = np.isfinite(mask) & ((np.nan_to_num(mask).astype('int16') & 0b101110) == 0)
    values = {key: np.where(valid, ratios(a * .0001, b * .0001), np.nan)
              for key, a, b in [('ndvi', nir, red), ('ndmi', nir, swir), ('ndsi', green, swir)]}
    return values, [pair[1] for pair in results]


def landsat_values(rasters, item, grid):
    mirror = landsat_mirror(item)
    if mirror is None:
        raise FileNotFoundError('No hay una copia abierta de este producto de USGS')
    results = [read_band(rasters, mirror, band, grid) for band in ('lwir11', 'qa_pixel', 'qa')]
    raw, mask, qa = (pair[0] for pair in results)
    valid = np.isfinite(mask) & np.isfinite(qa) & ((np.nan_to_num(mask).astype('int32') & 0b111111) == 0)
    return {'surface_temperature_k': np.where(valid & (raw > 0), raw * .00341802 + 149, np.nan)}, [
        pair[1] for pair in results]


def temporal_summary(series):
    results = {}
    for name, samples in series.items():
        if not samples:
            results[name] = {'status': 'no_valid_observations', 'value': None}
            continue
        stack = np.stack(samples)
        counts = np.isfinite(stack).sum(axis=0)
        if not counts.any():
            results[name] = {'status': 'no_valid_observations', 'value': None}
            continue
        values = np.nanmedian(stack[:, counts > 0], axis=0)
        results[name] = {'status': 'pilot', 'p50': float(np.median(values)),
                         'valid_fraction': float((counts > 0).mean()), 'valid_samples': int(counts.sum()),
                         'observations_with_valid_pixels': int(np.isfinite(stack).any(axis=(1, 2)).sum())}
    return results


def run(max_areas):
    results = {}
    for label, (lat, lon) in list(topo.BENCHMARK.items())[:max_areas]:
        crs = topo.owner(lon, lat)
        x, y = topo.projection(topo.WGS84, crs).transform(lon, lat)
        half = topo.WINDOW / 2
        bounds = topo.geographic_boxes(crs, (x - half, y - half, x + half, y + half))
        center_bbox = f'{lon - .001},{lat - .001},{lon + .001},{lat + .001}'
        grid = (crs, bounds, from_origin(x - half, y + half, 30, 30), (100, 100))
        series = {key: [] for key in ('ndvi', 'ndmi', 'ndsi', 'surface_temperature_k')}
        assets = []
        for period in PERIODS:
            with ExitStack() as stack:
                rasters = topo.Rasters(stack, 'range')
                for collection, bands in {**HLS, 'landsat-c2l2-st': ('lwir11', 'qa_pixel', 'qa')}.items():
                    is_hls = collection in HLS
                    item = None
                    try:
                        items = catalog(NASA if is_hls else USGS, collections=collection, bbox=center_bbox,
                                        datetime=period, limit=20)
                        if not is_hls:
                            items = [feature for feature in items if feature['id'].startswith(('LC08_', 'LC09_'))]
                        item = representative(items, bands)
                        if item is None:
                            assets.append({'collection': collection, 'period': period, 'status': 'no_scene'})
                            continue
                        if is_hls and not os.environ.get('EARTHDATA_TOKEN'):
                            assets.append({'collection': collection, 'id': item['id'], 'status': 'earthdata_login_required'})
                            continue
                        values, urls = hls_values(rasters, item, bands, grid) if is_hls else landsat_values(rasters, item, grid)
                        for key, value in values.items():
                            series[key].append(value)
                        assets.append({'collection': collection, 'id': item['id'], 'date': item['properties'].get('datetime'),
                                       'status': 'read', 'urls': urls})
                    except (OSError, KeyError, ValueError) as exc:
                        # Avoid writing signed URLs or request headers to evidence or logs.
                        assets.append({'collection': collection, 'period': period,
                                       'id': item['id'] if item else None, 'status': 'unavailable',
                                       'error_type': type(exc).__name__})
        results[label] = {'center': [lon, lat], 'cell_m': 30, 'window_m': 3000,
                          'metrics': temporal_summary(series), 'assets': assets}
        sources.atomic_json(sources.MANIFESTS / 'temporal-2024.json',
                            {'periods': PERIODS, 'areas': results, 'thermal_native_m': 100,
                             'role': 'pilot_context_only'})
        print(label, {key: sum(item['status'] == key for item in assets)
                      for key in ('read', 'unavailable', 'no_scene', 'earthdata_login_required')}, flush=True)
