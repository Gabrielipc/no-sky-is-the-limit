"""On-demand acquisition for `enrichment_surface` (audit 2026-11-14, §2.2 and §3).

Turns official granules into the `raw_inputs` that `etl_surface_dimensions` already knows how
to summarize. Every reader works product-first: each granule is opened once and sampled for
every window it covers, so a tile shared by many candidates is read only once.

| Dimension                 | Product (access)                                    | Reader                     |
|---------------------------|-----------------------------------------------------|----------------------------|
| aridity                   | GPM_3IMERGM.07 HDF5 (GES DISC, HTTP ranges)          | nearest 0.1° pixel         |
| soil_moisture             | SPL3SMP_E.006 HDF5 (NSIDC, HTTP ranges)              | nearest EASE2 9 km pixel   |
| thermal_emissivity        | AG100.003 HDF5 1°x1° tiles (LP DAAC, HTTP ranges)    | 100 m pixels in footprint  |
| permafrost                | ESA CCI Permafrost v5.0 NetCDF4 (CEDA, public)       | 1 km pixels in footprint   |
| snow_persistence          | MOD10A1.061 HDF4 (NSIDC, whole granule, then erased) | 500 m pixels in footprint  |
| apparent_thermal_inertia  | MOD11A1/MYD11A1 + MCD43A3 HDF4 (LP DAAC, idem)       | 1 km pixels in footprint   |
| sar_backscatter           | OPERA_L2_RTC-S1_V1 COG (ASF, GDAL ranges)            | 30 m local grid, median    |

Checked live on 2026-11-14: CMR links of every product, AG100 layout (`Emissivity/Mean` int16
×0.001, `Geolocation/*`, row 0 = north edge) and SPL3SMP_E layout (`Soil_Moisture_Retrieval_Data_AM/*`,
1624×3856, chunks of one row). GES DISC (IMERG) answers 403 "EULA Acceptance Failure" until the
Earthdata account authorizes the GES DISC application. MODIS HDF4 needs the `libgdal-hdf4` plugin.
The CCI NetCDF grid and the OPERA mask codes follow the product documentation and were not opened
here; both readers check what they find and fail loudly otherwise.

The Earthdata token is read from `EARTHDATA_TOKEN`, sent only to Earthdata hosts and dropped on
redirects to signed object URLs. CEDA is public and never receives it.
"""
from __future__ import annotations

import calendar
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
import json
import math
import os
from pathlib import Path
import re
import tempfile
from typing import Any, Callable, Iterable
import urllib.parse
import urllib.request

from affine import Affine
import numpy as np
from pyproj import CRS, Transformer

from pipelines import etl_altimetry as http
from pipelines import etl_extractors as extractors
from pipelines import etl_surface_dimensions as surface

CMR_GRANULES = 'https://cmr.earthdata.nasa.gov/search/granules.json'
EARTHDATA_HOSTS = (
    'data.gesdisc.earthdata.nasa.gov',
    'data.nsidc.earthdatacloud.nasa.gov',
    'data.lpdaac.earthdatacloud.nasa.gov',
    'cumulus.asf.earthdatacloud.nasa.gov',
)
CEDA_HOST = 'dap.ceda.ac.uk'
HALF_M = extractors.WINDOW_M / 2

COLLECTIONS = {
    'imerg_monthly': {'short_name': 'GPM_3IMERGM', 'version': '07', 'suffix': '.HDF5'},
    'smap': {'short_name': 'SPL3SMP_E', 'version': '006', 'suffix': '.h5'},
    'ag100': {'short_name': 'AG100', 'version': '003', 'suffix': '.h5'},
    'mod10a1': {'short_name': 'MOD10A1', 'version': '61', 'suffix': '.hdf'},
    'mod11a1': {'short_name': 'MOD11A1', 'version': '061', 'suffix': '.hdf'},
    'myd11a1': {'short_name': 'MYD11A1', 'version': '061', 'suffix': '.hdf'},
    'mcd43a3': {'short_name': 'MCD43A3', 'version': '061', 'suffix': '.hdf'},
    'opera_rtc': {'short_name': 'OPERA_L2_RTC-S1_V1', 'suffix': '_VV.tif'},
}
PRODUCT_IDS = {
    'aridity': ('GPM_3IMERGM.07',),
    'soil_moisture': ('SPL3SMP_E.006',),
    'thermal_emissivity': ('AG100.003',),
    'permafrost': ('ESA_CCI_PERMAFROST_v5.0',),
    'snow_persistence': ('MOD10A1.061',),
    'apparent_thermal_inertia': ('MOD11A1.061', 'MYD11A1.061', 'MCD43A3.061'),
    'sar_backscatter': ('OPERA_L2_RTC-S1_V1',),
}
SEASON_OF_MONTH = {12: 'DJF', 1: 'DJF', 2: 'DJF', 3: 'MAM', 4: 'MAM', 5: 'MAM',
                   6: 'JJA', 7: 'JJA', 8: 'JJA', 9: 'SON', 10: 'SON', 11: 'SON'}

# EASE-Grid 2.0 global 9 km (SPL3SMP_E): EPSG:6933, 3856 x 1624 cells.
EASE2_9KM = {'cell_m': 9008.055210146, 'x0': -17367530.44516137, 'y0': 7314540.830638824,
             'cols': 3856, 'rows': 1624}
EASE2 = Transformer.from_crs('EPSG:4326', 'EPSG:6933', always_xy=True)
# MODIS sinusoidal grid (tiles of 2400 x 2400 500 m cells).
MODIS_SIN = CRS.from_proj4('+proj=sinu +lon_0=0 +x_0=0 +y_0=0 +R=6371007.181 +units=m +no_defs')
MODIS_TILE_M = 1111950.5196666666
MODIS_X0, MODIS_Y0 = -20015109.354, 10007554.677
TO_SIN = Transformer.from_crs('EPSG:4326', MODIS_SIN, always_xy=True)
CCI_BASE = 'https://dap.ceda.ac.uk/neodc/esacci/permafrost/data'
CCI_FILES = {
    'PFR': '{base}/permafrost_extent/L4/area4/pp/v05.0/{hemi}/{year}/'
           'ESACCI-PERMAFROST-L4-PFR-MODISLST_CRYOGRID-{area}_PP-{year}-fv05.0.nc',
    'ALT': '{base}/active_layer_thickness/L4/area4/pp/v05.0/{hemi}/{year}/'
           'ESACCI-PERMAFROST-L4-ALT-MODISLST_CRYOGRID-{area}_PP-{year}-fv05.0.nc',
}
# Checked on CEDA 2026-11-15: both files are WGS84 lat/lon grids of 0.01° (`lat`, `lon`,
# `spatial_ref`); northern hemisphere = AREA4 (lat 25..85), Antarctica = AREA27 (lat -85..-60).
CCI_AREAS = {'northern_hemisphere': 'AREA4', 'Antarctica': 'AREA27'}


def cci_url(var: str, hemi: str, year: int) -> str:
    return CCI_FILES[var].format(base=CCI_BASE, hemi=hemi, year=year, area=CCI_AREAS[hemi])
# OPERA RTC-S1 layover/shadow mask: 0 = clear; 1 shadow, 2 layover, 3 both; 255 = no data.
OPERA_MASK_CLEAR = 0


@dataclass(frozen=True)
class Site:
    region_id: str
    longitude: float
    latitude: float

    @classmethod
    def from_row(cls, row: dict) -> 'Site':
        return cls(str(row['region_id']), float(row['longitude']), float(row['latitude']))

    def bbox(self, half_m: float = HALF_M) -> tuple[float, float, float, float]:
        dlat = half_m / 111_320.0
        dlon = half_m / (111_320.0 * max(math.cos(math.radians(self.latitude)), 0.05))
        return (self.longitude - dlon, self.latitude - dlat, self.longitude + dlon, self.latitude + dlat)

    def local_xy(self, lon: np.ndarray, lat: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        laea = CRS.from_proj4(f'+proj=laea +lon_0={self.longitude} +lat_0={self.latitude} +datum=WGS84 +units=m')
        return Transformer.from_crs('EPSG:4326', laea, always_xy=True).transform(lon, lat)


@dataclass
class FetchResult:
    """Raw inputs per region, the granules used and diagnostics for one dimension."""
    dimension: str
    inputs: dict[str, dict[str, Any]] = field(default_factory=dict)
    granules: list[str] = field(default_factory=list)
    period: str | None = None
    support: str = ''
    errors: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Access helpers (injected in tests)
# ---------------------------------------------------------------------------
def search_cmr(collection: dict, bbox: tuple[float, float, float, float] | None = None,
               start: date | None = None, end: date | None = None, page_size: int = 2000,
               max_pages: int = 20) -> list[dict]:
    """Granules of a collection (public CMR, no credentials), oldest first."""
    params = {'short_name': collection['short_name'], 'page_size': page_size, 'sort_key': 'start_date'}
    if collection.get('version'):
        params['version'] = collection['version']
    if bbox is not None:
        params['bounding_box'] = ','.join(f'{v:.6f}' for v in bbox)
    if start is not None or end is not None:
        params['temporal'] = f"{start.isoformat() if start else ''}T00:00:00Z,{end.isoformat() if end else ''}T23:59:59Z"
    out, search_after = [], None
    for _ in range(max_pages):
        headers = {'CMR-Search-After': search_after} if search_after else {}
        req = urllib.request.Request(f'{CMR_GRANULES}?{urllib.parse.urlencode(params)}', headers=headers)
        with urllib.request.urlopen(req, timeout=60) as response:
            entries = json.load(response)['feed']['entry']
            search_after = response.headers.get('CMR-Search-After')
        for e in entries:
            links = [l['href'] for l in e.get('links', []) if l.get('href', '').startswith('https://')
                     and urllib.parse.urlsplit(l['href']).hostname in EARTHDATA_HOSTS]
            url = next((h for h in links if h.endswith(collection['suffix'])), None)
            if url:
                out.append({'id': e['title'], 'url': url, 'time_start': e.get('time_start', ''), 'links': links})
        if len(entries) < page_size or not search_after:
            break
    return out


def open_h5(url: str, block_size: int = 256 * 1024):
    """h5py file over HTTP ranges (Earthdata token on the first request only; CEDA without it)."""
    import h5py  # analysis-only dependency (.tools/minerales)
    host = urllib.parse.urlsplit(url).hostname
    auth = host != CEDA_HOST
    allowed = EARTHDATA_HOSTS if auth else (CEDA_HOST,)
    return h5py.File(_RangeFile(url, block_size=block_size, allowed_hosts=allowed, auth=auth), 'r')


class _RangeFile(http.RangeFile):
    """`RangeFile` that can skip the token for public hosts."""

    def __init__(self, url: str, *, auth: bool = True, **kwargs) -> None:
        self.auth = auth
        super().__init__(url, **kwargs)

    def _request(self, start: int, end: int) -> bytes:
        if self.auth:
            return super()._request(start, end)
        req = urllib.request.Request(self.url, headers={'Range': f'bytes={start}-{end}'})
        with urllib.request.urlopen(req, timeout=90) as r:
            data = r.read()
            self.size = int(r.headers['Content-Range'].rsplit('/', 1)[1])
            self.etag = self.etag or (r.headers.get('ETag') or '').strip('"') or None
        self.requests += 1
        self.bytes_read += len(data)
        return data


def download(url: str, target: Path, chunk: int = 1 << 20) -> Path:
    """Stream a protected granule to `target` (HDF4 cannot be read over ranges)."""
    http._check_host(url, EARTHDATA_HOSTS)
    req = urllib.request.Request(url, headers=http._token_header())
    target.parent.mkdir(parents=True, exist_ok=True)
    staged = target.with_suffix(target.suffix + '.part')
    with http._OPENER.open(req, timeout=300) as r, open(staged, 'wb') as fh:
        while block := r.read(chunk):
            fh.write(block)
    staged.replace(target)
    return target


def signed_url(url: str) -> str:
    """Resolve an Earthdata URL to its signed object URL (valid ~1 h) for GDAL range reads."""
    http._check_host(url, EARTHDATA_HOSTS)
    req = urllib.request.Request(url, headers={**http._token_header(), 'Range': 'bytes=0-0'})
    with http._OPENER.open(req, timeout=60) as r:
        return r.geturl()


def _map(fn: Callable, items: list, workers: int) -> list:
    if workers <= 1 or len(items) <= 1:
        return [fn(i) for i in items]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(fn, items))


def _months(start: date, end: date) -> list[date]:
    out, d = [], date(start.year, start.month, 1)
    while d <= end:
        out.append(d)
        d = date(d.year + (d.month == 12), d.month % 12 + 1, 1)
    return out


def _granule_date(granule: dict) -> date:
    return datetime.fromisoformat(granule['time_start'].replace('Z', '+00:00')).date()


def _every(granules: list[dict], step_days: int) -> list[dict]:
    """Keep granules whose date falls on the step grid (all of them for `step_days <= 1`)."""
    if step_days <= 1 or not granules:
        return granules
    first = _granule_date(granules[0])
    return [g for g in granules if (_granule_date(g) - first).days % step_days == 0]


# ---------------------------------------------------------------------------
# Aridity: IMERG monthly (mm/h mean rate -> mm/month), nearest 0.1° pixel
# ---------------------------------------------------------------------------
def imerg_index(lon: float, lat: float) -> tuple[int, int]:
    """(lon, lat) indices of `Grid/precipitation` (time, 3600 lon, 1800 lat; centers at ±x.x5)."""
    return min(int((lon + 180.0) / 0.1), 3599), min(int((lat + 90.0) / 0.1), 1799)


def fetch_aridity(sites: list[Site], start: date, end: date, *, workers: int = 8,
                  search=search_cmr, opener=open_h5) -> FetchResult:
    result = FetchResult('aridity', period=f'{start:%Y-%m}/{end:%Y-%m}', support='nearest_native_pixel_0.1deg')
    granules = search(COLLECTIONS['imerg_monthly'], None, start, end)
    months = {m: None for m in _months(start, end)}

    def read(g: dict):
        month = _granule_date(g).replace(day=1)
        hours = calendar.monthrange(month.year, month.month)[1] * 24.0
        with opener(g['url']) as h5:
            dset = h5['Grid/precipitation']
            values = {}
            for s in sites:
                i, j = imerg_index(s.longitude, s.latitude)
                rate = float(dset[0, i, j])
                values[s.region_id] = rate * hours if rate >= 0.0 else math.nan
        return month, g['id'], values

    per_site = {s.region_id: dict.fromkeys(months, math.nan) for s in sites}
    for month, gid, values in _map(read, [g for g in granules if _granule_date(g).replace(day=1) in months], workers):
        result.granules.append(gid)
        for rid, v in values.items():
            per_site[rid][month] = v
    for rid, series in per_site.items():
        result.inputs[rid] = {'monthly_precip_mm': np.array(list(series.values()), dtype=float)}
    return result


# ---------------------------------------------------------------------------
# Soil moisture: SMAP L3 enhanced, nearest EASE2 9 km cell, AM overpass
# ---------------------------------------------------------------------------
def ease2_index(lon: float, lat: float) -> tuple[int, int]:
    x, y = EASE2.transform(lon, lat)
    g = EASE2_9KM
    row = int((g['y0'] - y) // g['cell_m'])
    col = int((x - g['x0']) // g['cell_m'])
    return min(max(row, 0), g['rows'] - 1), min(max(col, 0), g['cols'] - 1)


def fetch_soil_moisture(sites: list[Site], start: date, end: date, *, step_days: int = 8, workers: int = 8,
                        search=search_cmr, opener=open_h5) -> FetchResult:
    result = FetchResult('soil_moisture', period=f'{start}/{end}', support='nearest_native_pixel_ease2_9km')
    granules = _every(search(COLLECTIONS['smap'], None, start, end), step_days)
    group = 'Soil_Moisture_Retrieval_Data_AM/'

    def read(g: dict):
        with opener(g['url']) as h5:
            sm, qa = h5[group + 'soil_moisture'], h5[group + 'retrieval_qual_flag']
            out = {}
            for s in sites:
                r, c = ease2_index(s.longitude, s.latitude)
                value = float(sm[r, c])
                out[s.region_id] = (value if value != -9999.0 else math.nan, int(qa[r, c]))
        return g['id'], out

    series = {s.region_id: ([], []) for s in sites}
    for gid, values in _map(read, granules, workers):
        result.granules.append(gid)
        for rid, (v, q) in values.items():
            series[rid][0].append(v)
            series[rid][1].append(q)
    for rid, (sm, qa) in series.items():
        result.inputs[rid] = {'sm_m3m3': np.array(sm, dtype=float), 'qa_flag': np.array(qa, dtype=np.int64)}
    return result


# ---------------------------------------------------------------------------
# Thermal-IR emissivity: ASTER GED AG100 (1°x1° tiles, 100 m)
# ---------------------------------------------------------------------------
def ag100_tile(lon: float, lat: float) -> tuple[int, int]:
    """Tile key as in the granule name `AG100.v003.<north lat>.<west lon>.0001`."""
    return math.floor(lat) + 1, math.floor(lon)


def fetch_emissivity(sites: list[Site], *, workers: int = 4, search=search_cmr, opener=open_h5) -> FetchResult:
    result = FetchResult('thermal_emissivity', period='2000/2008', support='native_100m_pixels_in_footprint')
    by_tile: dict[tuple[int, int], list[Site]] = {}
    for s in sites:
        by_tile.setdefault(ag100_tile(s.longitude, s.latitude), []).append(s)

    def read(item):
        (north, west), tile_sites = item
        center = Site('tile', west + 0.5, north - 0.5)
        found = [g for g in search(COLLECTIONS['ag100'], center.bbox(100.0))
                 if re.search(rf'AG100\.v003\.{north}\.{west}\.', g['id'])]
        if not found:
            return None, {s.region_id: None for s in tile_sites}
        with opener(found[0]['url']) as h5:
            lat, lon = h5['Geolocation/Latitude'], h5['Geolocation/Longitude']
            n, m = lat.shape
            lat0, lat1, lon0, lon1 = float(lat[0, 0]), float(lat[n - 1, 0]), float(lon[0, 0]), float(lon[0, m - 1])
            emis = h5['Emissivity/Mean']
            out = {}
            for s in tile_sites:
                w, so, e, no = s.bbox()
                r0 = max(int(math.floor((lat0 - no) / (lat0 - lat1) * (n - 1))), 0)
                r1 = min(int(math.ceil((lat0 - so) / (lat0 - lat1) * (n - 1))) + 1, n)
                c0 = max(int(math.floor((w - lon0) / (lon1 - lon0) * (m - 1))), 0)
                c1 = min(int(math.ceil((e - lon0) / (lon1 - lon0) * (m - 1))) + 1, m)
                block = emis[:, r0:r1, c0:c1].astype(float)
                rows = lat0 - (lat0 - lat1) * np.arange(r0, r1) / (n - 1)
                cols = lon0 + (lon1 - lon0) * np.arange(c0, c1) / (m - 1)
                glon, glat = np.meshgrid(cols, rows)
                x, y = s.local_xy(glon, glat)
                inside = (np.abs(x) <= HALF_M) & (np.abs(y) <= HALF_M)
                block = np.where(block <= -9999, np.nan, block * 0.001)
                out[s.region_id] = {'emissivity_b10_b14': block[:, inside]}
        return found[0]['id'], out

    for gid, values in _map(read, list(by_tile.items()), workers):
        if gid:
            result.granules.append(gid)
        for rid, raw in values.items():
            if raw is not None:
                result.inputs[rid] = raw
            else:
                result.errors.append(f'{rid}: sin tesela AG100')
    return result


# ---------------------------------------------------------------------------
# Permafrost: ESA CCI v5.0 (CEDA, public NetCDF4, WGS84 lat/lon 0.01°)
# ---------------------------------------------------------------------------
def _cci_crs(h5, var: str) -> CRS:
    mapping = h5[var].attrs.get('grid_mapping')
    if mapping is not None:
        name = mapping.decode() if isinstance(mapping, bytes) else str(mapping)
        if name in h5:
            attrs = h5[name].attrs
            for key in ('crs_wkt', 'spatial_ref'):
                if key in attrs:
                    text = attrs[key]
                    return CRS.from_wkt(text.decode() if isinstance(text, bytes) else str(text))
            if 'straight_vertical_longitude_from_pole' in attrs:
                cf = {k: (v.decode() if isinstance(v, bytes) else (v.item() if hasattr(v, 'item') else v))
                      for k, v in attrs.items()}
                return CRS.from_cf(cf)
    raise ValueError(f'La variable {var} del CCI no declara una proyección legible')


def cci_coords(h5) -> tuple[str, str]:
    """Names of the (x, y) coordinate variables: `lon`/`lat` (v5.0) or projected `x`/`y`."""
    for xname, yname in (('lon', 'lat'), ('x', 'y'), ('longitude', 'latitude')):
        if xname in h5 and yname in h5:
            return xname, yname
    raise KeyError(f'El NetCDF del CCI no tiene coordenadas reconocibles: {list(h5.keys())}')


def _cci_window(h5, var: str, site: Site) -> np.ndarray:
    crs = _cci_crs(h5, var)
    xname, yname = cci_coords(h5)
    x = h5[xname][:].astype(float)
    y = h5[yname][:].astype(float)
    if crs.is_geographic:
        w, so, e, no = site.bbox()
        cols = np.flatnonzero((x >= w) & (x <= e))
        rows = np.flatnonzero((y >= so) & (y <= no))
    else:
        cx, cy = Transformer.from_crs('EPSG:4326', crs, always_xy=True).transform(site.longitude, site.latitude)
        cols = np.flatnonzero(np.abs(x - cx) <= HALF_M)
        rows = np.flatnonzero(np.abs(y - cy) <= HALF_M)
    dset = h5[var]
    if cols.size == 0 or rows.size == 0:
        return np.full((0,), np.nan)
    sl = (slice(rows[0], rows[-1] + 1), slice(cols[0], cols[-1] + 1))
    block = (dset[(0,) + sl] if dset.ndim == 3 else dset[sl]).astype(float)
    fill = dset.attrs.get('_FillValue')
    if fill is not None:
        block = np.where(block == float(np.asarray(fill).ravel()[0]), np.nan, block)
    scale = float(np.asarray(dset.attrs.get('scale_factor', 1.0)).ravel()[0])
    offset = float(np.asarray(dset.attrs.get('add_offset', 0.0)).ravel()[0])
    return (block * scale + offset).ravel()


def fetch_permafrost(sites: list[Site], year: int = 2023, *, opener=open_h5) -> FetchResult:
    result = FetchResult('permafrost', period=str(year), support='native_1km_pixels_in_footprint')
    for hemi, chosen in (('northern_hemisphere', [s for s in sites if s.latitude >= 0]),
                         ('Antarctica', [s for s in sites if s.latitude < 0])):
        if not chosen:
            continue
        urls = {k: cci_url(k, hemi, year) for k in CCI_FILES}
        with opener(urls['PFR']) as pfr_h5, opener(urls['ALT']) as alt_h5:
            result.granules += [f'{hemi}/{Path(u).name}' for u in urls.values()]
            for s in chosen:
                pfr = _cci_window(pfr_h5, 'PFR', s)
                alt = _cci_window(alt_h5, 'ALT', s)
                result.inputs[s.region_id] = {'pfr_pct': pfr, 'alt_m': alt if alt.shape == pfr.shape else None}
    return result


# ---------------------------------------------------------------------------
# MODIS HDF4 (snow and apparent thermal inertia): whole granule, read, erase
# ---------------------------------------------------------------------------
def modis_tile(lon: float, lat: float) -> tuple[int, int]:
    x, y = TO_SIN.transform(lon, lat)
    return int((x - MODIS_X0) // MODIS_TILE_M), int((MODIS_Y0 - y) // MODIS_TILE_M)


def _tile_tag(tile: tuple[int, int]) -> str:
    return f'.h{tile[0]:02d}v{tile[1]:02d}.'


def modis_pixels(site: Site, transform, shape: tuple[int, int]) -> tuple[np.ndarray, np.ndarray]:
    """Row/col of the tile pixels whose centers fall in the 3 km footprint (local equal-area)."""
    x, y = TO_SIN.transform(site.longitude, site.latitude)
    inv = ~transform
    c, r = inv * (x, y)
    pad = int(math.ceil(HALF_M / abs(transform.a))) + 2
    rows = np.arange(int(r) - pad, int(r) + pad + 1)
    cols = np.arange(int(c) - pad, int(c) + pad + 1)
    rr, cc = np.meshgrid(rows, cols, indexing='ij')
    px, py = transform * (cc + 0.5, rr + 0.5)
    lon, lat = Transformer.from_crs(MODIS_SIN, 'EPSG:4326', always_xy=True).transform(px, py)
    lx, ly = site.local_xy(lon, lat)
    inside = (np.abs(lx) <= HALF_M) & (np.abs(ly) <= HALF_M)
    inside &= (rr >= 0) & (rr < shape[0]) & (cc >= 0) & (cc < shape[1])
    return rr[inside], cc[inside]


def read_hdf4_layers(path: Path, layers: Iterable[str]) -> tuple[dict[str, np.ndarray], Any]:
    """Raw arrays of the named HDF4-EOS subdatasets plus the grid transform of the first one."""
    import rasterio
    out, transform = {}, None
    with rasterio.open(path) as container:
        subdatasets = container.subdatasets
    for layer in layers:
        name = next((sd for sd in subdatasets if sd.endswith(':' + layer)), None)
        if name is None:
            raise KeyError(f'{path.name} no contiene {layer}')
        with rasterio.open(name) as src:
            out[layer] = src.read(1)
            transform = transform or src.transform
    return out, transform


@dataclass
class _ModisJob:
    collection: str
    layers: tuple[str, ...]
    decode: Callable[[dict[str, np.ndarray], np.ndarray, np.ndarray], dict[str, np.ndarray]]
    coarsen: int = 1  # sample footprint cells on a grid this many times coarser (500 m -> 1 km)


def _modis_series(sites: list[Site], job: _ModisJob, start: date, end: date, step_days: int,
                  cache_dir: Path, workers: int, search, downloader, reader,
                  result: FetchResult) -> dict[str, list[tuple[date, dict[str, np.ndarray]]]]:
    """Per site, the decoded footprint pixels of every granule of its tile (oldest first)."""
    by_tile: dict[tuple[int, int], list[Site]] = {}
    for s in sites:
        by_tile.setdefault(modis_tile(s.longitude, s.latitude), []).append(s)
    series: dict[str, list] = {s.region_id: [] for s in sites}
    for tile, tile_sites in by_tile.items():
        granules = [g for g in search(COLLECTIONS[job.collection], tile_sites[0].bbox(500.0), start, end)
                    if _tile_tag(tile) in g['id'] + g['url']]
        granules = _every(granules, step_days)

        def read(g: dict):
            target = cache_dir / Path(urllib.parse.urlsplit(g['url']).path).name
            try:
                downloader(g['url'], target)
                arrays, transform = reader(target, job.layers)
            except Exception as exc:  # one bad granule must not stop the tile
                return g, None, f"{g['id']}: {type(exc).__name__}: {exc}"
            finally:
                target.unlink(missing_ok=True)
            shape = next(iter(arrays.values())).shape
            if job.coarsen > 1:
                transform = transform * Affine.scale(job.coarsen)
                shape = (shape[0] // job.coarsen, shape[1] // job.coarsen)
            values = {}
            for s in tile_sites:
                rr, cc = modis_pixels(s, transform, shape)
                values[s.region_id] = job.decode(arrays, rr, cc)
            return g, values, None

        for g, values, error in _map(read, granules, workers):
            if error:
                result.errors.append(error)
                continue
            result.granules.append(g['id'])
            for rid, decoded in values.items():
                series[rid].append((_granule_date(g), decoded))
    return series


def _decode_snow(arrays, rr, cc):
    return {'ndsi': arrays['NDSI_Snow_Cover'][rr, cc].astype(float),
            'qa': arrays['NDSI_Snow_Cover_Basic_QA'][rr, cc].astype(np.int64)}


def lst_kelvin(raw: np.ndarray, qc: np.ndarray, max_error_k: float = 2.0) -> np.ndarray:
    """MOD11A1 LST (K) with QC bits 0-1 in {00, 01} and LST error (bits 6-7) within `max_error_k`."""
    raw = np.asarray(raw).astype(float)
    qc = np.asarray(qc).astype(np.int64)
    error_class_max = {1.0: 0, 2.0: 1, 3.0: 2}.get(float(max_error_k), 1)
    ok = (raw > 0) & ((qc & 0b11) <= 1) & (((qc >> 6) & 0b11) <= error_class_max)
    return np.where(ok, raw * 0.02, np.nan)


def _decode_lst(arrays, rr, cc):
    return {'day': lst_kelvin(arrays['LST_Day_1km'][rr, cc], arrays['QC_Day'][rr, cc]),
            'night': lst_kelvin(arrays['LST_Night_1km'][rr, cc], arrays['QC_Night'][rr, cc])}


def albedo_on_1km(raw: np.ndarray, quality: np.ndarray, rr: np.ndarray, cc: np.ndarray) -> np.ndarray:
    """Mean white-sky shortwave albedo of the 2x2 500 m cells under each 1 km cell (full inversions only)."""
    raw = np.asarray(raw).astype(float)
    ok = (raw != 32767) & (np.asarray(quality) == 0)
    albedo = np.where(ok, raw * 0.001, np.nan)
    blocks = np.stack([albedo[2 * rr + dr, 2 * cc + dc] for dr in (0, 1) for dc in (0, 1)])
    with np.errstate(all='ignore'):
        return np.nanmean(blocks, axis=0)


def fetch_snow(sites: list[Site], start: date, end: date, cache_dir: Path, *, step_days: int = 4,
               workers: int = 4, search=search_cmr, downloader=download, reader=read_hdf4_layers) -> FetchResult:
    result = FetchResult('snow_persistence', period=f'{start}/{end}', support='native_500m_pixels_in_footprint')
    job = _ModisJob('mod10a1', ('NDSI_Snow_Cover', 'NDSI_Snow_Cover_Basic_QA'), _decode_snow)
    series = _modis_series(sites, job, start, end, step_days, cache_dir, workers, search, downloader, reader, result)
    for rid, obs in series.items():
        if obs:
            result.inputs[rid] = {'ndsi_snow_cover': np.stack([o['ndsi'] for _, o in obs]),
                                  'qa_flag': np.stack([o['qa'] for _, o in obs])}
    return result


def fetch_apparent_thermal_inertia(sites: list[Site], start: date, end: date, cache_dir: Path, *,
                                   lst_step_days: int = 1, albedo_step_days: int = 8, workers: int = 4,
                                   search=search_cmr, downloader=download, reader=read_hdf4_layers) -> FetchResult:
    """Terra + Aqua LST and MCD43A3 albedo on the 1 km footprint pixels, labelled by season."""
    result = FetchResult('apparent_thermal_inertia', period=f'{start}/{end}',
                         support='native_1km_pixels_in_footprint_seasonal_medians')
    lst_layers = ('LST_Day_1km', 'QC_Day', 'LST_Night_1km', 'QC_Night')
    terra = _modis_series(sites, _ModisJob('mod11a1', lst_layers, _decode_lst), start, end, lst_step_days,
                          cache_dir, workers, search, downloader, reader, result)
    aqua = _modis_series(sites, _ModisJob('myd11a1', lst_layers, _decode_lst), start, end, lst_step_days,
                         cache_dir, workers, search, downloader, reader, result)

    def decode_albedo(arrays, rr, cc):
        # rr/cc are the same 1 km footprint cells as LST (coarsen=2 on the aligned 500 m grid).
        return {'albedo': albedo_on_1km(arrays['Albedo_WSA_shortwave'],
                                        arrays['BRDF_Albedo_Band_Mandatory_Quality_shortwave'], rr, cc)}

    albedo = _modis_series(sites, _ModisJob('mcd43a3', ('Albedo_WSA_shortwave',
                                                        'BRDF_Albedo_Band_Mandatory_Quality_shortwave'),
                                            decode_albedo, coarsen=2),
                           start, end, albedo_step_days, cache_dir, workers, search, downloader, reader, result)
    for s in sites:
        lst = terra[s.region_id] + aqua[s.region_id]
        alb = albedo[s.region_id]
        if not lst or not alb:
            continue
        n_pix = lst[0][1]['day'].size
        alb_rows = [o['albedo'] for _, o in alb if o['albedo'].size == n_pix]
        alb_dates = [d for d, o in alb if o['albedo'].size == n_pix]
        if not alb_rows:
            result.errors.append(f'{s.region_id}: albedo y LST no comparten píxeles')
            continue
        result.inputs[s.region_id] = {
            'lst_day_k': np.stack([o['day'] for _, o in lst]),
            'lst_night_k': np.stack([o['night'] for _, o in lst]),
            'albedo': np.stack(alb_rows),
            'day_season': np.array([f'{d.year + (d.month == 12)}-{SEASON_OF_MONTH[d.month]}' for d, _ in lst]),
            'night_season': np.array([f'{d.year + (d.month == 12)}-{SEASON_OF_MONTH[d.month]}' for d, _ in lst]),
            'albedo_season': np.array([f'{d.year + (d.month == 12)}-{SEASON_OF_MONTH[d.month]}' for d in alb_dates]),
        }
    return result


# ---------------------------------------------------------------------------
# SAR backscatter: OPERA RTC-S1 bursts on a 30 m local grid, per-pixel temporal median
# ---------------------------------------------------------------------------
def read_opera_scene(urls: dict[str, str], site: Site, cell_m: float = 30.0) -> dict[str, np.ndarray]:
    """VV, VH (linear gamma0) and layover/shadow mask warped to the site's local 3 km grid."""
    import rasterio
    from rasterio.enums import Resampling
    from rasterio.transform import from_origin
    from rasterio.vrt import WarpedVRT

    n = int(round(extractors.WINDOW_M / cell_m))
    crs = CRS.from_proj4(f'+proj=laea +lon_0={site.longitude} +lat_0={site.latitude} +datum=WGS84 +units=m')
    transform = from_origin(-HALF_M, HALF_M, cell_m, cell_m)
    out = {}
    for key, resampling in (('VV', Resampling.average), ('VH', Resampling.average), ('mask', Resampling.nearest)):
        with rasterio.open('/vsicurl/' + signed_url(urls[key])) as src, WarpedVRT(
                src, crs=crs.to_wkt(), transform=transform, width=n, height=n, resampling=resampling,
                src_nodata=src.nodata if src.nodata is not None else (255 if key == 'mask' else np.nan),
                nodata=255 if key == 'mask' else np.nan) as vrt:
            out[key] = vrt.read(1)
    return out


def combine_opera_scenes(scenes: list[dict[str, np.ndarray]]) -> dict[str, np.ndarray]:
    """Per-pixel median over scenes, using only clear (mask 0) positive observations."""
    vv = np.stack([np.where((s['mask'] == OPERA_MASK_CLEAR) & (s['VV'] > 0), s['VV'], np.nan) for s in scenes])
    vh = np.stack([np.where((s['mask'] == OPERA_MASK_CLEAR) & (s['VH'] > 0), s['VH'], np.nan) for s in scenes])
    with np.errstate(all='ignore'):
        return {'sigma0_vv_linear': np.nanmedian(vv, axis=0), 'sigma0_vh_linear': np.nanmedian(vh, axis=0)}


def fetch_sar(sites: list[Site], start: date, end: date, *, max_scenes: int = 12, workers: int = 4,
              search=search_cmr, scene_reader=read_opera_scene) -> FetchResult:
    result = FetchResult('sar_backscatter', period=f'{start}/{end}', support='30m_local_grid_temporal_median')
    for s in sites:
        granules = search(COLLECTIONS['opera_rtc'], s.bbox(), start, end)[-max_scenes:]

        def read(g: dict):
            urls = {'VV': g['url']}
            for key, suffix in (('VH', '_VH.tif'), ('mask', '_mask.tif')):
                urls[key] = next((h for h in g['links'] if h.endswith(suffix)), g['url'].replace('_VV.tif', suffix))
            try:
                return g['id'], scene_reader(urls, s), None
            except Exception as exc:
                return g['id'], None, f"{g['id']}: {type(exc).__name__}: {exc}"

        scenes = []
        for gid, scene, error in _map(read, granules, workers):
            if error:
                result.errors.append(error)
            else:
                result.granules.append(gid)
                scenes.append(scene)
        if scenes:
            result.inputs[s.region_id] = combine_opera_scenes(scenes)
    return result


# ---------------------------------------------------------------------------
# Rows and manifests
# ---------------------------------------------------------------------------
def build_manifests(results: list[FetchResult], fetched_at: datetime) -> tuple[str, list[dict]]:
    """One manifest id for the run; one manifest row per product with its period and granule count."""
    spec = surface.load_surface_spec()
    granules = sorted({g for r in results for g in r.granules})
    manifest_id = extractors.make_manifest_id(granules or ['empty'], 'surface-fetch-v1')
    rows = []
    for r in results:
        sources = {src['product_id']: src for src in spec['dimensions'][r.dimension]['sources'].values()}
        for product_id in PRODUCT_IDS[r.dimension]:
            src = sources.get(product_id, {})
            rows.append({
                'source_manifest_id': manifest_id,
                'product_id': product_id,
                'asset_id': f'{r.dimension}:{product_id}:{len(r.granules)}_granules:{r.support}',
                'access_mode': 'on_demand',
                'sha256_or_etag': None,
                'native_resolution_m': float(src.get('native_resolution_m', 0.0)),
                'effective_resolution_m': float(src.get('native_resolution_m', 0.0)),
                'observation_period': r.period,
                'created_at': fetched_at,
                'crs_wkt': surface.EARTH_CRS_WKT,
                'planetary_frame': 'EARTH_WGS84',
                'doi': src.get('doi'),
                'product_version': src.get('product_version'),
            })
    return manifest_id, rows


def build_rows(sites: list[Site], results: list[FetchResult], manifest_id: str,
               fetched_at: datetime, min_valid_fraction: float = surface.MIN_VALID_FRACTION) -> list[dict]:
    """`enrichment_surface` rows. Dimensions not fetched in this run keep `on_demand_fetchable`."""
    rows = []
    for s in sites:
        raw = {r.dimension: r.inputs[s.region_id] for r in results if s.region_id in r.inputs}
        rows.append(surface.extract_surface_dimensions_window(
            s.region_id, raw_inputs=raw, source_manifest_id=manifest_id, updated_at=fetched_at,
            min_valid_fraction=min_valid_fraction))
    return rows


def default_cache_dir() -> Path:
    base = os.environ.get('ATLAS_CACHE_DIR')
    return Path(base) / 'surface' if base else Path(tempfile.gettempdir()) / 'analogos-surface'


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def season_range(year: int) -> tuple[date, date]:
    """Climatological year Dec(year-1)..Nov(year) so every season is complete."""
    return date(year - 1, 12, 1), date(year, 11, 30)

