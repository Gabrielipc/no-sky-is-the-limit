"""Readers that feed `pipelines.spectral_params` with reflectance from each body.

- CRISM MTRDR corrected reflectance (`*_if*_mtr3.img`, ENVI BSQ float32 on PDS): only the
  bands and rows needed are fetched with HTTP range requests and cached locally.
- EMIT L2A reflectance (`EMIT_L2A_RFL`, NetCDF4 swath + GLT on LP DAAC): see `emit_l2a_*`.
- Chandrayaan-1 M3 L2 reflectance (`*_RFL.IMG`, PDS3 BIL + `*_LOC.IMG`): see `m3_*`.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
import hashlib
import re
import time
from pathlib import Path

import httpx
from pyproj import Transformer
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
USER_AGENT = 'analogos-planetarios-etl/1.0'
CRISM_INVALID = 65535.0


def parse_envi_header(text: str) -> dict:
    """Minimal ENVI header parser (scalars and brace lists)."""
    out: dict = {}
    for m in re.finditer(r'^\s*([\w ]+?)\s*=\s*(\{.*?\}|[^\n]*)', text, re.M | re.S):
        key, value = m.group(1).strip().lower(), m.group(2).strip()
        if value.startswith('{'):
            value = value[1:-1]
            if key in ('wavelength', 'band names', 'fwhm'):
                value = [v.strip() for v in value.replace('\n', ' ').split(',') if v.strip()]
        out[key] = value
    return out


def http_range(url: str, start: int, length: int, client: httpx.Client, attempts: int = 6) -> bytes:
    """Exact byte range; retries network errors and rate limits (429/5xx) with exponential backoff."""
    for attempt in range(attempts):
        try:
            r = client.get(url, headers={'Range': f'bytes={start}-{start + length - 1}'})
            if r.status_code == 429 or r.status_code >= 500:
                raise httpx.HTTPStatusError(f'HTTP {r.status_code}', request=r.request, response=r)
            if r.status_code != 206 or len(r.content) != length:
                raise ValueError(f'Respuesta parcial inesperada ({r.status_code}, {len(r.content)} bytes)')
            return r.content
        except httpx.HTTPError:
            if attempt == attempts - 1:
                raise
            time.sleep(min(60.0, 2.0 * 2 ** attempt))
    raise AssertionError('unreachable')


@dataclass(frozen=True)
class EnviBsqRemote:
    """A remote ENVI BSQ float32 little-endian cube described by a local header."""
    url: str
    header_path: Path

    @property
    def header(self) -> dict:
        return parse_envi_header(self.header_path.read_text(encoding='latin-1'))

    @property
    def shape(self) -> tuple[int, int, int]:
        h = self.header
        return int(h['bands']), int(h['lines']), int(h['samples'])

    @property
    def wavelengths(self) -> np.ndarray:
        return np.array([float(v) for v in self.header['wavelength']])

    def _cached_slice(self, band: int, rows: tuple[int, int], n_samples: int, cache_dir: Path) -> np.ndarray | None:
        r0, r1 = rows
        tag = hashlib.sha256(f'{self.url}|{r0}|{r1}'.encode()).hexdigest()[:12]
        path = cache_dir / f'b{band:03d}_{tag}.npy'
        if path.exists():
            arr = np.load(path)
            if arr.shape == (r1 - r0, n_samples):
                return arr
        for sup_r0, sup_r1 in ((552, 752),):
            if sup_r0 <= r0 < r1 <= sup_r1:
                sup_tag = hashlib.sha256(f'{self.url}|{sup_r0}|{sup_r1}'.encode()).hexdigest()[:12]
                sup_path = cache_dir / f'b{band:03d}_{sup_tag}.npy'
                if sup_path.exists():
                    sup = np.load(sup_path)
                    if sup.shape == (sup_r1 - sup_r0, n_samples):
                        return sup[r0 - sup_r0:r1 - sup_r0]
        return None

    def read(self, bands: list[int], rows: tuple[int, int], cache_dir: Path, offline: bool = False) -> np.ndarray:
        """Bands x rows[0]:rows[1] x all samples; invalid (65535) becomes NaN. Cached per band."""
        h = self.header
        if h.get('interleave', '').lower() != 'bsq' or h.get('data type') != '4' or h.get('byte order') != '0':
            raise ValueError('Se espera ENVI BSQ float32 little-endian')
        n_bands, n_lines, n_samples = self.shape
        r0, r1 = rows
        if not 0 <= r0 < r1 <= n_lines:
            raise ValueError('Filas fuera del cubo')
        cache_dir.mkdir(parents=True, exist_ok=True)
        tag = hashlib.sha256(f'{self.url}|{r0}|{r1}'.encode()).hexdigest()[:12]
        out = np.full((len(bands), r1 - r0, n_samples), np.nan, dtype='float32')
        missing: list[tuple[int, int]] = []
        for i, band in enumerate(bands):
            cached = self._cached_slice(band, rows, n_samples, cache_dir)
            if cached is not None:
                out[i] = cached
            elif not offline:
                missing.append((i, band))
        if missing:
            with httpx.Client(timeout=60, headers={'User-Agent': USER_AGENT}, follow_redirects=True) as client:
                for i, band in missing:
                    path = cache_dir / f'b{band:03d}_{tag}.npy'
                    offset = int(h.get('header offset', 0)) + (band * n_lines + r0) * n_samples * 4
                    raw = http_range(self.url, offset, (r1 - r0) * n_samples * 4, client)
                    arr = np.frombuffer(raw, dtype='<f4').reshape(r1 - r0, n_samples)
                    np.save(path, arr)
                    out[i] = arr
        out = out.astype('float64')
        out[out == CRISM_INVALID] = np.nan
        return out


class RangeFile:
    """Read-only file object over HTTP range requests with a block cache (for h5py remote reads).

    The bearer token is taken from the environment by the caller and kept only in memory.
    """

    def __init__(self, url: str, token: str | None = None, block_size: int = 4 * 1024 * 1024,
                 max_blocks: int = 256):
        headers = {'User-Agent': USER_AGENT}
        if token:
            headers['Authorization'] = f'Bearer {token}'
        self.url = url
        self.client = httpx.Client(timeout=120, headers=headers, follow_redirects=True)
        self.block_size, self.max_blocks = block_size, max_blocks
        self.pos = 0
        self.blocks: dict[int, bytes] = {}
        self.bytes_fetched = 0
        r = self.client.get(url, headers={'Range': 'bytes=0-0'})
        if r.status_code != 206:
            raise OSError(f'El servidor no admite lecturas por rangos ({r.status_code})')
        self.size = int(r.headers['Content-Range'].split('/')[-1])
        self.etag = r.headers.get('ETag')

    def _block(self, index: int) -> bytes:
        if index not in self.blocks:
            if len(self.blocks) >= self.max_blocks:
                self.blocks.pop(next(iter(self.blocks)))
            start = index * self.block_size
            length = min(self.block_size, self.size - start)
            self.blocks[index] = http_range(self.url, start, length, self.client)
            self.bytes_fetched += length
        return self.blocks[index]

    def read(self, n: int = -1) -> bytes:
        if n < 0:
            n = self.size - self.pos
        n = max(0, min(n, self.size - self.pos))
        out = bytearray()
        while n > 0:
            index, offset = divmod(self.pos, self.block_size)
            chunk = self._block(index)[offset:offset + n]
            out += chunk
            self.pos += len(chunk)
            n -= len(chunk)
        return bytes(out)

    def readinto(self, buffer) -> int:
        data = self.read(len(buffer))
        buffer[:len(data)] = data
        return len(data)

    def seek(self, offset: int, whence: int = 0) -> int:
        self.pos = {0: offset, 1: self.pos + offset, 2: self.size + offset}[whence]
        return self.pos

    def tell(self) -> int:
        return self.pos

    def seekable(self) -> bool:
        return True

    def readable(self) -> bool:
        return True

    def close(self) -> None:
        self.client.close()


# ---------------------------------------------------------------------------
# Footprint samplers (one per instrument) for pipelines.spectral_bridge
# ---------------------------------------------------------------------------
def crism_footprint(cube_src: EnviBsqRemote, in_path: Path, longitude: float, latitude: float, side_m: float,
                    names: list[str], cache_dir: Path, product_id: str, offline: bool = False):
    """CRISM MTRDR corrected reflectance over the footprint; valid = VNIR/IR mask (IN band 9) == 0."""
    import rasterio
    from pipelines import spectral_bridge as bridge
    from pipelines import spectral_params as sp

    geom, local = bridge.footprint('Mars', longitude, latitude, side_m)
    with rasterio.open(in_path) as ds:
        g = bridge.footprint_in(geom, local, ds.crs)
        inside = bridge.raster_mask(g, ds.transform, (ds.height, ds.width))
        rows, cols = np.nonzero(inside)
        r0, r1, c0, c1 = rows.min(), rows.max() + 1, cols.min(), cols.max() + 1
        qa = ds.read(9, window=((r0, r1), (c0, c1)))
        pixel = abs(ds.transform.a)
    inside = inside[r0:r1, c0:c1]
    wl = cube_src.wavelengths
    bands = sp.required_band_indices(wl, names, 'channels')
    data = cube_src.read(bands, (int(r0), int(r1)), cache_dir, offline=offline)[:, :, c0:c1]
    full = np.full((wl.size,) + data.shape[1:], np.nan)
    full[bands] = data
    in_cov = inside & np.isfinite(qa) & (qa != CRISM_INVALID)
    valid = in_cov & (qa == 0) & np.isfinite(full[bands]).any(axis=0)
    return bridge.FootprintSample(
        instrument='CRISM_MTRDR', product_id=product_id, wavelengths=wl,
        reflectance=full[:, valid][:, None, :], footprint_cells=int(inside.sum()),
        in_coverage_cells=int(in_cov.sum()), valid_cells=int(valid.sum()), pixel_m=float(pixel),
        kernel_mode='channels',
        notes=['Reflectancia corregida MTRDR (IF); celdas válidas con máscara VNIR/IR = 0'],
    )


def emit_footprint(rfl_url: str, mask_url: str, longitude: float, latitude: float, side_m: float,
                   token: str, product_id: str):
    """EMIT L2A surface reflectance over the footprint in the GLT ortho grid (~60 m).

    Valid cells: GLT support, reflectance not fill, and the L2A aggregate mask flag = 0
    (clouds, cirrus, water, spacecraft, dilated cloud). Bands with good_wavelengths = 0 are NaN.
    """
    import h5py
    from affine import Affine
    from pipelines import spectral_bridge as bridge

    geom, local = bridge.footprint('Earth', longitude, latitude, side_m)
    rfl, msk = RangeFile(rfl_url, token, block_size=256 * 1024), RangeFile(mask_url, token, block_size=256 * 1024)
    try:
        with h5py.File(rfl, 'r') as f, h5py.File(msk, 'r') as m:
            gt = Affine.from_gdal(*f.attrs['geotransform'])
            g = bridge.footprint_in(geom, local, 'EPSG:4326', densify_m=30)
            minx, miny, maxx, maxy = g.bounds
            c0, r0 = (~gt) * (minx, maxy)
            c1, r1 = (~gt) * (maxx, miny)
            c0, r0 = int(np.floor(c0)) - 1, int(np.floor(r0)) - 1
            c1, r1 = int(np.ceil(c1)) + 1, int(np.ceil(r1)) + 1
            gx, gy = f['location/glt_x'], f['location/glt_y']
            if c0 < 0 or r0 < 0 or c1 > gx.shape[1] or r1 > gx.shape[0]:
                raise ValueError('La huella sale de la rejilla ortorrectificada de la escena')
            ix, iy = gx[r0:r1, c0:c1].astype(np.int64), gy[r0:r1, c0:c1].astype(np.int64)
            inside = bridge.raster_mask(g, gt * Affine.translation(c0, r0), ix.shape)
            n_rows, n_cols, n_bands = f['reflectance'].shape
            has = inside & (ix > 0) & (iy > 0) & (ix <= n_cols) & (iy <= n_rows)
            sx, sy = ix[has] - 1, iy[has] - 1
            sr0, sr1, sc0, sc1 = sy.min(), sy.max() + 1, sx.min(), sx.max() + 1
            block = f['reflectance'][sr0:sr1, sc0:sc1, :].astype('float64')
            spectra = block[sy - sr0, sx - sc0, :]
            spectra[spectra == -9999.0] = np.nan
            wl = f['sensor_band_parameters/wavelengths'][:].astype('float64')
            good_wl = f['sensor_band_parameters/good_wavelengths'][:].astype(bool)
            spectra[:, ~good_wl] = np.nan
            names = [b.decode() if isinstance(b, bytes) else str(b) for b in m['sensor_band_parameters/mask_bands'][:]]
            agg = names.index('Aggregate Flag')
            if m['mask'].shape[:2] != (n_rows, n_cols):
                raise ValueError('La máscara L2A no comparte la geometría de la reflectancia')
            mblock = m['mask'][sr0:sr1, sc0:sc1, agg]
            clear = mblock[sy - sr0, sx - sc0] == 0
            valid_px = clear & np.isfinite(spectra).any(axis=1)
            notes = [f"Reflectancia de superficie L2A v002; celdas en la rejilla GLT; máscara agregada = 0 ({int((~clear).sum())} celdas enmascaradas)",
                     f"{int((~good_wl).sum())} bandas marcadas como no válidas (vapor de agua y extremos)"]
            return bridge.FootprintSample(
                instrument='EMIT_L2A', product_id=product_id, wavelengths=wl,
                reflectance=spectra[valid_px].T[:, None, :], footprint_cells=int(inside.sum()),
                in_coverage_cells=int(has.sum()), valid_cells=int(valid_px.sum()),
                pixel_m=60.0, kernel_mode='nm', notes=notes,
            )
    finally:
        rfl.close()
        msk.close()


M3_BASE = 'https://planetarydata.jpl.nasa.gov/img/data/m3'
M3_INVALID = -999.0


def m3_urls(product: str, period: str, month: str) -> dict[str, str]:
    """PDS Imaging URLs of an M3 L2 product (RFL in CH1M3_0004) and its L1B geometry (CH1M3_0003)."""
    stem = product.replace('_V01_RFL', '')
    l2 = f'{M3_BASE}/CH1M3_0004/DATA/{period}/{month}/L2/{stem}_V01'
    l1 = f'{M3_BASE}/CH1M3_0003/DATA/{period}/{month}/L1B/{stem}_V03'
    return {'rfl': f'{l2}_RFL.IMG', 'rfl_hdr': f'{l2}_RFL.HDR', 'loc': f'{l1}_LOC.IMG', 'loc_hdr': f'{l1}_LOC.HDR',
            'obs': f'{l1}_OBS.IMG', 'obs_hdr': f'{l1}_OBS.HDR'}


def _fetch_text(url: str, client: httpx.Client) -> str:
    r = client.get(url)
    r.raise_for_status()
    return r.text


def _bil_lines(url: str, header: dict, r0: int, r1: int, client: httpx.Client, dtype: str) -> np.ndarray:
    """Lines r0:r1 of a BIL cube as (lines, bands, samples)."""
    bands, samples = int(header['bands']), int(header['samples'])
    item = np.dtype(dtype).itemsize
    line_bytes = bands * samples * item
    raw = http_range(url, int(header.get('header offset', 0)) + r0 * line_bytes, (r1 - r0) * line_bytes, client)
    return np.frombuffer(raw, dtype=dtype).reshape(r1 - r0, bands, samples)


def m3_footprint(urls: dict[str, str], longitude: float, latitude: float, side_m: float, product_id: str,
                 cache_dir: Path, max_incidence_deg: float = 85.0):
    """M3 L2 reflectance of the swath pixels whose centres fall inside the footprint.

    Valid pixels: reflectance not -999 in some band, and solar incidence on the facet
    (acos of OBS band 10) below `max_incidence_deg`; near the poles the L2 photometric
    correction is extrapolated, so incidence is reported with every sample.
    """
    from pipelines import spectral_bridge as bridge

    geom, local = bridge.footprint('Moon', longitude, latitude, side_m)
    half = side_m / 2
    cache_dir.mkdir(parents=True, exist_ok=True)
    with httpx.Client(timeout=120, headers={'User-Agent': USER_AGENT}, follow_redirects=True) as client:
        loc_h = parse_envi_header(_fetch_text(urls['loc_hdr'], client))
        rfl_h = parse_envi_header(_fetch_text(urls['rfl_hdr'], client))
        obs_h = parse_envi_header(_fetch_text(urls['obs_hdr'], client))
        if loc_h.get('data type') != '5' or rfl_h.get('data type') != '4' or rfl_h.get('interleave', '').strip() != 'bil':
            raise ValueError('Formato M3 inesperado (LOC float64 BIL, RFL float32 BIL)')
        loc_path = cache_dir / Path(urls['loc']).name.replace('.IMG', '.npy')
        if loc_path.exists():
            loc = np.load(loc_path)
        else:
            r = client.get(urls['loc'])
            r.raise_for_status()
            lines, samples = int(loc_h['lines']), int(loc_h['samples'])
            loc = np.frombuffer(r.content, dtype='<f8').reshape(lines, 3, samples)
            np.save(loc_path, loc)
        lon, lat = loc[:, 0, :], loc[:, 1, :]
        x, y = Transformer.from_crs(f'+proj=longlat {bridge.BODY_SHAPES["Moon"]}', local, always_xy=True).transform(lon, lat)
        inside = (np.abs(x) <= half) & (np.abs(y) <= half)
        if not inside.any():
            raise ValueError(f'{product_id} no cubre la huella')
        rows = np.nonzero(inside.any(axis=1))[0]
        r0, r1 = int(rows.min()), int(rows.max()) + 1
        rfl = _bil_lines(urls['rfl'], rfl_h, r0, r1, client, '<f4').astype('float64')
        obs = _bil_lines(urls['obs'], obs_h, r0, r1, client, '<f4').astype('float64')
    rfl[rfl == M3_INVALID] = np.nan
    sub = inside[r0:r1]
    spectra = np.transpose(rfl, (1, 0, 2))[:, sub]            # (bands, n_inside)
    cos_i = obs[:, 9, :][sub]
    incidence = np.degrees(np.arccos(np.clip(cos_i, -1, 1)))
    lit = incidence < max_incidence_deg
    has_data = np.isfinite(spectra).any(axis=0) & (np.nanmax(np.where(np.isfinite(spectra), spectra, -1), axis=0) > 0)
    valid = lit & has_data
    wl = np.array([float(v) for v in rfl_h['wavelength']])
    # Expected cells: footprint area over the mean pixel area estimated from LOC spacing.
    xs, ys = x[r0:r1], y[r0:r1]
    dx = np.nanmedian(np.hypot(np.diff(xs, axis=1), np.diff(ys, axis=1)))
    dy = np.nanmedian(np.hypot(np.diff(xs, axis=0), np.diff(ys, axis=0)))
    expected = int(round(side_m * side_m / (dx * dy))) if dx > 0 and dy > 0 else int(sub.sum())
    notes = [
        f'M3 L2 v01 (modo global); píxeles de barrido con centro en la huella; píxel ≈ {dx:.0f} × {dy:.0f} m',
        f'Incidencia solar sobre la faceta: mediana {np.nanmedian(incidence):.1f}°, P90 {np.nanpercentile(incidence, 90):.1f}°; '
        f'válidos con incidencia < {max_incidence_deg:.0f}°',
        f'{int((~lit).sum())} píxeles excluidos por incidencia, {int((lit & ~has_data).sum())} sin datos',
    ]
    return bridge.FootprintSample(
        instrument='M3_L2', product_id=product_id, wavelengths=wl,
        reflectance=spectra[:, valid][:, None, :], footprint_cells=max(expected, int(sub.sum())),
        in_coverage_cells=int(sub.sum()), valid_cells=int(valid.sum()), pixel_m=float(np.sqrt(dx * dy)),
        kernel_mode='nm', notes=notes,
    ), {'incidence_p50_deg': float(np.nanmedian(incidence)), 'incidence_p90_deg': float(np.nanpercentile(incidence, 90)),
        'pixels_inside': int(sub.sum()), 'expected_cells': expected}


def m3_min_distance_m(urls: dict[str, str], longitude: float, latitude: float, stride: int = 50) -> float:
    """Distance from the site to the nearest LOC pixel on every `stride`-th line (coarse screening)."""
    from pipelines import spectral_bridge as bridge

    _, local = bridge.footprint('Moon', longitude, latitude, 1.0)
    to_local = Transformer.from_crs(f'+proj=longlat {bridge.BODY_SHAPES["Moon"]}', local, always_xy=True)
    with httpx.Client(timeout=60, headers={'User-Agent': USER_AGENT}, follow_redirects=True) as client:
        h = parse_envi_header(_fetch_text(urls['loc_hdr'], client))
        lines = int(h['lines'])
        best = np.inf
        for r in range(0, lines, stride):
            loc = _bil_lines(urls['loc'], h, r, r + 1, client, '<f8')[0]
            x, y = to_local.transform(loc[0], loc[1])
            best = min(best, float(np.nanmin(np.hypot(x, y))))
    return best


def m3_cached_loc_screening(loc_npy_path: Path, longitude: float, latitude: float,
                            sides_m: Sequence[float] = (1800, 3000)) -> dict:
    """Screen a cached M3 LOC `.npy` file locally for distance and footprint pixel support."""
    from pipelines import spectral_bridge as bridge

    loc = np.load(loc_npy_path)
    _, local = bridge.footprint('Moon', longitude, latitude, 1.0)
    to_local = Transformer.from_crs(f'+proj=longlat {bridge.BODY_SHAPES["Moon"]}', local, always_xy=True)
    x, y = to_local.transform(loc[:, 0, :], loc[:, 1, :])
    dist = np.hypot(x, y)
    min_dist = float(np.nanmin(dist))
    by_side: dict[str, dict] = {}
    for side_m in sides_m:
        half = side_m / 2
        inside = (np.abs(x) <= half) & (np.abs(y) <= half)
        n_in = int(inside.sum())
        rec: dict = {'covers_footprint': bool(inside.any()), 'pixels_inside': n_in}
        if inside.any():
            rows = np.nonzero(inside.any(axis=1))[0]
            r0 = max(0, int(rows.min()))
            r1 = min(loc.shape[0], int(rows.max()) + 1)
            if r1 - r0 < 2 and loc.shape[0] >= 2:
                r0 = max(0, r0 - 1)
                r1 = min(loc.shape[0], r0 + 2)
            xs, ys = x[r0:r1], y[r0:r1]
            dx = float(np.nanmedian(np.hypot(np.diff(xs, axis=1), np.diff(ys, axis=1))))
            dy = float(np.nanmedian(np.hypot(np.diff(xs, axis=0), np.diff(ys, axis=0))))
            expected = int(round(side_m * side_m / (dx * dy))) if dx > 0 and dy > 0 else n_in
            rec.update(
                row_range=[int(rows.min()), int(rows.max()) + 1],
                dx_m=dx,
                dy_m=dy,
                pixel_m=float(np.sqrt(dx * dy)) if dx > 0 and dy > 0 else None,
                expected_cells=expected,
                max_possible_valid_fraction=float(n_in / max(expected, n_in)) if max(expected, n_in) > 0 else 0.0,
            )
        by_side[str(int(side_m))] = rec
    return {
        'loc_file': str(loc_npy_path),
        'shape': list(loc.shape),
        'min_distance_m': min_dist,
        'footprints': by_side,
    }
