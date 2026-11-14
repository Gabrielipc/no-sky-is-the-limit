#!/usr/bin/env python3
"""Análisis regional trazable, independiente del catálogo exploratorio de la app.

Ejecutar con el entorno Pixi. --download obtiene solo las entradas que falten;
ningún archivo original existente se reemplaza si su hash no coincide.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import re
import tempfile
import urllib.request

# Evitar escrituras de caché fuera del espacio de trabajo/sandbox.
os.environ.setdefault('MPLCONFIGDIR', str(Path(tempfile.gettempdir()) / 'analogos-matplotlib'))
os.environ.setdefault('XDG_CACHE_HOME', str(Path(tempfile.gettempdir()) / 'analogos-cache'))
Path(os.environ['XDG_CACHE_HOME']).mkdir(parents=True, exist_ok=True)
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import LightSource
import numpy as np
import PIL
import pyproj
from pyproj import CRS, Geod, Transformer
import rasterio
from rasterio.enums import Resampling
from rasterio.transform import from_origin
from rasterio.warp import reproject, transform_bounds
from rasterio.windows import Window, from_bounds
from scipy.stats import wasserstein_distance
import scipy
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / 'specs/analysis/primer-caso-fase2.json'


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')


def acquire(site, download=False):
    path = ROOT / site['input']
    if not path.exists():
        if not download:
            raise FileNotFoundError(f'Falta {path}; ejecutar con --download')
        path.parent.mkdir(parents=True, exist_ok=True)
        part = path.with_name(path.name + '.part')
        req = urllib.request.Request(site['url'], headers={'User-Agent': 'Analogos-Fase2/1.0'})
        with urllib.request.urlopen(req, timeout=60) as response, part.open('wb') as f:
            if response.status != 200:
                raise ValueError('Se requiere una respuesta completa HTTP 200')
            size = 0
            while block := response.read(1024 * 1024):
                size += len(block)
                if size > site['bytes']:
                    raise ValueError('Descarga mayor que el tamaño documentado')
                f.write(block)
        if part.stat().st_size != site['bytes'] or digest(part) != site['sha256']:
            raise ValueError(f'Descarga incompleta o identidad distinta: {part}')
        part.rename(path)
    if path.stat().st_size != site['bytes'] or digest(path) != site['sha256']:
        raise ValueError(f'Entrada distinta de la documentada; no se sobrescribe: {path}')
    return path


def local_crs(site):
    shape = f'+R={site["radius_m"]}' if site['body'] == 'Mars' else '+datum=WGS84'
    return CRS.from_proj4(f'+proj=aeqd +lat_0={site["latitude"]} +lon_0={site["longitude"]} {shape} +units=m +no_defs')


def read_crop(path, site, config):
    """Ventana nativa con padding explícito; los vacíos participan como 0 en soporte."""
    dst_crs = local_crs(site)
    half = config['window_m'] / 2 + config['margin_m']
    with rasterio.open(path) as ds:
        if ds.crs is None or ds.count != 1:
            raise ValueError('Se requiere una banda con CRS documentado')
        if site['body'] == 'Mars':
            if ds.tags().get('PRODUCT_ID', '').strip('"') != site['product_id']:
                raise ValueError('La etiqueta PDS no corresponde al producto esperado')
            native = CRS.from_wkt(ds.crs.to_wkt())
            if abs(native.ellipsoid.semi_major_metre - site['radius_m']) > 1e-6:
                raise ValueError('El radio marciano no coincide con la etiqueta')
        bounds = transform_bounds(dst_crs, ds.crs, -half, -half, half, half, densify_pts=41)
        w = from_bounds(*bounds, ds.transform)
        c, r = math.floor(w.col_off) - 2, math.floor(w.row_off) - 2
        win = Window(c, r, math.ceil(w.col_off + w.width) + 2 - c,
                     math.ceil(w.row_off + w.height) + 2 - r)
        a = ds.read(1, window=win, boundless=True, masked=True).astype('float64')
        data = a.filled(np.nan)
        valid = ~np.ma.getmaskarray(a) & np.isfinite(data)
        if 'valid_range_m' in site:
            lo, hi = site['valid_range_m']
            valid &= (data >= lo) & (data <= hi)
        data[~valid] = np.nan
        src_transform = ds.window_transform(win)
        native_crs = ds.crs
        meta = {'input': site['input'], 'sha256': digest(path), 'bytes': path.stat().st_size,
                'product_id': site['product_id'], 'source_url': site['url'],
                'source_crs_wkt': ds.crs.to_wkt(), 'source_transform': list(ds.transform),
                'source_shape': [ds.height, ds.width], 'source_nodata': ds.nodata,
                'source_window': [int(win.col_off), int(win.row_off), int(win.width), int(win.height)],
                'crop_transform': list(src_transform), 'crop_cells': int(data.size),
                'crop_valid_cells': int(valid.sum()), 'crop_valid_fraction': float(valid.mean()),
                'source_step_units': list(ds.res), 'target_crs_wkt': dst_crs.to_wkt(),
                'vertical_reference': site['vertical_reference'], 'source_limitations': site['limitations']}
        if site['body'] == 'Mars':
            with path.open('rb') as label:
                text = label.read(27736).decode('ascii', errors='strict')
            def number(key):
                return float(re.search(rf'^\s*{key}\s*=\s*([-+0-9.eE]+)', text, re.M).group(1))
            stride = int(number('RECORD_BYTES'))
            offset = (int(number(r'\^IMAGE')) - 1) * stride
            raw = np.memmap(path, dtype='<f4', mode='r', offset=offset, shape=(ds.height,ds.width))
            controls=[]
            for rr,cc in [(int(win.row_off+win.height//2),int(win.col_off+win.width//2)),
                          (int(win.row_off+5),int(win.col_off+5)),
                          (int(win.row_off+win.height-6),int(win.col_off+win.width-6))]:
                value=float(ds.read(1, window=Window(cc,rr,1,1))[0,0])
                if value != float(raw[rr,cc]):
                    raise ValueError('Decodificación binaria independiente no coincide con GDAL')
                controls.append({'row':rr,'column':cc,'elevation_m':value})
            expected_origin = (-(number('SAMPLE_PROJECTION_OFFSET')+.5)*number('MAP_SCALE'),
                               (number('LINE_PROJECTION_OFFSET')+.5)*number('MAP_SCALE'))
            np.testing.assert_allclose([ds.transform.c,ds.transform.f],expected_origin,rtol=0,atol=1e-6)
            meta['independent_binary_controls']=controls
            meta['label_geotransform_origin_check']='passed; PDS offsets interpreted independently at raster outer edge'
    # Una muestra de paso físico; no es una estimación de resolución efectiva.
    geog = CRS.from_wkt(native_crs.to_wkt()).geodetic_crs
    to_native = Transformer.from_crs(geog, native_crs, always_xy=True)
    x, y = to_native.transform(site['longitude'], site['latitude'])
    to_geo = Transformer.from_crs(native_crs, geog, always_xy=True)
    lon, lat = to_geo.transform(x, y)
    gx, gy = to_geo.transform(x + abs(src_transform.a), y)
    hx, hy = to_geo.transform(x, y + abs(src_transform.e))
    geod = Geod(a=site['radius_m'], b=site['radius_m']) if site['body'] == 'Mars' else Geod(ellps='WGS84')
    meta['native_step_at_center_m'] = [abs(geod.inv(lon, lat, gx, gy)[2]), abs(geod.inv(lon, lat, hx, hy)[2])]
    return data, valid, src_transform, native_crs, dst_crs, meta


def aggregate(data, valid, src_transform, src_crs, dst_crs, dst_transform, shape, tolerance):
    """El promedio de elevación omite nodata; la máscara de soporte NO los omite."""
    elevation = np.full(shape, np.nan, dtype='float64')
    support = np.zeros(shape, dtype='float64')
    args = dict(src_transform=src_transform, src_crs=src_crs, dst_transform=dst_transform,
                dst_crs=dst_crs, resampling=Resampling.average, num_threads=1)
    reproject(np.where(valid, data, np.nan), elevation, src_nodata=np.nan,
              dst_nodata=np.nan, **args)
    reproject(valid.astype('float64'), support, src_nodata=None, dst_nodata=0, **args)
    support = np.clip(support, 0, 1)
    elevation[(support < 1 - tolerance) | ~np.isfinite(elevation)] = np.nan
    return elevation, support


def slopes(elevation, cell):
    z = elevation
    center = z[1:-1, 1:-1]
    good = np.isfinite(center) & np.isfinite(z[1:-1, :-2]) & np.isfinite(z[1:-1, 2:])
    good &= np.isfinite(z[:-2, 1:-1]) & np.isfinite(z[2:, 1:-1])
    dx = (z[1:-1, 2:] - z[1:-1, :-2]) / (2 * cell)
    dy = (z[:-2, 1:-1] - z[2:, 1:-1]) / (2 * cell)
    out = np.degrees(np.arctan(np.hypot(dx, dy)))
    out[~good] = np.nan
    return out


def describe(elevation, slope, edges):
    z, s = elevation[np.isfinite(elevation)], slope[np.isfinite(slope)]
    return {'cells': int(elevation.size), 'valid_elevation_cells': int(z.size),
            'valid_slope_cells': int(s.size), 'elevation_coverage': float(z.size / elevation.size),
            'slope_coverage': float(s.size / slope.size),
            'relief_p95_p5_m': float(np.percentile(z, 95, method='linear') - np.percentile(z, 5, method='linear')) if z.size else None,
            'slope_quantiles_deg': dict(zip(['p10', 'p50', 'p90'], map(float, np.percentile(s, [10, 50, 90], method='linear')))) if s.size else None,
            'slope_histogram_counts': np.histogram(s, bins=edges)[0].tolist(),
            'status': 'available_exploratory' if z.size and s.size else 'insufficient_data'}


def save_raster(path, array, crs, transform):
    with rasterio.open(path, 'w', driver='GTiff', height=array.shape[0], width=array.shape[1],
                       count=1, dtype='float64', crs=crs, transform=transform, nodata=np.nan,
                       compress='deflate') as ds:
        ds.write(array, 1)


def geometry(site, config):
    crs = local_crs(site)
    to_geo = Transformer.from_crs(crs, crs.geodetic_crs, always_xy=True)
    half = config['window_m'] / 2
    # Densificar bordes: estos polígonos describen la ventana EXACTA de análisis.
    ring = []
    corners = [(-half, -half), (half, -half), (half, half), (-half, half), (-half, -half)]
    for a, b in zip(corners, corners[1:]):
        for t in np.linspace(0, 1, 17, endpoint=False):
            ring.append(list(to_geo.transform(a[0] + t * (b[0]-a[0]), a[1] + t * (b[1]-a[1]))))
    ring.append(ring[0])
    return {'type': 'Feature', 'properties': {'site_id': site['id'], 'body': site['body'],
            'side_m': config['window_m'], 'crs_wkt': crs.geodetic_crs.to_wkt(),
            'role': 'analysis extent; supersedes nominal phase-1 polygon only for this experiment'},
            'geometry': {'type': 'Polygon', 'coordinates': [ring]}}


def inspect_ortho(config, meta, out, download):
    """Pillow decodifica JP2; la geometría procede de su etiqueta PDS, no de PIL."""
    spec = config['orthoimage']
    path = acquire(spec, download)
    label = (ROOT / spec['label']).read_text()
    dtm_label = (ROOT / 'docs/evidencia-fase-1/jezero-dtm-etiqueta.txt').read_text()
    keys = ['MAP_SCALE', 'CENTER_LATITUDE', 'CENTER_LONGITUDE', 'A_AXIS_RADIUS',
            'LINE_PROJECTION_OFFSET', 'SAMPLE_PROJECTION_OFFSET', 'LINES', 'LINE_SAMPLES']
    for key in keys:
        pattern = rf'^\s*{key}\s*=\s*([^\r\n]+)'
        if re.search(pattern, label, re.M).group(1) != re.search(pattern, dtm_label, re.M).group(1):
            raise ValueError(f'Geometría de ortoimagen y DTM distinta: {key}')
    c,r,w,h = meta['source_window']
    with Image.open(path) as im:
        if im.size != tuple(reversed(meta['source_shape'])):
            raise ValueError('Dimensiones de ortoimagen inesperadas')
        crop = np.asarray(im.crop((c,r,c+w,r+h)))
    crop_valid = (crop > 1) & (crop < 255)
    fig,ax = plt.subplots(figsize=(7,7), constrained_layout=True)
    ax.imshow(np.ma.masked_where(~crop_valid,crop), cmap='gray')
    ax.set(title='Jezero · ortoimagen RED C · mismo recorte que el DTM', xlabel='Columna del recorte', ylabel='Fila del recorte')
    fig.savefig(out/'jezero-ortoimagen-qa.png', dpi=160); plt.close(fig)
    write_json(out/'ortoimagen-qa.json', {'input':spec['input'], 'url':spec['url'],
        'sha256':digest(path), 'label_sha256':digest(ROOT/spec['label']),
        'decoder':'Pillow JPEG2000 (GDAL JP2OpenJPEG absent; no dependency change)',
        'geometry':'Detached PDS label matches DTM grid in checked keys; no independent registration precision claimed',
        'source_window':meta['source_window'], 'crop_pixels':int(crop.size),
        'crop_pixels_not_null_or_saturated':int(crop_valid.sum()),
        'use':'visual inspection only; not an additional similarity variable'})


def run(config_path, download=False):
    config = json.loads(config_path.read_text())
    for cell in config['scales_m']:
        if cell <= 0 or config['window_m'] % cell or config['margin_m'] % cell or config['margin_m'] < cell:
            raise ValueError('Ventana y margen deben ser múltiplos de escala y admitir vecinos de pendiente')
    out = ROOT / config['output']
    out.mkdir(parents=True, exist_ok=True)
    results, metadata, distributions = [], [], {}
    for site in config['sites']:
        path = acquire(site, download)
        data, valid, transform, src_crs, dst_crs, meta = read_crop(path, site, config)
        metadata.append(meta)
        save_raster(out / f'{site["id"]}-native-crop.tif', data, src_crs, transform)
        # Panel de inspección de DEM a su paso nativo; sin exigir precisión de ese paso.
        fig, ax = plt.subplots(1, 2, figsize=(9, 4), constrained_layout=True)
        step = meta['native_step_at_center_m']
        shade = LightSource(315, 45).hillshade(np.where(valid, data, np.nan), vert_exag=1, dx=step[0], dy=step[1])
        for pane, image, title, cmap in zip(ax, [data, shade], ['Elevación nativa (m)', 'Relieve sombreado · exageración 1'], ['terrain', 'gray']):
            im = pane.imshow(image, cmap=cmap); pane.set_title(title); pane.set_xlabel('Columna nativa'); pane.set_ylabel('Fila nativa')
            if cmap == 'terrain': fig.colorbar(im, ax=pane, shrink=.75)
        fig.suptitle(site['name']); fig.savefig(out / f'{site["id"]}-qa.png', dpi=140); plt.close(fig)
        for cell in config['scales_m']:
            n, margin = config['window_m'] // cell, config['margin_m'] // cell
            half = config['window_m'] / 2 + config['margin_m']
            dst_transform = from_origin(-half, half, cell, cell)
            elev, support = aggregate(data, valid, transform, src_crs, dst_crs, dst_transform,
                                      (n + 2*margin, n + 2*margin), config['support_tolerance'])
            z = elev[margin:-margin, margin:-margin]
            s = slopes(elev, cell)[margin-1:margin-1+n, margin-1:margin-1+n]
            stats = describe(z, s, config['slope_histogram_edges_deg'])
            stats.update(site_id=site['id'], cell_m=cell, slope_baseline_m=2*cell,
                         aggregation_footprint_m=cell, window_m=config['window_m'],
                         histogram_edges_deg=config['slope_histogram_edges_deg'],
                         support_min=float(support[margin:-margin, margin:-margin].min()),
                         support_max=float(support[margin:-margin, margin:-margin].max()))
            results.append(stats)
            distributions[(site['id'], cell)] = s[np.isfinite(s)]
            center_transform = from_origin(-config['window_m']/2, config['window_m']/2, cell, cell)
            for suffix, arr in [('elevation', z), ('slope', s), ('support', support[margin:-margin, margin:-margin])]:
                save_raster(out / f'{site["id"]}-{cell}m-{suffix}.tif', arr, dst_crs, center_transform)
            fig, ax = plt.subplots(1, 2, figsize=(9, 4), constrained_layout=True)
            for pane, image, title, cmap in zip(ax, [z-np.nanmedian(z) if np.isfinite(z).any() else z, s], ['Elevación respecto a mediana (m)', 'Pendiente (°)'], ['terrain','magma']):
                half_window = config['window_m']/2
                im = pane.imshow(image, extent=(-half_window,half_window,-half_window,half_window), cmap=cmap)
                pane.set_title(title); pane.set_xlabel('Este local (m)'); pane.set_ylabel('Norte local (m)'); fig.colorbar(im, ax=pane, shrink=.75)
            fig.suptitle(f'{site["name"]} · celdas {cell} m'); fig.savefig(out / f'{site["id"]}-{cell}m.png', dpi=140); plt.close(fig)
    comparisons = []
    reference = config['sites'][0]['id']
    for cell in config['scales_m']:
        ref = next(r for r in results if r['site_id'] == reference and r['cell_m'] == cell)
        for site in config['sites'][1:]:
            item = next(r for r in results if r['site_id'] == site['id'] and r['cell_m'] == cell)
            available = ref['status'] == item['status'] == 'available_exploratory'
            comparisons.append({'reference': reference, 'candidate': site['id'], 'cell_m': cell,
                'slope_wasserstein_deg': float(wasserstein_distance(distributions[(reference, cell)], distributions[(site['id'], cell)])) if available else None,
                'candidate_minus_reference_relief_m': item['relief_p95_p5_m'] - ref['relief_p95_p5_m'] if available else None,
                'status': 'exploratory_no_combined_score' if available else 'insufficient_data'})
    fig, axes = plt.subplots(1, len(config['scales_m']), figsize=(10,4), constrained_layout=True, squeeze=False)
    for ax, cell in zip(axes[0], config['scales_m']):
        for site in config['sites']:
            values = np.sort(distributions[(site['id'], cell)])
            if len(values): ax.step(values, np.arange(1,len(values)+1)/len(values), where='post', label=site['id'])
        ax.set(title=f'Celdas {cell} m · pendiente sobre base {2*cell} m', xlabel='Pendiente (°)', ylabel='Fracción acumulada'); ax.legend(fontsize=8); ax.grid(alpha=.2)
    fig.savefig(out/'distribuciones-pendiente.png', dpi=150); plt.close(fig)
    write_json(out/'resultados.json', {'case_id': config['case_id'], 'results': results, 'comparisons': comparisons,
               'dimensions_not_evaluated': ['geology_and_materials', 'thermal_properties', 'rocks_and_obstacles', 'dust', 'water_and_ice'],
               'missing_dimension_policy': 'Not measured, not zero, not evidence of similarity; see phase-1 feasibility matrix.',
               'interpretation': 'Regional exploratory terrain descriptors; not validated analog labels or mobility assessment.'})
    write_json(out/'procesamiento.json', {'config': str(config_path.relative_to(ROOT)), 'config_sha256': digest(config_path),
               'code_sha256': digest(Path(__file__)), 'versions': {'python': platform.python_version(), 'numpy': np.__version__, 'rasterio': rasterio.__version__, 'gdal': rasterio.__gdal_version__, 'pyproj':pyproj.__version__, 'scipy':scipy.__version__, 'matplotlib':matplotlib.__version__, 'pillow':PIL.__version__},
               'method': 'Average elevation and independent valid-support raster; complete support only; central differences after aggregation; linear quantiles; no vertical datum transformation, no cross-body reprojection',
               'inputs': metadata})
    geoms = [geometry(s, config) for s in config['sites']]
    write_json(out/'areas-marte.json', {'type':'FeatureCollection', 'note':'Mars coordinate system; not Earth RFC7946 GeoJSON', 'features':[g for g in geoms if g['properties']['body']=='Mars']})
    write_json(out/'areas-tierra.geojson', {'type':'FeatureCollection', 'features':[g for g in geoms if g['properties']['body']=='Earth']})
    if 'orthoimage' in config:
        inspect_ortho(config, metadata[0], out, download)
    for r in results:
        print(r['site_id'], r['cell_m'], r['valid_elevation_cells'], r['valid_slope_cells'], r['slope_quantiles_deg'], r['relief_p95_p5_m'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=DEFAULT_CONFIG)
    parser.add_argument('--download', action='store_true')
    args = parser.parse_args()
    run(args.config.resolve(), args.download)
