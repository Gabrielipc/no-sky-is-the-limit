"""Inventory and bounded acquisition for the offline 30 m atlas."""
import fcntl
import hashlib
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
CACHE = Path(os.environ.get('ATLAS_CACHE_DIR') or (ROOT / 'data/raw/atlas30'))
MANIFESTS = Path(os.environ.get('ATLAS_MANIFESTS_DIR') or (ROOT / 'data/manifests/atlas30'))
CACHE_LIMIT = 100_000_000_000
GLO_BUCKET = 'https://copernicus-dem-30m.s3.amazonaws.com'
WORLDCOVER = 'https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map'
JRC_LIST = 'https://s3.waw4-1.cloudferro.com/swift/v1/global-surface-water/'
TILE = re.compile(r'Copernicus_DSM_COG_10_([NS])(\d{2})_00_([EW])(\d{3})_00_DEM')
CATALOG = {
    'land': {'product': 'Natural Earth Land 1:10m', 'version': '5.1.1', 'product_version': '5.1.1',
             'doi': None, 'license': 'Public domain', 'crs': 'EPSG:4326', 'coverage': 'world land polygons',
             'url': 'https://naturalearth.s3.amazonaws.com/10m_physical/ne_10m_land.zip'},
    'glo30': {'product': 'Copernicus DEM GLO-30 Public (DSM)', 'version': 'DGED COG public inventory',
              'product_version': '2023_1', 'doi': '10.5270/ESA-c5d3d65',
              'license': 'Copernicus DEM GLO-30, attribution required', 'crs': 'EPSG:4326',
              'vertical_reference': 'EGM2008', 'native_resolution_m': 30,
              'coverage': 'public 1° tiles, with gaps',
              'url': GLO_BUCKET + '/tileList.txt'},
    'worldcover': {'product': 'ESA WorldCover Map', 'version': '2021 v200', 'product_version': 'v200',
                   'doi': '10.5281/zenodo.7254221', 'license': 'CC BY 4.0',
                   'native_resolution_m': 10, 'crs': 'EPSG:4326', 'period': '2021',
                   'url': 'https://esa-worldcover.org/en/data-access'},
    'jrc': {'product': 'JRC Global Surface Water Occurrence', 'version': '1.5', 'product_version': '1.5',
            'doi': None, 'license': 'Copernicus Programme, EC JRC/Google attribution',
            'native_resolution_m': 30, 'crs': 'EPSG:4326', 'period': '1984–2024',
            'url': 'https://global-surface-water.appspot.com/download'},
    'hls': {'product': 'NASA HLS L30/S30', 'version': '2.0', 'product_version': '2.0',
            'doi': '10.5067/HLS/HLSS30.002', 'native_resolution_m': 30,
            'access': 'CMR and Earthdata Login', 'url': 'https://hls.gsfc.nasa.gov/data-access-and-tools/'},
    'landsat': {'product': 'Landsat 8/9 Collection 2 Level-2 ST', 'version': 'Collection 2',
                'product_version': 'C2_L2', 'doi': '10.5066/P9OGBGM6',
                'native_resolution_m': 100, 'distributed_cell_m': 30,
                'access': 'USGS Landsat catalog', 'url': 'https://www.usgs.gov/landsat-missions/landsat-data-access'},
    'esa_cci_permafrost': {
        'product': 'ESA CCI Permafrost v5.0 (Open Science Catalog)',
        'version': '5.0', 'product_version': '5.0',
        'doi': '10.5285/6ef1a60b678f4048a20b5c8d94d665c9',
        'native_resolution_m': 1000, 'crs': 'EPSG:4326', 'period': '1997–2023',
        'access': 'ESA Open Science Catalog / CEDA',
        'url': 'https://climate.esa.int/en/projects/permafrost/',
    },
    'gpm_imerg': {
        'product': 'GPM IMERG Final Precipitation L3 Daily v07',
        'version': '07', 'product_version': '07',
        'doi': '10.5067/GPM/IMERGDF/DAY/07',
        'native_resolution_m': 11132, 'crs': 'EPSG:4326',
        'access': 'NASA GES DISC / CMR',
        'url': 'https://disc.gsfc.nasa.gov/datasets/GPM_3IMERGDF_07/summary',
    },
    'smap_spl3smp_e': {
        'product': 'SMAP Enhanced L3 Radiometer Daily 9 km Soil Moisture v006',
        'version': '006', 'product_version': '006',
        'doi': '10.5067/4DQ54OUIJ9DL',
        'native_resolution_m': 9000, 'crs': 'EPSG:6933',
        'access': 'NASA NSIDC DAAC / CMR',
        'url': 'https://nsidc.org/data/spl3smp_e/versions/6',
    },
    'modis_mod10a1': {
        'product': 'MODIS/Terra Snow Cover Daily L3 Global 500m v061',
        'version': '061', 'product_version': '061',
        'doi': '10.5067/MODIS/MOD10A1.061',
        'native_resolution_m': 500, 'crs': 'MODIS Sinusoidal',
        'access': 'NASA NSIDC DAAC / CMR',
        'url': 'https://nsidc.org/data/mod10a1/versions/61',
    },
    'aster_ged_ag100': {
        'product': 'ASTER Global Emissivity Dataset 100m v003',
        'version': '003', 'product_version': '003',
        'doi': '10.5067/Community/ASTER_GED/AG100.003',
        'native_resolution_m': 100, 'crs': 'EPSG:4326',
        'access': 'NASA LP DAAC / CMR',
        'url': 'https://lpdaac.usgs.gov/products/ag100v003/',
    },
    'sentinel1_rtc': {
        'product': 'OPERA Sentinel-1 Radiometric Terrain Corrected Backscatter / CDSE RTC',
        'version': 'V1', 'product_version': 'V1',
        'doi': '10.5067/SNWG/OPERA_L2_RTC-S1_V1',
        'native_resolution_m': 20, 'crs': 'UTM/WGS84',
        'access': 'NASA ASF DAAC / ESA CDSE',
        'url': 'https://documentation.dataspace.copernicus.eu/Data/Sentinel1.html',
    },
}

# Canonical DOI / product_version lookup by store `product_id` (audit §4).
PRODUCT_PROVENANCE = {
    'copernicus-glo30': CATALOG['glo30'],
    'esa-worldcover-2021': CATALOG['worldcover'],
    'jrc-gsw-v1_5': CATALOG['jrc'],
    'ESA_CCI_PERMAFROST_v5.0': CATALOG['esa_cci_permafrost'],
    'GPM_3IMERGDF.07': CATALOG['gpm_imerg'],
    'SPL3SMP_E.006': CATALOG['smap_spl3smp_e'],
    'MOD10A1.061': CATALOG['modis_mod10a1'],
    'AG100.003': CATALOG['aster_ged_ag100'],
    'OPERA_L2_RTC-S1_V1': CATALOG['sentinel1_rtc'],
}


def catalog_provenance(product_id: str) -> dict:
    """Return {'doi': ..., 'product_version': ...} for a known store `product_id`."""
    entry = PRODUCT_PROVENANCE.get(product_id, {})
    return {'doi': entry.get('doi'), 'product_version': entry.get('product_version')}


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(mode='w', dir=path.parent, encoding='utf-8', delete=False) as stream:
        pending = Path(stream.name)
        try:
            json.dump(value, stream, ensure_ascii=False, allow_nan=False)
            stream.write('\n')
            stream.flush()
            pending.replace(path)
        finally:
            pending.unlink(missing_ok=True)


def asset(source, name, url):
    return {'source': source, 'id': name, 'url': url}


def inventory_assets():
    return [asset('land', 'ne_10m_land.zip', CATALOG['land']['url']),
            asset('glo30', 'tileList.txt', CATALOG['glo30']['url'])]


def cached(entry):
    return CACHE / entry['source'] / entry['id']


def identity_path(entry):
    return MANIFESTS / 'assets' / entry['source'] / (entry['id'] + '.json')


# Benchmarks set ATLAS_IGNORE_LOCAL_CACHE=1 to measure remote transfer; catalogue
# inventories (GLO-30 tile list, Natural Earth) are still read from the cache.
CATALOGUE_IDS = ('tileList.txt', 'ne_10m_land.zip')


def local_identity(entry):
    if os.environ.get('ATLAS_IGNORE_LOCAL_CACHE') == '1' and entry['id'] not in CATALOGUE_IDS:
        return None
    path, record = cached(entry), identity_path(entry)
    if not path.is_file() or not record.is_file():
        return None
    identity = json.loads(record.read_text())
    if identity['url'] != entry['url'] or path.stat().st_size != identity['bytes'] or digest(path) != identity['sha256']:
        raise ValueError(f'Identidad local inesperada: {path}')
    return identity


def request(url, method='GET', headers=None):
    return urlopen(Request(url, method=method, headers=headers or {}), timeout=30)


def remote_identity(entry, open_url=request, ranged=False):
    try:
        method, headers = ('GET', {'Range': 'bytes=0-0'}) if ranged else ('HEAD', None)
        with open_url(entry['url'], method, headers) as response:
            size = response.headers.get('Content-Length')
            if ranged:
                match = re.fullmatch(r'bytes 0-0/(\d+)', response.headers.get('Content-Range', ''))
                if response.status != 206 or not match:
                    return {**entry, 'status': 'range_unavailable', 'bytes': None}
                size = match.group(1)
            return {**entry, 'status': 'available', 'bytes': int(size) if size else None,
                    'etag': response.headers.get('ETag'),
                    'last_modified': response.headers.get('Last-Modified'),
                    'accessed_at': datetime.now(timezone.utc).isoformat()}
    except HTTPError as exc:
        if exc.code not in (403, 404):
            raise
        return {**entry, 'status': f'http_{exc.code}', 'bytes': None}


def transfer(entry, open_url=request):
    path = cached(entry)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise ValueError(f'Archivo local sin verificar: {path}')
    partial = path.with_suffix(path.suffix + '.part')
    expected = entry['bytes']
    offset = partial.stat().st_size if partial.exists() and entry['etag'] else 0
    if offset > expected:
        raise ValueError(f'Descarga parcial mayor que el original: {partial}')
    marker = partial.with_suffix(partial.suffix + '.etag')
    if not marker.exists() or marker.read_text() != entry['etag']:
        offset = 0
    if entry['etag']:
        marker.write_text(entry['etag'])
    headers = {'If-Match': entry['etag']} if entry['etag'] else {}
    if offset < expected:
        if offset:
            headers['Range'] = f'bytes={offset}-'
        with open_url(entry['url'], headers=headers) as response:
            if offset and (response.status != 206 or response.headers.get('Content-Range') !=
                           f'bytes {offset}-{expected - 1}/{expected}'):
                raise OSError(f'Respuesta de reanudación inesperada: {entry["id"]}')
            with partial.open('ab' if offset else 'wb') as stream:
                while block := response.read(1024 * 1024):
                    offset += len(block)
                    if offset > expected:
                        raise ValueError(f'Respuesta mayor que el tamaño previsto: {entry["id"]}')
                    stream.write(block)
    if offset != expected:
        raise OSError(f'Descarga incompleta: {entry["id"]}')
    result = {**entry, 'status': 'verified_local', 'sha256': digest(partial)}
    # The final file is visible only after its complete identity has been recorded.
    atomic_json(identity_path(entry), result)
    partial.replace(path)
    marker.unlink(missing_ok=True)
    return result


def fetch(entries, max_bytes, cache_limit=CACHE_LIMIT, *, inspect=None, download=None):
    CACHE.mkdir(parents=True, exist_ok=True)
    with (CACHE / '.download.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        return fetch_locked(entries, max_bytes, cache_limit, inspect or remote_identity, download or transfer)


def fetch_locked(entries, max_bytes, cache_limit, inspect, download):
    results = [local_identity(entry) or inspect(entry) for entry in entries]
    pending = [entry for entry in results if entry['status'] == 'available']
    if any(entry['bytes'] is None for entry in pending):
        raise ValueError('El proveedor no informó el tamaño de una descarga')
    estimate = sum(entry['bytes'] for entry in pending)
    disk = sum(path.stat().st_size for path in CACHE.rglob('*') if path.is_file())
    if estimate > max_bytes or disk + estimate > cache_limit:
        raise ValueError(f'Lote de {estimate} bytes supera el presupuesto o la caché de {cache_limit} bytes')
    for index, entry in enumerate(results):
        if entry['status'] != 'available':
            continue
        for attempt in range(3):
            try:
                results[index] = {**download(entry), 'newly_verified_bytes': entry['bytes']}
                break
            except OSError:
                if attempt == 2:
                    raise
                time.sleep(2 ** attempt)
    return results


def glo_inventory():
    entry = inventory_assets()[1]
    if not local_identity(entry):
        raise ValueError('Falta el inventario de GLO-30. Ejecuta atlas30.py inventory')
    tiles = {}
    for name in cached(entry).read_text().splitlines():
        match = TILE.fullmatch(name.strip())
        if match:
            ns, latitude, ew, longitude = match.groups()
            key = (int(latitude) * (-1 if ns == 'S' else 1),
                   int(longitude) * (-1 if ew == 'W' else 1))
            filename = name.strip() + '.tif'
            tiles[key] = asset('glo30', filename, f'{GLO_BUCKET}/{name.strip()}/{filename}')
    if not tiles:
        raise ValueError('Inventario de GLO-30 sin teselas reconocibles')
    return tiles


def worldcover_asset(latitude, longitude):
    grid = f'{"N" if latitude >= 0 else "S"}{abs(latitude):02}{"E" if longitude >= 0 else "W"}{abs(longitude):03}'
    name = f'ESA_WorldCover_10m_2021_v200_{grid}_Map.tif'
    return asset('worldcover', name, f'{WORLDCOVER}/{name}')


def jrc_asset(latitude, longitude):
    """Inputs are the southwest tile corner; JRC names tiles by the northwest corner."""
    north = latitude + 10
    grid = f'{abs(longitude)}{"E" if longitude >= 0 else "W"}_{abs(north)}{"N" if north >= 0 else "S"}'
    name = f'occurrence_{grid}_v1_5_2024.tif'
    return asset('jrc', name, JRC_LIST + 'download2024/Aggregated/VER1-5/occurrence/' + name)


def cdse_lookup(latitude, longitude):
    grid = f'{"N" if latitude >= 0 else "S"}{abs(latitude):02}_{"E" if longitude >= 0 else "W"}{abs(longitude):03}'
    attribute = "Attributes/OData.CSC.StringAttribute/any(a:a/Name eq '{}' and a/OData.CSC.StringAttribute/Value eq '{}')"
    query = {'$filter': ' and '.join((attribute.format('gridId', grid),
                                    attribute.format('productType', 'SAR_DGE_30_A4AD'))),
             '$select': 'Id,Name,Online,ContentLength', '$top': 10}
    url = 'https://catalogue.dataspace.copernicus.eu/odata/v1/Products?' + urlencode(query)
    with request(url) as response:
        products = json.load(response)['value']
    return {'grid': grid, 'products': products, 'status': 'access_required' if products else 'not_listed'}
