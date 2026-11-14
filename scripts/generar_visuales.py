#!/usr/bin/env python3
"""Publish small visual derivatives; never change reviewed scientific evidence.

Run with the existing Pixi environment. No downloads or metric recomputation.
The regional background is a visual resampling of the verified GMTED archive.
"""
import hashlib
import json
import math
from pathlib import Path

import numpy as np
from PIL import Image
import rasterio
from rasterio.enums import Resampling
from rasterio.windows import from_bounds

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'frontend/public/analysis'


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def verify(path, entry):
    if path.stat().st_size != entry['bytes'] or digest(path) != entry['sha256']:
        raise ValueError(f'Input identity mismatch: {path.name}')


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False) + '\n')


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    evidence = ROOT / 'docs/evidencia-fase-2'
    entries = {e['file']: e for e in json.loads((evidence / 'manifest-local.json').read_text())['files']}
    verify(evidence / 'resultados.json', entries['resultados.json'])
    result = json.loads((evidence / 'resultados.json').read_text())
    layers = {'case_id': result['case_id'], 'results_sha256': entries['resultados.json']['sha256'],
              'window_m': 1800, 'slope_range': [0, 25], 'sites': {}, 'inputs': []}
    height_limit = 0
    for site in ('mars-jezero-fan', 'earth-utah', 'earth-atacama'):
        layers['sites'][site] = {}
        for cell in (60, 120):
            values = {}
            for variable in ('slope', 'elevation'):
                name = f'{site}-{cell}m-{variable}.tif'
                verify(evidence / name, entries[name])
                layers['inputs'].append({'file': f'docs/evidencia-fase-2/{name}', 'sha256': entries[name]['sha256']})
                with rasterio.open(evidence / name) as src:
                    a = src.read(1, masked=True)
                    if variable == 'elevation':
                        a = a - np.ma.median(a)
                        height_limit = max(height_limit, float(np.ma.abs(a).max()))
                    elif a.min() < 0 or a.max() > 25:
                        raise ValueError('Slope exceeds declared common legend')
                    values[variable] = [None if masked else round(float(v), 4)
                                        for v, masked in zip(a.data.ravel(), np.ma.getmaskarray(a).ravel())]
                    values['rows'], values['columns'] = a.shape
                    values['bounds_m'] = list(src.bounds)
            layers['sites'][site][str(cell)] = values
    layers['height_range'] = [-math.ceil(height_limit / 10) * 10, math.ceil(height_limit / 10) * 10]
    write_json(OUT / 'terrain.json', layers)

    cfg = json.loads((ROOT / 'specs/search/busqueda-regional-v1.json').read_text())
    source = next(s for s in cfg['sources'] if s['id'] == 'mn75_grd')
    archive = ROOT / source['input']
    verify(archive, source)
    backgrounds = []
    with rasterio.open('/vsizip/' + str(archive) + '/mn75_grd/hdr.adf') as src:
        for area in cfg['areas']:
            w, s, e, n = area['bbox']
            rows, columns = 512, 512
            a = src.read(1, window=from_bounds(w, s, e, n, src.transform),
                         out_shape=(rows, columns), masked=True, resampling=Resampling.average)
            lo, hi = np.percentile(a.compressed(), [2, 98])
            elevation = np.clip((a.filled(lo) - lo) / max(hi - lo, 1), 0, 1)
            dy, dx = np.gradient(elevation)
            shade = np.clip(0.50 + 12 * (dx - dy), 0.22, 0.84)
            # Context only: muted hillshade, not a quantitative comparison scale.
            intensity = np.uint8(np.clip(34 + 100 * shade + 24 * elevation, 0, 255))
            rgb = np.stack([intensity * .91, intensity, intensity * .94], axis=-1).astype('uint8')
            rgba = np.dstack([rgb, np.where(np.ma.getmaskarray(a), 0, 255).astype('uint8')])
            filename = f"{area['id']}-context.png"
            Image.fromarray(rgba).save(OUT / filename)
            backgrounds.append({'area_id': area['id'], 'bbox': area['bbox'], 'file': filename,
                                'role': 'GMTED shaded context; contrast adjusted per region; not a measured layer'})
    manifest = {'generator': 'scripts/generar_visuales.py', 'generator_sha256': digest(Path(__file__)),
                'scientific_results_sha256': layers['results_sha256'], 'regional_source': source,
                'backgrounds': backgrounds,
                'files': [{'file': name, 'bytes': (OUT / name).stat().st_size, 'sha256': digest(OUT / name)}
                          for name in ['terrain.json', *(b['file'] for b in backgrounds)]]}
    write_json(OUT / 'manifest.json', manifest)
    print(f'Visual derivatives published in {OUT}; reviewed evidence preserved.')


if __name__ == '__main__':
    main()
