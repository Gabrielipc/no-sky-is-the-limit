#!/usr/bin/env python3
"""Small, calibrated visual DEM derivatives for Cesium. Never modifies analysis evidence.

Requires numpy + rasterio (the API venv is sufficient). Download originals to
ignored data/raw/frontend-surface before running; see frontend/public/surface/README.md.
"""
from pathlib import Path
import hashlib
import json
import struct
import zlib

import numpy as np
import rasterio
from rasterio.warp import reproject, Resampling
from rasterio.transform import from_origin

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / 'data/raw/frontend-surface'
OUT = ROOT / 'frontend/public/surface'
PDS = 'https://pds-geosciences.wustl.edu/mgs/urn-nasa-pds-mgs_mola_topography_derived/meg004/'
BLUE = 'https://gibs.earthdata.nasa.gov/wms/epsg4326/best/wms.cgi?SERVICE=WMS&REQUEST=GetMap&VERSION=1.1.1&LAYERS=BlueMarble_NextGeneration&STYLES=&SRS=EPSG:4326&BBOX=-180,-90,180,90&WIDTH=2048&HEIGHT=1024&FORMAT=image/jpeg'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def png(path, a):
    """Lossless 8-bit RGB/RGBA/gray; no gamma/color profile on data images."""
    a = np.asarray(a, dtype=np.uint8)
    height, width = a.shape[:2]
    channels = 1 if a.ndim == 2 else a.shape[2]
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data) & 0xffffffff)
    raw = b''.join(b'\0' + row.tobytes() for row in a)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, {1: 0, 3: 2, 4: 6}[channels], 0, 0, 0)) + chunk(b'IDAT', zlib.compress(raw, 9)) + chunk(b'IEND', b''))


def build():
    OUT.mkdir(parents=True, exist_ok=True)
    source = RAW / 'megr90n000cb.img'
    if source.stat().st_size != 1440 * 720 * 2:
        raise ValueError('Unexpected MOLA size')
    label = (RAW / 'megr90n000cb.lbl').read_text()
    for field in ('OFFSET                       = 3396000', 'SAMPLE_TYPE                  = MSB_INTEGER'):
        if field not in label:
            raise ValueError('Unexpected MOLA encoding')
    radius = np.fromfile(source, dtype='>i2').reshape(720, 1440).astype(float)
    # Convert east-positive 0..360, pixel-center samples to Cesium -180..180 tiles.
    for level in range(5):
        nx, ny = 2 ** (level + 1), 2 ** level
        for y in range(ny):
            lat = 90 - (y + np.linspace(0, 1, 65)) / ny * 180
            sy = np.clip((90 - lat) * 4 - .5, 0, 719)
            y0 = np.floor(sy).astype(int); y1 = np.minimum(y0 + 1, 719); fy = (sy-y0)[:, None]
            for x in range(nx):
                lon = -180 + (x + np.linspace(0, 1, 65)) / nx * 360
                sx = (lon % 360) * 4 - .5
                x0 = np.floor(sx).astype(int); fx = (sx-x0)[None, :]
                a = radius[y0[:, None], x0[None, :] % 1440] * (1-fx) + radius[y0[:, None], (x0[None, :]+1) % 1440] * fx
                b = radius[y1[:, None], x0[None, :] % 1440] * (1-fx) + radius[y1[:, None], (x0[None, :]+1) % 1440] * fx
                v = np.rint(a * (1-fy) + b * fy).astype(np.int32) + 32768
                png(OUT / f'mola/{level}/{x}/{y}.png', np.stack([v >> 8, v & 255, np.zeros_like(v)], -1))
    config = json.loads((ROOT / 'specs/analysis/primer-caso-fase2.json').read_text())
    entries = {i['file']: i for i in json.loads((ROOT/'docs/evidencia-fase-2/manifest-local.json').read_text())['files']}
    sites = []
    for site in config['sites']:
        if site['id'] not in ('mars-jezero-fan', 'earth-utah', 'earth-atacama'):
            continue
        ident = site['id']; mars = ident.startswith('mars'); count = 97 if mars else 61
        step = 1800 / (count-1)
        file = ROOT / f'docs/evidencia-fase-2/{ident}-native-crop.tif'
        if sha(file) != entries[file.name]['sha256']:
            raise ValueError(f'Changed source: {file}')
        ellipsoid = f"+a={site['radius_m']} +b={site['radius_m']}" if mars else '+datum=WGS84'
        crs = f"+proj=aeqd +lat_0={site['latitude']} +lon_0={site['longitude']} {ellipsoid} +units=m +no_defs"
        z = np.full((count, count), np.nan, dtype=np.float32)
        with rasterio.open(file) as src:
            reproject(rasterio.band(src, 1), z, src_transform=src.transform, src_crs=src.crs,
                      src_nodata=src.nodata, dst_transform=from_origin(-900-step/2,900+step/2,step,step),
                      dst_crs=crs, dst_nodata=np.nan, resampling=Resampling.average)
        valid = np.isfinite(z); lo, hi = float(np.nanmin(z)), float(np.nanmax(z)); scale = (hi-lo)/254 or 1
        gray = np.where(valid, np.rint((z-lo)/scale), 255).astype('uint8')
        png(OUT/f'{ident}-height.png',gray)
        # A derived shaded-relief texture, explicitly not a photograph.
        safe = np.where(valid,z,lo); dy, dx = np.gradient(safe,step)
        shade = np.clip((1 + .8*dx + .6*dy) / np.sqrt(1 + dx*dx + dy*dy) / 1.42,.15,1)
        t = (safe-lo)/max(hi-lo,1)
        base = np.array([202,155,111] if mars else [155,171,133])
        rgb = np.clip(base[None,None,:] * (shade[:,:,None]*.72 + t[:,:,None]*.18+.2),0,255).astype('uint8')
        png(OUT/f'{ident}-relief.png', np.dstack([rgb,valid.astype('uint8')*255]))
        sites.append(dict(id=ident,name=site['name'],body=site['body'],longitude=site['longitude'],latitude=site['latitude'],
                          width=count,height=count,cell_m=step,window_m=1800,offset_m=lo,scale_m=scale,nodata=255,
                          center_m=float(np.nanmedian(z)),min_m=lo,max_m=hi,coverage=float(valid.mean()),
                          heightmap=f'{ident}-height.png',texture=f'{ident}-relief.png',
                          source='HiRISE DTM' if mars else 'SRTM GL1',source_file=str(file.relative_to(ROOT)),source_sha256=sha(file),
                          source_url=site['url'],
                          vertical_reference='Local mesh centered on median; original DEM datum retained only in metadata'))
    with rasterio.open(RAW/'blue-marble-gibs.jpg') as src:
        rgb = src.read(out_shape=(3,1024,2048),resampling=Resampling.average).transpose(1,2,0)
    png(OUT/'blue-marble.png',rgb)
    manifest = dict(version=1,description='Visual derivatives only; not new scientific measurements.',
        mola=dict(radius_m=3396000,tile_size=65,max_level=4,pixels_per_degree=4,source_resolution_km=14.818,
                  encoding='height_m = R*256 + G - 32768; relative to 3396000 m sphere',
                  url=PDS+source.name,sha256=sha(source),label_url=PDS+'megr90n000cb.lbl',label_sha256=sha(RAW/'megr90n000cb.lbl')),
        blue_marble=dict(url=BLUE,sha256=sha(RAW/'blue-marble-gibs.jpg'),credit='NASA Earth Observatory / Reto Stöckli; August 2004',width=2048,height=1024),sites=sites)
    manifest['files']=[dict(file=str(p.relative_to(OUT)),sha256=sha(p),bytes=p.stat().st_size) for p in sorted(OUT.rglob('*.png'))]
    (OUT/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    print('Published',len(manifest['files']),'visual assets;',len(sites),'local DEMs')

if __name__ == '__main__':
    build()
