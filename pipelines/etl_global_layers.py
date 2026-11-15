"""Global coarse surface layer (phase A of the topographic selection bias mitigation plan).

Each product is reduced ONCE to a climatological global raster (`build`) and then sampled at
every Earth window of `base_windows` (`sample`), so aridity, snow, a coarse apparent thermal
inertia, emissivity indices, soil moisture and permafrost exist for all ~1.8 M windows and not
only for the topographic candidates.

| Layer         | Product (access)                                   | Raster(s) written                          |
|---------------|----------------------------------------------------|--------------------------------------------|
| imerg         | GPM_3IMERGM.07 HDF5, HTTP ranges (GES DISC)         | precip_annual_mm, dry_months_fraction      |
| snow          | MOD10CM.061 HDF4, whole granule then erased (NSIDC) | snow_cover_mean_pct, snow_months_fraction  |
| ati           | MYD11C3.061 + MCD43C3.061 HDF4 (LP DAAC)            | lst_day_night_delta_k, albedo_wsa, ati     |
| emissivity    | AG1km.003 HDF5 1° tiles, HTTP ranges (LP DAAC)      | emissivity_b10_b14 (5 bands, int16 x0.001) |
| soil_moisture | SPL3SMP_E.006 HDF5, two datasets by ranges (NSIDC)  | soil_moisture_mean, soil_moisture_obs_fraction |
| permafrost    | ESA CCI Permafrost v5.0 NetCDF4 (CEDA, public)      | permafrost_fraction_<hemisphere>           |

Rasters are GeoTIFF (deflate, tiled) in `<layers_dir>/<layer>/` with a `layer.json` that lists
products, granules, parameters and the SHA-256 of every output; a layer whose `layer.json`
exists is not rebuilt unless forced. Downloads go to a scratch directory and are erased after
reading. Sampling reads rasters in row strips and uses summed-area tables, so footprint means
over 1.8 M windows stay vectorized and memory-bounded.

All network access is injectable (`search`, `opener`, `downloader`, `reader`) for offline tests.
"""
from __future__ import annotations

from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import dataclass
from datetime import date, datetime, timezone
import calendar
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any, Callable, Iterable, Iterator
import urllib.parse

import numpy as np
from pyproj import CRS, Transformer
import rasterio
from rasterio.transform import from_origin
from rasterio.windows import Window

from pipelines import etl_extractors as extractors
from pipelines import etl_surface_fetch as fetch
from pipelines.etl_global_schema import GLOBAL_LAYERS, GLOBAL_LAYERS_VERSION, GLOBAL_RANGES

ROOT = Path(__file__).resolve().parents[1]
SPEC_PATH = ROOT / 'specs/sources/capa-global-superficie-v1.json'
LAYER_META = 'layer.json'
WGS84 = CRS.from_epsg(4326)
EASE2_CRS = CRS.from_epsg(6933)
AG1KM_PPD = 100
AG1KM_NODATA = -9999

COLLECTIONS = {
    'imerg': fetch.COLLECTIONS['imerg_monthly'],
    'mod10cm': {'short_name': 'MOD10CM', 'version': '61', 'suffix': '.hdf'},
    'myd11c3': {'short_name': 'MYD11C3', 'version': '061', 'suffix': '.hdf'},
    'mcd43c3': {'short_name': 'MCD43C3', 'version': '061', 'suffix': '.hdf'},
    'ag1km': {'short_name': 'AG1km', 'version': '003', 'suffix': '.h5'},
    'smap': fetch.COLLECTIONS['smap'],
}


def load_spec(path: Path = SPEC_PATH) -> dict:
    return json.loads(Path(path).read_text(encoding='utf-8'))


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Raster I/O
# ---------------------------------------------------------------------------
def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, 'rb') as fh:
        for block in iter(lambda: fh.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def _profile(crs, transform, shape, count=1, dtype='float32', nodata=np.nan) -> dict:
    return dict(driver='GTiff', width=shape[1], height=shape[0], count=count, dtype=dtype, crs=crs,
                transform=transform, nodata=nodata, compress='deflate', tiled=True, blockxsize=512,
                blockysize=512, BIGTIFF='IF_SAFER')


def write_raster(path: Path, array: np.ndarray, crs, transform, *, description: str = '') -> Path:
    """Single-band float32 GeoTIFF written to a staging name and moved into place."""
    path.parent.mkdir(parents=True, exist_ok=True)
    staged = path.with_suffix('.part.tif')
    data = np.asarray(array, dtype='float32')
    with rasterio.open(staged, 'w', **_profile(crs, transform, data.shape)) as dst:
        dst.write(data, 1)
        if description:
            dst.set_band_description(1, description)
    staged.replace(path)
    return path


def write_layer_meta(layer_dir: Path, meta: dict) -> Path:
    outputs = {}
    for name, file in meta['outputs'].items():
        p = layer_dir / file
        outputs[name] = {'file': file, 'bytes': p.stat().st_size, 'sha256': _sha256(p)}
    meta = meta | {'outputs': outputs, 'version': GLOBAL_LAYERS_VERSION,
                   'built_at': utc_now().isoformat(timespec='seconds')}
    staged = layer_dir / (LAYER_META + '.part')
    staged.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    staged.replace(layer_dir / LAYER_META)
    return layer_dir / LAYER_META


def read_layer_meta(layer_dir: Path) -> dict | None:
    p = layer_dir / LAYER_META
    return json.loads(p.read_text(encoding='utf-8')) if p.exists() else None


# ---------------------------------------------------------------------------
# Streaming helpers
# ---------------------------------------------------------------------------
def _stream(fn: Callable, items: list, workers: int) -> Iterator:
    """Results of `fn(item)` as they complete, with at most 2*workers in flight (bounded memory)."""
    if workers <= 1:
        for item in items:
            yield fn(item)
        return
    pending = set()
    it = iter(items)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for item in it:
            pending.add(pool.submit(fn, item))
            if len(pending) >= 2 * workers:
                done, pending = wait(pending, return_when=FIRST_COMPLETED)
                for f in done:
                    yield f.result()
        while pending:
            done, pending = wait(pending, return_when=FIRST_COMPLETED)
            for f in done:
                yield f.result()


def geo_transform(shape: tuple[int, int]):
    """North-up global EPSG:4326 transform of a (rows, cols) grid."""
    return from_origin(-180.0, 90.0, 360.0 / shape[1], 180.0 / shape[0])


class _Accumulator:
    """Lazily allocated per-pixel arrays (the grid shape comes from the first granule)."""

    def __init__(self, specs: dict[str, tuple[tuple[int, ...], str, float]]):
        self.specs = specs
        self.arrays: dict[str, np.ndarray] = {}
        self.shape: tuple[int, int] | None = None

    def ensure(self, shape: tuple[int, int]) -> dict[str, np.ndarray]:
        if self.shape is None:
            self.shape = tuple(shape)
            for name, (lead, dtype, fill) in self.specs.items():
                self.arrays[name] = np.full(lead + self.shape, fill, dtype=dtype)
        elif tuple(shape) != self.shape:
            raise ValueError(f'forma {tuple(shape)} distinta de la del primer gránulo {self.shape}')
        return self.arrays


def _granule_month(g: dict) -> date:
    return fetch._granule_date(g).replace(day=1)


def _hdf4_job(g: dict, layers: tuple[str, ...], cache_dir: Path, downloader, reader) -> dict[str, np.ndarray]:
    """Download one HDF4 granule, read the named layers and erase the file."""
    target = cache_dir / Path(urllib.parse.urlsplit(g['url']).path).name
    try:
        downloader(g['url'], target)
        arrays, _transform = reader(target, layers)
        return arrays
    finally:
        target.unlink(missing_ok=True)


@dataclass
class BuildContext:
    out_dir: Path
    cache_dir: Path
    workers: int = 8
    search: Callable = fetch.search_cmr
    opener: Callable = fetch.open_h5
    downloader: Callable = fetch.download
    reader: Callable = fetch.read_hdf4_layers
    log: Callable[[str], None] = lambda _m: None

    def layer_dir(self, layer: str) -> Path:
        d = self.out_dir / layer
        d.mkdir(parents=True, exist_ok=True)
        return d


# ---------------------------------------------------------------------------
# imerg: monthly precipitation -> annual mean and dry-month fraction
# ---------------------------------------------------------------------------
def imerg_to_grid(rate_lon_lat: np.ndarray) -> np.ndarray:
    """`Grid/precipitation[0]` (lon 3600, lat 1800 from the south) -> north-up (1800, 3600)."""
    return np.asarray(rate_lon_lat, dtype='float32').T[::-1, :]


def build_imerg(cfg: dict, ctx: BuildContext) -> dict:
    start, end = date.fromisoformat(cfg['period']['start']), date.fromisoformat(cfg['period']['end'])
    granules = [g for g in ctx.search(COLLECTIONS['imerg'], None, start, end)
                if start <= _granule_month(g) <= end]
    if not granules:
        raise RuntimeError('IMERG: CMR no devolvió gránulos en el periodo')
    acc = _Accumulator({'sum': ((12,), 'float32', 0.0), 'n': ((12,), 'int16', 0)})

    def read(g: dict):
        month = _granule_month(g)
        hours = calendar.monthrange(month.year, month.month)[1] * 24.0
        with ctx.opener(g['url']) as h5:
            rate = imerg_to_grid(h5['Grid/precipitation'][0])
        mm = np.where(rate >= 0.0, rate * hours, np.nan)
        return month, g['id'], mm

    used = []
    for month, gid, mm in _stream(read, granules, ctx.workers):
        a = acc.ensure(mm.shape)
        ok = np.isfinite(mm)
        a['sum'][month.month - 1][ok] += mm[ok]
        a['n'][month.month - 1][ok] += 1
        used.append(gid)
        ctx.log(f'  imerg {gid}')
    month_sum, month_n = acc.arrays['sum'], acc.arrays['n']
    transform = geo_transform(acc.shape)
    with np.errstate(invalid='ignore', divide='ignore'):
        clim = np.where(month_n > 0, month_sum / np.maximum(month_n, 1), np.nan)  # mm per calendar month
    complete = np.isfinite(clim).all(axis=0)
    annual = np.where(complete, clim.sum(axis=0), np.nan)
    dry = np.where(complete, (clim < float(cfg.get('dry_month_threshold_mm', 5.0))).mean(axis=0), np.nan)
    d = ctx.layer_dir('imerg')
    write_raster(d / 'precip_annual_mm.tif', annual, WGS84, transform, description='precip_annual_mm')
    write_raster(d / 'dry_months_fraction.tif', dry, WGS84, transform, description='dry_months_fraction')
    return {'layer': 'imerg', 'products': [cfg['product_id']], 'granules': sorted(used),
            'period': f"{start:%Y-%m}/{end:%Y-%m}", 'params': {k: cfg[k] for k in ('dry_month_threshold_mm',)},
            'outputs': {'precip_annual_mm': 'precip_annual_mm.tif', 'dry_months_fraction': 'dry_months_fraction.tif'}}


# ---------------------------------------------------------------------------
# snow: MOD10CM monthly CMG snow cover
# ---------------------------------------------------------------------------
SNOW_LAYER = 'Snow_Cover_Monthly_CMG'


def build_snow(cfg: dict, ctx: BuildContext) -> dict:
    start, end = date.fromisoformat(cfg['period']['start']), date.fromisoformat(cfg['period']['end'])
    granules = [g for g in ctx.search(COLLECTIONS['mod10cm'], None, start, end) if start <= _granule_month(g) <= end]
    if not granules:
        raise RuntimeError('MOD10CM: CMR no devolvió gránulos en el periodo')
    threshold = float(cfg.get('snow_month_threshold_pct', 50.0))
    acc = _Accumulator({'total': ((), 'float32', 0.0), 'snowy': ((), 'int16', 0), 'valid': ((), 'int16', 0)})

    def read(g: dict):
        arrays = _hdf4_job(g, (SNOW_LAYER,), ctx.cache_dir, ctx.downloader, ctx.reader)
        return g['id'], np.asarray(arrays[SNOW_LAYER])

    used = []
    for gid, raw in _stream(read, granules, ctx.workers):
        a = acc.ensure(raw.shape)
        ok = raw <= 100
        a['total'][ok] += raw[ok]
        a['snowy'] += (ok & (raw >= threshold)).astype('int16')
        a['valid'] += ok.astype('int16')
        used.append(gid)
        ctx.log(f'  snow {gid}')
    total, snowy, valid = acc.arrays['total'], acc.arrays['snowy'], acc.arrays['valid']
    transform = geo_transform(acc.shape)
    with np.errstate(invalid='ignore', divide='ignore'):
        mean = np.where(valid > 0, total / np.maximum(valid, 1), np.nan)
        frac = np.where(valid > 0, snowy / np.maximum(valid, 1), np.nan)
    d = ctx.layer_dir('snow')
    write_raster(d / 'snow_cover_mean_pct.tif', mean, WGS84, transform, description='snow_cover_mean_pct')
    write_raster(d / 'snow_months_fraction.tif', frac, WGS84, transform, description='snow_months_fraction')
    return {'layer': 'snow', 'products': [cfg['product_id']], 'granules': sorted(used),
            'period': f"{start:%Y-%m}/{end:%Y-%m}", 'params': {'snow_month_threshold_pct': threshold},
            'outputs': {'snow_cover_mean_pct': 'snow_cover_mean_pct.tif', 'snow_months_fraction': 'snow_months_fraction.tif'}}


# ---------------------------------------------------------------------------
# ati: MYD11C3 monthly LST day/night + MCD43C3 white-sky albedo -> coarse ATI
# ---------------------------------------------------------------------------
LST_LAYERS = ('LST_Day_CMG', 'LST_Night_CMG', 'QC_Day', 'QC_Night')
ALBEDO_LAYERS = ('Albedo_WSA_shortwave', 'BRDF_Quality')


def albedo_cmg(raw: np.ndarray, quality: np.ndarray, max_quality: int) -> np.ndarray:
    raw = np.asarray(raw).astype('float32')
    ok = (raw != 32767) & (raw >= 0) & (np.asarray(quality) <= max_quality)
    return np.where(ok, raw * 0.001, np.nan).astype('float32')


def ati_from_monthly(day_k: np.ndarray, night_k: np.ndarray, albedo: np.ndarray, *,
                     min_delta_k: float, min_valid_months: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Median over months of delta, albedo and (1 - albedo) / delta; NaN with < min_valid_months."""
    with np.errstate(invalid='ignore', divide='ignore'):
        delta = day_k - night_k
        ok = np.isfinite(delta) & np.isfinite(albedo) & (delta >= min_delta_k)
        ati = np.where(ok, (1.0 - albedo) / delta, np.nan)
        n = ok.sum(axis=0)
        enough = n >= min_valid_months
        out = []
        for stack in (np.where(ok, delta, np.nan), np.where(ok, albedo, np.nan), ati):
            med = np.full(stack.shape[1:], np.nan, dtype='float32')
            if enough.any():
                med[enough] = np.nanmedian(stack[:, enough], axis=0)
            out.append(med)
    return out[0], out[1], out[2]


def build_ati(cfg: dict, ctx: BuildContext) -> dict:
    year = int(cfg['year'])
    start, end = date(year, 1, 1), date(year, 12, 31)
    lst_granules = [g for g in ctx.search(COLLECTIONS['myd11c3'], None, start, end) if _granule_month(g).year == year]
    alb_granules = fetch._every(ctx.search(COLLECTIONS['mcd43c3'], None, start, end), int(cfg.get('albedo_step_days', 8)))
    if not lst_granules or not alb_granules:
        raise RuntimeError('ATI: faltan gránulos MYD11C3 o MCD43C3 en el año')
    max_err = float(cfg.get('max_lst_error_k', 2.0))
    acc = _Accumulator({'day': ((12,), 'float32', np.nan), 'night': ((12,), 'float32', np.nan),
                        'alb_sum': ((12,), 'float32', 0.0), 'alb_n': ((12,), 'uint8', 0)})

    def read_lst(g: dict):
        a = _hdf4_job(g, LST_LAYERS, ctx.cache_dir, ctx.downloader, ctx.reader)
        return (_granule_month(g).month, g['id'],
                fetch.lst_kelvin(a['LST_Day_CMG'], a['QC_Day'], max_err).astype('float32'),
                fetch.lst_kelvin(a['LST_Night_CMG'], a['QC_Night'], max_err).astype('float32'))

    def read_alb(g: dict):
        a = _hdf4_job(g, ALBEDO_LAYERS, ctx.cache_dir, ctx.downloader, ctx.reader)
        return (fetch._granule_date(g).month, g['id'],
                albedo_cmg(a['Albedo_WSA_shortwave'], a['BRDF_Quality'], int(cfg.get('max_brdf_quality', 2))))

    used = []
    for month, gid, d_k, n_k in _stream(read_lst, lst_granules, ctx.workers):
        a = acc.ensure(d_k.shape)
        a['day'][month - 1], a['night'][month - 1] = d_k, n_k
        used.append(gid)
        ctx.log(f'  ati lst {gid}')
    for month, gid, alb in _stream(read_alb, alb_granules, ctx.workers):
        a = acc.ensure(alb.shape)
        ok = np.isfinite(alb)
        a['alb_sum'][month - 1][ok] += alb[ok]
        a['alb_n'][month - 1] += ok.astype('uint8')
        used.append(gid)
        ctx.log(f'  ati albedo {gid}')
    day, night = acc.arrays['day'], acc.arrays['night']
    with np.errstate(invalid='ignore', divide='ignore'):
        albedo = np.where(acc.arrays['alb_n'] > 0, acc.arrays['alb_sum'] / np.maximum(acc.arrays['alb_n'], 1),
                          np.nan).astype('float32')
    del acc.arrays['alb_sum'], acc.arrays['alb_n']
    shape = acc.shape
    outputs = {'lst_day_night_delta_k': None, 'albedo_wsa': None, 'ati': None}
    results = {k: np.full(shape, np.nan, dtype='float32') for k in outputs}
    strip = 400
    for r0 in range(0, shape[0], strip):
        sl = slice(r0, min(r0 + strip, shape[0]))
        delta, alb, ati = ati_from_monthly(day[:, sl], night[:, sl], albedo[:, sl],
                                           min_delta_k=float(cfg.get('min_day_night_delta_k', 1.0)),
                                           min_valid_months=int(cfg.get('min_valid_months', 4)))
        results['lst_day_night_delta_k'][sl], results['albedo_wsa'][sl], results['ati'][sl] = delta, alb, ati
    d = ctx.layer_dir('ati')
    for name, arr in results.items():
        write_raster(d / f'{name}.tif', arr, WGS84, geo_transform(shape), description=name)
    params = {k: cfg[k] for k in ('albedo_step_days', 'max_lst_error_k', 'max_brdf_quality',
                                  'min_day_night_delta_k', 'min_valid_months') if k in cfg}
    return {'layer': 'ati', 'products': [cfg['product_id'], cfg['albedo_product_id']], 'granules': sorted(used),
            'period': str(year), 'params': params, 'outputs': {k: f'{k}.tif' for k in outputs}}


# ---------------------------------------------------------------------------
# emissivity: AG1km 1° tiles mosaicked into one 5-band int16 raster (0.01°)
# ---------------------------------------------------------------------------
AG1KM_NAME = re.compile(r'AG1km\.v003\.(-?\d+)\.(-?\d+)\.')


def ag1km_tile_key(granule_id: str) -> tuple[int, int] | None:
    m = AG1KM_NAME.search(granule_id)
    return (int(m.group(1)), int(m.group(2))) if m else None


def tile_to_grid(emis: np.ndarray, ppd: int = AG1KM_PPD) -> np.ndarray:
    """Resample an (5, n, m) tile onto the (5, ppd, ppd) cells of its degree by nearest index."""
    _, n, m = emis.shape
    if (n, m) == (ppd, ppd):
        return emis
    rows = np.minimum((np.arange(ppd) + 0.5) * n / ppd, n - 1).astype(int)
    cols = np.minimum((np.arange(ppd) + 0.5) * m / ppd, m - 1).astype(int)
    return emis[:, rows][:, :, cols]


def build_emissivity(cfg: dict, ctx: BuildContext) -> dict:
    granules = ctx.search(COLLECTIONS['ag1km'], None, None, None, max_pages=40)
    tiles = {}
    for g in granules:
        key = ag1km_tile_key(g['id'])
        if key:
            tiles[key] = g
    if not tiles:
        raise RuntimeError('AG1km: CMR no devolvió teselas')
    ppd = int(cfg.get('pixels_per_degree', AG1KM_PPD))
    d = ctx.layer_dir('emissivity')
    target = d / 'emissivity_b10_b14.tif'
    staged = target.with_suffix('.part.tif')
    profile = _profile(WGS84, from_origin(-180.0, 90.0, 1.0 / ppd, 1.0 / ppd), (180 * ppd, 360 * ppd),
                       count=5, dtype='int16', nodata=AG1KM_NODATA)

    def read(item):
        (north, west), g = item
        try:
            with ctx.opener(g['url']) as h5:
                emis = np.asarray(h5['Emissivity/Mean'][:], dtype='int16')
        except Exception as exc:  # one bad tile must not stop the mosaic
            return north, west, g['id'], None, f"{g['id']}: {type(exc).__name__}: {exc}"
        if emis.ndim != 3 or emis.shape[0] != 5:
            return north, west, g['id'], None, f"{g['id']}: forma inesperada {emis.shape}"
        return north, west, g['id'], tile_to_grid(emis, ppd), None

    used, errors = [], []
    with rasterio.open(staged, 'w', **profile) as dst:
        for north, west, gid, block, error in _stream(read, sorted(tiles.items()), ctx.workers):
            if error:
                errors.append(error)
                continue
            block = np.where(block <= -9999, AG1KM_NODATA, block).astype('int16')
            dst.write(block, window=Window((west + 180) * ppd, (90 - north) * ppd, ppd, ppd))
            used.append(gid)
            if len(used) % 500 == 0:
                ctx.log(f'  emissivity {len(used)}/{len(tiles)} teselas')
        for b, name in enumerate(('b10', 'b11', 'b12', 'b13', 'b14'), 1):
            dst.set_band_description(b, name)
    staged.replace(target)
    if errors:
        ctx.log(f'  emissivity: {len(errors)} teselas con error (primera: {errors[0]})')
    return {'layer': 'emissivity', 'products': [cfg['product_id']], 'granules_count': len(used),
            'errors': errors[:50], 'period': '2000/2008', 'params': {'valid_range': cfg.get('valid_range', [0.4, 1.05])},
            'outputs': {'emissivity_b10_b14': target.name}}


def emissivity_indices(bands: np.ndarray, valid_range=(0.4, 1.05)) -> dict[str, np.ndarray]:
    """(5, N) emissivity (b10..b14) -> mean and Ninomiya / mafic indices, NaN where invalid."""
    e = np.asarray(bands, dtype='float64')
    ok = np.all(np.isfinite(e) & (e >= valid_range[0]) & (e <= valid_range[1]), axis=0)
    e10, e11, e12, e13, e14 = e
    with np.errstate(invalid='ignore', divide='ignore'):
        out = {
            'emis_mean_b10_b14_cmg': e.mean(axis=0),
            'emis_quartz_index_cmg': e11 * e11 / (e10 * e12),
            'emis_carbonate_index_cmg': e13 / e14,
            'emis_mafic_index_cmg': (e10 + e11) / (e12 + e13),
        }
    return {k: np.where(ok, v, np.nan) for k, v in out.items()}


# ---------------------------------------------------------------------------
# soil_moisture: SMAP L3 enhanced, AM overpass, recommended-quality mean
# ---------------------------------------------------------------------------
SMAP_TRANSFORM = from_origin(fetch.EASE2_9KM['x0'], fetch.EASE2_9KM['y0'],
                             fetch.EASE2_9KM['cell_m'], fetch.EASE2_9KM['cell_m'])


def build_soil_moisture(cfg: dict, ctx: BuildContext) -> dict:
    start, end = date.fromisoformat(cfg['period']['start']), date.fromisoformat(cfg['period']['end'])
    granules = fetch._every(ctx.search(COLLECTIONS['smap'], None, start, end), int(cfg.get('step_days', 8)))
    if not granules:
        raise RuntimeError('SMAP: CMR no devolvió gránulos en el periodo')
    acc = _Accumulator({'total': ((), 'float64', 0.0), 'count': ((), 'int32', 0)})
    group = 'Soil_Moisture_Retrieval_Data_AM/'

    def read(g: dict):
        try:
            with ctx.opener(g['url']) as h5:
                sm = np.asarray(h5[group + 'soil_moisture'][:], dtype='float32')
                qa = np.asarray(h5[group + 'retrieval_qual_flag'][:])
        except Exception as exc:
            return g['id'], None, f"{g['id']}: {type(exc).__name__}: {exc}"
        ok = (sm != -9999.0) & (sm >= 0.0) & ((qa.astype('int64') & 1) == 0) & (qa != 65534)
        return g['id'], np.where(ok, sm, np.nan), None

    used, errors = [], []
    for gid, sm, error in _stream(read, granules, ctx.workers):
        if error:
            errors.append(error)
            continue
        a = acc.ensure(sm.shape)
        ok = np.isfinite(sm)
        a['total'][ok] += sm[ok]
        a['count'] += ok.astype('int32')
        used.append(gid)
        ctx.log(f'  soil_moisture {gid}')
    if not used:
        raise RuntimeError(f'SMAP: ningún gránulo legible ({errors[:1]})')
    total, count = acc.arrays['total'], acc.arrays['count']
    with np.errstate(invalid='ignore', divide='ignore'):
        mean = np.where(count > 0, total / np.maximum(count, 1), np.nan)
    frac = count / float(len(used))
    d = ctx.layer_dir('soil_moisture')
    write_raster(d / 'soil_moisture_mean.tif', mean, EASE2_CRS, SMAP_TRANSFORM, description='soil_moisture_mean')
    write_raster(d / 'soil_moisture_obs_fraction.tif', frac, EASE2_CRS, SMAP_TRANSFORM,
                 description='soil_moisture_obs_fraction')
    return {'layer': 'soil_moisture', 'products': [cfg['product_id']], 'granules': sorted(used), 'errors': errors[:50],
            'period': f'{start}/{end}', 'params': {'step_days': int(cfg.get('step_days', 8))},
            'outputs': {'soil_moisture_mean': 'soil_moisture_mean.tif',
                        'soil_moisture_obs_fraction': 'soil_moisture_obs_fraction.tif'}}


# ---------------------------------------------------------------------------
# permafrost: ESA CCI PFR per hemisphere, native polar stereographic grid
# ---------------------------------------------------------------------------
def cci_grid(h5, var: str) -> tuple[CRS, Any, np.ndarray]:
    """CRS, affine transform (north-up) and fraction array of a CCI PFR variable."""
    crs = fetch._cci_crs(h5, var)
    x = np.asarray(h5['x'][:], dtype='float64')
    y = np.asarray(h5['y'][:], dtype='float64')
    dset = h5[var]
    block = np.asarray(dset[0] if dset.ndim == 3 else dset[:], dtype='float64')
    fill = dset.attrs.get('_FillValue')
    if fill is not None:
        block = np.where(block == float(np.asarray(fill).ravel()[0]), np.nan, block)
    scale = float(np.asarray(dset.attrs.get('scale_factor', 1.0)).ravel()[0])
    offset = float(np.asarray(dset.attrs.get('add_offset', 0.0)).ravel()[0])
    block = block * scale + offset
    if y[0] < y[-1]:
        y, block = y[::-1], block[::-1]
    if x[0] > x[-1]:
        x, block = x[::-1], block[:, ::-1]
    dx, dy = abs(x[1] - x[0]), abs(y[0] - y[1])
    transform = from_origin(x[0] - dx / 2, y[0] + dy / 2, dx, dy)
    return crs, transform, np.clip(block / 100.0, 0.0, 1.0)


def build_permafrost(cfg: dict, ctx: BuildContext) -> dict:
    year = int(cfg['year'])
    d = ctx.layer_dir('permafrost')
    outputs, granules = {}, []
    for hemi in ('northern_hemisphere', 'Antarctica'):
        url = fetch.CCI_FILES['PFR'].format(base=fetch.CCI_BASE, hemi=hemi, year=year)
        with ctx.opener(url) as h5:
            crs, transform, frac = cci_grid(h5, 'PFR')
        name = f'permafrost_fraction_{hemi}'
        write_raster(d / f'{name}.tif', frac, crs, transform, description=name)
        outputs[name] = f'{name}.tif'
        granules.append(f'{hemi}/{Path(url).name}')
        ctx.log(f'  permafrost {hemi}')
    return {'layer': 'permafrost', 'products': [cfg['product_id']], 'granules': granules, 'period': str(year),
            'params': {}, 'outputs': outputs}


BUILDERS: dict[str, Callable[[dict, BuildContext], dict]] = {
    'imerg': build_imerg,
    'snow': build_snow,
    'ati': build_ati,
    'emissivity': build_emissivity,
    'soil_moisture': build_soil_moisture,
    'permafrost': build_permafrost,
}


def build_layers(layers: Iterable[str], ctx: BuildContext, spec: dict | None = None, *,
                 force: bool = False) -> dict[str, dict]:
    """Build the requested layers; a failing product is reported and the others continue."""
    spec = spec or load_spec()
    report = {}
    for layer in layers:
        layer_dir = ctx.out_dir / layer
        if not force and read_layer_meta(layer_dir):
            report[layer] = {'status': 'skipped_existing'}
            ctx.log(f'{layer}: ya construida ({layer_dir / LAYER_META})')
            continue
        ctx.log(f'{layer}: construyendo...')
        try:
            meta = BUILDERS[layer](spec['layers'][layer], ctx)
            write_layer_meta(ctx.layer_dir(layer), meta)
            report[layer] = {'status': 'built', 'granules': len(meta.get('granules', [])) or meta.get('granules_count', 0)}
        except Exception as exc:
            report[layer] = {'status': 'failed', 'error': f'{type(exc).__name__}: {exc}'}
            ctx.log(f'{layer}: ERROR {type(exc).__name__}: {exc}')
    return report


# ---------------------------------------------------------------------------
# Sampling
# ---------------------------------------------------------------------------
def _box_half_pixels(src, lons: np.ndarray, lats: np.ndarray, half_m: float) -> tuple[np.ndarray, np.ndarray]:
    """Half footprint size in pixels (rows, cols) for each point."""
    if src.crs and CRS.from_user_input(src.crs).is_geographic:
        dlat = half_m / 111_320.0
        dlon = half_m / (111_320.0 * np.maximum(np.cos(np.radians(lats)), 0.05))
        return dlat / abs(src.transform.e), dlon / abs(src.transform.a)
    return (np.full(lons.shape, half_m / abs(src.transform.e)), np.full(lons.shape, half_m / abs(src.transform.a)))


def sample_raster(path: Path, lons: np.ndarray, lats: np.ndarray, *, half_m: float | None = None,
                  strip_rows: int = 256, scale: float = 1.0) -> tuple[np.ndarray, np.ndarray]:
    """Per point and band: mean of valid cells (nearest cell if `half_m` is None), and an `inside` mask.

    Returns (values (bands, N), inside (N,)). `inside` is False where the point falls outside the raster.
    Reads the raster in row strips and uses summed-area tables, so it is vectorized and memory-bounded.
    """
    lons = np.asarray(lons, dtype='float64')
    lats = np.asarray(lats, dtype='float64')
    with rasterio.open(path) as src:
        crs = CRS.from_user_input(src.crs)
        if crs.is_geographic:
            xs, ys = lons, lats
        else:
            xs, ys = Transformer.from_crs(WGS84, crs, always_xy=True).transform(lons, lats)
        inv = ~src.transform
        cols_f, rows_f = inv * (np.asarray(xs, dtype="float64"), np.asarray(ys, dtype="float64"))
        rows = np.floor(rows_f).astype('int64')
        cols = np.floor(cols_f).astype('int64')
        inside = np.isfinite(rows_f) & (rows >= 0) & (rows < src.height) & (cols >= 0) & (cols < src.width)
        if half_m is None:
            hr = hc = np.zeros(lons.shape)
        else:
            hr, hc = _box_half_pixels(src, lons, lats, half_m)
        r0 = np.clip(np.floor(rows_f - hr).astype('int64'), 0, src.height)
        r1 = np.clip(np.floor(rows_f + hr).astype('int64') + 1, 0, src.height)
        c0 = np.clip(np.floor(cols_f - hc).astype('int64'), 0, src.width)
        c1 = np.clip(np.floor(cols_f + hc).astype('int64') + 1, 0, src.width)
        if half_m is None:
            r0, r1, c0, c1 = rows, rows + 1, cols, cols + 1
        out = np.full((src.count, lons.size), np.nan)
        nodata = src.nodata
        idx_all = np.flatnonzero(inside)
        margin = int(np.ceil(np.nanmax(hr))) + 1 if idx_all.size else 1
        for s0 in range(0, src.height, strip_rows):
            s1 = min(s0 + strip_rows, src.height)
            sel = idx_all[(rows[idx_all] >= s0) & (rows[idx_all] < s1)]
            if sel.size == 0:
                continue
            w0, w1 = max(s0 - margin, 0), min(s1 + margin, src.height)
            block = src.read(window=Window(0, w0, src.width, w1 - w0)).astype('float64')
            if nodata is not None and not (isinstance(nodata, float) and math.isnan(nodata)):
                block[block == nodata] = np.nan
            block *= scale
            a0, a1 = np.clip(r0[sel], w0, w1) - w0, np.clip(r1[sel], w0, w1) - w0
            b0, b1 = c0[sel], c1[sel]
            for b in range(src.count):
                band = block[b]
                valid = np.isfinite(band)
                vsum = np.zeros((band.shape[0] + 1, band.shape[1] + 1))
                vcnt = np.zeros_like(vsum)
                vsum[1:, 1:] = np.where(valid, band, 0.0).cumsum(0).cumsum(1)
                vcnt[1:, 1:] = valid.cumsum(0).cumsum(1)
                ssum = vsum[a1, b1] - vsum[a0, b1] - vsum[a1, b0] + vsum[a0, b0]
                scnt = vcnt[a1, b1] - vcnt[a0, b1] - vcnt[a1, b0] + vcnt[a0, b0]
                with np.errstate(invalid='ignore', divide='ignore'):
                    out[b, sel] = np.where(scnt > 0, ssum / scnt, np.nan)
    return out, inside


def _status(primary: np.ndarray, inside: np.ndarray) -> np.ndarray:
    st = np.full(primary.shape, 'unobserved_by_product', dtype=object)
    st[inside] = 'insufficient_coverage'
    st[inside & np.isfinite(primary)] = 'measured'
    return st


def sample_layer(layer: str, layer_dir: Path, lons: np.ndarray, lats: np.ndarray,
                 half_m: float = fetch.HALF_M) -> tuple[dict[str, np.ndarray], np.ndarray]:
    """Columns and per-window status of one built layer."""
    meta = read_layer_meta(layer_dir)
    n = len(lons)
    if not meta:
        return {}, np.full(n, 'on_demand_fetchable', dtype=object)
    outs = {k: layer_dir / v['file'] for k, v in meta['outputs'].items()}
    cols: dict[str, np.ndarray] = {}
    if layer == 'imerg':
        v, inside = sample_raster(outs['precip_annual_mm'], lons, lats)
        cols['precip_annual_mm_cmg'] = v[0]
        cols['dry_months_fraction_cmg'] = sample_raster(outs['dry_months_fraction'], lons, lats)[0][0]
        primary = cols['precip_annual_mm_cmg']
    elif layer == 'snow':
        v, inside = sample_raster(outs['snow_cover_mean_pct'], lons, lats)
        cols['snow_cover_mean_pct_cmg'] = v[0]
        cols['snow_months_fraction_cmg'] = sample_raster(outs['snow_months_fraction'], lons, lats)[0][0]
        primary = cols['snow_cover_mean_pct_cmg']
    elif layer == 'ati':
        v, inside = sample_raster(outs['ati'], lons, lats)
        cols['ati_cmg_per_k'] = v[0]
        cols['lst_day_night_delta_k_cmg'] = sample_raster(outs['lst_day_night_delta_k'], lons, lats)[0][0]
        cols['albedo_wsa_cmg'] = sample_raster(outs['albedo_wsa'], lons, lats)[0][0]
        primary = cols['ati_cmg_per_k']
    elif layer == 'emissivity':
        v, inside = sample_raster(outs['emissivity_b10_b14'], lons, lats, half_m=half_m, scale=0.001)
        cols.update(emissivity_indices(v, tuple(meta.get('params', {}).get('valid_range', (0.4, 1.05)))))
        primary = cols['emis_mean_b10_b14_cmg']
    elif layer == 'soil_moisture':
        v, inside = sample_raster(outs['soil_moisture_mean'], lons, lats)
        cols['soil_moisture_mean_cmg'] = v[0]
        frac = sample_raster(outs['soil_moisture_obs_fraction'], lons, lats)[0][0]
        cols['soil_moisture_obs_fraction_cmg'] = np.where(inside, frac, np.nan)
        primary = cols['soil_moisture_mean_cmg']
    elif layer == 'permafrost':
        values = np.full(n, np.nan)
        inside = np.zeros(n, dtype=bool)
        for hemi, sel in (('northern_hemisphere', lats >= 0), ('Antarctica', lats < 0)):
            key = f'permafrost_fraction_{hemi}'
            if key not in outs or not sel.any():
                continue
            v, ins = sample_raster(outs[key], lons[sel], lats[sel], half_m=half_m)
            values[sel] = v[0]
            inside[sel] = ins
        cols['permafrost_fraction_cmg'] = values
        primary = values
    else:
        raise KeyError(layer)
    for col in list(cols):
        low, high = GLOBAL_RANGES[col]
        arr = np.asarray(cols[col], dtype='float64')
        cols[col] = np.where((arr >= low) & (arr <= high), arr, np.nan)
    primary_col = GLOBAL_LAYERS[layer]['columns'][0] if layer != 'ati' else 'ati_cmg_per_k'
    return cols, _status(cols[primary_col], inside)


def manifests_for(layers_dir: Path, created_at: datetime, spec: dict | None = None) -> tuple[str, list[dict]]:
    """One manifest id per sampling run; one row per built layer product."""
    spec = spec or load_spec()
    rows, assets = [], []
    for layer in GLOBAL_LAYERS:
        meta = read_layer_meta(layers_dir / layer)
        if not meta:
            continue
        cfg = spec['layers'][layer]
        shas = ','.join(f"{k}:{v['sha256'][:16]}" for k, v in sorted(meta['outputs'].items()))
        assets.append(f'{layer}:{shas}')
        products = [(cfg['product_id'], cfg.get('doi'))]
        if cfg.get('albedo_product_id'):
            products.append((cfg['albedo_product_id'], cfg.get('albedo_doi')))
        for product_id, doi in products:
            rows.append({
                'source_manifest_id': None,
                'product_id': product_id,
                'asset_id': f"{GLOBAL_LAYERS_VERSION}:{layer}:{shas}",
                'access_mode': 'global_layer',
                'sha256_or_etag': next(iter(meta['outputs'].values()))['sha256'],
                'native_resolution_m': float(cfg.get('native_resolution_m', 0.0)),
                'effective_resolution_m': float(GLOBAL_LAYERS[layer]['support_m']),
                'observation_period': meta.get('period'),
                'created_at': created_at,
                'crs_wkt': WGS84.to_wkt(),
                'planetary_frame': 'EARTH_WGS84',
                'doi': doi,
                'product_version': cfg.get('product_version'),
            })
    manifest_id = extractors.make_manifest_id(assets or ['empty'], GLOBAL_LAYERS_VERSION)
    for r in rows:
        r['source_manifest_id'] = manifest_id
    return manifest_id, rows


def sample_columns(lons: np.ndarray, lats: np.ndarray, layers_dir: Path,
                   layers: Iterable[str] = tuple(GLOBAL_LAYERS)) -> tuple[dict[str, np.ndarray], dict[str, np.ndarray]]:
    """Column arrays and per-layer status arrays for all windows (each raster is read once)."""
    n = len(lons)
    layers = set(layers)
    columns: dict[str, np.ndarray] = {}
    statuses: dict[str, np.ndarray] = {}
    for layer in GLOBAL_LAYERS:
        if layer in layers:
            cols, st = sample_layer(layer, layers_dir / layer, np.asarray(lons, float), np.asarray(lats, float))
        else:
            cols, st = {}, np.full(n, 'on_demand_fetchable', dtype=object)
        for col in GLOBAL_LAYERS[layer]['columns']:
            columns[col] = np.asarray(cols.get(col, np.full(n, np.nan)), dtype='float64')
        statuses[f'{layer}_cmg_status'] = st
    return columns, statuses


def rows_from_columns(region_ids, columns: dict[str, np.ndarray], statuses: dict[str, np.ndarray],
                      manifest_id: str, updated_at: datetime, sl: slice = slice(None)) -> list[dict]:
    """`enrichment_global` rows of the windows in `sl`."""
    ids = np.asarray(region_ids, dtype=object)[sl]
    cols = {k: v[sl] for k, v in columns.items()}
    sts = {k: v[sl] for k, v in statuses.items()}
    rows = []
    for i in range(len(ids)):
        row = {'region_id': str(ids[i])}
        for col, arr in cols.items():
            v = arr[i]
            row[col] = float(v) if np.isfinite(v) else None
        for col, arr in sts.items():
            row[col] = str(arr[i])
        row.update(global_layers_version=GLOBAL_LAYERS_VERSION, source_manifest_id=manifest_id, updated_at=updated_at)
        rows.append(row)
    return rows


def built_layers(layers_dir: Path) -> list[str]:
    return [layer for layer in GLOBAL_LAYERS if read_layer_meta(layers_dir / layer)]
