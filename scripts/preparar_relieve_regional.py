#!/usr/bin/env python3
"""Refine Jezero with a bounded MOLA 128 ppd radius strip; preserve sphere datum.

Fetch bytes 70778880-79626239 of MEGR44N000HB.IMG to RAW first.
These are complete rows 3072..3455, covering 17..20 N and 0..90 E.
"""
import json
import numpy as np
from preparar_superficie_frontend import ROOT, RAW, OUT, png, sha

URL = 'https://pds-geosciences.wustl.edu/mgs/urn-nasa-pds-mgs_mola_topography_derived/meg128/megr44n000hb.img'
BOUNDS = [75, 17, 80, 20]


def interpolate(grid, x, y):
    x = np.clip(x, 0, grid.shape[1]-1); y = np.clip(y, 0, grid.shape[0]-1)
    x0 = np.floor(x).astype(int); y0 = np.floor(y).astype(int)
    x1 = np.minimum(x0+1, grid.shape[1]-1); y1 = np.minimum(y0+1, grid.shape[0]-1)
    fx = (x-x0)[None, :]; fy = (y-y0)[:, None]
    return (grid[y0[:,None], x0[None,:]]*(1-fx)+grid[y0[:,None], x1[None,:]]*fx)*(1-fy) + (grid[y1[:,None], x0[None,:]]*(1-fx)+grid[y1[:,None], x1[None,:]]*fx)*fy


def build():
    file = RAW/'mola128-rows3072-3455.bin'
    if sha(file) != '430ae7fb3b811bbe48697856d9ed21a412a1d14b4b29181cf7df474628bc762f':
        raise ValueError('MOLA range identity changed')
    if file.stat().st_size != 8847360:
        raise ValueError('Incomplete MOLA byte range; expected 8,847,360 bytes')
    fine = np.fromfile(file, dtype='>i2').reshape(384,11520).astype(float)
    coarse = np.fromfile(RAW/'megr90n000cb.img',dtype='>i2').reshape(720,1440).astype(float)
    # Repeat seam pixels so coarse interpolation is continuous across longitude zero.
    coarse = np.pad(coarse,((0,0),(1,1)),mode='wrap')
    keys = []
    for level in range(10):
        nx, ny = 2**(level+1), 2**level
        for y in range(ny):
            north, south = 90-y*180/ny, 90-(y+1)*180/ny
            if level>4 and (south>20 or north<17): continue
            lat = np.linspace(north,south,65)
            for x in range(nx):
                west, east = -180+x*360/nx, -180+(x+1)*360/nx
                if level>4 and (west>80 or east<75): continue
                lon = np.linspace(west,east,65)
                base = interpolate(coarse,(lon%360)*4+.5,(90-lat)*4-.5)
                detail = interpolate(fine,lon*128-.5,(20-lat)*128-.5)
                # Fade to the global radius grid over 0.2 degrees around the patch boundary.
                wx = np.clip(np.minimum(lon-75,80-lon)/.2,0,1)
                wy = np.clip(np.minimum(lat-17,20-lat)/.2,0,1)
                weight = wy[:,None]*wx[None,:]
                v = np.rint(base*(1-weight)+detail*weight).astype(np.int32)+32768
                png(OUT/f'mola/{level}/{x}/{y}.png',np.stack([v>>8,v&255,np.zeros_like(v)],-1))
                if level>4: keys.append(f'{level}/{x}/{y}')
    path = OUT/'manifest.json'; manifest = json.loads(path.read_text())
    manifest['mola']['regional'] = dict(bounds=BOUNDS,max_level=9,tiles=keys,pixels_per_degree=128,
        sample_spacing_m=463.0625,source_url=URL,source_range='bytes=70778880-79626239',
        source_bytes=8847360,source_sha256=sha(file),blend_degrees=.2,
        description='MOLA radius, not areoid elevation. Interpolated bins included; spacing is not effective resolution.')
    manifest['files']=[dict(file=str(p.relative_to(OUT)),sha256=sha(p),bytes=p.stat().st_size) for p in sorted(OUT.rglob('*.png'))]
    path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    print('Published',len(keys),'regional tiles; unchanged scientific evidence')

if __name__=='__main__': build()
