#!/usr/bin/env python3
"""Genera el catálogo del prototipo desde las teselas MOLA y SRTM descargadas."""
import hashlib
import json
from pathlib import Path

import numpy as np
import rasterio
from rasterio.crs import CRS
from rasterio.enums import Resampling
from rasterio.transform import from_origin
from rasterio.warp import reproject, transform

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / 'data' / 'raw'
OUT = ROOT / 'data' / 'regions.json'
META = ROOT / 'data' / 'procesamiento.json'
VIS = ROOT / 'frontend' / 'public' / 'regions'
SIZE = 20  # 20 celdas de 500 m = 10 km
CELL = 500
MARS_CRS = CRS.from_proj4('+proj=longlat +a=3396000 +b=3396000 +no_defs')
MARS_TRANSFORM = from_origin(0, 44, 1 / 128, 1 / 128)
SITES = [
    ('mars-jezero', 'Jezero · región de referencia', 'Mars', 18.44, 77.45, 'mola/megt44n000hb.img'),
    ('earth-atacama', 'Desierto de Atacama', 'Earth', -23.8, -67.9, 'srtm/S24W068.tif'),
    ('earth-utah', 'Meseta de Colorado', 'Earth', 38.6, -110.6, 'srtm/N38W111.tif'),
]

def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()

def target(lat, lon, mars):
    ellipsoid = '+a=3396000 +b=3396000' if mars else '+datum=WGS84'
    crs = CRS.from_proj4(f'+proj=aeqd +lat_0={lat} +lon_0={lon} {ellipsoid} +units=m +no_defs')
    # Una celda exterior de margen por lado para diferencias centrales.
    return crs, from_origin(-(SIZE / 2 + 1) * CELL, (SIZE / 2 + 1) * CELL, CELL, CELL)

def warp(source, src_transform, src_crs, dst_crs, dst_transform, method, nodata=None):
    out = np.full((SIZE + 2, SIZE + 2), np.nan, dtype='float32')
    reproject(source=source, destination=out, src_transform=src_transform, src_crs=src_crs,
              src_nodata=nodata, dst_transform=dst_transform, dst_crs=dst_crs,
              dst_nodata=np.nan, resampling=method, init_dest_nodata=True)
    return out

def main():
    catalog, metadata = [], []
    VIS.mkdir(parents=True, exist_ok=True)
    for ident, name, body, lat, lon, filename in SITES:
        path = RAW / filename
        if not path.exists():
            raise FileNotFoundError(f'Falta {path}; consulta data/README-datos-reales.md')
        mars = body == 'Mars'
        dst_crs, dst_transform = target(lat, lon, mars)
        if mars:
            if path.stat().st_size != 5632 * 11520 * 2:
                raise ValueError('Tamaño inesperado de la tesela MOLA de topografía')
            source = np.memmap(path, dtype='>i2', mode='r', shape=(5632, 11520))
            elev = warp(np.asarray(source, dtype='int16'), MARS_TRANSFORM, MARS_CRS, dst_crs, dst_transform, Resampling.bilinear)
            counts_path = RAW / 'mola/megc44n000hb.img'
            if counts_path.stat().st_size != 5632 * 11520:
                raise ValueError('Tamaño inesperado de la tesela MOLA de recuentos')
            counts = np.memmap(counts_path, dtype='u1', mode='r', shape=(5632, 11520))
            support = warp(counts, MARS_TRANSFORM, MARS_CRS, dst_crs, dst_transform, Resampling.nearest)
            observed = float(np.mean(support[1:-1, 1:-1] > 0))
            sources = [{'name':'MOLA MEGDR 128 ppd · topografía y recuentos', 'url':'https://pds-geosciences.wustl.edu/missions/mgs/megdr.html'}]
            limitations = [f'El {observed:.1%} de las celdas de la cuadrícula de salida tiene recuento MOLA mayor que cero según remuestreo por vecino más cercano; otras pueden estar interpoladas.', 'La resolución regional de MOLA no permite distinguir rocas ni obstáculos pequeños.']
        else:
            with rasterio.open(path) as ds:
                if ds.crs is None:
                    raise ValueError(f'Falta CRS en {path}')
                elev = warp(rasterio.band(ds, 1), ds.transform, ds.crs, dst_crs, dst_transform, Resampling.average, ds.nodata)
            observed = None
            sources = [{'name':'SRTM GL1 · distribución OpenTopography', 'url':'https://portal.opentopography.org/raster?jobId=rt1674642591184'}]
            limitations = ['SRTM es un modelo radar de superficie y puede contener artefactos o reflejar vegetación y estructuras.', 'Su resolución original se agregó a la cuadrícula regional de análisis.']
        center = elev[1:-1, 1:-1]
        valid = np.isfinite(center)
        coverage = float(valid.mean())
        if not valid.any():
            raise ValueError(f'Sin datos de elevación en {ident}')
        dx = (elev[1:-1, 2:] - elev[1:-1, :-2]) / (2 * CELL)
        dy = (elev[:-2, 1:-1] - elev[2:, 1:-1]) / (2 * CELL)
        slopes = np.degrees(np.arctan(np.hypot(dx, dy)))
        slope_valid = valid & np.isfinite(slopes)
        slope = float(slopes[slope_valid].mean()) if slope_valid.any() else None
        relief = float(np.percentile(center[valid], 95) - np.percentile(center[valid], 5))
        # Conservar la misma cuadrícula usada en las métricas, con vértices
        # geográficos transformados desde la proyección local (no un rectángulo aproximado).
        xs = [-5000 + col * CELL for row in range(SIZE + 1) for col in range(SIZE + 1)]
        ys = [5000 - row * CELL for row in range(SIZE + 1) for col in range(SIZE + 1)]
        lons, lats = transform(dst_crs, MARS_CRS if mars else CRS.from_epsg(4326), xs, ys)
        grid = {'id':ident, 'size':SIZE, 'cell_m':CELL,
                'vertices':[[round(x, 8), round(y, 8)] for x, y in zip(lons, lats)],
                'elevation_m':[[round(float(v), 3) if np.isfinite(v) else None for v in row] for row in center],
                'min_m':round(float(np.min(center[valid])), 3), 'max_m':round(float(np.max(center[valid])), 3)}
        (VIS / f'{ident}.json').write_text(json.dumps(grid, ensure_ascii=False, allow_nan=False) + '\n', encoding='utf-8')
        catalog.append({'id':ident, 'name':name, 'body':body, 'latitude':lat, 'longitude':lon,
            'scale_km':10, 'coverage':round(coverage, 4), 'metrics':{'slope_deg':round(slope, 4) if slope is not None else None, 'relief_m':round(relief, 4)},
            'description':'Ventana exploratoria de 10 × 10 km centrada en coordenadas provisionales.', 'sources':sources, 'limitations':limitations})
        entry = {'id':ident, 'input':str(path.relative_to(ROOT)), 'sha256':sha256(path), 'grid_crs':dst_crs.to_string(),
                 'grid_m':CELL, 'cells':SIZE * SIZE, 'valid_elevation_cells':int(valid.sum()), 'valid_slope_cells':int(slope_valid.sum()),
                 'resampling':'bilinear' if mars else 'average', 'fraction_output_cells_nearest_mola_count_positive':observed}
        if mars:
            entry['counts_input'] = str(counts_path.relative_to(ROOT))
            entry['counts_sha256'] = sha256(counts_path)
        metadata.append(entry)
    OUT.write_text(json.dumps(catalog, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    META.write_text(json.dumps({'method':'AEQD local; 500 m; margen 1 celda; pendiente por diferencias centrales; relieve p95-p5; elevación MOLA bilineal y SRTM promedio.', 'regions':metadata}, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    print(f'Escritas {len(catalog)} regiones en {OUT} y trazabilidad en {META}')

if __name__ == '__main__':
    main()
