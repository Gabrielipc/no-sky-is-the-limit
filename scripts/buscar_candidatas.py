#!/usr/bin/env python3
"""Bounded regional screening; no global scan or implicit network requests.

Commands: audit, search, detail CANDIDATE_ID [--download]. Uses the reviewed
phase-2 terrain primitives, while preserving its inputs and outputs.
"""
import argparse
import json
import math
import os
from pathlib import Path
import platform
import time
import urllib.request
import zipfile

import numpy as np
import pyproj
import rasterio
from rasterio.transform import from_origin
from rasterio.warp import transform_bounds
from rasterio.windows import Window, from_bounds
from scipy.stats import wasserstein_distance

import analizar_primer_caso as terrain

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / 'specs/search/busqueda-regional-v1.json'
DOCUMENTED_UNITS = 'Meters (USGS FGDC); vertical datum varies by input source, not verified per pixel. No absolute elevation comparison.'
LIMITATIONS = [
    'Preselección exploratoria; los umbrales son decisiones operativas, no criterios científicos validados.',
    'Ventana de 3 km y celdas de 300/600 m: resultados distintos de fase 2 (1,8 km, 60/120 m).',
    'GMTED integra fuentes heterogéneas. No hay máscara de procedencia, rellenos ni precisión local por píxel en este análisis.',
    'Las celdas válidas no demuestran observaciones directas ni ausencia de interpolación.',
    'La malla se muestrea cada 10 km; no inspecciona toda la superficie ni permite afirmar que no existan otras candidatas.',
    'Áreas elegidas en el interior continental; no se aplicó una máscara de tierra/agua. Lagos, infraestructura y acceso siguen sin evaluar.',
    'Geología, térmica, rocas, polvo, agua/hielo y transitabilidad no evaluados. Los controles no son verdad de referencia.',
    'El producto de 30″ se audita como contexto; no rellena vacíos de 7,5″ ni se usa a 300 m. No se incluyen áreas polares.',
]


def load_config(path=DEFAULT_CONFIG):
    cfg = json.loads(Path(path).read_text())
    if not 0 < cfg['max_windows'] <= 5000:
        raise ValueError('Window budget must be between 1 and 5000')
    if cfg['window_m'] <= 0 or cfg['stride_m'] < cfg['window_m'] or not 0 < cfg['min_coverage'] <= 1:
        raise ValueError('Invalid window, stride or coverage')
    if not cfg['scales_m'] or any(c < 250 or cfg['window_m'] % c or cfg['margin_m'] % c or cfg['margin_m'] < c for c in cfg['scales_m']):
        raise ValueError('Scales must be >=250 m and divide the window and margin')
    for area in cfg['areas']:
        w, s, e, n = area['bbox']
        if not (-180 <= w < e <= 180 and -56 < s < n < 84):
            raise ValueError('AOI outside the audited 7.5 arc-second domain')
    return cfg


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.part')
    terrain.write_json(temp, value)
    temp.replace(path)


def archive_uri(spec):
    return '/vsizip/' + str((ROOT / spec['input']).resolve()) + '/' + spec['id'] + '/hdr.adf'


def check_zip(path):
    with zipfile.ZipFile(path) as archive:
        # CRC reads all uncompressed members; no extraction, no archive paths written.
        bad = archive.testzip()
        if bad:
            raise ValueError(f'ZIP CRC failure: {bad}')
        return [{'file': i.filename, 'bytes': i.file_size, 'crc32': f'{i.CRC:08x}'} for i in archive.infolist() if not i.is_dir()]


def native_metadata(ds):
    return {'driver': ds.driver, 'shape': [ds.height, ds.width], 'crs_wkt': ds.crs.to_wkt(),
            'transform': list(ds.transform), 'bounds': list(ds.bounds), 'step_degrees': list(ds.res),
            'nodata': ds.nodata if ds.nodata is not None and math.isfinite(ds.nodata) else None,
            'nodata_encoding': 'NaN' if ds.nodata is not None and not math.isfinite(ds.nodata) else 'numeric',
            'dtype': ds.dtypes[0], 'band_units': ds.units[0],
            'units_assignment': DOCUMENTED_UNITS}


def audit(cfg):
    out = ROOT / cfg['output']
    out.mkdir(parents=True, exist_ok=True)
    plan_path = ROOT / 'data/manifests/plan.json'
    plan = json.loads(plan_path.read_text()) if plan_path.exists() else {'files': []}
    records = []
    for source in cfg['sources']:
        path = ROOT / source['input']
        print(f"Auditing {path.name}: SHA-256 and complete ZIP CRC", flush=True)
        if path.stat().st_size != source['bytes'] or terrain.digest(path) != source['sha256']:
            raise ValueError(f'Unexpected original; never overwritten: {path}')
        members = check_zip(path)
        with zipfile.ZipFile(path) as z:
            for filename in ('metadata.xml', 'prj.adf'):
                (out / f"{source['id']}-{filename}").write_bytes(z.read(source['id'] + '/' + filename))
        with rasterio.open(archive_uri(source)) as ds:
            if ds.crs.to_epsg() != 4326 or list(ds.shape) != source['shape'] or ds.count != 1 or ds.nodata != -32768:
                raise ValueError('Unexpected GMTED metadata')
            if not np.allclose(ds.res, source['arcsec'] / 3600, rtol=1e-7, atol=1e-10):
                raise ValueError('Unexpected angular spacing')
            samples = []
            for name, lon, lat in [('Utah', -110.6, 38.6), ('Atacama', -67.9, -23.8), ('Mojave', -116.1, 35.35),
                                    ('Greenland', -40, 72), ('Antarctica', 0, -80), ('Arctic outside grid', 0, 86), ('Pacific', -140, 0)]:
                row, col = ds.index(lon, lat)
                inside = 0 <= row < ds.height and 0 <= col < ds.width
                data = ds.read(1, window=Window(col - 2, row - 2, 5, 5), masked=True) if inside else np.ma.masked_all((5, 5))
                samples.append({'name': name, 'longitude': lon, 'latitude': lat, 'inside_grid': inside,
                                'valid_cells': int(data.count()), 'sample_cells': int(data.size),
                                'center_m': float(data[2, 2]) if not np.ma.is_masked(data[2, 2]) else None})
            metadata = native_metadata(ds)
        old = next((f for f in plan['files'] if f.get('path') == source['input'].removeprefix('data/raw/')), None)
        reconciliation = {'previous_status': old.get('status') if old else None,
                          'previous_sha256_matches': old.get('sha256') == source['sha256'] if old else None,
                          'previous_bytes_match': old.get('bytes') == source['bytes'] if old else None}
        record = {**source, 'metadata': metadata, 'zip_crc': 'passed_all_members', 'members': members,
                  'coverage_samples': samples, 'manifest_reconciliation': reconciliation}
        records.append(record)
        if old:
            old.update(status='verified_local', bytes=source['bytes'], sha256=source['sha256'],
                       zip_crc='passed_all_members', audit='docs/evidencia-fase-4/auditoria-gmted.json',
                       license='USGS public data; attribution and modifications described in phase-4 documentation')
    report = {'sources': records, 'limitations': LIMITATIONS, 'documentation': cfg['source_documentation'],
              'coverage_interpretation': 'Numeric validity only. Zero is a valid value, also observed in ocean and Greenland samples; no land/observation mask or global coverage percentage inferred.',
              'scope': 'Complete ZIP CRC and local identity, metadata, point-window samples. No global valid-land percentage or independent accuracy validation.'}
    atomic_json(out / 'auditoria-gmted.json', report)
    # Snapshot the reconciled GMTED entries without losing the historical report above.
    atomic_json(out / 'manifiesto-gmted.json', {'files': [f for f in plan['files'] if f.get('source') == 'gmted']})
    if plan_path.exists():
        atomic_json(plan_path, plan)
    return report


def grid_sites(area, cfg):
    w, s, e, n = area['bbox']
    origin = {'body': 'Earth', 'latitude': (s+n)/2, 'longitude': (w+e)/2}
    crs = terrain.local_crs(origin)
    inverse = pyproj.Transformer.from_crs(crs, 'EPSG:4326', always_xy=True)
    xmin, ymin, xmax, ymax = transform_bounds('EPSG:4326', crs, w, s, e, n, densify_pts=41)
    half = cfg['window_m']/2
    # Window containment is checked in geographic coordinates after densifying edges.
    for row, y in enumerate(np.arange(ymin + half, ymax - half + .001, cfg['stride_m'])):
        for col, x in enumerate(np.arange(xmin + half, xmax - half + .001, cfg['stride_m'])):
            lon, lat = inverse.transform(x, y)
            site = {'id': f"{area['id']}-{row:03d}-{col:03d}", 'name': f"{area['name']} · {row:03d}/{col:03d}",
                    'body': 'Earth', 'latitude': lat, 'longitude': lon, 'area_id': area['id'], 'role': 'generated', 'phase2_site_id': None}
            geom = terrain.geometry(site, cfg)
            ring = geom['geometry']['coordinates'][0]
            if all(w <= a <= e and s <= b <= n for a, b in ring):
                yield site


def read_local(ds, site, cfg):
    dst_crs = terrain.local_crs(site)
    half = cfg['window_m']/2 + cfg['margin_m']
    bounds = transform_bounds(dst_crs, ds.crs, -half, -half, half, half, densify_pts=21)
    win = from_bounds(*bounds, ds.transform)
    c, r = math.floor(win.col_off)-2, math.floor(win.row_off)-2
    win = Window(c, r, math.ceil(win.col_off+win.width)+2-c, math.ceil(win.row_off+win.height)+2-r)
    arr = ds.read(1, window=win, boundless=True, masked=True).astype('float64')
    z = arr.filled(np.nan)
    valid = ~np.ma.getmaskarray(arr) & np.isfinite(z)
    if 'valid_range_m' in site:
        lo, hi = site['valid_range_m']; valid &= (z >= lo) & (z <= hi)
    z[~valid] = np.nan
    return z, valid, ds.window_transform(win), ds.crs, dst_crs


def measurements(crop, cfg):
    data, valid, transform, src_crs, dst_crs = crop
    output, distributions = [], {}
    for cell in cfg['scales_m']:
        n, margin = cfg['window_m']//cell, cfg['margin_m']//cell
        half = cfg['window_m']/2 + cfg['margin_m']
        elev, support = terrain.aggregate(data, valid, transform, src_crs, dst_crs,
            from_origin(-half, half, cell, cell), (n+2*margin, n+2*margin), cfg['support_tolerance'])
        z = elev[margin:margin+n, margin:margin+n]
        slope = terrain.slopes(elev, cell)[margin-1:margin-1+n, margin-1:margin-1+n]
        stats = terrain.describe(z, slope, cfg['slope_histogram_edges_deg'])
        stats.update(cell_m=cell, slope_baseline_m=2*cell, window_m=cfg['window_m'])
        output.append(stats)
        distributions[cell] = slope[np.isfinite(slope)]
    return output, distributions


def compare(stats, distributions, ref_stats, ref_distributions):
    output = []
    for st, ref in zip(stats, ref_stats):
        cell = st['cell_m']
        enough = bool(distributions[cell].size and ref_distributions[cell].size)
        output.append({**st, 'slope_wasserstein_deg': float(wasserstein_distance(distributions[cell], ref_distributions[cell])) if enough else None,
                       'candidate_minus_reference_relief_m': st['relief_p95_p5_m']-ref['relief_p95_p5_m'] if st['relief_p95_p5_m'] is not None and ref['relief_p95_p5_m'] is not None else None})
    return output


def filter_reasons(metric, profile, min_coverage):
    reasons = []
    if metric['elevation_coverage'] < min_coverage or metric['slope_coverage'] < min_coverage:
        reasons.append('insufficient_coverage')
    if metric['slope_wasserstein_deg'] is None or metric['candidate_minus_reference_relief_m'] is None:
        reasons.append('missing_measurements')
    if not reasons:
        if metric['slope_wasserstein_deg'] > profile['slope_distance_max_deg']:
            reasons.append('slope_distance_above_threshold')
        if abs(metric['candidate_minus_reference_relief_m']) > profile['abs_relief_difference_max_m']:
            reasons.append('relief_difference_above_threshold')
    return reasons


def ensure_audit(cfg):
    report_path = ROOT / cfg['output'] / 'auditoria-gmted.json'
    report = json.loads(report_path.read_text())
    for source in cfg['sources']:
        record = next(r for r in report['sources'] if r['id'] == source['id'])
        path = ROOT / source['input']
        if record['sha256'] != source['sha256'] or record['zip_crc'] != 'passed_all_members' or path.stat().st_size != source['bytes'] or terrain.digest(path) != source['sha256']:
            raise ValueError('Source changed since audit; rerun audit with reviewed inputs')
    return report


def crop_area(source, area, cfg):
    path = ROOT / 'data/normalized/fase4' / f"{area['id']}-gmted75.tif"
    path.parent.mkdir(parents=True, exist_ok=True)
    # Crops are cheap to regenerate and never trusted as independent originals.
    w, s, e, n = area['bbox']
    with rasterio.open(archive_uri(source)) as ds:
        win = from_bounds(w-.03, s-.03, e+.03, n+.03, ds.transform).round_offsets().round_lengths()
        arr = ds.read(1, window=win, masked=True)
        terrain.save_raster(path, arr.astype('float64').filled(np.nan), ds.crs, ds.window_transform(win))
    return path


def reference_site():
    cfg = json.loads((ROOT/'specs/analysis/primer-caso-fase2.json').read_text())
    site = cfg['sites'][0]
    path = terrain.acquire(site, False)
    return site, path


def screening(cfg, config_path):
    started = time.perf_counter()
    audit_report = ensure_audit(cfg)
    reference, reference_path = reference_site()
    # Reuse independent PDS/binary/georeference controls for the wider reference crop.
    crop = terrain.read_crop(reference_path, reference, cfg)
    ref_stats, ref_distributions = measurements(crop[:5], cfg)
    if any(min(s['elevation_coverage'], s['slope_coverage']) < cfg['min_coverage'] for s in ref_stats):
        raise ValueError('Reference coverage insufficient at screening scale')
    candidates, crop_records, area_summaries = [], [], []
    generated = []
    for area in cfg['areas']:
        for site in grid_sites(area, cfg):
            generated.append(site)
            if len(generated) > cfg['max_windows']:
                raise ValueError('Configured scan exceeds bounded window budget')
    source = next(s for s in cfg['sources'] if s['role'] == 'screening')
    for area in cfg['areas']:
        print(f"Screening {area['id']}", flush=True)
        path = crop_area(source, area, cfg)
        with rasterio.open(path) as ds:
            native = ds.read(1, masked=True)
            crop_records.append({'area_id': area['id'], 'file': str(path.relative_to(ROOT)), 'sha256': terrain.digest(path), 'metadata': native_metadata(ds),
                                 'crop_cells': int(native.size), 'crop_valid_numeric_cells': int(native.count()),
                                 'crop_zero_cells': int(np.ma.filled(native == 0, False).sum()),
                                 'scope': 'Native pixel crop with 0.03-degree margin, not a land or observation mask.'})
            sites = [s for s in generated if s['area_id'] == area['id']]
            sites += [{**s, 'role': 'control'} for s in cfg['controls'] if s['area_id'] == area['id']]
            for site in sites:
                stats, distributions = measurements(read_local(ds, site, cfg), cfg)
                metrics = compare(stats, distributions, ref_stats, ref_distributions)
                for metric in metrics:
                    metric['filter_outcomes'] = {p: filter_reasons(metric, thresholds, cfg['min_coverage'])
                                                 for p, thresholds in cfg['profiles'].items()}
                candidate = {**site, 'evaluation_status': 'regional_only_pending_detail',
                    'metrics': metrics, 'area': terrain.geometry(site, cfg)}
                candidate['detail_plan'] = detail_plan(candidate, cfg)
                candidates.append(candidate)
        geod = pyproj.Geod(ellps='WGS84')
        w, s, e, n = area['bbox']
        aoi_area = abs(geod.polygon_area_perimeter([w,e,e,w,w], [s,s,n,n,s])[0]) / 1e6
        sampled_area = 0.0
        for candidate in candidates:
            if candidate['area_id'] != area['id'] or candidate['role'] != 'generated': continue
            ring = candidate['area']['geometry']['coordinates'][0]
            sampled_area += abs(geod.polygon_area_perimeter(*zip(*ring))[0]) / 1e6
        area_summaries.append({'area_id': area['id'], 'bbox_geodesic_area_km2': aoi_area,
                               'sampled_window_area_km2': sampled_area, 'sampled_fraction': sampled_area/aoi_area,
                               'note': 'Disjoint sampled window footprints; controls excluded. Unsampled gaps remain.'})
    sensitivity = []
    for cell in cfg['scales_m']:
        for profile_id, profile in cfg['profiles'].items():
            for area in cfg['areas']:
                sites = [s for s in candidates if s['role']=='generated' and s['area_id']==area['id']]
                accepted = [s['id'] for s in sites if not filter_reasons(next(m for m in s['metrics'] if m['cell_m']==cell), profile, cfg['min_coverage'])]
                sensitivity.append({'area_id': area['id'], 'cell_m': cell, 'profile': profile_id,
                                    'generated': len(sites), 'accepted': len(accepted), 'accepted_ids': accepted})
    controls = []
    for site in candidates:
        if site['role'] != 'control': continue
        controls.append({'id': site['id'], 'name': site['name'], 'outcomes': [
            {'cell_m': m['cell_m'], 'profile': p, 'reasons': filter_reasons(m, thresholds, cfg['min_coverage'])}
            for m in site['metrics'] for p, thresholds in cfg['profiles'].items()]})
    result = {'search_id': cfg['search_id'], 'config': cfg,
        'reference': {**reference, 'metrics': ref_stats, 'area': terrain.geometry(reference, cfg)},
        'candidates': candidates, 'sensitivity': sensitivity, 'control_filter_outcomes': controls, 'area_summaries': area_summaries,
        'limitations': LIMITATIONS, 'documentation': cfg['source_documentation']}
    out = ROOT / cfg['output']
    atomic_json(out/'candidatas.json', result)
    atomic_json(out/'procesamiento.json', {'config_sha256': terrain.digest(config_path),
        'code_sha256': terrain.digest(Path(__file__)), 'terrain_code_sha256': terrain.digest(ROOT/'scripts/analizar_primer_caso.py'),
        'reference_input': {'file': reference['input'], 'sha256': reference['sha256'], 'crop': crop[5]},
        'source_hashes': {s['id']: s['sha256'] for s in cfg['sources']}, 'regional_crops': crop_records,
        'audit_sha256': terrain.digest(out/'auditoria-gmted.json'),
        'versions': {'python': platform.python_version(), 'numpy': np.__version__, 'rasterio': rasterio.__version__, 'gdal': rasterio.__gdal_version__, 'pyproj': pyproj.__version__},
        'window_count': len(generated), 'control_count': len(cfg['controls']),
        'resources': {'compressed_original_bytes': sum(s['bytes'] for s in cfg['sources']),
                      'regional_crop_bytes': sum((ROOT/r['file']).stat().st_size for r in crop_records),
                      'global_raster_extracted': False, 'network_requests': 0},
        'elapsed_seconds': round(time.perf_counter()-started, 3),
        'method': 'Average elevation and independent complete-support mask; central-difference slope; Wasserstein in degrees and separate relief difference. Local AEQD, no vertical transformation or cross-body reprojection.'})
    publish_manifest(cfg)
    print(f"Generated {len(generated)} regional windows and {len(controls)} controls", flush=True)
    return result


def detail_plan(site, cfg):
    ring = site['area']['geometry']['coordinates'][0]
    half = cfg['window_m']/2 + 240
    crs = terrain.local_crs(site)
    w, s, e, n = transform_bounds(crs, 'EPSG:4326', -half, -half, half, half, densify_pts=21)
    tiles = []
    for lat in range(math.floor(s), math.floor(n)+1):
        for lon in range(math.floor(w), math.floor(e)+1):
            name = f"{'N' if lat>=0 else 'S'}{abs(lat):02d}{'E' if lon>=0 else 'W'}{abs(lon):03d}.tif"
            tiles.append({'filename': name, 'local_file': f'data/raw/srtm/{name}',
                          'url': 'https://opentopography.s3.sdsc.edu/raster/SRTM_GL1/SRTM_GL1_srtm/'+name})
    return {'candidate_id': site['id'], 'tiles': tiles, 'bbox': [w,s,e,n],
            'window_m': cfg['window_m'], 'scales_m': [60,120],
            'status': 'pending_acquisition_and_validation',
            'note': 'SRTM is a proposed detail source for these nonpolar areas; file coverage and units require checks. No implicit download in API.'}


def acquire_detail_tile(tile, download):
    path = ROOT/tile['local_file']
    if path.exists():
        known = json.loads((ROOT/'specs/analysis/primer-caso-fase2.json').read_text())['sites']
        identity = next((s for s in known if s['input'] == tile['local_file']), None)
        if identity and (path.stat().st_size != identity['bytes'] or terrain.digest(path) != identity['sha256']):
            raise ValueError('Known SRTM original changed; original preserved')
        return path
    if not download: raise FileNotFoundError(f"Missing {path.name}; use --download to acquire only the requested detail tile(s)")
    path.parent.mkdir(parents=True,exist_ok=True)
    part = path.with_name(path.name+'.part')
    limit = 50_000_000
    req = urllib.request.Request(tile['url'],headers={'User-Agent':'Analogos-Fase4/1.0'})
    try:
        with urllib.request.urlopen(req,timeout=60) as response, part.open('wb') as f:
            if response.status!=200: raise ValueError('Complete HTTP 200 required')
            size=0
            while block:=response.read(1024*1024):
                size+=len(block)
                if size>limit: raise ValueError('Detail tile exceeds 50 MB budget')
                f.write(block)
        with rasterio.open(part) as ds:
            if ds.crs.to_epsg()!=4326 or ds.count!=1 or ds.shape!=(3601,3601) or not np.allclose(ds.res,1/3600):
                raise ValueError('Unexpected SRTM GL1 tile')
        part.replace(path)
    except Exception:
        part.unlink(missing_ok=True)
        raise
    return path


def detail(cfg, candidate_id, download=False):
    out = ROOT/cfg['output']
    result = json.loads((out/'candidatas.json').read_text())
    site = next((s for s in result['candidates'] if s['id']==candidate_id),None)
    if site is None: raise ValueError('Unknown candidate')
    plan = detail_plan(site,cfg)
    if len(plan['tiles'])>4: raise ValueError('Detail request exceeds four-tile budget')
    paths=[acquire_detail_tile(tile,download) for tile in plan['tiles']]
    from rasterio.merge import merge
    import contextlib
    with contextlib.ExitStack() as stack:
        datasets=[stack.enter_context(rasterio.open(path)) for path in paths]
        for ds in datasets:
            if ds.crs.to_epsg()!=4326 or ds.shape!=(3601,3601) or ds.nodata!=-32768 or not np.allclose(ds.res,1/3600):
                raise ValueError('Unexpected local SRTM; original preserved')
        arr,transform=merge(datasets,bounds=plan['bbox'],nodata=-32768)
    local=ROOT/'data/normalized/fase4'/f'{candidate_id}-detail.tif'
    terrain.save_raster(local,np.where(arr[0]==-32768,np.nan,arr[0]).astype('float64'),'EPSG:4326',transform)
    detail_cfg={**cfg,'scales_m':[60,120],'margin_m':240}
    reference,reference_path=reference_site()
    ref_stats,ref_dist=measurements(terrain.read_crop(reference_path,reference,detail_cfg)[:5],detail_cfg)
    with rasterio.open(local) as ds:
        stats,dist=measurements(read_local(ds,site,detail_cfg),detail_cfg)
    metrics=compare(stats,dist,ref_stats,ref_dist)
    enough=all(min(m['elevation_coverage'],m['slope_coverage'])>=cfg['min_coverage'] for m in metrics+ref_stats)
    report={'candidate_id':candidate_id,'evaluation_status':'locally_evaluated_exploratory' if enough else 'insufficient_detail_coverage',
        'window_m':cfg['window_m'],'reference_metrics':ref_stats,'metrics':metrics,'plan':plan,
        'inputs':[{'file':str(p.relative_to(ROOT)),'sha256':terrain.digest(p),'bytes':p.stat().st_size} for p in paths],
        'source_catalog_sha256':terrain.digest(out/'candidatas.json'),
        'source_config_sha256':terrain.digest(DEFAULT_CONFIG),
        'code_sha256':terrain.digest(Path(__file__)),
        'limitations':['SRTM metres/EGM96 assigned by documented provenance; TIFF lacks vertical CRS and fill provenance.','Exploratory local terrain descriptors, no validated analogue or mobility determination.','3 km window; does not replace 1.8 km phase-2 measurements.']}
    (out/'detalle').mkdir(exist_ok=True)
    atomic_json(out/'detalle'/f'{candidate_id}.json',report)
    publish_manifest(cfg)
    return report


def publish_manifest(cfg):
    out=ROOT/cfg['output']
    names=['auditoria-gmted.json','manifiesto-gmted.json','candidatas.json','procesamiento.json']
    paths=[out/name for name in names if (out/name).exists()]
    paths+=sorted((out/'detalle').glob('*.json')) if (out/'detalle').exists() else []
    paths+=[DEFAULT_CONFIG,Path(__file__),ROOT/'scripts/analizar_primer_caso.py']
    atomic_json(out/'manifest-local.json',{'scope':'Local identity only; paths relative to evidence folder',
        'files':[{'file':os.path.relpath(p,out),'bytes':p.stat().st_size,'sha256':terrain.digest(p)} for p in paths]})


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['audit','search','detail'])
    parser.add_argument('candidate_id',nargs='?')
    parser.add_argument('--download',action='store_true')
    args=parser.parse_args()
    cfg=load_config()
    if args.command=='audit': audit(cfg)
    elif args.command=='search': screening(cfg,DEFAULT_CONFIG)
    elif not args.candidate_id: parser.error('detail requires candidate_id')
    else:
        report=detail(cfg,args.candidate_id,args.download)
        print(report['candidate_id'],report['evaluation_status'])


if __name__=='__main__':
    main()
