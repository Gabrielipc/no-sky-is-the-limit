#!/usr/bin/env python3
"""Publish native CRISM SR indicators and IN coverage for the phase-2 Jezero window."""
import hashlib
import json
from pathlib import Path
import re

import numpy as np
import rasterio
from rasterio.features import geometry_mask
from rasterio.warp import transform_geom
from rasterio.windows import Window, from_bounds

ROOT = Path(__file__).resolve().parents[1]
AREA = ROOT / 'docs/evidencia-fase-2/areas-marte.json'
ACQUISITION = ROOT / 'docs/investigacion-marte/adquisicion-crism.json'
OUTPUT = ROOT / 'docs/evidencia-crism'
PREFIX = 'crism/frt000047a3/frt000047a3_07_'
PRODUCT = 'FRT000047A3'
SIS = 'https://pds-geosciences.wustl.edu/mro/mro-m-crism-2-edr-v1/mrocr_0015/document/crism_dpsis.htm'
INDICATORS = (
    ('OLINDEX3', 'Señal sensible al olivino', 'También responde a piroxenos de alto calcio y filosilicatos de hierro.'),
    ('BD530_2', 'Señal férrica a 0,53 µm', 'Profundidad de absorción sensible a hematita cristalina.'),
    ('D2300', 'Señal de silicatos con Fe/Mg–OH', 'Caída espectral cerca de 2,3 µm asociada a silicatos hidroxilados de hierro y magnesio.'),
    ('MIN2295_2480', 'Señal sensible a carbonatos de Mg', 'Combina rasgos de 2,30 y 2,48 µm. También puede responder a absorciones de metal–OH.'),
    ('BD1900R2', 'Señal de hidratación a 1,9 µm', 'Profundidad de absorción asociada a agua molecular en materiales hidratados.'),
)
RESIDUAL = 'ATM Correction Spectral Shift Artifact'


def identity(path):
    with path.open('rb') as stream:
        return {'bytes': path.stat().st_size, 'sha256': hashlib.file_digest(stream, 'sha256').hexdigest()}


def verify(path, expected):
    if identity(path) != {key: expected[key] for key in ('bytes', 'sha256')}:
        raise ValueError(f'Identidad distinta: {path.name}')


def native_window(dataset, feature):
    geometry = transform_geom(feature['properties']['crs_wkt'], dataset.crs, feature['geometry'])
    vertices = np.asarray(geometry['coordinates'][0])
    bounds = from_bounds(*vertices.min(axis=0), *vertices.max(axis=0), dataset.transform)
    left, top = np.floor([bounds.col_off, bounds.row_off]).astype(int)
    right, bottom = np.ceil([bounds.col_off + bounds.width, bounds.row_off + bounds.height]).astype(int)
    if not (0 <= left < right <= dataset.width and 0 <= top < bottom <= dataset.height):
        raise ValueError('El rectángulo CRISM no contiene la ventana de Jezero')
    window = Window(int(left), int(top), int(right-left), int(bottom-top))
    transform = dataset.window_transform(window)
    inside = geometry_mask([geometry], (window.height, window.width), transform, invert=True)
    return window, transform, inside


def layer(dataset, band, window, support, code, label, description):
    values = dataset.read(band, window=window, masked=True).filled(np.nan)
    valid = support & np.isfinite(values)
    sample = values[valid]
    limits = np.quantile(sample, [.02, .5, .98]).tolist() if sample.size else [None] * 3
    return {'id': code, 'label': label, 'description': description, 'band': band,
            'valid_cells': int(sample.size), 'p02': limits[0], 'median': limits[1], 'p98': limits[2],
            'values': [round(float(value), 8) if keep else None for value, keep in zip(values.flat, valid.flat)]}


def run():
    acquisition = json.loads(ACQUISITION.read_text())
    if not acquisition['complete'] or acquisition['observation_id'] != PRODUCT or acquisition['package'] != 'parameters':
        raise ValueError('Se requiere el informe verificado del paquete CRISM SR/IN')
    entries = {entry['path']: entry for entry in acquisition['files'] if entry['verified']}
    for code in ('sr', 'in'):
        for extension in ('img', 'hdr', 'lbl'):
            relative = f'{PREFIX}{code}166j_mtr3.{extension}'
            verify(ROOT / 'data/raw' / relative, entries[relative])
    area_manifest = AREA.with_name('manifest-local.json')
    area_entry = next(e for e in json.loads(area_manifest.read_text())['files'] if e['file'] == AREA.name)
    verify(AREA, area_entry)
    feature = next(f for f in json.loads(AREA.read_text())['features'] if f['properties']['site_id'] == 'mars-jezero-fan')
    if feature['properties']['body'] != 'Mars' or feature['properties']['side_m'] != 1800:
        raise ValueError('Ventana marciana distinta')
    raw = ROOT / 'data/raw'
    date = re.search(r'^START_TIME\s*=\s*(\d{4}-\d{2}-\d{2})', (raw / f'{PREFIX}sr166j_mtr3.lbl').read_text(), re.M)[1]
    with rasterio.open(raw / f'{PREFIX}sr166j_mtr3.img') as sr, rasterio.open(raw / f'{PREFIX}in166j_mtr3.img') as info:
        if (sr.shape != info.shape or sr.transform != info.transform or sr.crs != info.crs
                or sr.nodata != 65535 or info.nodata != 65535 or info.descriptions[8] != 'VNIR/IR Mask'):
            raise ValueError('Rejillas o máscara CRISM incompatibles')
        window, transform, inside = native_window(sr, feature)
        mask = info.read(9, window=window)
        if not np.isin(mask[inside], [0, 1, info.nodata]).all():
            raise ValueError('Código no reconocido en la máscara VNIR/IR')
        supported = inside & (mask == 0)
        # Confirm the mask polarity against the paired SR raster before applying it.
        reference = sr.read(sr.descriptions.index('OLINDEX3') + 1, window=window, masked=True).filled(np.nan)
        if not np.array_equal(inside & np.isfinite(reference), supported):
            raise ValueError('La máscara IN y el soporte del indicador de referencia SR discrepan')
        layers = [layer(sr, sr.descriptions.index(code) + 1, window, supported, code, label, note)
                  for code, label, note in INDICATORS]
        layers.append(layer(info, info.descriptions.index(RESIDUAL) + 1, window, supported,
                            'atm_residual', 'Residuo de corrección atmosférica',
                            'Indicador de artefactos de la corrección atmosférica alrededor de 2 µm.'))
        result = {
            'observation_id': PRODUCT, 'date': date, 'window_m': 1800, 'documentation': SIS,
            'grid': {'rows': window.height, 'columns': window.width,
                     'step_m': [transform.a, -transform.e], 'transform': list(transform)[:6],
                     'crs_wkt': sr.crs.to_wkt(), 'offset': [window.col_off, window.row_off],
                     'inside': inside.ravel().tolist(),
                     'mask': [int(v) if keep and v != info.nodata else None for v, keep in zip(mask.flat, inside.flat)]},
            'coverage': {'total': int(inside.sum()), 'supported': int(supported.sum()),
                         'excluded': int((inside & (mask == 1)).sum()),
                         'missing': int((inside & (mask == info.nodata)).sum())},
            'layers': layers,
        }

    OUTPUT.mkdir(exist_ok=True)
    destination = OUTPUT / 'resultados.json'
    temporary = destination.with_suffix('.part')
    temporary.write_text(json.dumps(result, ensure_ascii=False, allow_nan=False, separators=(',', ':')) + '\n')
    temporary.replace(destination)
    tracked = (Path(__file__).resolve(), AREA, ACQUISITION, destination)
    manifest = {'schema': 1, 'files': [{'file': str(path.relative_to(ROOT)), **identity(path)} for path in tracked]}
    temporary = OUTPUT / 'manifest-local.part'
    temporary.write_text(json.dumps(manifest, indent=2) + '\n')
    temporary.replace(OUTPUT / 'manifest-local.json')
    print(PRODUCT, result['coverage'])


if __name__ == '__main__':
    run()
