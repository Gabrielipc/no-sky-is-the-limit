#!/usr/bin/env python3
"""Surface feature pilot with native support and explicit QA experiments."""
import json
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path

import h5py
import numpy as np
import rasterio
import shapely
from pyproj import CRS, Transformer
from rasterio.transform import from_origin
from rasterio.warp import Resampling, reproject
from shapely import affinity
from shapely.geometry import mapping, shape
from shapely.ops import transform

import analizar_minerales as emit
import analizar_primer_caso as terrain
import explorar_fuentes_atlas as eda

ROOT = eda.ROOT
OUT = ROOT / 'docs/evidencia-armonizacion-superficie'
EXPLORATION = ROOT / 'docs/exploracion-fuentes-v1'
COAST_SPEC = ROOT / 'specs/analysis/validacion-armonizacion-topografica.json'
JRC_COAST = ROOT / 'specs/sources/jrc-costa-carolina-v1.json'
MATERIAL_SPEC = ROOT / 'specs/analysis/minerales-emit-v1.json'
MARS_SPEC = ROOT / 'specs/analysis/primer-caso-fase2.json'
WINDOW_M = 3000
PILOT_FRACTION = .80
MIN_EMIT_SAMPLES = 30


def earth_crs(center, projection='laea'):
    lon, lat = center
    return CRS.from_proj4(f'+proj={projection} +lon_0={lon} +lat_0={lat} +datum=WGS84 +units=m')


def target_grid(cell):
    half = WINDOW_M / 2
    return from_origin(-half, half, cell, cell), (WINDOW_M // cell,) * 2


def projected_polygon(geometry, source, target):
    project = Transformer.from_crs(source, target, always_xy=True).transform
    return transform(project, shape(geometry))


def intersected_areas(dataset, window, geometry, center):
    """Intersect native pixel polygons in a local equal-area projection."""
    target = earth_crs(center, 'laea')
    footprint = projected_polygon(geometry, 'EPSG:4326', target)
    transform_px = dataset.window_transform(window)
    r, c = np.mgrid[:int(window.height), :int(window.width)]
    project = Transformer.from_crs(dataset.crs, target, always_xy=True).transform
    corners = []
    for dx, dy in ((0, 0), (1, 0), (1, 1), (0, 1)):
        x, y = transform_px * ((c + dx).ravel(), (r + dy).ravel())
        corners.append(np.column_stack(project(x, y)))
    pixels = shapely.polygons(np.stack(corners, axis=1))
    areas = shapely.area(shapely.intersection(pixels, footprint)).reshape(r.shape)
    return areas, footprint.area


def area_summary(values, areas, footprint_area, source):
    valid = np.isfinite(values) & (areas > 0)
    supported = float(areas[valid].sum())
    result = {'footprint_m2': footprint_area, 'valid_area_m2': supported,
              'valid_fraction': supported / footprint_area}
    if not supported:
        return {**result, 'values': None}
    if source == 'worldcover':
        summary = {str(code): float(areas[valid & (values == code)].sum() / supported)
                   for code in eda.WORLD_CODES}
    else:
        summary = {'mean_occurrence_pct': float(np.average(values[valid], weights=areas[valid])),
                   'area_fraction_occurrence_gt0': float(areas[valid & (values > 0)].sum() / supported),
                   'area_fraction_occurrence_ge50': float(areas[valid & (values >= 50)].sum() / supported)}
    return {**result, 'values': summary}


def static_features():
    coast = json.loads(COAST_SPEC.read_text())['sites']['costa-carolina']
    centers = {**eda.CENTERS, 'costa-carolina': coast['center_lon_lat']}
    records = [r for r in json.loads((EXPLORATION / 'perfiles-espaciales.json').read_text())
               if r['source'] in ('worldcover', 'jrc')]
    records.append({'site': 'costa-carolina', 'source': 'worldcover', 'path': coast['assets']['WorldCover']['path']})
    records.append({'site': 'costa-carolina', 'source': 'jrc', 'path': json.loads(JRC_COAST.read_text())['path']})
    by_site_source = {(r['site'], r['source']): r for r in records}
    if len(by_site_source) != len(records):
        raise ValueError('Overlapping static assets require a mosaic with explicit precedence')
    results = []
    for site, center in centers.items():
        geometry = eda.aoi(*center, side=WINDOW_M)
        for source in ('worldcover', 'jrc'):
            key = (site, source)
            row = {'site': site, 'source': source, 'window_m': WINDOW_M, 'center_lon_lat': center}
            if key not in by_site_source:
                results.append({**row, 'status': 'missing_local_asset', 'area_weighted': None})
                continue
            path = by_site_source[key]['path']
            with rasterio.open(ROOT / path) as dataset:
                window, _ = eda.native_crop(dataset, geometry)
                native = eda.read_crop(dataset, 1, window)
                values = eda.physical(native, source, '')
                areas, footprint = intersected_areas(dataset, window, geometry, center)
                affine, grid_shape = target_grid(30)
                nearest = np.full(grid_shape, np.nan)
                reproject(values, nearest, src_transform=dataset.window_transform(window),
                          src_crs=dataset.crs, src_nodata=np.nan, dst_transform=affine,
                          dst_crs=earth_crs(center), dst_nodata=np.nan, resampling=Resampling.nearest)
            equal_weights = np.full(nearest.shape, footprint / nearest.size)
            results.append({**row, 'status': 'measured', 'path': path,
                            'area_weighted': area_summary(values, areas, footprint, source),
                            'nearest_30m': area_summary(nearest, equal_weights, footprint, source),
                            'out_of_domain_area_m2': float(areas[np.isfinite(native) & ~np.isfinite(values)].sum())})
    return results


def scene_arrays(paths, geometry):
    arrays = []
    reference = None
    for path in paths:
        with rasterio.open(ROOT / path) as dataset:
            grid = (dataset.crs, dataset.transform, dataset.shape)
            if reference is None:
                reference = grid
                window, inside = eda.native_crop(dataset, geometry)
                affine = dataset.window_transform(window)
            elif grid != reference:
                raise ValueError(f'Scene bands do not share a grid: {path}')
            arrays.append(eda.read_crop(dataset, 1, window))
    return arrays, inside, affine, reference[0]


def normalized_difference(a, b, valid, min_sum):
    support = valid & np.isfinite(a) & np.isfinite(b) & (a >= 0) & (b >= 0) & (a + b >= min_sum)
    return np.divide(a - b, a + b, where=support, out=np.full(a.shape, np.nan))


def hls_feature(arrays, inside, scene):
    green, red, nir, swir = [eda.physical(a, 'hls', 'reflectance') for a in arrays[:4]]
    qa = arrays[4]
    bits = np.nan_to_num(qa, nan=255).astype(np.uint16)
    clear_land = eda.hls_mask(qa, 'clear') & ((bits & 32) == 0)
    policies = {}
    selected_arrays = {}
    for min_sum, remove_high in ((.001, False), (.01, False), (.01, True)):
        masks = {'ndsi': clear_land, 'ndvi': clear_land & ((bits & 16) == 0),
                 'ndmi': clear_land & ((bits & 16) == 0)}
        values = {}
        for name, a, b in (('ndvi', nir, red), ('ndmi', nir, swir), ('ndsi', green, swir)):
            valid = inside & masks[name]
            if remove_high:
                valid &= (bits >> 6) != 3
            values[name] = normalized_difference(a, b, valid, min_sum)
        policies[f'{min_sum:g}_' + ('exclude_high_aerosol' if remove_high else 'all_aerosol')] = {
            name: eda.stats(a[inside], int(inside.sum())) for name, a in values.items()}
        if min_sum == .01 and remove_high:
            selected_arrays = values
    date = datetime.strptime(scene.split('.')[3], '%Y%jT%H%M%S').replace(tzinfo=timezone.utc)
    snow = inside & clear_land & ((bits & 16) != 0)
    return {'datetime_utc': date.isoformat(), 'sensor_family': scene.split('.')[1],
            'qa_snow_clear_centers': int(snow.sum()), 'policies': policies}, selected_arrays


def landsat_feature(arrays, inside, affine, crs, center):
    raw, qa, st_qa = arrays
    temp = eda.physical(raw, 'landsat', 'ST_B10')
    uncertainty = eda.physical(st_qa, 'landsat', 'ST_QA')
    bits = np.nan_to_num(qa, nan=1).astype(np.uint16)
    land = eda.landsat_mask(qa, keep_snow=True) & ((bits & 128) == 0)
    valid = land & np.isfinite(temp) & np.isfinite(uncertainty)
    output, size = target_grid(120)
    parameters = dict(src_transform=affine, src_crs=crs, dst_transform=output,
                      dst_crs=earth_crs(center), resampling=Resampling.average, num_threads=1)
    policies = {}
    for limit in (None, 2, 3, 4):
        eligible = valid if limit is None else valid & (uncertainty <= limit)
        support = np.zeros(size, dtype=float)
        aggregate = np.full(size, np.nan)
        reproject(eligible.astype(float), support, **parameters)
        reproject(np.where(eligible, temp, np.nan), aggregate, src_nodata=np.nan, dst_nodata=np.nan, **parameters)
        policies['unlimited' if limit is None else str(limit)] = {
            'mean_observed_fraction': float(support.mean()),
            'native': eda.stats(temp[eligible & inside], int(inside.sum())),
            'uncertainty_native_k': eda.stats(uncertainty[eligible & inside], int(inside.sum())),
            'aggregated_120m': {str(f): eda.stats(aggregate[support >= f - 1e-9], aggregate.size)
                                for f in (.5, .75, .95)}}
    return policies


def temporal_features():
    records = json.loads((EXPLORATION / 'perfiles-temporales.json').read_text())
    output = []
    matched = []
    for row in records:
        record = {k: row[k] for k in ('site', 'source', 'scene')}
        if row['status'] != 'profiled':
            output.append({**record, 'status': row['status']})
            continue
        center = eda.CENTERS[row['site']]
        arrays, inside, affine, crs = scene_arrays(row['paths'], eda.aoi(*center, side=WINDOW_M))
        record.update(paths=row['paths'], status='measured', window_m=WINDOW_M, center_lon_lat=center)
        if row['source'] == 'hls':
            profile, values = hls_feature(arrays, inside, row['scene'])
            record.update(profile)
            matched.append((record, values, affine, crs))
        else:
            record.update(acquisition_date=datetime.strptime(row['scene'].split('_')[3], '%Y%m%d').date().isoformat(),
                          policies=landsat_feature(arrays, inside, affine, crs, center))
        output.append(record)
    pairs = []
    for (a, av, at, ac), (b, bv, bt, bc) in combinations(matched, 2):
        if (a['site'] != b['site'] or a['datetime_utc'][:10] != b['datetime_utc'][:10]
                or a['sensor_family'] == b['sensor_family'] or (at, ac) != (bt, bc)):
            continue
        pairs.append({'site': a['site'], 'scenes': [a['scene'], b['scene']],
                      'seconds_apart': abs((datetime.fromisoformat(a['datetime_utc'])
                                            - datetime.fromisoformat(b['datetime_utc'])).total_seconds()),
                      'paired_absolute_differences': {k: eda.stats(np.abs(av[k] - bv[k])) for k in av}})
    return output, pairs


def emit_family_name(entry):
    label = entry['label'].split(' · ')[0]
    if label != entry['name']:
        return label
    lower = entry['name'].lower()
    if lower.startswith('organic_'):
        return 'Orgánico o sintético'
    if 'aragonite' in lower:
        return 'Aragonito'
    if 'nacrite' in lower:
        return 'Caolinita'
    if 'beidellite' in lower:
        return 'Esmectita'
    if 'lepidolite' in lower or 'margarite' in lower:
        return 'Mica'
    if 'sioh_' in lower:
        return 'Sílice o vidrio hidratado'
    return label


def aggregate_emit_families(counts_by_id, classes):
    by_id = {str(c['id']): emit_family_name(c) for c in classes}
    aggregated = {}
    for code, count in counts_by_id.items():
        family = by_id.get(str(code), str(code))
        aggregated[family] = aggregated.get(family, 0) + int(count)
    return aggregated


def shannon_entropy_bits(counts_dict):
    total = sum(counts_dict.values())
    if total <= 0:
        return None
    probs = [c / total for c in counts_dict.values() if c > 0]
    return float(-sum(p * np.log2(p) for p in probs))


def emit_features():
    rows = []
    cfg = json.loads(MATERIAL_SPEC.read_text())
    for scene in cfg['scenes']:
        site = 'desierto' if scene['site_id'] == 'earth-utah' else 'atacama-materiales'
        for width in (1800, WINDOW_M):
            geometry = eda.aoi(*eda.CENTERS[site], side=width)
            profile = emit.read_scene(scene, geometry)
            with h5py.File(ROOT / scene['mineral']['input']) as ds:
                ix, iy, inside, _, _ = emit.crop_glt(ds, geometry)
                height, columns = ds['group_1_mineral_id'].shape
            valid = inside & (ix > 0) & (iy > 0) & (ix <= columns) & (iy <= height)
            locations = np.flatnonzero(valid)
            keys = (iy.ravel()[locations] - 1) * columns + ix.ravel()[locations] - 1
            _, first = np.unique(keys, return_index=True)
            unique = locations[first]
            if len(unique) != profile['unique_raw_samples']:
                raise ValueError('Inconsistent EMIT sample identity count')
            groups = {}
            for name, group in profile['groups'].items():
                ids, depth, fit, uncertainty = [np.asarray(group[k], dtype=float) for k in ('ids', 'depth', 'fit', 'uncertainty')]
                usable = np.asarray(group['usable'], dtype=bool)
                masks = {'available_match': usable,
                         'depth_gt_2sigma_only': usable & (depth > 2 * uncertainty),
                         'fit_0.8_only': usable & (2 * fit >= .8),
                         'fit_0.9_only': usable & (2 * fit >= .9)}
                for minimum in (.5, .8, .9):
                    masks[str(minimum)] = usable & (2 * fit >= minimum) & (depth > 2 * uncertainty)
                sensitivity = {}
                for policy, selected in masks.items():
                    selected_unique = unique[selected[unique]]
                    counts_u = eda.counts(ids[selected_unique])
                    counts_fam = aggregate_emit_families(counts_u, group['classes'])
                    sensitivity[policy] = {'mapped_cells': int(selected.sum()), 'unique_samples': len(selected_unique),
                        'counts_unique': counts_u, 'counts_mapped': eda.counts(ids[selected]),
                        'family_counts_unique': counts_fam,
                        'library_entropy_bits': shannon_entropy_bits(counts_u),
                        'family_entropy_bits': shannon_entropy_bits(counts_fam),
                        'band_depth_unique': eda.stats(depth[selected_unique]), 'fit_restored_unique': eda.stats(2 * fit[selected_unique])}
                groups[name] = {'sample_ids_valid': int(np.isfinite(ids[unique]).sum()),
                                'no_match_unique': int((ids[unique] == 0).sum()),
                                'classes': group['classes'], 'sensitivity': sensitivity}
            rows.append({'site': site, 'scene': profile['product_id'], 'date': profile['date'], 'window_m': width,
                         'glt_cells': profile['glt_cells'], 'footprint_centers': profile['footprint_cells'],
                         'unique_source_samples': len(unique), 'paths': [a['input'] for a in profile['sources']],
                         'groups': groups})
    return rows


def mars_features():
    cfg = json.loads(MARS_SPEC.read_text())
    site = cfg['sites'][0]
    sr = 'data/raw/crism/frt000047a3/frt000047a3_07_sr166j_mtr3.img'
    info = sr.replace('_sr', '_in')
    themis = 'data/raw/themis/Jezero_Thermal_Inertia_v1.tiff'
    indicators = ('OLINDEX3', 'BD530_2', 'D2300', 'MIN2295_2480', 'BD1900R2')
    thermal_rows, mineral_rows = [], []
    with rasterio.open(ROOT / sr) as values, rasterio.open(ROOT / info) as masks, rasterio.open(ROOT / themis) as inertia:
        if (values.crs, values.transform, values.shape) != (masks.crs, masks.transform, masks.shape):
            raise ValueError('CRISM science and mask grids differ')
        for width in (1800, WINDOW_M):
            feature = terrain.geometry(site, {'window_m': width})
            geom, crs = feature['geometry'], feature['properties']['crs_wkt']
            window, inside = eda.native_crop(values, geom, crs)
            qa = eda.read_crop(masks, 9, window)
            n = int(inside.sum())
            in_swath = int(np.isfinite(qa[inside]).sum())
            masked = inside & (qa == 0)
            summaries = {}
            for name in indicators:
                a = eda.read_crop(values, values.descriptions.index(name) + 1, window)
                summaries[name] = {
                    'mask_0': eda.stats(a[masked], n),
                    'raster_valid_only': eda.stats(a[inside], n),
                    'in_swath_mask_0': eda.stats(a[masked], in_swath),
                }
            mineral_rows.append({'site': site['id'], 'window_m': width, 'paths': [sr, info],
                                 'footprint_centers': n, 'in_swath_centers': in_swath,
                                 'outside_swath_centers': n - in_swath,
                                 'qa_counts': eda.counts(qa[inside]),
                                 'mask_comparison_note': 'non_informative: SR nodata (65535) already coincides with IN!=0 in these crops',
                                 'indicators': summaries})
            native_polygon = projected_polygon(geom, crs, inertia.crs)
            for dx, dy in ((0, 0), (-100, 0), (100, 0), (0, -100), (0, 100)):
                moved = mapping(affinity.translate(native_polygon, xoff=dx, yoff=dy))
                crop, selected = eda.native_crop(inertia, moved, inertia.crs)
                a = eda.read_crop(inertia, 1, crop)[selected]
                a[a <= 0] = np.nan
                profile = eda.stats(a, int(selected.sum()))
                valid = a[np.isfinite(a)]
                profile['iqr'] = float(np.diff(np.percentile(valid, [25, 75]))[0]) if len(valid) else None
                thermal_rows.append({'site': site['id'], 'window_m': width, 'path': themis,
                                     'offset_native_m': [dx, dy], 'grid_step_m': list(inertia.res),
                                     'inertia': profile})
    return mineral_rows, thermal_rows


def verify_inputs(results):
    known = {item['path']: item for item in json.loads((EXPLORATION / 'identidades-entradas.json').read_text())}
    coast = json.loads(COAST_SPEC.read_text())['sites']['costa-carolina']['assets']['WorldCover']
    known[coast['path']] = coast
    jrc = json.loads(JRC_COAST.read_text())
    known[jrc['path']] = jrc
    paths = set()
    for rows in results.values():
        for row in rows:
            if 'path' in row:
                paths.add(row['path'])
            paths.update(row.get('paths', []))
    for path in list(paths):
        if path.startswith('data/raw/crism/'):
            paths.update(str(Path(path).with_suffix(suffix)) for suffix in ('.hdr', '.lbl'))
    identities = []
    for path in sorted(paths):
        expected = known[path]
        file = ROOT / path
        if (file.stat().st_size, eda.digest(file)) != (expected['bytes'], expected['sha256']):
            raise ValueError(f'Input differs from the recorded snapshot: {path}')
        identities.append({key: expected[key] for key in ('path', 'bytes', 'sha256')})
    return identities


def select_pilot_values(results):
    """Materialize the proposed shortlist with explicit nulls and provenance."""
    records = []

    def add(row, name, value, unit, role, support, source, *, status=None, **details):
        records.append({'site': row['site'], 'window_m': row.get('window_m', WINDOW_M),
                        'body': 'Mars' if source in ('themis', 'crism') else 'Earth',
                        'feature_id': name, 'unit': unit, 'role': role, 'source': source,
                        'value': value, 'status': status or ('measured' if value is not None else 'no_support'),
                        'support': support, **details})

    for row in results['cover_and_water']:
        data = row['area_weighted']
        support = {k: data[k] for k in ('valid_fraction', 'valid_area_m2', 'footprint_m2')} if data else None
        adequate = data is not None and data['valid_fraction'] >= PILOT_FRACTION
        values = data['values'] if adequate else {}
        status = row['status'] if data is None else 'measured' if adequate else 'insufficient_coverage'
        if row['source'] == 'worldcover':
            names = [('trees', 10), ('built', 50), ('bare_or_sparse', 60), ('permanent_water', 80)]
            for label, code in names:
                add(row, f'worldcover_{label}_area_fraction', values.get(str(code)), 'fraction', 'earth_filter',
                    support, 'worldcover', status=status, period='2021', path=row.get('path'), source_nominal_m=10)
        else:
            add(row, 'jrc_occurrence_mean_pct', values.get('mean_occurrence_pct'), 'percent', 'earth_context',
                support, 'jrc', status=status, period='1984–2024', path=row.get('path'), source_nominal_m=30)

    optical_days = {}
    for row in results['optical_and_landsat']:
        if row['status'] != 'measured':
            name, unit = ('hls_ndvi_p50', '1') if row['source'] == 'hls' else ('landsat_lst_p50_k', 'K')
            add(row, name, None, unit, 'earth_context', None, row['source'], status=row['status'])
        elif row['source'] == 'hls':
            optical_days.setdefault((row['site'], row['datetime_utc'][:10]), []).append(row)
        else:
            policy = row['policies']['3']
            stats = policy['aggregated_120m']['0.75']
            good = stats['valid_fraction'] >= PILOT_FRACTION
            add(row, 'landsat_lst_p50_k', stats['p50'] if good else None, 'K', 'earth_context',
                {'accepted_cells': stats['n'], 'total_cells': stats['denominator'],
                 'valid_fraction': stats['valid_fraction'], 'mean_observed_fraction': policy['mean_observed_fraction'],
                 'st_qa_p50_k': policy['uncertainty_native_k']['p50']}, 'landsat',
                status='measured' if good else 'insufficient_coverage', date=row['acquisition_date'],
                scene=row['scene'], paths=row['paths'], sensor_sampling_nominal_m=100, analysis_cell_m=120)
    for (site, date), alternatives in sorted(optical_days.items()):
        policy = '0.01_exclude_high_aerosol'
        chosen = min(alternatives, key=lambda row: (-row['policies'][policy]['ndvi']['valid_fraction'], row['datetime_utc'], row['scene']))
        stats = chosen['policies'][policy]['ndvi']
        good = stats['valid_fraction'] >= PILOT_FRACTION
        add(chosen, 'hls_ndvi_p50', stats['p50'] if good else None, '1', 'earth_context',
            {'valid_centers': stats['n'], 'total_centers': stats['denominator'], 'valid_fraction': stats['valid_fraction']},
            'hls', status='measured' if good else 'insufficient_coverage', date=date,
            datetime_utc=chosen['datetime_utc'], scene=chosen['scene'], alternatives=[r['scene'] for r in alternatives],
            paths=chosen['paths'], analysis_cell_m=30)

    for row in results['themis']:
        if row['offset_native_m'] != [0, 0]:
            continue
        stats = row['inertia']
        good = stats['valid_fraction'] is not None and stats['valid_fraction'] >= PILOT_FRACTION
        support = {'valid_centers': stats['n'], 'total_centers': stats['denominator'], 'valid_fraction': stats['valid_fraction']}
        for field in ('p50', 'iqr'):
            add(row, f'themis_thermal_inertia_{field}', stats[field] if good else None, 'J m^-2 K^-1 s^-1/2', 'mars_context',
                support, 'themis', status='measured' if good else 'insufficient_coverage',
                path=row['path'], native_grid_m=row['grid_step_m'])

    for row in results['crism']:
        for name, values in row['indicators'].items():
            stats = values['mask_0']
            good = stats['valid_fraction'] is not None and stats['valid_fraction'] >= PILOT_FRACTION
            swath = values['in_swath_mask_0']
            support = {'valid_centers': stats['n'], 'total_centers': stats['denominator'],
                       'valid_fraction': stats['valid_fraction'],
                       'in_swath_centers': row['in_swath_centers'],
                       'outside_swath_centers': row['outside_swath_centers'],
                       'in_swath_valid_fraction': swath['valid_fraction']}
            for stat_key in ('p95', 'p50'):
                add(row, f'crism_{name.lower()}_{stat_key}', stats[stat_key] if good else None, '1', 'spectral_evidence',
                    support, 'crism', status='measured' if good else 'insufficient_coverage',
                    unmasked_p95=stats['p95'], unmasked_p50=stats['p50'],
                    paths=row['paths'], source_nominal_m=18)

    for row in results['emit']:
        for group, details in row['groups'].items():
            for policy in ('0.8', '0.9'):
                scenario = details['sensitivity'][policy]
                n = scenario['unique_samples']
                status = 'no_support' if n == 0 else 'insufficient_sample' if n < MIN_EMIT_SAMPLES else 'measured'
                keep = status == 'measured'
                fractions_id = {code: count / n for code, count in scenario['counts_unique'].items()} if keep else None
                fractions_fam = {fam: count / n for fam, count in scenario['family_counts_unique'].items()} if keep else None
                support = {'qualified_unique_samples': n, 'unique_glt_samples': row['unique_source_samples'],
                           'measured_unique_samples': details['sample_ids_valid'], 'no_match_unique': details['no_match_unique'],
                           'library_entropy_bits': scenario['library_entropy_bits'],
                           'family_entropy_bits': scenario['family_entropy_bits']}
                common = dict(status=status, scene=row['scene'], date=row['date'], spectral_group=int(group),
                              fit_min=float(policy), minimum_depth_to_uncertainty=2, classes=details['classes'],
                              paths=row['paths'], source_nominal_m=60)
                add(row, 'emit_mineral_family_fraction', fractions_fam, 'fraction', 'spectral_evidence',
                    support, 'emit', **common)
                add(row, 'emit_library_match_fraction', fractions_id, 'fraction', 'spectral_evidence',
                    support, 'emit', **common)
    return {'version': 1, 'pilot_quality_thresholds': {'minimum_window_fraction': PILOT_FRACTION,
            'hls_min_band_sum': .01, 'hls_exclude_high_aerosol': True,
            'landsat_max_st_qa_k': 3, 'landsat_min_cell_support': .75,
            'emit_min_qualified_samples': MIN_EMIT_SAMPLES}, 'records': records}


def plot_quality(temporal):
    from matplotlib import pyplot as plt

    figure, (optical, thermal) = plt.subplots(1, 2, figsize=(11, 4.9), layout='constrained')
    styles = [('desierto', 'Desierto', '#b8782a'), ('montana', 'Montaña', '#6b56a7'),
              ('costa', 'Costa', '#167b70'), ('tropico', 'Trópico', '#2879ac')]
    for site, label, color in styles:
        hls = [r for r in temporal if r['site'] == site and r['source'] == 'hls' and r['status'] == 'measured']
        dates = [datetime.fromisoformat(r['datetime_utc']) for r in hls]
        fractions = [100 * r['policies']['0.01_exclude_high_aerosol']['ndvi']['valid_fraction'] for r in hls]
        optical.scatter(dates, fractions, label=label, color=color, s=32)
        landsat = [r for r in temporal if r['site'] == site and r['source'] == 'landsat' and r['status'] == 'measured']
        for index, row in enumerate(landsat):
            coverage = [100 * row['policies'][k]['aggregated_120m']['0.75']['valid_fraction'] for k in ('2', '3', '4', 'unlimited')]
            thermal.plot(range(4), coverage, marker='o' if index == 0 else 's', color=color, alpha=.85)
    optical.set(title='NDVI HLS por fecha', ylabel='Soporte útil en la huella (%)', ylim=(-4, 104))
    optical.tick_params(axis='x', labelrotation=30)
    optical.legend(frameon=False, loc='lower left', fontsize=9)
    thermal.set(title='Temperatura Landsat a 120 m', ylabel='Celdas con ≥75 % de área válida (%)', ylim=(-4, 104),
                xticks=range(4), xticklabels=['≤2 K', '≤3 K', '≤4 K', 'Sin límite'], xlabel='Límite de incertidumbre ST_QA')
    for ax in (optical, thermal):
        ax.grid(axis='y', alpha=.18)
        ax.axhline(100 * PILOT_FRACTION, color='#777777', linestyle='--', linewidth=.9)
        ax.spines[['right', 'top']].set_visible(False)
    figure.suptitle('Soporte por observación en huellas de 3 km', fontweight='bold')
    figure.savefig(OUT / 'soporte-optico-termico.png', dpi=170)
    plt.close(figure)


def main():
    print('Cobertura y agua', flush=True)
    static = static_features()
    print('Óptica y temperatura', flush=True)
    temporal, pairs = temporal_features()
    print('Materiales e inercia térmica', flush=True)
    minerals = emit_features()
    crism, themis = mars_features()
    results = {'cover_and_water': static, 'optical_and_landsat': temporal, 'matched_hls': pairs,
               'emit': minerals, 'crism': crism, 'themis': themis}
    inputs = verify_inputs(results)
    OUT.mkdir(exist_ok=True)
    eda.write(OUT / 'mediciones.json', results)
    eda.write(OUT / 'entradas.json', inputs)
    eda.write(OUT / 'features-piloto.json', select_pilot_values(results))
    plot_quality(temporal)
    files = [Path(__file__), COAST_SPEC, JRC_COAST, MATERIAL_SPEC, MARS_SPEC,
             EXPLORATION / 'identidades-entradas.json', EXPLORATION / 'perfiles-espaciales.json',
             EXPLORATION / 'perfiles-temporales.json', Path(eda.__file__), Path(terrain.__file__),
             Path(emit.__file__), OUT / 'mediciones.json', OUT / 'entradas.json', OUT / 'features-piloto.json',
             OUT / 'soporte-optico-termico.png']
    eda.write(OUT / 'manifest.json', {'files': [
        {'path': str(p.resolve().relative_to(ROOT)), 'sha256': eda.digest(p)} for p in files]})
    print({k: len(v) for k, v in results.items()}, flush=True)


if __name__ == '__main__':
    main()
