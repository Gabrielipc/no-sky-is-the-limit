#!/usr/bin/env python3
"""Offline source discovery and native-support EDA; never publishes a ranking.

Run: bash scripts/ejecutar_minerales.sh scripts/explorar_fuentes_atlas.py
Raw inputs are read only. Raster samples are diagnostic, not a global estimator.
"""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import re
import shutil
import sys
import tarfile
import tempfile
import zipfile

import h5py
import numpy as np
import rasterio
from rasterio.features import geometry_mask
from rasterio.windows import Window, from_bounds
from pyproj import CRS, Transformer
from shapely.geometry import box, mapping, shape
from shapely import segmentize
from shapely.ops import transform
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import analizar_minerales as emit

OUT = ROOT / 'docs/exploracion-fuentes-v1'
CENTERS = {'desierto': (-110.6, 38.6), 'montana': (11.2, 46.6),
           'costa': (-70.1, -23.65), 'tropico': (114.6, .6),
           'polar': (.2, -80.7), 'atacama-materiales': (-67.9, -23.8)}
WORLD_CODES = [10, 20, 30, 40, 50, 60, 70, 80, 90, 95, 100]


def clean(v):
    if isinstance(v, bytes): return v.decode('utf-8', errors='replace')
    if isinstance(v, Path): return str(v)
    if isinstance(v, np.ndarray): return clean(v.tolist())
    if isinstance(v, np.generic): return clean(v.item())
    if isinstance(v, dict): return {str(k): clean(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)): return [clean(x) for x in v]
    if isinstance(v, float) and not math.isfinite(v): return None
    return v


def write(path, value):
    path.write_text(json.dumps(clean(value), ensure_ascii=False, indent=2, allow_nan=False) + '\n')


def digest(path):
    with Path(path).open('rb') as f: return hashlib.file_digest(f, 'sha256').hexdigest()


def family(path):
    parts = path.relative_to(ROOT / 'data/raw').parts
    return parts[1] if parts[0] == 'atlas30' and len(parts) > 2 else parts[0]


def stats(values, denominator=None):
    values = np.asarray(values, dtype=float).ravel()
    values = values[np.isfinite(values)]
    d = int(denominator) if denominator is not None else None
    return {'n': int(values.size), 'denominator': d,
            'valid_fraction': float(values.size / d) if d else None,
            'min': float(values.min()) if values.size else None,
            'p05': float(np.quantile(values, .05)) if values.size else None,
            'p50': float(np.median(values)) if values.size else None,
            'p95': float(np.quantile(values, .95)) if values.size else None,
            'max': float(values.max()) if values.size else None}


def counts(values):
    v = np.asarray(values).ravel()
    v = v[np.isfinite(v)]
    a, n = np.unique(v, return_counts=True)
    return {str(int(k)): int(c) for k, c in zip(a, n)}


def hls_mask(qa, policy='clear'):
    # v2 bits: cloud 1, adjacency 2, shadow 3, snow 4, water 5, aerosol 6-7.
    qa = np.asarray(qa)
    finite = np.isfinite(qa)
    q = np.where(finite, qa, 255).astype(np.uint16)
    bits = {'clear': 14, 'legacy': 46, 'dry_land': 62}[policy]
    return finite & (q != 255) & ((q & bits) == 0)


def landsat_mask(qa, keep_snow=False):
    finite = np.isfinite(qa)
    q = np.where(finite, qa, 1).astype(np.uint16)
    return finite & ((q & (31 if keep_snow else 63)) == 0)


def physical(values, fam, variable):
    a = np.asarray(values, dtype=float).copy()
    if fam == 'jrc': a[(a < 0) | (a > 100)] = np.nan
    elif fam == 'worldcover': a[~np.isin(a, WORLD_CODES)] = np.nan
    elif fam == 'hls' and variable != 'Fmask':
        a[a == -9999] = np.nan
        a *= .0001
    elif fam == 'landsat' and variable == 'ST_B10':
        a[a < 293] = np.nan
        a = a * .00341802 + 149
    elif fam == 'landsat' and variable == 'ST_QA':
        a[(a < 0) | (a > 32767)] = np.nan
        a *= .01
    return a


def variable_name(path, band, description):
    if family(path) == 'hls': return path.name.split('.')[-2]
    if family(path) == 'landsat':
        return next(s for s in ('ST_B10', 'QA_PIXEL', 'ST_QA') if s in path.name)
    return description or f'band_{band}'


def raster_header(target):
    with rasterio.open(target) as d:
        return {'driver': d.driver, 'shape': [d.height, d.width], 'bands': d.count,
                'crs': d.crs.to_wkt() if d.crs else None, 'bounds': list(d.bounds),
                'transform': list(d.transform)[:6], 'step': list(d.res),
                'variables': [{'band': i, 'name': desc or f'band_{i}', 'dtype': dt,
                               'nodata': nd, 'scale_header': sc, 'offset_header': off,
                               'unit_header': unit}
                              for i, desc, dt, nd, sc, off, unit in zip(d.indexes, d.descriptions,
                              d.dtypes, d.nodatavals, d.scales, d.offsets, d.units)],
                'metadata_selected': {k: v for k, v in d.tags().items() if k in (
                    'PRODUCT_ID', 'SENSING_TIME', 'ACCODE', 'cloud_coverage',
                    'CLOUD_COVERAGE', 'SPATIAL_COVERAGE', 'AREA_OR_POINT')}}


def patches(target, fam):
    """Five fixed native 32x32 patches; no overviews, interpolation or global claim."""
    result = []
    with rasterio.open(target) as d:
        for fx, fy in ((.1, .1), (.9, .1), (.5, .5), (.1, .9), (.9, .9)):
            w, h = min(32, d.width), min(32, d.height)
            win = Window(int((d.width-w)*fx), int((d.height-h)*fy), w, h)
            # All bands for CRISM; one band for ordinary rasters.
            for b in d.indexes:
                a = d.read(b, window=win, masked=True).astype(float).filled(np.nan)
                row = {'band': b, 'window': [win.col_off, win.row_off, w, h],
                       'statistics_storage_units': stats(a, a.size)}
                if fam in ('jrc', 'worldcover'):
                    row['value_counts'] = counts(a)
                    row['after_domain_mask'] = stats(physical(a, fam, ''), a.size)
                result.append(row)
    return result


def inventory():
    records = []
    paths = sorted(p for p in (ROOT / 'data/raw').rglob('*') if p.is_file())
    for j, p in enumerate(paths):
        fam = family(p)
        row = {'path': str(p.relative_to(ROOT)), 'family': fam, 'bytes': p.stat().st_size,
               'mtime_ns': p.stat().st_mtime_ns, 'status': 'sidecar_or_uninterpreted'}
        try:
            if p.suffix.lower() == '.jp2':
                label=ROOT/'docs/evidencia-fase-1'/p.with_suffix('.LBL').name
                with Image.open(p) as im:
                    row.update(status='image_header_and_patches_read', decoder='Pillow JPEG2000',
                               shape=[im.height,im.width],mode=im.mode,
                               geometry_label=str(label.relative_to(ROOT)),
                               variables=[{'name':'RED_C image intensity','unit_header':None}])
                    row['diagnostic_patches']=[]
                    for fx,fy in ((.1,.1),(.9,.1),(.5,.5),(.1,.9),(.9,.9)):
                        x,y=int((im.width-32)*fx),int((im.height-32)*fy)
                        row['diagnostic_patches'].append({'window':[x,y,32,32],
                            'statistics_storage_units':stats(np.asarray(im.crop((x,y,x+32,y+32))),1024)})
                row['label_selected']={k:re.search(rf'^\s*{k}\s*=\s*([^\r\n]+)',label.read_text(),re.M)[1]
                    for k in ('MAP_SCALE','LINES','LINE_SAMPLES','A_AXIS_RADIUS','CENTER_LONGITUDE')}
                row['note']='GDAL JP2OpenJPEG unavailable; Pillow reads values, PDS label supplies geometry'
            elif p.suffix.lower() in ('.tif', '.tiff', '.img'):
                # LOLA's detached PDS label, unlike its IMG, is a GDAL entry point.
                target = p.with_suffix('.lbl') if fam == 'lola_gdr' else p
                row.update(raster_header(target), status='header_read')
            elif p.suffix == '.nc':
                with h5py.File(p) as f:
                    row['attributes'] = {k: clean(f.attrs[k]) for k in (
                        'product_version','time_coverage_start','time_coverage_end',
                        'spatialResolution','spatial_ref','geotransform') if k in f.attrs}
                    row['variables'] = []
                    def collect(n, o):
                        if isinstance(o, h5py.Dataset):
                            row['variables'].append({'name': n, 'shape': list(o.shape), 'dtype': str(o.dtype),
                                'attributes': {k: clean(v) for k, v in o.attrs.items() if k in (
                                'units','long_name','_FillValue','scale_factor','add_offset','valid_range')}})
                    f.visititems(collect)
                    row['status'] = 'variables_read'
            elif p.name.endswith('.tar.gz'):
                row['members'] = []
                with tarfile.open(p) as archive, tempfile.TemporaryDirectory() as tmp:
                    for member in archive:
                        if not member.isfile(): continue
                        item = {'name': member.name, 'bytes': member.size}
                        if member.name.endswith('.tif'):
                            # Only copy a regular member to a controlled temporary filename.
                            copy = Path(tmp) / 'raster.tif'
                            with archive.extractfile(member) as src, copy.open('wb') as dst:
                                shutil.copyfileobj(src, dst)
                            item.update(raster_header(copy))
                            item['diagnostic_patches'] = patches(copy, fam)
                            copy.unlink()
                        row['members'].append(item)
                    row['status'] = 'archive_headers_and_patches_read'
            elif p.suffix == '.zip':
                with zipfile.ZipFile(p) as z: row['member_names'] = z.namelist()
                if fam == 'gmted2010':
                    row.update(raster_header(f'/vsizip/{p}/{p.stem}'), status='archive_header_read')
                elif fam == 'land':
                    import geopandas as gpd
                    g = gpd.read_file(f'zip://{p}')
                    row.update(status='vector_read', feature_count=len(g), crs=g.crs.to_wkt(),
                               columns={k: str(v) for k, v in g.dtypes.items()},
                               bounds=g.total_bounds.tolist(), invalid_geometries=int((~g.is_valid).sum()))
            elif p.suffix in ('.part', '.lock', '.etag'):
                row['status'] = 'operational_or_incomplete_excluded'
        except Exception as e:
            row['status'], row['error_type'] = 'read_error', type(e).__name__
        records.append(row)
        if j % 250 == 0: print('inventory', j, '/', len(paths), flush=True)
    return records


def aoi(lon, lat, side=3000):
    crs = CRS.from_proj4(f'+proj=aeqd +lat_0={lat} +lon_0={lon} +datum=WGS84 +units=m')
    geom = segmentize(box(-side/2, -side/2, side/2, side/2), 100)
    return mapping(transform(Transformer.from_crs(crs, 4326, always_xy=True).transform, geom))


def native_crop(d, geom, src_crs='EPSG:4326', max_cells=12_000_000):
    g = transform(Transformer.from_crs(src_crs, d.crs, always_xy=True).transform, shape(geom))
    if not box(*d.bounds).intersects(g): return None
    win = from_bounds(*g.bounds, d.transform)
    left, top = math.floor(win.col_off), math.floor(win.row_off)
    right, bottom = math.ceil(win.col_off+win.width), math.ceil(win.row_off+win.height)
    if (right-left)*(bottom-top) > max_cells: raise ValueError('Native crop budget exceeded')
    win = Window(left, top, right-left, bottom-top)
    inside = geometry_mask([mapping(g)], (bottom-top, right-left), d.window_transform(win), invert=True)
    return win, inside


def read_crop(d, band, win):
    return d.read(band, window=win, boundless=True, masked=True).astype(float).filled(np.nan)


def native_profiles(records):
    profiles = []
    wanted = {'glo30','worldcover','jrc','srtm','3dep'}
    geometries = {k: aoi(*v) for k, v in CENTERS.items()}
    for rec in records:
        fam = rec['family']
        if fam not in wanted or rec['status'] != 'header_read': continue
        p = ROOT / rec['path']
        with rasterio.open(p) as d:
            for site, geom in geometries.items():
                crop = native_crop(d, geom)
                if crop is None: continue
                win, inside = crop
                raw = read_crop(d, 1, win)
                values = physical(raw, fam, '')
                item = {'site': site, 'source': fam, 'path': rec['path'], 'window_m': 3000,
                        'denominator': 'all native pixel centers in footprint; no land mask',
                        'statistics': stats(values[inside], inside.sum())}
                if fam in ('jrc','worldcover'):
                    item['raw_value_counts'] = counts(raw[inside])
                    if fam == 'worldcover': item['valid_class_counts'] = counts(values[inside])
                profiles.append(item)
    return profiles, geometries


def temporal_profiles(geometries):
    spec = json.loads((ROOT / 'specs/sources/contexto-atlas-2024.json').read_text())
    rows = []
    for site, products in spec['areas'].items():
        for fam in ('hls', 'landsat'):
            if not products[fam]:
                rows.append({'site': site,'source': fam,'status':'no_scene_selected','scene': None})
            for scene in products[fam]:
                bands = (['B03','B04','B05','B06','Fmask'] if '.L30.' in scene else
                         ['B03','B04','B8A','B11','Fmask']) if fam == 'hls' else ['ST_B10','QA_PIXEL','ST_QA']
                paths = [ROOT / 'data/raw/atlas30' / fam / (
                    f'{scene}.{b}.tif' if fam=='hls' else f'{scene.removesuffix("_ST")}_{b}.TIF') for b in bands]
                item = {'site':site, 'source':fam,'scene':scene,'window_m':3000,
                        'paths':[str(p.relative_to(ROOT)) for p in paths], 'status':'profiled',
                        'denominator':'all native pixel centers in footprint; no land mask'}
                arrays=[]
                reference=None
                for p in paths:
                    with rasterio.open(p) as d:
                        grid=(d.crs,d.transform,d.shape)
                        if reference is None:
                            reference=grid
                            crop=native_crop(d,geometries[site])
                            if crop is None: break
                            win, inside=crop
                        elif grid!=reference: raise ValueError('Scene bands have different grids')
                        arrays.append(read_crop(d,1,win))
                        item.setdefault('metadata_selected',{}).update({k:v for k,v in d.tags().items()
                            if k in ('SENSING_TIME','ACCODE','CLOUD_COVERAGE','SPATIAL_COVERAGE')})
                if not arrays:
                    item['status']='outside_scene_extent'; rows.append(item); continue
                n=int(inside.sum()); item['footprint_centers']=n
                item['variables']={b:stats(physical(a,fam,b)[inside],n) for b,a in zip(bands,arrays)}
                if fam=='hls':
                    green,red,nir,swir=[physical(a,fam,b) for a,b in zip(arrays[:4],bands[:4])]
                    qa=arrays[-1]; item['qa_counts']=counts(qa[inside]); policies={}
                    for policy in ('clear','legacy','dry_land'):
                        valid=inside & hls_mask(qa,policy)
                        metrics={}
                        for name,a,b in [('ndvi',nir,red),('ndmi',nir,swir),('ndsi',green,swir)]:
                            ok=valid & np.isfinite(a) & np.isfinite(b) & (np.abs(a+b)>1e-6)
                            v=(a[ok]-b[ok])/(a[ok]+b[ok])
                            metrics[name]={**stats(v,n),'outside_minus1_plus1':int((np.abs(v)>1).sum())}
                        policies[policy]=metrics
                    item['policies']=policies
                    q=np.nan_to_num(qa,nan=255).astype(np.uint16)
                    item['qa_flag_counts']={name:int((inside & (q!=255) & ((q & (1<<bit))!=0)).sum())
                        for bit,name in [(1,'cloud'),(2,'adjacent'),(3,'shadow'),(4,'snow'),(5,'water')]}
                    item['high_aerosol_clear_centers']=int((inside & hls_mask(qa) & ((q>>6)==3)).sum())
                    land_ok=inside & hls_mask(qa,'dry_land') & np.isfinite(red) & np.isfinite(nir)
                    item['ndvi_denominator_diagnostics']={
                        'negative_input_centers':int((land_ok & ((red<0)|(nir<0))).sum()),
                        'small_absolute_sum_counts':{str(t):int((land_ok & (np.abs(red+nir)<=t)).sum())
                                                     for t in (.0001,.001,.01,.05)}}
                else:
                    raw,qa,unc=arrays; temp=physical(raw,fam,'ST_B10'); unc=physical(unc,fam,'ST_QA')
                    item['qa_counts']=counts(qa[inside]); item['policies']={}
                    for label,keep_snow in [('legacy',False),('keep_snow',True)]:
                        ok=inside & landsat_mask(qa,keep_snow) & np.isfinite(temp) & np.isfinite(unc)
                        item['policies'][label]={'temperature_k':stats(temp[ok],n),'uncertainty_k':stats(unc[ok],n)}
                        if label=='legacy':
                            item['uncertainty_sensitivity']={str(t):stats(temp[ok & (unc<=t)],n) for t in (1,2,3)}
                rows.append(item)
    return rows


def material_profiles(geometries):
    cfg=json.loads((ROOT/'specs/analysis/minerales-emit-v1.json').read_text())
    rows=[]
    for scene in cfg['scenes']:
        site='desierto' if scene['site_id']=='earth-utah' else 'atacama-materiales'
        # Existing reader verifies full hashes, pairing and GLT; use the NEW 3 km polygon.
        result=emit.read_scene(scene,geometries[site]); n=result['footprint_cells']
        item={k:result[k] for k in ('product_id','date','footprint_cells','glt_cells','unique_raw_samples')}
        item.update(site=site, window_m=3000, groups={})
        for key,g in result['groups'].items():
            valid=np.asarray(g['usable'],bool)
            ids=np.asarray(g['ids'],float); fit=np.asarray(g['fit'],float)
            depth=np.asarray(g['depth'],float); unc=np.asarray(g['uncertainty'],float)
            item['groups'][key]={'data_cells':g['data_cells'],'matched_cells':g['matched_cells'],
                'no_match_cells':g['no_match_cells'],'class_counts':counts(ids[valid]),
                'classes':g['classes'], 'fit_stored':stats(fit[valid]),
                'fit_times_two':stats(2*fit[valid]),'band_depth':stats(depth[valid]),
                'band_depth_uncertainty':stats(unc[valid]),
                'exploratory_quality_counts':{str(t):int((valid & (2*fit>=t) & (depth>2*unc)).sum()) for t in (.5,.8,.9)},
                'fit_scaling_note':'NASA LP DAAC tutorial restores fit by multiplying by 2; raw value retained. '
                                   'Thresholds are exploratory; version/build and masks need harmonization validation.',
                'fit_scaling_source':'https://nasa.github.io/LPDAAC-Data-Resources/external/Working_with_EMIT_L2B_Mineralogy.html'}
        rows.append(item)
    return rows


def mars_profiles():
    from scripts.analizar_primer_caso import geometry
    cfg=json.loads((ROOT/'specs/analysis/primer-caso-fase2.json').read_text())
    site=cfg['sites'][0]
    # Same explicit Mars sphere as the existing Jezero footprint; a new 3 km AOI.
    geom=geometry(site,dict(cfg,window_m=3000))
    # geometry() returns a feature with the declared planetary CRS.
    if 'geometry' not in geom: raise ValueError('Unexpected Mars geometry')
    crs=geom['properties']['crs_wkt']; rows=[]
    sr=ROOT/'data/raw/crism/frt000047a3/frt000047a3_07_sr166j_mtr3.img'
    info=sr.with_name(sr.name.replace('_sr','_in'))
    with rasterio.open(sr) as d, rasterio.open(info) as q:
        win,inside=native_crop(d,geom['geometry'],crs)
        mask=read_crop(q,9,win); good=inside & (mask==0)
        item={'source':'crism','window_m':3000,'footprint_centers':int(inside.sum()),
              'mask_counts':counts(mask[inside]),'variables':[]}
        for b,name in zip(d.indexes,d.descriptions):
            a=read_crop(d,b,win)
            item['variables'].append({'name':name,**stats(a[good],inside.sum())})
        residual=read_crop(q,q.descriptions.index('ATM Correction Spectral Shift Artifact')+1,win)
        item['atmospheric_residual']=stats(residual[good],inside.sum()); rows.append(item)
    for source,p in [('hirise_dtm',ROOT/site['input']),('themis',ROOT/'data/raw/themis/Jezero_Thermal_Inertia_v1.tiff')]:
        with rasterio.open(p) as d:
            win,inside=native_crop(d,geom['geometry'],crs)
            a=read_crop(d,1,win)
            rows.append({'source':source,'window_m':3000,'path':str(p.relative_to(ROOT)),
                         'statistics':stats(a[inside],inside.sum()),
                         'registration':'nominal CRS transform only; independent coregistration pending'})
    return rows,geom


def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--output',type=Path,default=OUT)
    args=parser.parse_args(); out=args.output; out.mkdir(parents=True,exist_ok=True)
    inv=inventory(); write(out/'inventario.json',inv)
    print('native profiles',flush=True)
    native,geometries=native_profiles(inv); write(out/'perfiles-espaciales.json',native)
    print('temporal profiles',flush=True)
    temporal=temporal_profiles(geometries); write(out/'perfiles-temporales.json',temporal)
    print('material profiles',flush=True)
    materials=material_profiles(geometries); write(out/'perfiles-emit.json',materials)
    mars,mars_geom=mars_profiles(); write(out/'perfiles-marte.json',mars)
    write(out/'huellas.json',{'earth':geometries,'mars':mars_geom,'window_m':3000})
    sampled=[]
    candidates=[r for r in inv if r['status']=='header_read' and r['family'] not in ('hls','landsat')]
    groups=defaultdict(list)
    for r in candidates: groups[r['family']].append(r)
    for fam,entries in groups.items():
        # Deterministic lexicographic spread, not random or area-representative.
        limit=24 if fam=='glo30' else 4
        ix=np.unique(np.linspace(0,len(entries)-1,min(limit,len(entries))).astype(int))
        for i in ix:
            rec=entries[i]; p=ROOT/rec['path']
            target=p.with_suffix('.lbl') if fam=='lola_gdr' else p
            sampled.append({'path':rec['path'],'family':fam,'patches':patches(target,fam)})
    write(out/'muestras-diagnosticas.json',sampled)
    used=set(r['path'] for r in native) | set(r['path'] for r in sampled)
    used.update(p for r in temporal for p in r.get('paths',[]))
    used.update(r['path'] for r in inv if r['family'] in ('emit','crism','hirise','themis',
                'arcticdem_v4_1','rema_v2_0','gmted2010','land'))
    # Hash only interpreted/profiled inputs; the global header inventory retains size/mtime.
    print('hashing interpreted inputs',flush=True)
    identities=[]; by_path={r['path']:r for r in inv}
    for name in sorted(used):
        p=ROOT/name; before=p.stat(); original=by_path[name]
        if (before.st_size,before.st_mtime_ns)!=(original['bytes'],original['mtime_ns']):
            raise ValueError(f'Input changed during exploration: {name}')
        sha=digest(p); after=p.stat()
        if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):
            raise ValueError(f'Input changed during hashing: {name}')
        identities.append({'path':name,'bytes':before.st_size,'sha256':sha})
    write(out/'identidades-entradas.json',identities)
    summary={fam:{'files':len(rs),'bytes':sum(r['bytes'] for r in rs),
                  'statuses':dict(Counter(r['status'] for r in rs))}
             for fam,rs in ((f,[r for r in inv if r['family']==f]) for f in sorted(set(r['family'] for r in inv)))}
    write(out/'resumen.json',{'families':summary,'files':len(inv),'bytes':sum(r['bytes'] for r in inv),
        'header_errors':[r['path'] for r in inv if r['status']=='read_error'],
        'spatial_profiles':len(native),'temporal_records':len(temporal),
        'python':platform.python_version(),'rasterio':rasterio.__version__,'h5py':h5py.__version__,
        'numpy':np.__version__, 'sampling':'native pixel centers; no area weighting; no global inference',
        'inventory_identity':'size and mtime only; no full raw checksum audit',
        'emit_identity':'MIN/MINUNCERT SHA-256 verified by existing reader',
        'diagnostic_patches':'five 32x32 native patches per selected asset; selection is lexicographic',
        'snapshot_date_local':'2026-11-10','timezone':'America/Managua'})
    tracked=[Path(__file__),ROOT/'specs/sources/contexto-atlas-2024.json',
             ROOT/'specs/analysis/minerales-emit-v1.json',ROOT/'specs/analysis/primer-caso-fase2.json',
             ROOT/'scripts/analizar_minerales.py',ROOT/'scripts/analizar_primer_caso.py']
    outputs=[out/name for name in ('inventario.json','perfiles-espaciales.json','perfiles-temporales.json',
             'perfiles-emit.json','perfiles-marte.json','huellas.json','muestras-diagnosticas.json',
             'identidades-entradas.json','resumen.json')]
    # Explicit dependencies prevent a circular/stale manifest when figures already exist.
    write(out/'manifest.json',{'files':[{'path':str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else str(p.resolve()),
                                       'sha256':digest(p),'bytes':p.stat().st_size}
                                      for p in tracked+outputs]})
    print(json.dumps({'files':len(inv),'header_errors':sum(r['status']=='read_error' for r in inv),
                      'output':str(out)},ensure_ascii=False),flush=True)


if __name__=='__main__': main()
