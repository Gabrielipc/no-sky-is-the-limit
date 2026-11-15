"""Prepare visual Copernicus DEM grids for an explicit Jezero result list.

Usage: .pixi/envs/default/bin/python frontend/scripts/cache-jezero-terrain.py results.json
Only derived images are saved; existing catalog entries are preserved.
"""
import hashlib
import json
import math
import sys
from pathlib import Path

import numpy as np
import rasterio
from PIL import Image
from rasterio.transform import from_origin
from rasterio.warp import Resampling, reproject, transform_bounds
from rasterio.windows import from_bounds

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'frontend/public/surface/unified'


def sample(src, lon, lat, cell, count):
    crs = f'+proj=aeqd +lat_0={lat} +lon_0={lon} +datum=WGS84 +units=m'
    half = (count - 1) * cell / 2
    bounds = transform_bounds(crs, src.crs, -half-2*cell, -half-2*cell, half+2*cell, half+2*cell, densify_pts=41)
    win = from_bounds(*bounds, transform=src.transform).round_offsets().round_lengths()
    arr = src.read(1, window=win, boundless=False).astype('float32')
    if src.nodata is not None:
        arr[arr == src.nodata] = np.nan
    dst = np.full((count, count), np.nan, dtype='float32')
    reproject(arr, dst, src_transform=src.window_transform(win), src_crs=src.crs, src_nodata=np.nan,
              dst_transform=from_origin(-half-cell/2, half+cell/2, cell, cell), dst_crs=crs,
              dst_nodata=np.nan, resampling=Resampling.bilinear)
    return dst


def save_grid(z, row, cell, kind, url):
    valid = np.isfinite(z)
    if not valid.any():
        raise ValueError('Sin muestras válidas')
    vals = z[valid]
    lo, hi = float(vals.min()), float(vals.max())
    scale = max((hi-lo)/254, 0.0001)
    q = np.full(z.shape, 255, dtype='uint8')
    q[valid] = np.clip(np.rint((vals-lo)/scale), 0, 254).astype('uint8')
    ident, lon, lat = row['region_id'], row['longitude'], row['latitude']
    filename = f'{ident}-{kind}.png'
    Image.fromarray(q).save(OUT / filename)
    return dict(id=ident, name=f'Candidata {row["rank"]}', body='Earth', longitude=lon, latitude=lat,
                width=z.shape[1], height=z.shape[0], cell_m=cell, window_m=(z.shape[1]-1)*cell,
                offset_m=lo, scale_m=scale, nodata=255, center_m=float(np.median(vals)), min_m=lo,
                max_m=hi, coverage=float(valid.mean()), heightmap='unified/'+filename, texture='unified/'+filename,
                source='Copernicus DEM GLO-30', source_url=url, datum='EGM2008 · DSM, incluye objetos superficiales',
                native_resolution_m='1 arcsec (~30 m; varía con latitud)', quantization_error_m=scale/2,
                sha256=hashlib.sha256((OUT/filename).read_bytes()).hexdigest(),
                grid_crs=f'Local azimuthal equidistant at {lat}, {lon}; raster north-up')


def main():
    rows = json.loads(Path(sys.argv[1]).read_text())['results']
    catalog_path = OUT / 'catalog.json'
    catalog = json.loads(catalog_path.read_text())
    env = dict(GDAL_DISABLE_READDIR_ON_OPEN='EMPTY_DIR', CPL_VSIL_CURL_ALLOWED_EXTENSIONS='.tif,.TIF',
               GDAL_HTTP_TIMEOUT='20', GDAL_HTTP_MAX_RETRY='0')
    with rasterio.Env(**env):
        for row in rows:
            ident, lat, lon = row['region_id'], row['latitude'], row['longitude']
            sn, ew = ('N' if lat >= 0 else 'S'), ('E' if lon >= 0 else 'W')
            tile = f'Copernicus_DSM_COG_10_{sn}{abs(math.floor(lat)):02}_00_{ew}{abs(math.floor(lon)):03}_00_DEM'
            url = f'https://copernicus-dem-30m.s3.amazonaws.com/{tile}/{tile}.tif'
            try:
                with rasterio.open('/vsicurl/'+url) as src:
                    grids = {kind: save_grid(sample(src, lon, lat, cell, n), row, cell, kind, url)
                             for kind, cell, n in [('local', 30, 61), ('regional', 150, 161)]}
                catalog['sites'][ident] = grids
                catalog.get('missing', {}).pop(ident, None)
                print(ident, 'OK', flush=True)
            except Exception as e:
                print(ident, 'sin datos:', e, flush=True)
    catalog_path.write_text(json.dumps(catalog, ensure_ascii=False, indent=2)+'\n')


if __name__ == '__main__':
    main()
