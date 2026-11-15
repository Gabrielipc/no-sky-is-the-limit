#!/usr/bin/env python3
"""Bounded browser preview from existing georeferenced CTX tiles (9 × 512 px).
No scientific DEM processing. Requires numpy and rasterio from the project env.
"""
import hashlib
import json
import math
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.request import urlopen
import numpy as np
import rasterio
from rasterio.io import MemoryFile
from rasterio.errors import NotGeoreferencedWarning
import warnings

OUT=Path(__file__).resolve().parents[1]/'public/surface'
BASE='https://astro.arcgis.com/arcgis/rest/services/OnMars/CTX/MapServer/tile'
LEVEL=8

def fetch(key):
    x,y=key
    url=f'{BASE}/{LEVEL}/{y}/{x}'
    with urlopen(url,timeout=40) as response: data=response.read()
    with warnings.catch_warnings():
        warnings.simplefilter('ignore',NotGeoreferencedWarning)
        with MemoryFile(data) as memory:
            with memory.open() as src: pixels=src.read(1)
    if pixels.shape!=(512,512):raise ValueError('Unexpected source tile')
    return x,y,pixels,{'url':url,'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data)}

def build():
    canvas=np.zeros((1536,1536),dtype=np.uint8);sources=[]
    with ThreadPoolExecutor(max_workers=3) as pool:
        for x,y,pixels,source in pool.map(fetch,[(x,y) for y in range(100,103) for x in range(365,368)]):
            canvas[(y-100)*512:(y-99)*512,(x-365)*512:(x-364)*512]=pixels;sources.append(source)
    path=OUT/'jezero-ctx-regional.png'
    with warnings.catch_warnings():
        warnings.simplefilter('ignore',NotGeoreferencedWarning)
        with rasterio.open(path,'w',driver='PNG',width=1536,height=1536,count=1,dtype='uint8') as dst:dst.write(canvas,1)
    cell=180/(2**LEVEL)
    metadata={'file':path.name,'rectangle_degrees':[-180+365*cell,90-103*cell,-180+368*cell,90-100*cell],
              'width':1536,'height':1536,'sampling_degrees':cell/512,'sampling_equator_m':math.radians(cell/512)*3396190,
              'description':'CTX context mosaic at level 8. Native CTX is finer; this derivative is downsampled. Uncontrolled mosaic, positional accuracy not asserted.',
              'credit':'NASA/JPL/MSSS/Caltech Murray Lab; served by NASA Mars Trek / Esri OnMars',
              'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'sources':sources}
    (OUT/'regional-preview.json').write_text(json.dumps(metadata,indent=2)+'\n')
    print(path, path.stat().st_size,metadata['rectangle_degrees'])
if __name__=='__main__':build()
