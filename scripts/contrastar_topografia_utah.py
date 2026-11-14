#!/usr/bin/env python3
"""Controlled, offline DEM comparison on the Utah pilot footprint."""
import json
from pathlib import Path
import platform

import numpy as np
from rasterio.transform import from_origin

import analizar_primer_caso as terrain
from analizar_dimensiones import geometry_descriptors
from explorar_fuentes_atlas import CENTERS

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'docs/evidencia-armonizacion-utah'
IDENTITIES = ROOT / 'docs/exploracion-fuentes-v1/identidades-entradas.json'
INPUTS = {
    '3DEP': ('data/raw/3dep/USGS_1M_12_x53y428_UT_FEMA_FS_FlamingGorge_2020_B20.tif', 'NAVD88'),
    'GLO-30': ('data/raw/atlas30/glo30/Copernicus_DSM_COG_10_N38_00_W111_00_DEM.tif', 'EGM2008'),
    'SRTM': ('data/raw/srtm/N38W111.tif', 'EGM96'),
}
CELLS = (30, 60, 120)
WINDOWS = (1800, 3000)
RADII = (360, 720)
HALO = max(RADII)
FIXED_BASE = 240
TOLERANCE = 1e-6


def center_crop(array, side_m, cell_m):
    n = side_m // cell_m
    start = (array.shape[0] - n) // 2
    return array[start:start + n, start:start + n]


def slope(elevation, cell_m, base_m):
    """Central differences requiring finite samples along both axes."""
    if base_m < 2 * cell_m or base_m % (2 * cell_m):
        raise ValueError('Slope base must be an even multiple of the cell size')
    step = base_m // (2 * cell_m)
    if step == 1:
        return np.pad(terrain.slopes(elevation, cell_m), 1, constant_values=np.nan)
    height, width = elevation.shape
    center = elevation[step:-step, step:-step]
    valid = np.isfinite(center)
    for offset in range(-step, step + 1):
        valid &= np.isfinite(elevation[step + offset:height - step + offset, step:-step])
        valid &= np.isfinite(elevation[step:-step, step + offset:width - step + offset])
    dx = (elevation[step:-step, 2 * step:] - elevation[step:-step, :-2 * step]) / base_m
    dy = (elevation[:-2 * step, step:-step] - elevation[2 * step:, step:-step]) / base_m
    angles = np.degrees(np.arctan(np.hypot(dx, dy)))
    return np.pad(np.where(valid, angles, np.nan), step, constant_values=np.nan)


def summarize(arrays, descriptor, setting_m, unit):
    common = np.logical_and.reduce([np.isfinite(a) for a in arrays.values()])
    n = int(common.sum())
    if not n:
        raise ValueError(f'No common cells for {descriptor} at {setting_m} m')
    values = {source: a[common] for source, a in arrays.items()}
    stats = {}
    paired = {}
    for source, sample in values.items():
        p05, p50, p90, p95 = np.percentile(sample, [5, 50, 90, 95])
        if descriptor == 'relief':
            stats[source] = {'p95_minus_p05': float(p95 - p05)}
            continue
        stats[source] = {'p50': float(p50), 'p90': float(p90)}
        if source != '3DEP':
            delta = sample - values['3DEP']
            paired[source] = {
                'median_signed': float(np.median(delta)),
                'median_absolute': float(np.median(np.abs(delta))),
                'p90_absolute': float(np.percentile(np.abs(delta), 90)),
            }
    return {'descriptor': descriptor, 'setting_m': setting_m, 'unit': unit,
            'common_cells': n, 'total_cells': common.size,
            'common_fraction': n / common.size, 'statistics': stats,
            'paired_against_3dep': paired}


def read_grids():
    known = {entry['path']: entry for entry in json.loads(IDENTITIES.read_text())}
    lon, lat = CENTERS['desierto']
    config = {'window_m': max(WINDOWS), 'margin_m': HALO}
    half = config['window_m'] / 2 + HALO
    grids = {cell: {} for cell in CELLS}
    metadata = {}
    transforms = {cell: from_origin(-half, half, cell, cell) for cell in CELLS}
    for source, (path, datum) in INPUTS.items():
        site = {'longitude': lon, 'latitude': lat, 'body': 'Earth', 'product_id': Path(path).stem,
                'input': path, 'url': None, 'vertical_reference': datum, 'limitations': []}
        data, valid, src_transform, src_crs, dst_crs, meta = terrain.read_crop(ROOT / path, site, config)
        if (meta['bytes'], meta['sha256']) != (known[path]['bytes'], known[path]['sha256']):
            raise ValueError(f'Input differs from inventory: {path}')
        metadata[source] = meta
        for cell, transform in transforms.items():
            n = int(2 * half) // cell
            elevation, _ = terrain.aggregate(data, valid, src_transform, src_crs, dst_crs,
                                             transform, (n, n), TOLERANCE)
            grids[cell][source] = elevation
        del data, valid
    return grids, metadata, {str(cell): list(t)[:6] for cell, t in transforms.items()}


def calculate(grids):
    rows = []
    for cell, original in grids.items():
        shared = np.logical_and.reduce([np.isfinite(a) for a in original.values()])
        elevation = {source: np.where(shared, a, np.nan) for source, a in original.items()}
        metrics = [('relief', None, 'm', elevation)]
        for base in sorted({2 * cell, FIXED_BASE}):
            arrays = {source: slope(a, cell, base) for source, a in elevation.items()}
            metrics.append(('slope', base, 'deg', arrays))
        for radius in RADII:
            arrays = {source: geometry_descriptors(a, cell, radius)['roughness_rms']
                      for source, a in elevation.items()}
            metrics.append(('roughness', radius, 'm', arrays))
        for window in WINDOWS:
            coverage = {source: float(np.isfinite(center_crop(a, window, cell)).mean())
                        for source, a in original.items()}
            for descriptor, setting, unit, arrays in metrics:
                crops = {source: center_crop(a, window, cell) for source, a in arrays.items()}
                row = summarize(crops, descriptor, setting, unit)
                rows.append({'window_m': window, 'cell_m': cell,
                             'elevation_coverage_by_source': coverage, **row})
    return rows


def plot(rows):
    from matplotlib import pyplot as plt

    figure, axes = plt.subplots(1, 3, figsize=(11, 4.0), layout='constrained')
    panels = (
        ('relief', None, 'p95_minus_p05', 'Relieve P95–P5 (m)'),
        ('slope', FIXED_BASE, 'p90', 'Pendiente P90 (°) · base 240 m'),
        ('roughness', RADII[0], 'p50', 'Rugosidad mediana (m) · radio 360 m'),
    )
    colors = {'3DEP': '#243f65', 'GLO-30': '#a75b17', 'SRTM': '#167b70'}
    for ax, (descriptor, setting, statistic, title) in zip(axes, panels):
        selected = sorted((r for r in rows if r['descriptor'] == descriptor
                           and r['setting_m'] == setting and r['window_m'] == 3000),
                          key=lambda r: r['cell_m'])
        for source in INPUTS:
            ax.plot(CELLS, [r['statistics'][source][statistic] for r in selected],
                    color=colors[source], marker='o', label=source)
        ax.set(title=title, xlabel='Tamaño de celda (m)', xticks=CELLS)
        ax.grid(alpha=.2)
        ax.spines[['right', 'top']].set_visible(False)
    axes[0].legend(frameon=False)
    figure.suptitle('Control de Utah · misma huella de 3 km y soporte común', fontweight='bold')
    figure.savefig(OUT / 'sensibilidad.png', dpi=180)
    plt.close(figure)


def verify_vertical_offset(elevation):
    """Confirm the measured terrain descriptors ignore a constant offset."""
    original = {'relief': np.nanpercentile(elevation, 95) - np.nanpercentile(elevation, 5),
                'slope': slope(elevation, 30, FIXED_BASE),
                'roughness': geometry_descriptors(elevation, 30, RADII[0])['roughness_rms']}
    shifted = elevation + 1000
    altered = {'relief': np.nanpercentile(shifted, 95) - np.nanpercentile(shifted, 5),
               'slope': slope(shifted, 30, FIXED_BASE),
               'roughness': geometry_descriptors(shifted, 30, RADII[0])['roughness_rms']}
    errors = {}
    for key in original:
        np.testing.assert_allclose(original[key], altered[key], rtol=0, atol=1e-7, equal_nan=True)
        errors[key] = float(np.nanmax(np.abs(original[key] - altered[key])))
    return {'offset_m': 1000, 'max_abs_change': errors, 'atol': 1e-7}


def main():
    grids, metadata, transforms = read_grids()
    rows = calculate(grids)
    check = verify_vertical_offset(grids[30]['3DEP'])
    lon, lat = CENTERS['desierto']
    result = {'center_lon_lat': [lon, lat], 'grid_transforms_including_halo': transforms,
              'halo_m': HALO, 'full_support_tolerance': TOLERANCE,
              'fixed_slope_base_m': FIXED_BASE, 'vertical_conversion': 'none',
              'elevation_resampling': 'GDAL average from native grid, one pass per resolution',
              'inputs': metadata, 'vertical_offset_check': check,
              'versions': {'python': platform.python_version(), 'numpy': np.__version__,
                           'gdal': terrain.rasterio.__gdal_version__, 'proj': terrain.pyproj.proj_version_str},
              'measurements': rows}
    OUT.mkdir(exist_ok=True)
    terrain.write_json(OUT / 'resultados.json', result)
    plot(rows)
    files = [Path(__file__).resolve(), IDENTITIES, Path(terrain.__file__),
             ROOT / 'scripts/analizar_dimensiones.py', ROOT / 'scripts/explorar_fuentes_atlas.py',
             OUT / 'resultados.json', OUT / 'sensibilidad.png']
    terrain.write_json(OUT / 'manifest.json', {'files': [
        {'path': str(p.relative_to(ROOT)), 'sha256': terrain.digest(p)} for p in files]})
    print(f'{len(rows)} configuraciones, cobertura común mínima {min(r["common_fraction"] for r in rows):.1%}')


if __name__ == '__main__':
    main()
