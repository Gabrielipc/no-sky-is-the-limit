#!/usr/bin/env python3
"""Release multidimensional offline. No modifica la evidencia topográfica anterior."""
import argparse
import json
import math
from pathlib import Path
import platform
import sys

import numpy as np
import pyproj
from pyproj import CRS
import rasterio
import scipy
from rasterio.features import geometry_mask
from rasterio.transform import from_origin
from rasterio.warp import transform_geom
from rasterio.windows import Window, from_bounds
from scipy.ndimage import correlate
from scipy.stats import wasserstein_distance

sys.path.insert(0, str(Path(__file__).resolve().parent))
import analizar_primer_caso as terrain

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / 'specs/scenarios/superficie-multidimensional-v1.json'
METRICS = {
    'roughness_rms': {'name': 'Rugosidad sin inclinación', 'unit': 'm',
                      'description': 'RMS del residuo de elevación tras ajustar un plano en cada vecindario cuadrado. Un plano inclinado tiene rugosidad cero.'},
    'topographic_position': {'name': 'Posición topográfica', 'unit': 'm',
                            'description': 'Elevación de la celda menos la media del vecindario: positiva en posiciones altas y negativa en bajas.'},
    'laplacian': {'name': 'Curvatura discreta', 'unit': 'm⁻¹',
                  'description': 'Laplaciano de elevación con cuatro vecinos; positivo en formas cóncavas y negativo en convexas. No es curvatura geométrica normalizada.'},
}
PENDING = {
    'geology_and_materials': ('Materiales', ['crism', 'emit-l2b-min', 'jezero-geology-sim3464', 'utah-geology', 'atacama-geology'],
                            'Faltan productos locales procesados y una correspondencia revisada entre clases minerales/geológicas.'),
    'rocks_and_obstacles': ('Rocas y obstáculos', ['hirise-ortho-a', 'naip'],
                            'Las imágenes requieren anotaciones, tamaño mínimo detectable y validación. El DEM no es un inventario de obstáculos.'),
    'dust': ('Polvo y formas eólicas', ['tes-dust-context', 'hirise-ortho-a', 'naip'],
             'Sin medición local comparable de polvo. Arena, polvo superficial y aerosoles son variables distintas.'),
    'water_and_ice': ('Agua y hielo', ['jrc-surface-water', 'swim4mim'],
                      'Sin escenario y mediciones compatibles: agua terrestre actual y ambiente lacustre antiguo no son la misma observación.'),
}
LIMITATIONS = [
    'Descriptores exploratorios de terreno; no certifican analogía, movilidad ni seguridad.',
    'Rugosidad, posición y curvatura comparten los mismos DEM con pendiente y relieve; no son evidencias independientes.',
    'El paso de celda no iguala la resolución efectiva, los errores de sensor ni la referencia vertical de los productos.',
    'El vecindario se extiende fuera de la ventana analizada. Su radio se mantiene en metros al cambiar de celda.',
    'La curvatura discreta es sensible al ruido y al tamaño de celda; no se combina con las otras variables en una puntuación.',
    'Inercia térmica solo observada para Jezero. Temperatura terrestre no sustituye a inercia térmica.',
    'La cobertura mide soporte numérico; no exactitud física ni observaciones independientes.',
]


def geometry_descriptors(elevation, cell_m, radius_m):
    """Full square support only. Plane fit removes slope from RMS roughness."""
    if cell_m <= 0 or radius_m < cell_m or radius_m % cell_m:
        raise ValueError('Radio positivo y múltiplo del tamaño de celda')
    z = np.asarray(elevation, dtype=float)
    if z.ndim != 2:
        raise ValueError('La elevación debe ser una matriz')
    radius = int(radius_m // cell_m)
    k = 2 * radius + 1
    kernel = np.ones((k, k))
    good = np.isfinite(z)
    # Center before sums of squares to avoid loss of significance at large datums.
    offset = float(np.median(z[good])) if good.any() else 0.0
    a = np.where(good, z - offset, 0.0)
    count = correlate(good.astype(float), kernel, mode='constant', cval=0)
    total = correlate(a, kernel, mode='constant', cval=0)
    total2 = correlate(a*a, kernel, mode='constant', cval=0)
    yy, xx = np.mgrid[-radius:radius+1, -radius:radius+1] * cell_m
    sx = correlate(a, xx.astype(float), mode='constant', cval=0)
    sy = correlate(a, yy.astype(float), mode='constant', cval=0)
    n = k*k
    residual = (total2 - total*total/n - sx*sx/np.sum(xx*xx) - sy*sy/np.sum(yy*yy))/n
    roughness = np.sqrt(np.maximum(residual, 0))
    tpi = a - total/n
    # Roundoff in the least-squares expression is not physical roughness.
    roughness[residual <= np.finfo(float).eps * np.maximum(total2/n, 1) * 64] = 0
    roughness[count != n] = np.nan
    tpi[count != n] = np.nan
    laplacian = np.full(z.shape, np.nan)
    center = z[1:-1, 1:-1]
    laplacian[1:-1, 1:-1] = ((z[1:-1, :-2]-center) + (z[1:-1, 2:]-center)
                                            + (z[:-2, 1:-1]-center) + (z[2:, 1:-1]-center))/(cell_m**2)
    return {'roughness_rms': roughness, 'topographic_position': tpi, 'laplacian': laplacian}


def describe(values, min_coverage):
    a = np.asarray(values)
    finite = a[np.isfinite(a)]
    coverage = finite.size/a.size if a.size else 0
    return {'status': 'measured' if finite.size and coverage >= min_coverage else 'insufficient_quality',
            'valid_cells': int(finite.size), 'total_cells': int(a.size), 'coverage': float(coverage),
            'quantiles': dict(zip(('p10', 'p50', 'p90'), map(float, np.percentile(finite, [10, 50, 90])))) if finite.size else None}


def compare(reference, candidate, min_coverage):
    rs, cs = describe(reference, min_coverage), describe(candidate, min_coverage)
    enough = rs['status'] == cs['status'] == 'measured'
    return {'status': 'comparable' if enough else 'insufficient_quality',
            'wasserstein': float(wasserstein_distance(reference[np.isfinite(reference)], candidate[np.isfinite(candidate)])) if enough else None,
            'candidate_minus_reference_median': cs['quantiles']['p50']-rs['quantiles']['p50'] if enough else None}


def grid(array):
    return {'rows': array.shape[0], 'columns': array.shape[1],
            'values': [float(x) if np.isfinite(x) else None for x in array.ravel()]}


def inspect_thermal(spec, area, min_coverage):
    path = ROOT/spec['input']
    source = {k: spec[k] for k in ('input', 'product_id', 'url', 'doi', 'license', 'units', 'sha256', 'bytes')}
    if not path.exists():
        return {'status': 'not_acquired', 'summary': None, 'grid': None, 'source': source,
                'reason': 'Falta el producto térmico local.'}
    if path.stat().st_size != spec['bytes'] or terrain.digest(path) != spec['sha256']:
        raise ValueError('El original térmico difiere de su identidad documentada')
    with rasterio.open(path) as ds:
        if ds.crs is None or ds.count != 1 or ds.nodata != spec['nodata']:
            raise ValueError('Metadatos térmicos inesperados')
        crs = CRS.from_wkt(ds.crs.to_wkt())
        if abs(crs.ellipsoid.semi_major_metre-spec['sphere_radius_m']) > 1e-6:
            raise ValueError('Esfera térmica distinta de la documentada')
        # Explicit shared-longitude/latitude assumption, never Earth CRS for Mars.
        geom = transform_geom(crs.geodetic_crs.to_wkt(), ds.crs, area['geometry'])
        coords = np.asarray(geom['coordinates'][0])
        w = from_bounds(coords[:, 0].min(), coords[:, 1].min(), coords[:, 0].max(), coords[:, 1].max(), ds.transform)
        left, top = math.floor(w.col_off), math.floor(w.row_off)
        win = Window(left, top, math.ceil(w.col_off+w.width)-left, math.ceil(w.row_off+w.height)-top)
        a = ds.read(1, window=win, boundless=True, masked=True).astype(float).filled(np.nan)
        inside = geometry_mask([geom], out_shape=a.shape, transform=ds.window_transform(win), invert=True)
        a[~inside] = np.nan
        summary = describe(a[inside], min_coverage)
        summary['total_cells'] = int(inside.sum())
        return {'status': summary['status'], 'summary': summary, 'grid': grid(a), 'source': source,
                'native_step_projected_m': list(ds.res), 'crs_wkt': ds.crs.to_wkt(),
                'spatial_assumption': 'Longitudes/latitudes del polígono interpretadas sobre la esfera térmica de 3.396.190 m; corregistro independiente pendiente.',
                'reason': 'Propiedad observada solo en Jezero; no hay comparación térmica con la Tierra.'}


def validate_config(config):
    radius, margin, window = (config[k] for k in ('neighborhood_radius_m', 'margin_m', 'window_m'))
    if not 0 < config['min_coverage'] <= 1 or not 0 <= config['support_tolerance'] < 1:
        raise ValueError('Cobertura o tolerancia inválida')
    for cell in config['scales_m']:
        if cell <= 0 or radius < cell or radius % cell or margin < radius+cell or margin % cell or window <= 0 or window % cell:
            raise ValueError('Ventana, vecindario, margen y celda incompatibles')


def run(config_path=DEFAULT_CONFIG):
    config = json.loads(config_path.read_text())
    validate_config(config)
    base_path = ROOT/config['base_case']
    base = json.loads(base_path.read_text())
    if base['window_m'] != config['window_m'] or base['sites'][0]['id'] != config['reference_id']:
        raise ValueError('El caso base no coincide con este escenario')
    catalog_path = ROOT/config['source_catalog']
    catalog = json.loads(catalog_path.read_text())
    crop_config = {**base, 'margin_m': config['margin_m']}
    result_sites, provenance, distributions = [], [], {}
    for site in base['sites']:
        path = terrain.acquire(site)  # Original identities checked, no implicit network.
        data, valid, transform, src_crs, dst_crs, meta = terrain.read_crop(path, site, crop_config)
        provenance.append(meta)
        scales = []
        for cell in config['scales_m']:
            n, margin = config['window_m']//cell, config['margin_m']//cell
            half = config['window_m']/2 + config['margin_m']
            elevation, _ = terrain.aggregate(data, valid, transform, src_crs, dst_crs, from_origin(-half, half, cell, cell),
                                              (n+2*margin, n+2*margin), config['support_tolerance'])
            arrays = {key: value[margin:-margin, margin:-margin] for key, value in geometry_descriptors(elevation, cell, config['neighborhood_radius_m']).items()}
            distributions[(site['id'], cell)] = arrays
            scales.append({'cell_m': cell, 'neighborhood_radius_m': config['neighborhood_radius_m'],
                           'neighborhood_width_samples': 2*config['neighborhood_radius_m']//cell+1,
                           'descriptors': {key: describe(a, config['min_coverage']) for key, a in arrays.items()},
                           'grids': {key: grid(a) for key, a in arrays.items()}})
        area = terrain.geometry(site, base)
        pending = [{'id': key, 'name': name, 'status': 'not_evaluated', 'value': None, 'source_ids': ids, 'reason': reason}
                   for key, (name, ids, reason) in PENDING.items()]
        thermal = inspect_thermal(config['thermal'], area, config['min_coverage']) if site['id'] == config['thermal']['site_id'] else {
            'status': 'not_acquired', 'summary': None, 'grid': None, 'source': None,
            'reason': 'Sin inercia térmica terrestre comparable. Temperatura superficial es otra magnitud.'}
        result_sites.append({**{k: site[k] for k in ('id', 'name', 'body', 'latitude', 'longitude')},
                             'area': area, 'source': {k: site[k] for k in ('product_id', 'url', 'sha256', 'bytes', 'vertical_reference')},
                             'scales': scales, 'thermal': thermal, 'pending_dimensions': pending})
    comparisons = []
    reference = config['reference_id']
    for cell in config['scales_m']:
        for site in base['sites'][1:]:
            comparisons.append({'candidate_id': site['id'], 'cell_m': cell,
                                'metrics': {key: compare(distributions[(reference, cell)][key], distributions[(site['id'], cell)][key], config['min_coverage']) for key in METRICS},
                                'thermal': {'status': 'not_comparable', 'wasserstein': None, 'reason': 'Falta una medición terrestre de inercia térmica compatible.'}})
    # Keep documentation/source selection in the reproducible identity too.
    result = {'scenario_id': config['scenario_id'], 'window_m': config['window_m'], 'scales_m': config['scales_m'],
              'neighborhood_radius_m': config['neighborhood_radius_m'], 'min_coverage': config['min_coverage'],
              'metrics': METRICS, 'sites': result_sites, 'comparisons': comparisons,
              'sources': catalog['sources'], 'limitations': LIMITATIONS, 'combined_score': None}
    out = ROOT/config['output']
    out.mkdir(parents=True, exist_ok=True)
    terrain.write_json(out/'resultados.json', result)
    terrain.write_json(out/'procesamiento.json', {'config': config, 'config_sha256': terrain.digest(config_path),
                       'inputs': provenance, 'thermal': config['thermal'], 'method': METRICS,
                       'versions': {'python': platform.python_version(), 'numpy': np.__version__, 'rasterio': rasterio.__version__,
                                    'gdal': rasterio.__gdal_version__, 'pyproj': pyproj.__version__, 'scipy': scipy.__version__}})
    files = [out/'resultados.json', out/'procesamiento.json', config_path, base_path, catalog_path,
             Path(__file__).resolve(), Path(terrain.__file__).resolve()]
    import os
    terrain.write_json(out/'manifest-local.json', {'schema': 1, 'files': [
        {'file': os.path.relpath(f, out), 'bytes': f.stat().st_size, 'sha256': terrain.digest(f)} for f in files]})
    print(f'Release: {out}; {len(result_sites)} sitios, {len(comparisons)} comparaciones. Sin puntuación combinada.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=DEFAULT_CONFIG)
    args = parser.parse_args()
    run(args.config.resolve())
