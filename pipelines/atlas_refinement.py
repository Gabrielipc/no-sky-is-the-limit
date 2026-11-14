"""Exact ranking and three geographic case files for a published 30 m release."""
import json
from contextlib import ExitStack

import matplotlib.pyplot as plt
import numpy as np
from pyproj import Geod
from scipy.stats import wasserstein_distance

from backend.app import atlas_store as store
from pipelines import atlas_sources as sources, atlas_topography as topo

GEOD = Geod(ellps='WGS84')


def compare(candidate, candidate_arrays, profile, profile_arrays, scales):
    if candidate['relief_m'] is None:
        return None
    a, b = (arrays['slope'][np.isfinite(arrays['slope'])] for arrays in (candidate_arrays, profile_arrays))
    distances = [float(wasserstein_distance(a, b)), abs(candidate['relief_m'] - profile['relief_m']),
                 abs(candidate['roughness_m'] - profile['roughness_m'])]
    return {**dict(zip(store.DISTANCES, distances)),
            'distance': sum(weight / sum(store.DEFAULT_WEIGHTS) * value / scales[key]
                            for weight, key, value in zip(store.DEFAULT_WEIGHTS, store.DISTANCES, distances))}


def map_comparison(path, profile_arrays, candidate_arrays):
    figure, axes = plt.subplots(2, 2, figsize=(7, 6), layout='constrained')
    for column, (metric, unit, color) in enumerate([('slope', '°', 'magma'), ('roughness', 'm', 'viridis')]):
        vmax = max(float(np.nanpercentile(arrays[metric], 98)) for arrays in (profile_arrays, candidate_arrays))
        for row, (label, arrays) in enumerate([('Jezero', profile_arrays), ('Candidata terrestre', candidate_arrays)]):
            image = axes[row, column].imshow(arrays[metric], vmin=0, vmax=max(vmax, 1e-5),
                                             cmap=color, extent=(-1.5, 1.5, -1.5, 1.5))
            axes[row, column].set(title=f'{label} · {"pendiente" if column == 0 else "rugosidad"}',
                                  xlabel='km', ylabel='km')
        figure.colorbar(image, ax=axes[:, column], label=unit)
    figure.suptitle('Comparación a 30 m · escala de color compartida por métrica')
    figure.savefig(path, dpi=125)
    plt.close(figure)


def source_contrast(site, land, rasters, profile, profile_arrays, scales):
    base = json.loads(topo.terrain.DEFAULT_CONFIG.read_text())
    half = topo.WINDOW // 2 + topo.HALO
    bounds = topo.geographic_boxes(site['zone'], (site['x'] - half, site['y'] - half,
                                                  site['x'] + half, site['y'] + half))
    local = {}
    for control in base['sites'][1:]:
        if (sources.ROOT / control['input']).is_file():
            local[control['product_id']] = control
    entries = {}
    for lat, lon in topo.tile_keys(bounds, 1):
        if not -56 <= lat < 60:
            continue
        key = f'{"N" if lat >= 0 else "S"}{abs(lat):02}{"E" if lon >= 0 else "W"}{abs(lon):03}.tif'
        url = 'https://opentopography.s3.sdsc.edu/raster/SRTM_GL1/SRTM_GL1_srtm/' + key
        if key in local:
            path = topo.terrain.acquire(local[key], False)
            if key not in rasters.opened:
                rasters.opened[key] = rasters.stack.enter_context(topo.rasterio.open(path))
        elif rasters.mode == 'cache':
            continue
        entries[(lat, lon)] = sources.asset('srtm', key, url)
    if entries:
        try:
            row, arrays = topo.measure(site, land, rasters, entries)
        except OSError:
            row = {'status': 'dem_unavailable', 'asset_ids': []}
        if row['status'] == 'rankable':
            return {'product': 'SRTM GL1', 'status': row['status'],
                    'assets': [rasters.identities.get(key, {k: local[key][k] for k in ('url', 'sha256')})
                               if key in local else rasters.identities[key] for key in row['asset_ids']],
                    'distances': compare(row, arrays, profile, profile_arrays, scales)}
    return {'status': 'unavailable', 'reason': 'El contraste SRTM no tiene cobertura suficiente en esta ventana.'}


def refine(release, manifest, land, inventory, mode):
    _, ordered = store.search(release, manifest, limit=20)
    if not ordered:
        return
    profile, profile_arrays = topo.reference()
    scales = manifest['normalization']
    with store.connect(release) as db:
        # Best ranked member of each processing area gives candidates for diverse case files.
        areas = db.execute("SELECT DISTINCT area FROM windows WHERE status = 'rankable' ORDER BY area").fetchall()
    _, pool = store.search(release, manifest, limit=min(1000, sum(manifest['counts'].values())))
    primary = {row['region_id'] for row in ordered}
    robustness = {}
    for name, weights in {'slope_relief': (50, 50, 0), 'equal_weights': (1, 1, 1)}.items():
        _, alternative = store.search(release, manifest, weights=weights, limit=20)
        robustness[name] = {'weights': weights, 'top20_overlap': len(primary & {row['region_id'] for row in alternative})}
    sources.atomic_json(release / 'ranking-sensitivity.json', robustness)
    cohort = []
    for rank, row in enumerate(pool, 1):
        if all(abs(GEOD.inv(row['longitude'], row['latitude'], old['longitude'], old['latitude'])[2]) >= 100000
               for _, old in cohort):
            cohort.append((rank, row))
        if len(cohort) == 3:
            break
    if len(cohort) < 3 and len(areas) > 1:
        for (area,) in areas:
            if any(row['area'] == area for _, row in cohort):
                continue
            # The fallback reads a single area's shortlist without materializing the full index.
            _, local = store.search(release, manifest, limit=1, area=area)
            if local and all(abs(GEOD.inv(local[0]['longitude'], local[0]['latitude'], row['longitude'], row['latitude'])[2])
                             >= 100000 for _, row in cohort):
                cohort.append((None, local[0]))
            if len(cohort) == 3:
                break
    directory = release / 'expedients'
    directory.mkdir()
    recomputed = {}
    exact = []
    with ExitStack() as stack:
        stack.enter_context(topo.rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN='EMPTY_DIR',
                                               GDAL_HTTP_TIMEOUT=30, GDAL_HTTP_MAX_RETRY=2,
                                               GDAL_CACHEMAX=128 * 1024**2))
        rasters = topo.Rasters(stack, mode)
        for rank, row in [*enumerate(ordered, 1), *cohort]:
            key = row['region_id']
            if key in recomputed:
                continue
            site = store.candidate(release, key)
            measured, arrays = topo.measure(site, land, rasters, inventory)
            result = compare(measured, arrays, profile, profile_arrays, scales)
            recomputed[key] = (site, arrays, result)
            if rank and rank <= len(ordered):
                exact.append({'region_id': key, 'initial_rank': rank, 'status': measured['status'], 'exact': result})
        exact.sort(key=lambda row: (row['exact'] is None, row['exact']['distance'] if row['exact'] else 0, row['region_id']))
        for rank, row in enumerate((row for row in exact if row['exact']), 1):
            row['refined_rank'] = rank
        sources.atomic_json(release / 'refinement.json', exact)
        for initial_rank, row in cohort:
            key = row['region_id']
            site, arrays, exact_result = recomputed[key]
            if exact_result is None:
                continue
            case = directory / key
            case.mkdir()
            sensitivity = []
            for cell in (60, 120):
                other_profile, other_reference = topo.reference(cell)
                measured, other = topo.measure(site, land, rasters, inventory, cell=cell)
                sensitivity.append({'cell_m': cell, 'status': measured['status'],
                                    'comparison': compare(measured, other, other_profile, other_reference, scales)})
            map_comparison(case / 'terrain.png', profile_arrays, arrays)
            signed = {'slope_p50_deg': site['slope_p50_deg'] - profile['slope_p50_deg'],
                      'relief_m': site['relief_m'] - profile['relief_m'],
                      'roughness_m': site['roughness_m'] - profile['roughness_m']}
            sources.atomic_json(case / 'case.json', {
                'region_id': key, 'latitude': row['latitude'], 'longitude': row['longitude'], 'area': row['area'],
                'initial_rank': initial_rank, 'cell_m': 30, 'exact': exact_result, 'signed_differences': signed,
                'sensitivity': sensitivity, 'source_contrast': source_contrast(site, land, rasters, profile, profile_arrays, scales),
                'sources': {'earth': site['asset_ids'], 'mars': profile['product']},
                'potential_use': 'Comparar distribuciones de pendiente y relieve en ventanas de 3 km para elegir sitios de ensayo topográfico.',
                'limitations': ['Copernicus representa la superficie e incluye vegetación y construcciones donde estén presentes.',
                                'La malla de 30 m no iguala la resolución efectiva de los sensores.',
                                'El ranking no mide composición, procesos geológicos ni transitabilidad.',
                                'La validación independiente de esta candidata está pendiente.'],
                'map': 'terrain.png'})
