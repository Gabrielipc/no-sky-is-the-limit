#!/usr/bin/env python3
"""Repeat the Utah source/scale trial on forest and coastal controls."""
import json
from pathlib import Path

import numpy as np
from rasterio.transform import from_origin

import analizar_primer_caso as terrain
import contrastar_topografia_utah as trial
from analizar_dimensiones import geometry_descriptors
from explorar_fuentes_atlas import WORLD_CODES

ROOT = trial.ROOT
SPEC = ROOT / 'specs/analysis/validacion-armonizacion-topografica.json'
OUT = ROOT / 'docs/evidencia-validacion-topografica'
UTAH = ROOT / 'docs/evidencia-armonizacion-utah/resultados.json'
VERTICAL = {'3DEP': 'NAVD88', '3DEP_13': 'NAVD88', 'GLO-30': 'EGM2008', 'SRTM': 'EGM96', 'WorldCover': None}


def prepare(site):
    lon, lat = site['center_lon_lat']
    config = {'window_m': max(trial.WINDOWS), 'margin_m': trial.HALO}
    half = config['window_m'] / 2 + trial.HALO
    grids = {cell: {} for cell in trial.CELLS}
    cover = {cell: {} for cell in trial.CELLS}
    metadata = {}
    for source, asset in site['assets'].items():
        path = asset['path']
        request = {'longitude': lon, 'latitude': lat, 'body': 'Earth', 'product_id': Path(path).stem,
                   'input': path, 'url': asset['url'], 'vertical_reference': VERTICAL[source], 'limitations': []}
        data, valid, transform, crs, target_crs, meta = terrain.read_crop(ROOT / path, request, config)
        if (meta['bytes'], meta['sha256']) != (asset['bytes'], asset['sha256']):
            raise ValueError(f'Input differs from specification: {path}')
        metadata[source] = meta
        variables = {'elevation': data}
        if source == 'WorldCover':
            valid &= np.isin(data, WORLD_CODES)
            variables = {'land': data != 80, 'trees': data == 10, 'water': data == 80}
        for cell in trial.CELLS:
            n = int(2 * half) // cell
            target = from_origin(-half, half, cell, cell)
            for key, values in variables.items():
                result, support = terrain.aggregate(values, valid, transform, crs, target_crs,
                                                    target, (n, n), trial.TOLERANCE)
                if source == 'WorldCover':
                    cover[cell][key] = result
                    cover[cell]['classified_fraction'] = support
                else:
                    grids[cell][source] = result
        del data, valid, variables, values
    return grids, cover, metadata


def measured_arrays(grids, eligibility, cell):
    common = eligibility & np.logical_and.reduce([np.isfinite(a) for a in grids.values()])
    z = {source: np.where(common, a, np.nan) for source, a in grids.items()}
    yield 'relief', None, 'm', z
    for base in sorted({2 * cell, trial.FIXED_BASE}):
        yield 'slope', base, 'deg', {source: trial.slope(a, cell, base) for source, a in z.items()}
    for radius in trial.RADII:
        yield 'roughness', radius, 'm', {
            source: geometry_descriptors(a, cell, radius)['roughness_rms'] for source, a in z.items()}


def profile(grids, cover, coast):
    measurements = []
    maps = {}
    crop = trial.center_crop
    for cell, dem in grids.items():
        land = cover[cell]['land']
        policies = {'sin_mascara': np.ones(land.shape, bool)}
        if coast:
            policies.update({'tierra_50': land >= .50, 'tierra_95': land >= .95})
        for name, eligible in policies.items():
            for descriptor, setting, unit, arrays in measured_arrays(dem, eligible, cell):
                for width in trial.WINDOWS:
                    sample = {source: crop(a, width, cell) for source, a in arrays.items()}
                    eligible_core = crop(eligible, width, cell)
                    common = np.logical_and.reduce([np.isfinite(a) for a in sample.values()])
                    n = int(common.sum())
                    n_eligible = int(eligible_core.sum())
                    row = {'window_m': width, 'cell_m': cell, 'policy': name,
                           'eligible_cells': n_eligible, 'common_cells': n, 'total_cells': common.size,
                           'common_fraction': n / common.size,
                           'fraction_of_eligible': n / n_eligible if n_eligible else None,
                           'descriptor': descriptor, 'setting_m': setting, 'unit': unit,
                           'statistics': None, 'paired_against_3dep': None}
                    if n:
                        row.update(trial.summarize(sample, descriptor, setting, unit))
                    measurements.append(row)
                    if coast and cell == 30 and width == 3000 and name == 'tierra_95':
                        maps[(descriptor, setting)] = np.where(common, 2, eligible_core.astype(int))
    return measurements, maps


def cover_summary(cover):
    rows = []
    for cell in trial.CELLS:
        for width in trial.WINDOWS:
            row = {'cell_m': cell, 'window_m': width}
            for key, values in cover[cell].items():
                sample = trial.center_crop(values, width, cell)
                valid = np.isfinite(sample)
                row[key] = {'mean_of_valid_cells': float(sample[valid].mean()) if valid.any() else None,
                            'fraction_of_cells': float(valid.mean())}
            rows.append(row)
    return rows


def row_at(rows, descriptor, setting, cell=30, width=3000, policy='sin_mascara'):
    return next(row for row in rows if (row['descriptor'], row['setting_m'], row['cell_m'],
                row['window_m'], row.get('policy', 'sin_mascara')) == (descriptor, setting, cell, width, policy))


def reference_sensitivity(grids, cover, policy):
    """Change only the reference product on identical observed cells."""
    cell, width = 30, 3000
    dem = grids[cell]
    shared = np.isfinite(dem['3DEP']) & np.isfinite(dem['3DEP_13'])
    eligible = shared & (cover[cell]['land'] >= .95) if policy == 'tierra_95' else shared
    result = {}
    for label in ('3DEP', '3DEP_13'):
        inputs = {key: dem[key] for key in ('GLO-30', 'SRTM')}
        inputs['3DEP'] = dem[label]
        rows = []
        for descriptor, setting, unit, arrays in measured_arrays(inputs, eligible, cell):
            sample = {source: trial.center_crop(a, width, cell) for source, a in arrays.items()}
            if any(np.isfinite(a).any() for a in sample.values()):
                rows.append(trial.summarize(sample, descriptor, setting, unit))
        result[label] = rows
    return {'cell_m': cell, 'window_m': width, 'policy': policy, 'measurements': result}


def matched_slope_bases(grids, cover, policy):
    """Use the same centers for both bases, including on the coast."""
    cell, width = 30, 3000
    dem = grids[cell]
    eligible = np.logical_and.reduce([np.isfinite(a) for a in dem.values()])
    if policy == 'tierra_95':
        eligible &= cover[cell]['land'] >= .95
    by_base = {}
    for base in (60, 240):
        by_base[base] = {source: trial.center_crop(
            trial.slope(np.where(eligible, a, np.nan), cell, base), width, cell)
            for source, a in dem.items()}
    shared = np.logical_and.reduce([np.isfinite(a) for arrays in by_base.values() for a in arrays.values()])
    if not shared.any():
        return []
    return [trial.summarize({source: np.where(shared, a, np.nan) for source, a in arrays.items()},
                            'slope', base, 'deg') for base, arrays in by_base.items()]


def plot_source_effect(results, coast_maps):
    from matplotlib import pyplot as plt
    from matplotlib.colors import ListedColormap
    from matplotlib.patches import Patch

    figure, axes = plt.subplots(1, 3, figsize=(11, 4.0), sharey=True, layout='constrained')
    labels = [item['label'] for item in results.values()]
    positions = np.arange(len(labels))
    panels = [('relief', None, 'Relieve P95–P5 (m)'),
              ('slope', 240, 'Pendiente · base 240 m (°)'),
              ('roughness', 360, 'Rugosidad · radio 360 m (m)')]
    for ax, (descriptor, setting, title) in zip(axes, panels):
        for source, shift, color in [('GLO-30', -.15, '#a75b17'), ('SRTM', .15, '#167b70')]:
            values = []
            for item in results.values():
                row = row_at(item['measurements'], descriptor, setting, policy=item['primary_policy'])
                if row['statistics'] is None:
                    values.append(np.nan)
                elif descriptor == 'relief':
                    s = row['statistics']
                    values.append(abs(s[source]['p95_minus_p05'] - s['3DEP']['p95_minus_p05']))
                else:
                    values.append(row['paired_against_3dep'][source]['median_absolute'])
            ax.scatter(values, positions + shift, label=source, color=color, s=36)
        for index, item in enumerate(results.values()):
            row = row_at(item['measurements'], descriptor, setting, policy=item['primary_policy'])
            if row['statistics'] is None:
                ax.text(.04, index, 'Sin soporte común', transform=ax.get_yaxis_transform(),
                        va='center', color='#555555', fontsize=8)
        xlabel = 'Diferencia absoluta' if descriptor == 'relief' else 'Mediana de diferencias absolutas por celda'
        ax.set(title=title, xlabel=xlabel)
        ax.set_xlim(left=0)
        ax.grid(axis='x', alpha=.2)
    axes[0].set_yticks(positions, labels)
    axes[0].invert_yaxis()
    axes[0].legend(frameon=False, loc='upper right')
    figure.suptitle('Diferencias frente a 3DEP · huella de 3 km y celdas de 30 m', fontweight='bold')
    figure.savefig(OUT / 'diferencias-por-ambiente.png', dpi=180)
    plt.close(figure)

    figure, axes = plt.subplots(1, 3, figsize=(10, 4.0), layout='constrained')
    colors = ['#d7e8ef', '#d88a51', '#28706d']
    for ax, key, title in zip(axes, [('relief', None), ('roughness', 360), ('roughness', 720)],
                             ['Elevación', 'Rugosidad · 360 m', 'Rugosidad · 720 m']):
        ax.imshow(coast_maps[key], cmap=ListedColormap(colors), vmin=0, vmax=2,
                  interpolation='nearest', extent=(-1.5, 1.5, -1.5, 1.5))
        ax.set(title=title, xlabel='km', xticks=[-1, 0, 1], yticks=[-1, 0, 1])
    axes[0].set_ylabel('km')
    figure.legend(handles=[Patch(color=c, label=t) for c, t in zip(colors,
                  ['Fuera de la máscara de tierra', 'Tierra con soporte insuficiente', 'Soporte común'])],
                  loc='outside lower center', ncol=3, frameon=False, fontsize=9)
    figure.suptitle('Costa de Carolina · soporte por descriptor con máscara de tierra del 95 %', fontweight='bold')
    figure.savefig(OUT / 'soporte-costero.png', dpi=180)
    plt.close(figure)


def main():
    spec = json.loads(SPEC.read_text())
    utah = json.loads(UTAH.read_text())
    results = {'desierto-utah': {'label': 'Utah · desierto', 'primary_policy': 'sin_mascara',
                                'measurements': utah['measurements'], 'inputs': utah['inputs']}}
    coast_maps = {}
    for key, site in spec['sites'].items():
        grids, cover, metadata = prepare(site)
        check = reference_sensitivity(grids, cover, site['primary_policy']) if '3DEP_13' in grids[30] else None
        for dem in grids.values():
            dem.pop('3DEP_13', None)
        rows, maps = profile(grids, cover, site['environment'] == 'coast')
        base_control = matched_slope_bases(grids, cover, site['primary_policy'])
        coast_maps.update(maps)
        results[key] = {'label': site['label'], 'center_lon_lat': site['center_lon_lat'],
                        'primary_policy': site['primary_policy'], 'measurements': rows,
                        'land_cover': cover_summary(cover), 'inputs': metadata,
                        'reference_sensitivity': check, 'matched_slope_bases_30m_3km': base_control}
        print(key, len(rows), flush=True)
    OUT.mkdir(exist_ok=True)
    terrain.write_json(OUT / 'resultados.json', results)
    plot_source_effect(results, coast_maps)
    files = [SPEC, UTAH, Path(__file__).resolve(), Path(trial.__file__), Path(terrain.__file__),
             ROOT / 'scripts/analizar_dimensiones.py', ROOT / 'scripts/explorar_fuentes_atlas.py',
             OUT / 'resultados.json', OUT / 'diferencias-por-ambiente.png', OUT / 'soporte-costero.png']
    terrain.write_json(OUT / 'manifest.json', {'files': [
        {'path': str(p.relative_to(ROOT)), 'sha256': terrain.digest(p)} for p in files]})


if __name__ == '__main__':
    main()
