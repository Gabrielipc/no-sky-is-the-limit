#!/usr/bin/env python3
"""Offline EMIT classification + quality on the delivered GLT, without interpolation.

Run with bash scripts/ejecutar_minerales.sh after scripts/preparar_minerales.sh.
Originals and earlier scientific releases are read-only inputs.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import platform

import h5py
import numpy as np
import rasterio
from rasterio.features import geometry_mask
from rasterio.transform import Affine
from rasterio.warp import reproject, Resampling
from rasterio.windows import from_bounds

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / 'specs/analysis/minerales-emit-v1.json'


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def verify(path, entry):
    if not Path(path).is_file() or Path(path).stat().st_size != entry['bytes'] or digest(path) != entry['sha256']:
        raise ValueError(f'Identidad de entrada distinta: {Path(path).name}')


def text(value):
    return value.decode('utf-8') if isinstance(value, bytes) else str(value)


def json_array(values):
    return [float(v) if np.isfinite(v) else None for v in np.asarray(values).ravel()]


def apply_glt(raw, ix, iy):
    """Positive one-based indices only; zero means no GLT support, never last row."""
    raw = np.asarray(raw)
    if raw.ndim != 2 or ix.shape != iy.shape:
        raise ValueError('Dimensiones GLT incompatibles')
    if np.any(ix < 0) or np.any(iy < 0):
        raise ValueError('Índices GLT negativos no admitidos')
    good = (ix > 0) & (iy > 0) & (ix <= raw.shape[1]) & (iy <= raw.shape[0])
    out = np.full(ix.shape, np.nan)
    out[good] = raw[iy[good] - 1, ix[good] - 1]
    return out


def read_variable(dataset, ix, iy, inside):
    # Read only the raw rectangle referenced by the small geographic crop.
    good = inside & (ix > 0) & (iy > 0) & (ix <= dataset.shape[1]) & (iy <= dataset.shape[0])
    out = np.full(ix.shape, np.nan)
    if not good.any():
        return out
    left, right = int(ix[good].min()) - 1, int(ix[good].max())
    top, bottom = int(iy[good].min()) - 1, int(iy[good].max())
    raw = dataset[top:bottom, left:right].astype(float)
    for fill in np.asarray(dataset.attrs.get('_FillValue', [])).ravel():
        raw[raw == fill] = np.nan
    raw = raw * float(np.asarray(dataset.attrs.get('scale_factor', 1)).ravel()[0]) + float(np.asarray(dataset.attrs.get('add_offset', 0)).ravel()[0])
    out[good] = raw[iy[good] - 1 - top, ix[good] - 1 - left]
    return out


def crop_glt(file, geometry):
    transform = Affine.from_gdal(*file.attrs['geotransform'])
    if transform.a <= 0 or transform.e >= 0 or transform.b != 0 or transform.d != 0:
        raise ValueError('GLT sin orientación norte-arriba compatible')
    if rasterio.crs.CRS.from_wkt(text(file.attrs['spatial_ref'])) != rasterio.crs.CRS.from_epsg(4326):
        raise ValueError('La GLT no declara WGS84')
    coords = np.asarray(geometry['coordinates'][0])
    window = from_bounds(coords[:, 0].min(), coords[:, 1].min(), coords[:, 0].max(), coords[:, 1].max(), transform)
    left, top = math.floor(window.col_off), math.floor(window.row_off)
    columns, rows = math.ceil(window.col_off + window.width) - left, math.ceil(window.row_off + window.height) - top
    if not 0 < rows * columns <= 100000:
        raise ValueError('Recorte GLT fuera de presupuesto')
    cropped_transform = transform * Affine.translation(left, top)
    inside = geometry_mask([geometry], out_shape=(rows, columns), transform=cropped_transform, invert=True)
    ix, iy = np.zeros((rows, columns), dtype=np.int64), np.zeros((rows, columns), dtype=np.int64)
    full_rows, full_columns = file['location/glt_x'].shape
    l, t, r, b = max(0, left), max(0, top), min(full_columns, left + columns), min(full_rows, top + rows)
    if l < r and t < b:
        ix[t-top:b-top, l-left:r-left] = file['location/glt_x'][t:b, l:r]
        iy[t-top:b-top, l-left:r-left] = file['location/glt_y'][t:b, l:r]
    if np.any((ix < 0) & inside) or np.any((iy < 0) & inside):
        raise ValueError('Índices GLT negativos: revisar convención antes de procesar')
    return ix, iy, inside, cropped_transform, (left, top, columns, rows)


def mineral_label(name, index):
    # Presentation aliases only. Never combine library entries or mixed spectra.
    lower = name.lower()
    known = [('hematite', 'Hematita'), ('goethite', 'Goethita'), ('muscovite', 'Moscovita'), ('illite', 'Illita'),
             ('kaolin', 'Caolinita'), ('calcite', 'Calcita'), ('dolomite', 'Dolomita'), ('gypsum', 'Yeso'),
             ('montmor', 'Montmorillonita'), ('chlorite', 'Clorita'), ('vermicul', 'Vermiculita'),
             ('palygorskite', 'Paligorskita'), ('jarosite', 'Jarosita'), ('nontron', 'Nontronita')]
    aliases = list(dict.fromkeys(label for token, label in known if token in lower))
    label = ' + '.join(aliases) if aliases else name
    if '+' in lower.replace('fe3+', '').replace('fe2+', ''):
        label = 'Mezcla de biblioteca: ' + label
    return f'{label} · {index}'


def read_scene(scene, geometry):
    for key in ('mineral', 'uncertainty'):
        verify(ROOT / scene[key]['input'], scene[key])
    with h5py.File(ROOT / scene['mineral']['input'], 'r') as f, h5py.File(ROOT / scene['uncertainty']['input'], 'r') as u:
        if not np.array_equal(f.attrs['geotransform'], u.attrs['geotransform']) or text(f.attrs['time_coverage_start']) != text(u.attrs['time_coverage_start']):
            raise ValueError('MIN y MINUNCERT no tienen la misma georreferencia/fecha')
        if f['group_1_mineral_id'].shape != u['group_1_fit'].shape:
            raise ValueError('MIN y MINUNCERT tienen dimensiones distintas')
        ix, iy, inside, transform, (left, top, columns, rows) = crop_glt(f, geometry)
        uix, uiy, uinside, _, _ = crop_glt(u, geometry)
        if not np.array_equal(ix, uix) or not np.array_equal(iy, uiy) or not np.array_equal(inside, uinside):
            raise ValueError('MIN y MINUNCERT no comparten la misma GLT')
        table = {int(i): {'id': int(i), 'name': text(name), 'label': mineral_label(text(name), int(i)),
                          'sample': text(sample), 'group': int(group), 'library': text(library)}
                 for i, name, sample, group, library in zip(f['mineral_metadata/index'][:], f['mineral_metadata/name'][:],
                    f['mineral_metadata/sample_name'][:], f['mineral_metadata/group'][:], f['mineral_metadata/library'][:])}
        groups, any_classified = {}, np.zeros(inside.shape, dtype=bool)
        for group in (1, 2):
            ids = read_variable(f[f'group_{group}_mineral_id'], ix, iy, inside)
            positive = ids[np.isfinite(ids) & (ids > 0)]
            if any(int(i) not in table or table[int(i)]['group'] != group for i in np.unique(positive)):
                raise ValueError('Código mineral sin entrada compatible en su biblioteca')
            depth = read_variable(f[f'group_{group}_band_depth'], ix, iy, inside)
            fit = read_variable(u[f'group_{group}_fit'], ix, iy, inside)
            uncertainty = read_variable(u[f'group_{group}_band_depth_unc'], ix, iy, inside)
            matched = (ids > 0) & np.isfinite(depth) & np.isfinite(fit) & np.isfinite(uncertainty) & (depth >= 0) & (uncertainty >= 0)
            any_classified |= matched
            groups[str(group)] = {'ids': [int(v) if np.isfinite(v) else None for v in ids.ravel()],
                                  'depth': json_array(depth), 'fit': json_array(fit), 'uncertainty': json_array(uncertainty),
                                  'usable': matched.ravel().tolist(),
                                  'data_cells': int((np.isfinite(ids) & inside).sum()), 'matched_cells': int(matched.sum()),
                                  'no_match_cells': int(((ids == 0) & inside).sum()),
                                  'classes': [table[int(i)] for i in sorted(np.unique(positive))]}
        shape = f['group_1_mineral_id'].shape
        glt_valid = inside & (ix > 0) & (iy > 0) & (ix <= shape[1]) & (iy <= shape[0])
        return {'product_id': scene['product_id'], 'date': text(f.attrs['time_coverage_start']),
                'rows': rows, 'columns': columns, 'inside': inside.ravel().tolist(),
                'footprint_cells': int(inside.sum()), 'glt_cells': int(glt_valid.sum()),
                'unique_raw_samples': len(set(zip(ix[glt_valid].tolist(), iy[glt_valid].tolist()))),
                'available_classification_cells': int(any_classified.sum()),
                'transform': list(transform)[:6],
                'bounds': list(rasterio.transform.array_bounds(rows, columns, transform)),
                'groups': groups, 'sources': [dict(role=key, **scene[key]) for key in ('mineral', 'uncertainty')]}


def run(config_path=CONFIG):
    config_path = Path(config_path)
    cfg = json.loads(config_path.read_text())
    if cfg['window_m'] != 1800:
        raise ValueError('Solo se admite el caso local de 1,8 km')
    manifest_path = ROOT / cfg['phase2_manifest']
    entries = {e['file']: e for e in json.loads(manifest_path.read_text())['files']}
    for key in ('areas', 'base_results'):
        path = ROOT / cfg[key]
        verify(path, entries[path.name])
    areas = json.loads((ROOT / cfg['areas']).read_text())['features']
    sites = []
    processing = {'versions': {'python': platform.python_version(), 'h5py': h5py.__version__, 'hdf5': h5py.version.hdf5_version, 'numpy': np.__version__, 'rasterio': rasterio.__version__}, 'method': 'Delivered one-based GLT, no interpolation of categorical IDs; native grid retained. Pixel-center mask of the phase-2 Earth polygon.', 'scene_audits': []}
    tracked = [config_path, Path(__file__).resolve(), ROOT / cfg['areas'], ROOT / cfg['base_results'], ROOT / 'requirements-minerales.txt']
    for site_id, name in [('earth-utah', 'Utah'), ('earth-atacama', 'Atacama')]:
        area = next(a for a in areas if a['properties']['site_id'] == site_id)
        scenes = [read_scene(scene, area['geometry']) for scene in cfg['scenes'] if scene['site_id'] == site_id]
        chosen = sorted(scenes, key=lambda scene: (-scene['available_classification_cells'], scene['product_id']))[0]
        for scene in scenes:
            processing['scene_audits'].append({'site_id': site_id, 'product_id': scene['product_id'], 'date': scene['date'], 'footprint_cells': scene['footprint_cells'], 'available_classification_cells': scene['available_classification_cells'], 'selected': scene is chosen,
                'groups': {key: {k: group[k] for k in ('data_cells', 'matched_cells', 'no_match_cells')} for key, group in scene['groups'].items()}})
        slope_path = ROOT / f'docs/evidencia-fase-2/{site_id}-60m-slope.tif'
        verify(slope_path, entries[slope_path.name])
        tracked.append(slope_path)
        slope = np.full((chosen['rows'], chosen['columns']), np.nan)
        transform = Affine(*chosen['transform'])
        with rasterio.open(slope_path) as src:
            reproject(rasterio.band(src, 1), slope, src_transform=src.transform, src_crs=src.crs, src_nodata=np.nan,
                      dst_transform=transform, dst_crs='EPSG:4326', dst_nodata=np.nan, resampling=Resampling.nearest)
        slope[~np.asarray(chosen['inside']).reshape(slope.shape)] = np.nan
        sites.append({'id': site_id, 'name': name, 'status': 'measured' if chosen['available_classification_cells'] else 'no_valid_classification',
                      'window_m': 1800, 'grid': chosen, 'slope_deg': json_array(slope),
                      'slope_source': {'file': str(slope_path.relative_to(ROOT)), 'sha256': digest(slope_path), 'cell_m': 60, 'resampling': 'nearest, display/filter overlay only; not independent measurements'},
                      'scene_audits': [a for a in processing['scene_audits'] if a['site_id'] == site_id]})
    result = {'release_id': cfg['release_id'], 'window_m': cfg['window_m'], 'sites': sites,
              'quality_note': cfg['quality_filter_note'], 'documentation': cfg['documentation'],
              'mars': {'status': 'not_acquired', 'name': 'Jezero', 'reason': 'Falta adquirir y evaluar un producto mineral CRISM compatible. Los códigos de biblioteca EMIT no son clases marcianas.', 'documentation': 'https://pds-geosciences.wustl.edu/missions/mro/crism.htm'},
              'limitations': ['Identificaciones de biblioteca espectral; no concentración química ni fracción de mineral en el suelo.',
                'Los dos grupos espectrales pueden coexistir. No sumar sus proporciones.',
                'El umbral de ajuste R² es exploratorio y no representa una probabilidad de acierto.',
                'Las celdas geográficas pueden repetir muestras nativas y no son observaciones independientes.',
                'No se adquirieron las máscaras L2A de nube/sombra/bandas. Los filtros usan solo ajuste e incertidumbre L2B; no certifican cielo despejado.',
                'Paso GLT angular nativo conservado; el paso físico depende de latitud y eje. No se remuestrean IDs al cambiar la celda topográfica.',
                'El recorte sigue el polígono previo de Tierra. La selección de escena favorece disponibilidad local antes de filtrar.',
                'La composición terrestre todavía no se compara con Marte ni aporta una puntuación combinada.']}
    out = ROOT / cfg['output']
    out.mkdir(parents=True, exist_ok=True)
    for filename, value in [('resultados.json', result), ('procesamiento.json', processing)]:
        path = out / filename
        path.with_suffix('.json.part').write_text(json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False) + '\n')
        path.with_suffix('.json.part').replace(path)
    tracked.extend([out / 'resultados.json', out / 'procesamiento.json'])
    inventory = {'schema': 1, 'files': [{'file': str(path.relative_to(ROOT)), 'bytes': path.stat().st_size, 'sha256': digest(path)} for path in tracked]}
    (out / 'manifest-local.json').write_text(json.dumps(inventory, indent=2) + '\n')
    for site in sites:
        print(site['name'], site['grid']['product_id'], site['grid']['available_classification_cells'], '/', site['grid']['footprint_cells'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=CONFIG)
    run(parser.parse_args().config)
