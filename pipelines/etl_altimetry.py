"""ICESat-2 laser bridge over candidate windows (audit 2026-11-14, section 3, priority 7).

Laser altimetry measures heights along profiles, without DEM interpolation. Over the 3 km
core of a window this module computes, from ATL08 v007 terrain segments:

- along-track slopes between consecutive 20 m sub-segments and 100 m segments;
- differential slopes at 200 m and 600 m baselines (Kreslavsky & Head 2000; used with
  LOLA by Rosenburg et al. 2011): s_d(L) = dh(L)/L - dh(2L)/(2L), centred on one point,
  which removes the regional slope and keeps the roughness at scale L;
- the same along-track slopes and differential slopes from GLO-30 sampled at the same
  segments, and the height difference DEM - laser (GLO-30 lifted to the ellipsoid with
  EGM2008), which validates the DEM features with an independent measurement.

Along-track slopes are directional (|grad h| |cos theta|), so they are compared with the DEM
sampled on the same pairs, never with the 240 m slope of the window. The 600 m differential
slope is the baseline that MOLA (about 300 m shot spacing) and LOLA can also resolve.

Granules are found in CMR (public) and read by HTTP ranges from NSIDC with
EARTHDATA_TOKEN taken only from the environment; nothing is downloaded whole.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
import io
import json
import math
import os
import time
import urllib.error
import urllib.parse
import urllib.request

import numpy as np
from pyproj import Transformer
from rasterio.enums import Resampling
from scipy.ndimage import map_coordinates

from pipelines import atlas_topography as topo
from pipelines import etl_extractors as ex
from pipelines.etl_bridges_schema import ALTIMETRY_INSTRUMENT, ALTIMETRY_METRICS

CMR_GRANULES = 'https://cmr.earthdata.nasa.gov/search/granules.json'
ATL08 = {'short_name': 'ATL08', 'version': '007', 'provider': 'NSIDC_CPRD'}
ATL08_CONCEPT_ID = 'C3565574177-NSIDC_CPRD'
PRODUCT_ID = 'NSIDC ATL08.007'
DATA_HOST = 'data.nsidc.earthdatacloud.nasa.gov'
HARMONY = 'https://harmony.earthdata.nasa.gov'
HARMONY_HOST = 'harmony.earthdata.nasa.gov'
ALLOWED_HOSTS = (DATA_HOST, HARMONY_HOST)
# Variables requested from the Harmony trajectory subsetter for every beam.
LAND_SEGMENT_VARIABLES = (
    'latitude', 'longitude', 'latitude_20m', 'longitude_20m', 'layer_flag', 'segment_watermask',
    'segment_snowcover', 'terrain/h_te_best_fit', 'terrain/h_te_best_fit_20m', 'terrain/te_quality_score',
    'terrain/n_te_photons', 'terrain/subset_te_flag',
)
HARMONY_POLL_S = 10.0
HARMONY_TIMEOUT_S = 3600.0
BEAMS = ('gt1l', 'gt1r', 'gt2l', 'gt2r', 'gt3l', 'gt3r')
FILL_LIMIT = 1e38
CORE_HALF_M = ex.WINDOW_M // 2
# Geographic search box margin around the core (degrees of latitude); longitude scaled by cos(lat).
SEARCH_MARGIN_M = 200.0

# Quality of a terrain segment: clear sky (layer_flag 0), not water, finite height, terrain
# quality score in [60, 100] (127 is fill) and at least 20 terrain photons. 20 m sub-segments
# also need subset_te_flag = 1. `h_te_uncertainty` is not used: it adds systematic terms and
# reaches 20-300 m over bare desert (checked on Atacama granules of 2026). Thresholds are
# initial decisions recorded with each run.
MIN_TE_QUALITY_SCORE = 60
MIN_TE_PHOTONS = 20
# segment_snowcover (ATL09 daily snow/ice): 0 ice-free water, 1 snow-free land, 2 snow, 3 ice.
SNOW_CODE_MIN = 2
STEP_100M = 100.0
STEP_20M = 20.0
PAIR_TOLERANCE = 0.15          # fraction of the nominal distance accepted for a pair
DIFF_BASELINES_M = (200.0, 600.0)
MIN_PAIRS_100M = 20            # fewer pairs -> insufficient_coverage
GEOID = Transformer.from_crs('EPSG:4326+3855', 'EPSG:4979', always_xy=True)
CRS_WKT_ITRF = 'EPSG:7912 (ITRF2014, elipsoide WGS84)'


# ---------------------------------------------------------------------------
# Profile metrics (pure numpy; also usable for LOLA or MOLA profiles)
# ---------------------------------------------------------------------------
def along_track(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Along-track coordinate of a straight profile: projection on its first-to-last axis."""
    if len(x) < 2:
        return np.zeros(len(x))
    dx, dy = x[-1] - x[0], y[-1] - y[0]
    norm = math.hypot(dx, dy) or 1.0
    return (x - x[0]) * dx / norm + (y - y[0]) * dy / norm


def pair_indices(s: np.ndarray, step_m: float, tol: float = PAIR_TOLERANCE) -> tuple[np.ndarray, np.ndarray]:
    """Consecutive points of a sorted profile whose separation is step_m within tolerance."""
    i = np.arange(len(s) - 1)
    d = np.abs(s[1:] - s[:-1])
    keep = np.abs(d - step_m) <= tol * step_m
    return i[keep], i[keep] + 1


def diff_indices(s: np.ndarray, baseline_m: float, step_m: float,
                 tol: float = PAIR_TOLERANCE) -> tuple[np.ndarray, ...]:
    """Index quadruples (c, a, b, d) for the differential slope at `baseline_m`.

    a, b are at -L/2 and +L/2 of the centre point and c, d at -L and +L, with L/2 = k * step.
    Missing segments break the index spacing, so every separation is checked on `s`.
    """
    k = int(round(baseline_m / (2 * step_m)))
    if k < 1:
        raise ValueError('La línea base debe ser al menos dos pasos')
    centre = np.arange(2 * k, len(s) - 2 * k)
    if centre.size == 0:
        empty = np.array([], dtype=int)
        return empty, empty, empty, empty
    c, a, b, d = centre - 2 * k, centre - k, centre + k, centre + 2 * k
    ok = (np.abs(np.abs(s[b] - s[a]) - baseline_m) <= tol * baseline_m) & \
         (np.abs(np.abs(s[d] - s[c]) - 2 * baseline_m) <= tol * 2 * baseline_m)
    return c[ok], a[ok], b[ok], d[ok]


def pair_slopes_deg(s: np.ndarray, h: np.ndarray, i: np.ndarray, j: np.ndarray) -> np.ndarray:
    dh, ds = h[j] - h[i], np.abs(s[j] - s[i])
    ok = np.isfinite(dh) & (ds > 0)
    return np.degrees(np.arctan(np.abs(dh[ok]) / ds[ok]))


def diff_slopes_deg(s: np.ndarray, h: np.ndarray, c, a, b, d) -> np.ndarray:
    s_short = (h[b] - h[a]) / (s[b] - s[a])
    s_long = (h[d] - h[c]) / (s[d] - s[c])
    sd = s_short - s_long
    return np.degrees(np.arctan(np.abs(sd[np.isfinite(sd)])))


def _pct(values: list[np.ndarray], q: float) -> float | None:
    v = np.concatenate(values) if values else np.array([])
    return float(np.percentile(v, q)) if v.size else None


@dataclass
class Profile:
    """One beam crossing of the core: 100 m segments and their 20 m sub-segments."""
    granule: str
    beam: str
    beam_type: str
    date: str
    x: np.ndarray
    y: np.ndarray
    h: np.ndarray
    snow: np.ndarray  # bool: snow or ice flagged on the segment
    x20: np.ndarray
    y20: np.ndarray
    h20: np.ndarray
    h_dem: np.ndarray = field(default=None)  # GLO-30 on the ellipsoid at (x, y)


def profile_metrics(profiles: list[Profile]) -> dict:
    """Laser and DEM metrics pooled over all profiles; DEM metrics use the same pairs."""
    acc: dict[str, list[np.ndarray]] = {k: [] for k in (
        'l20', 'l100', 'd100', 'dh', *(f'l_diff_{int(b)}' for b in DIFF_BASELINES_M),
        *(f'd_diff_{int(b)}' for b in DIFF_BASELINES_M))}
    n_seg = 0
    snow = []
    for p in profiles:
        s_all = along_track(p.x, p.y)
        order = np.argsort(s_all)
        s, h = s_all[order], p.h[order]
        hd = p.h_dem[order] if p.h_dem is not None else np.full_like(h, np.nan)
        n_seg += len(s)
        snow.append(p.snow)
        i, j = pair_indices(s, STEP_100M)
        acc['l100'].append(pair_slopes_deg(s, h, i, j))
        both = np.isfinite(hd[i]) & np.isfinite(hd[j])
        acc['d100'].append(pair_slopes_deg(s, hd, i[both], j[both]))
        for base in DIFF_BASELINES_M:
            q = diff_indices(s, base, STEP_100M)
            acc[f'l_diff_{int(base)}'].append(diff_slopes_deg(s, h, *q))
            acc[f'd_diff_{int(base)}'].append(diff_slopes_deg(s, hd, *q))
        acc['dh'].append((hd - h)[np.isfinite(hd)])
        if len(p.h20) > 1:
            s20_all = along_track(p.x20, p.y20)
            o20 = np.argsort(s20_all)
            s20, h20 = s20_all[o20], p.h20[o20]
            i20, j20 = pair_indices(s20, STEP_20M)
            acc['l20'].append(pair_slopes_deg(s20, h20, i20, j20))
    dh = np.concatenate(acc['dh']) if acc['dh'] else np.array([])
    med = float(np.median(dh)) if dh.size else None
    snow_all = np.concatenate(snow) if snow else np.array([])
    count = lambda k: int(sum(len(a) for a in acc[k]))  # noqa: E731
    return {
        'n_tracks': len(profiles),
        'n_segments': n_seg,
        'n_pairs_20m': count('l20'),
        'n_pairs_100m': count('l100'),
        'n_diff_200m': count('l_diff_200'),
        'n_diff_600m': count('l_diff_600'),
        'laser_slope_20m_p50_deg': _pct(acc['l20'], 50),
        'laser_slope_20m_p90_deg': _pct(acc['l20'], 90),
        'laser_slope_100m_p50_deg': _pct(acc['l100'], 50),
        'laser_slope_100m_p90_deg': _pct(acc['l100'], 90),
        'laser_diff_slope_200m_p50_deg': _pct(acc['l_diff_200'], 50),
        'laser_diff_slope_600m_p50_deg': _pct(acc['l_diff_600'], 50),
        'dem_slope_100m_p50_deg': _pct(acc['d100'], 50),
        'dem_slope_100m_p90_deg': _pct(acc['d100'], 90),
        'dem_diff_slope_200m_p50_deg': _pct(acc['d_diff_200'], 50),
        'dem_diff_slope_600m_p50_deg': _pct(acc['d_diff_600'], 50),
        'dem_minus_laser_median_m': med,
        'dem_minus_laser_nmad_m': float(1.4826 * np.median(np.abs(dh - med))) if dh.size else None,
        'snow_flag_fraction': float(np.mean(snow_all)) if snow_all.size else None,
    }


def altimetry_status(metrics: dict) -> str:
    if metrics['n_segments'] == 0:
        return 'no_swath_coverage'
    if metrics['n_pairs_100m'] < MIN_PAIRS_100M:
        return 'insufficient_coverage'
    return 'measured'


# ---------------------------------------------------------------------------
# Geometry of a window
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Core:
    """3 km core of a window in its UTM/UPS zone (same owner rule as the sweep)."""
    longitude: float
    latitude: float
    zone: object
    x0: float
    y0: float

    @classmethod
    def at(cls, longitude: float, latitude: float) -> 'Core':
        zone = topo.owner(longitude, latitude)
        x0, y0 = topo.projection(topo.WGS84, zone).transform(longitude, latitude)
        return cls(longitude, latitude, zone, x0, y0)

    def to_xy(self, lon: np.ndarray, lat: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        x, y = topo.projection(topo.WGS84, self.zone).transform(lon, lat)
        return np.asarray(x) - self.x0, np.asarray(y) - self.y0

    def inside(self, lon: np.ndarray, lat: np.ndarray, half: float = CORE_HALF_M) -> np.ndarray:
        x, y = self.to_xy(lon, lat)
        return (np.abs(x) <= half) & (np.abs(y) <= half)

    def search_bbox(self) -> tuple[float, float, float, float]:
        half = CORE_HALF_M * math.sqrt(2) + SEARCH_MARGIN_M
        dlat = half / 111_320.0
        dlon = half / (111_320.0 * max(math.cos(math.radians(self.latitude)), 0.05))
        return (self.longitude - dlon, max(self.latitude - dlat, -90.0),
                self.longitude + dlon, min(self.latitude + dlat, 90.0))


# ---------------------------------------------------------------------------
# Access: CMR search and HTTP range reads
# ---------------------------------------------------------------------------
def search_granules(bbox: tuple[float, float, float, float], collection: dict = ATL08,
                    page_size: int = 2000) -> list[dict]:
    """ATL08 granules intersecting `bbox` (W, S, E, N); public CMR, no credentials."""
    query = urllib.parse.urlencode({**collection, 'bounding_box': ','.join(f'{v:.6f}' for v in bbox),
                                    'page_size': page_size, 'sort_key': 'start_date'})
    with urllib.request.urlopen(f'{CMR_GRANULES}?{query}', timeout=60) as response:
        entries = json.load(response)['feed']['entry']
    out = []
    for e in entries:
        url = next((link['href'] for link in e.get('links', [])
                    if link['href'].startswith(f'https://{DATA_HOST}/') and link['href'].endswith('.h5')), None)
        if url:
            out.append({'id': e['title'], 'url': url, 'time_start': e['time_start'],
                        'size_mb': float(e.get('granule_size') or 0.0)})
    return out


class _StripAuthOnRedirect(urllib.request.HTTPRedirectHandler):
    """Follow redirects but never forward the Earthdata token to another host (S3, CloudFront)."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        new = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new is not None and urllib.parse.urlsplit(newurl).hostname != urllib.parse.urlsplit(req.full_url).hostname:
            new.remove_header('Authorization')
        return new


_OPENER = urllib.request.build_opener(_StripAuthOnRedirect)


def _token_header() -> dict:
    token = os.environ.get('EARTHDATA_TOKEN')
    if not token:
        raise PermissionError('ICESat-2 requiere EARTHDATA_TOKEN en el entorno')
    if any(ord(c) < 33 for c in token):
        raise ValueError('EARTHDATA_TOKEN contiene caracteres inválidos')
    return {'Authorization': 'Bearer ' + token}


def _check_host(url: str) -> str:
    if urllib.parse.urlsplit(url).scheme != 'https' or urllib.parse.urlsplit(url).hostname not in ALLOWED_HOSTS:
        raise ValueError(f'Host no permitido para ICESat-2: {url}')
    return url


def _multipart(fields: list[tuple[str, str]]) -> tuple[bytes, str]:
    boundary = 'icesat2-' + os.urandom(8).hex()
    parts = [f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n' for k, v in fields]
    return (''.join(parts) + f'--{boundary}--\r\n').encode(), f'multipart/form-data; boundary={boundary}'


def submit_subset_job(bbox: tuple[float, float, float, float], concept_id: str = ATL08_CONCEPT_ID) -> str:
    """Ask the Harmony trajectory subsetter for the land-segment variables inside `bbox`."""
    w, s, e, n = bbox
    fields = [('subset', f'lat({s:.6f}:{n:.6f})'), ('subset', f'lon({w:.6f}:{e:.6f})'), ('forceAsync', 'true')]
    fields += [('variable', f'{b}/land_segments/{v}') for b in BEAMS for v in LAND_SEGMENT_VARIABLES]
    body, ctype = _multipart(fields)
    url = f'{HARMONY}/{concept_id}/ogc-api-coverages/1.0.0/collections/parameter_vars/coverage/rangeset'
    req = urllib.request.Request(url, data=body, headers={**_token_header(), 'Content-Type': ctype}, method='POST')
    with _OPENER.open(req, timeout=120) as response:  # 303 -> /jobs/<id>
        return json.load(response)['jobID']


def wait_subset_job(job_id: str, timeout_s: float = HARMONY_TIMEOUT_S, poll_s: float = HARMONY_POLL_S) -> dict:
    """Poll a Harmony job until it ends; returns its status with every data link."""
    t0 = time.monotonic()
    url = f'{HARMONY}/jobs/{job_id}?page=1&limit=2000'
    while True:
        with _OPENER.open(urllib.request.Request(url, headers=_token_header()), timeout=60) as response:
            job = json.load(response)
        if job['status'] in ('successful', 'complete_with_errors', 'failed', 'canceled'):
            return job
        if time.monotonic() - t0 > timeout_s:
            raise TimeoutError(f'El trabajo Harmony {job_id} no terminó en {timeout_s:.0f} s')
        time.sleep(poll_s)


def subset_outputs(job: dict) -> list[dict]:
    """Granule dicts (original id, time, URL of the subset file) from a finished Harmony job."""
    out = []
    for link in job.get('links', []):
        if link.get('rel') != 'data' or not link.get('title', '').endswith('.h5'):
            continue
        out.append({'id': link['title'].replace('_subsetted.h5', '.h5'), 'url': _check_host(link['href']),
                    'time_start': link.get('temporal', {}).get('start', '')})
    return out


class RangeFile(io.RawIOBase):
    """Read-only, block-cached file over HTTP ranges for h5py.

    The first request carries the Earthdata bearer token and resolves the redirect to the
    signed object URL (the token is dropped on the redirect); later blocks go straight to
    that URL. The token never leaves memory.
    """

    def __init__(self, url: str, block_size: int = 128 * 1024, attempts: int = 4) -> None:
        super().__init__()
        _check_host(url)
        self.url, self.block, self.attempts = url, block_size, attempts
        self.pos, self.cache, self.signed = 0, {}, None
        self.requests, self.bytes_read, self.etag, self.size = 0, 0, None, None
        self._block(0)

    def _request(self, start: int, end: int) -> bytes:
        for attempt in range(1, self.attempts + 1):
            headers = {'Range': f'bytes={start}-{end}'}
            target = self.signed
            if target is None:
                headers.update(_token_header())
                target = self.url
            try:
                with _OPENER.open(urllib.request.Request(target, headers=headers), timeout=90) as r:
                    data = r.read()
                    if self.signed is None:
                        self.signed = r.geturl()
                        self.etag = (r.headers.get('ETag') or '').strip('"') or None
                    self.size = int(r.headers['Content-Range'].rsplit('/', 1)[1])
            except urllib.error.HTTPError as exc:
                if exc.code in (401, 403) and self.signed is not None:
                    self.signed = None  # expired signature: resolve again with the token
                elif exc.code < 500 and exc.code != 429:
                    raise
                if attempt == self.attempts:
                    raise
            except (urllib.error.URLError, TimeoutError, ConnectionError):
                if attempt == self.attempts:
                    raise
            else:
                self.requests += 1
                self.bytes_read += len(data)
                return data
            time.sleep(2.0 * attempt)
        raise AssertionError('unreachable')

    def _block(self, index: int) -> bytes:
        if index not in self.cache:
            self.cache[index] = self._request(index * self.block, (index + 1) * self.block - 1)
        return self.cache[index]

    def readable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return True

    def tell(self) -> int:
        return self.pos

    def seek(self, offset: int, whence: int = 0) -> int:
        base = {0: 0, 1: self.pos, 2: self.size}[whence]
        self.pos = base + offset
        return self.pos

    def readinto(self, buffer) -> int:
        end = min(self.pos + len(buffer), self.size)
        out = bytearray()
        p = self.pos
        while p < end:
            index = p // self.block
            block = self._block(index)
            chunk = block[p - index * self.block: p - index * self.block + (end - p)]
            if not chunk:
                break
            out += chunk
            p += len(chunk)
        buffer[:len(out)] = out
        self.pos = p
        return len(out)


def _valid(a: np.ndarray) -> np.ndarray:
    return np.isfinite(a) & (np.abs(a) < FILL_LIMIT)


def read_profiles(h5, granule: dict, core: Core) -> list[Profile]:
    """Quality-filtered terrain segments of every beam crossing the core of `core`."""
    profiles = []
    date = granule['time_start'][:10]
    for beam in BEAMS:
        if f'{beam}/land_segments/latitude' not in h5:
            continue
        seg = h5[f'{beam}/land_segments']
        lat = seg['latitude'][:]
        w, s, e, n = core.search_bbox()
        rough = np.flatnonzero((lat >= s) & (lat <= n))  # latitude first: longitude is read only there
        if rough.size == 0:
            continue
        i0, i1 = int(rough.min()), int(rough.max()) + 1
        lat, lon = lat[i0:i1], seg['longitude'][i0:i1]
        inside = core.inside(lon, lat)
        if not inside.any():
            continue
        h = seg['terrain/h_te_best_fit'][i0:i1].astype('float64')
        score = seg['terrain/te_quality_score'][i0:i1]
        ok = (inside & _valid(h) & (seg['layer_flag'][i0:i1] == 0) & (seg['segment_watermask'][i0:i1] == 0)
              & (score >= MIN_TE_QUALITY_SCORE) & (score <= 100)
              & (seg['terrain/n_te_photons'][i0:i1] >= MIN_TE_PHOTONS))
        if not ok.any():
            continue
        h20 = seg['terrain/h_te_best_fit_20m'][i0:i1].astype('float64')
        lat20, lon20 = seg['latitude_20m'][i0:i1].astype('float64'), seg['longitude_20m'][i0:i1].astype('float64')
        ok20 = (ok[:, None] & _valid(h20) & _valid(lat20) & _valid(lon20)
                & (seg['terrain/subset_te_flag'][i0:i1] == 1))
        x, y = core.to_xy(lon[ok], lat[ok])
        x20, y20 = core.to_xy(lon20[ok20], lat20[ok20]) if ok20.any() else (np.array([]), np.array([]))
        inside20 = (np.abs(x20) <= CORE_HALF_M) & (np.abs(y20) <= CORE_HALF_M)
        beam_type = h5[beam].attrs.get('atlas_beam_type', b'')
        profiles.append(Profile(
            granule=granule['id'], beam=beam,
            beam_type=beam_type.decode() if isinstance(beam_type, bytes) else str(beam_type),
            date=date, x=x, y=y, h=h[ok], snow=seg['segment_snowcover'][i0:i1][ok].astype('int16') >= SNOW_CODE_MIN,
            x20=x20[inside20], y20=y20[inside20], h20=h20[ok20][inside20],
        ))
    return profiles


def read_granule(granule: dict, core: Core, block_size: int = 128 * 1024) -> dict:
    """Profiles of one granule plus access diagnostics; failures are reported, not raised."""
    import h5py  # analysis-only dependency (.tools/minerales)
    t0 = time.perf_counter()
    try:
        f = RangeFile(granule['url'], block_size=block_size)
        with h5py.File(f, 'r') as h5:
            profiles = read_profiles(h5, granule, core)
        return {'granule': granule, 'profiles': profiles, 'etag': f.etag, 'requests': f.requests,
                'bytes': f.bytes_read, 'seconds': time.perf_counter() - t0, 'error': None}
    except Exception as exc:  # noqa: BLE001 - one bad granule must not stop the window
        return {'granule': granule, 'profiles': [], 'etag': None, 'requests': 0, 'bytes': 0,
                'seconds': time.perf_counter() - t0, 'error': f'{type(exc).__name__}: {str(exc)[:160]}'}


# ---------------------------------------------------------------------------
# DEM at the laser segments
# ---------------------------------------------------------------------------
def dem_grid(core: Core, rasters: topo.Rasters, inventory: dict) -> tuple[np.ndarray, object, list[str]]:
    """GLO-30 over the core (plus one cell) on the 30 m UTM grid of the window."""
    half = CORE_HALF_M + 2 * ex.CELL_M
    crs, bounds, affine, shape = ex.window_grid(core.zone, core.x0, core.y0, half)
    entries = [inventory[k] for k in topo.tile_keys(bounds, 1) if k in inventory]
    z, ids = topo.mosaic(rasters, entries, crs, bounds, affine, shape, Resampling.bilinear)
    return z, affine, ids


def sample_dem_ellipsoid(core: Core, z: np.ndarray, affine, x: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Bilinear GLO-30 at core-relative (x, y), lifted from EGM2008 to the WGS84 ellipsoid."""
    if x.size == 0:
        return np.array([])
    col = (core.x0 + x - affine.c) / affine.a - 0.5
    row = (core.y0 + y - affine.f) / affine.e - 0.5
    filled = np.where(np.isfinite(z), z, 0.0)
    values = map_coordinates(filled, [row, col], order=1, mode='constant', cval=np.nan)
    support = map_coordinates(np.isfinite(z).astype('float64'), [row, col], order=1, mode='constant', cval=0.0)
    values[support < 1 - 1e-6] = np.nan
    lon, lat = topo.projection(core.zone, topo.WGS84).transform(core.x0 + x, core.y0 + y)
    _, _, h_ell = GEOID.transform(lon, lat, values)
    return np.asarray(h_ell, dtype='float64')


# ---------------------------------------------------------------------------
# Record
# ---------------------------------------------------------------------------
def build_record(region_id: str, granules: list[dict], results: list[dict], profiles: list[Profile],
                 dem_ids: list[str], now: datetime, access_mode: str = 'range') -> tuple[dict, list[dict]]:
    metrics = profile_metrics(profiles)
    used = sorted({p.granule for p in profiles})
    dates = sorted(p.date for p in profiles)
    manifest_id = ex.make_manifest_id(used + list(dem_ids), 'icesat2-atl08-v007') if used else 'none'
    row = {
        'region_id': region_id,
        'instrument': ALTIMETRY_INSTRUMENT,
        'product_id': PRODUCT_ID,
        'observation_period': f'{dates[0]}/{dates[-1]}' if dates else None,
        'granules_found': len(granules),
        'granules_with_data': len(used),
        **{k: metrics[k] for k in ('n_tracks', 'n_segments', 'n_pairs_20m', 'n_pairs_100m',
                                   'n_diff_200m', 'n_diff_600m')},
        **{k: metrics[k] for k in ALTIMETRY_METRICS},
        'altimetry_status': altimetry_status(metrics),
        'source_manifest_id': manifest_id,
        'updated_at': now,
    }
    by_id = {r['granule']['id']: r for r in results}
    manifests = [{
        'source_manifest_id': manifest_id,
        'product_id': PRODUCT_ID,
        'asset_id': gid,
        'access_mode': access_mode,
        'sha256_or_etag': by_id[gid]['etag'],
        'native_resolution_m': STEP_100M,
        'effective_resolution_m': STEP_100M,
        'observation_period': by_id[gid]['granule']['time_start'][:10],
        'created_at': now,
        'crs_wkt': CRS_WKT_ITRF,
        'planetary_frame': 'EARTH_WGS84',
    } for gid in used]
    return row, manifests


ACCESS_MODES = ('harmony', 'direct')


def extract_altimetry_record(site: dict, rasters: topo.Rasters | None, inventory: dict | None,
                             workers: int = 16, now: datetime | None = None,
                             max_granules: int | None = None,
                             access: str = 'harmony') -> tuple[dict, list[dict], dict]:
    """Search, read and summarise ATL08 over the 3 km core of `site` (region_id, lon, lat).

    `access='harmony'` subsets the granules server-side (trajectory subsetter: bbox and the
    land-segment variables) and reads each small output by ranges; `direct` reads the
    original granules by ranges (several MB each, much slower on a slow link).
    Returns (enrichment_altimetry row, manifest rows, diagnostics). Without `rasters` the DEM
    columns stay null (laser-only run).
    """
    if access not in ACCESS_MODES:
        raise ValueError(f'Modo de acceso desconocido: {access}')
    now = now or datetime.now(timezone.utc)
    core = Core.at(site['longitude'], site['latitude'])
    granules = search_granules(core.search_bbox())
    if max_granules is not None:
        granules = granules[-max_granules:]
    t0 = time.perf_counter()
    job_info = None
    if access == 'harmony' and granules:
        job_id = submit_subset_job(core.search_bbox())
        job = wait_subset_job(job_id)
        to_read = subset_outputs(job)
        if max_granules is not None:
            keep = {g['id'] for g in granules}
            to_read = [g for g in to_read if g['id'] in keep]
        job_info = {'job_id': job_id, 'status': job['status'], 'input_granules': job.get('numInputGranules'),
                    'outputs': len(to_read), 'warnings': len(job.get('warnings') or []),
                    'seconds': round(time.perf_counter() - t0, 1)}
    else:
        to_read = granules
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        results = list(pool.map(lambda g: read_granule(g, core, block_size=64 * 1024), to_read))
    profiles = [p for r in results for p in r['profiles']]
    dem_ids: list[str] = []
    if rasters is not None and profiles:
        z, affine, dem_ids = dem_grid(core, rasters, inventory)
        for p in profiles:
            p.h_dem = sample_dem_ellipsoid(core, z, affine, p.x, p.y)
    row, manifests = build_record(site['region_id'], granules, results, profiles, dem_ids, now,
                                  access_mode='harmony_subset_range' if access == 'harmony' else 'range')
    diagnostics = {
        'access': access,
        'harmony_job': job_info,
        'granules_found': len(granules),
        'granules_failed': [{'id': r['granule']['id'], 'error': r['error']} for r in results if r['error']],
        'read_seconds': round(time.perf_counter() - t0, 1),
        'bytes_read': int(sum(r['bytes'] for r in results)),
        'http_requests': int(sum(r['requests'] for r in results)),
        'dem_assets': dem_ids,
        'beams': {t: sum(1 for p in profiles if p.beam_type == t) for t in ('strong', 'weak')},
        'quality_filter': {'layer_flag': 0, 'segment_watermask': 0,
                           'te_quality_score': [MIN_TE_QUALITY_SCORE, 100], 'min_n_te_photons': MIN_TE_PHOTONS,
                           'subset_te_flag_20m': 1,
                           'pair_tolerance': PAIR_TOLERANCE, 'min_pairs_100m': MIN_PAIRS_100M},
    }
    return row, manifests, diagnostics
