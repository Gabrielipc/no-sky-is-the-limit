#!/usr/bin/env python3
"""Phase 5: bounded, offline source/scale sensitivity scenario.

Reuses reviewed phase-4 windows without changing its release. Missing detail
remains pending; no network acquisition or learned similarity is performed.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import time

import numpy as np
import rasterio
from rasterio.warp import transform_bounds
from scipy.stats import wasserstein_distance

import analizar_primer_caso as terrain
import buscar_candidatas as regional

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / 'specs/scenarios/estabilidad-topografica-v1.json'
SOURCE_CONFIG = ROOT / 'specs/analysis/primer-caso-fase2.json'
PREVIOUS = ROOT / 'docs/evidencia-fase-4'
LIMITATIONS = [
    'Muestra de conveniencia estratificada, condicionada por las teselas locales; no estima tasas de error del catálogo.',
    'GMTED y SRTM pueden compartir observaciones de origen: el contraste entre productos no es una validación independiente ni aísla el efecto del sensor.',
    'Los perfiles heredados de fase 4 solo se aplican a 300/600 m. No se extrapolan a 60/120 m.',
    'Los cambios a escala común describen sensibilidad al producto y procesamiento, no exactitud física. Cambiar escala modifica también la referencia de Jezero.',
    'Cobertura numérica no equivale a observación directa. Resolución efectiva, rellenos y errores locales siguen sin cuantificar.',
    'Geología, térmica, obstáculos, polvo, agua/hielo, acceso y movilidad siguen sin evaluar; no se certifican análogos.',
]


def checked_previous(name):
    entry = next(e for e in json.loads((PREVIOUS/'manifest-local.json').read_text())['files'] if e['file'] == name)
    path = PREVIOUS/name
    if path.stat().st_size != entry['bytes'] or terrain.digest(path) != entry['sha256']:
        raise ValueError(f'Phase-4 evidence changed: {name}')
    return path


def load_config(path=CONFIG):
    cfg = json.loads(Path(path).read_text())
    if (cfg['window_m'] != 3000 or cfg['scales_m'] != [60, 120, 300, 600]
            or cfg['margin_m'] != 600 or cfg['selection_cell_m'] != 300
            or cfg['selection_profile'] != 'baseline' or cfg['per_stratum'] != 1
            or not 1 <= cfg['max_candidates'] <= 20):
        raise ValueError('Unsupported scenario scope or budget')
    return cfg


def detail_plan(site, cfg):
    # Include the 600 m margin required by the coarsest slope stencil.
    plan = regional.detail_plan(site, cfg)
    half = cfg['window_m']/2 + cfg['margin_m']
    bounds = transform_bounds(terrain.local_crs(site), 'EPSG:4326', -half, -half, half, half, densify_pts=41)
    tiles = []
    w, s, e, n = bounds
    for lat in range(math.floor(s), math.floor(n)+1):
        for lon in range(math.floor(w), math.floor(e)+1):
            filename = f"{'N' if lat >= 0 else 'S'}{abs(lat):02d}{'E' if lon >= 0 else 'W'}{abs(lon):03d}.tif"
            tiles.append({'filename': filename, 'local_file': f'data/raw/srtm/{filename}',
                          'url': 'https://opentopography.s3.sdsc.edu/raster/SRTM_GL1/SRTM_GL1_srtm/'+filename})
    return {**plan, 'bbox': list(bounds), 'tiles': tiles, 'margin_m': cfg['margin_m'], 'scales_m': cfg['scales_m']}


def select_cohort(release, cfg, available):
    sites = release['candidates']
    chosen = {s['id']: (s, 'control') for s in sites if s['role'] == 'control'}
    for anchor in cfg['anchors']:
        site = next(s for s in sites if s['id'] == anchor)
        chosen[anchor] = (site, 'phase4_anchor')
    strata = []
    for area in release['config']['areas']:
        for accepted in (True, False):
            pool = [s for s in sites if s['role'] == 'generated' and s['area_id'] == area['id']
                    and (not next(m for m in s['metrics'] if m['cell_m'] == cfg['selection_cell_m'])['filter_outcomes'][cfg['selection_profile']]) == accepted]
            def key(site):
                local = available(detail_plan(site, cfg))
                return (not local if cfg['prefer_local_tiles'] else False,
                        hashlib.sha256(f"{cfg['selection_seed']}:{site['id']}".encode()).hexdigest())
            ordered = sorted(pool, key=key)
            selected = ordered[:cfg['per_stratum']]
            label = 'accepted' if accepted else 'excluded'
            strata.append({'area_id': area['id'], 'decision': label, 'pool_count': len(pool),
                           'locally_available_count': sum(available(detail_plan(s, cfg)) for s in pool),
                           'selected_ids': [s['id'] for s in selected]})
            for site in selected:
                chosen.setdefault(site['id'], (site, label))
    if len(chosen) > cfg['max_candidates']:
        raise ValueError('Cohort exceeds configured budget')
    return [chosen[k] for k in sorted(chosen)], strata


def adequate(metric, minimum):
    return (min(metric['elevation_coverage'], metric['slope_coverage']) >= minimum
            and metric.get('slope_wasserstein_deg') is not None
            and metric.get('candidate_minus_reference_relief_m') is not None)


def read_detail(paths, site, cfg):
    # The bounded cohort uses single reviewed tiles. Cropping directly preserves
    # the native pixel origin; merge(bounds=...) would introduce a shifted grid.
    if len(paths) != 1:
        raise ValueError('This reviewed scenario supports one native SRTM tile per window')
    with rasterio.open(paths[0]) as ds:
        if (ds.crs is None or ds.crs.to_epsg() != 4326 or ds.count != 1 or ds.shape != (3601, 3601)
                or ds.nodata != -32768 or not np.allclose(ds.res, 1/3600)):
            raise ValueError('Unexpected reviewed SRTM metadata')
        return regional.read_local(ds, site, cfg)


def source_contrast(gmted, srtm, gdist, sdist, reference, profiles, minimum):
    """Paired comparison at identical footprints/scales; insufficient is null."""
    output = []
    for old in gmted:
        cell = old['cell_m']
        new = next(m for m in srtm if m['cell_m'] == cell)
        ref = next(m for m in reference if m['cell_m'] == cell)
        enough = (adequate(old, minimum) and adequate(new, minimum)
                  and min(ref['elevation_coverage'], ref['slope_coverage']) >= minimum)
        decisions = {}
        for name, thresholds in profiles.items():
            a = regional.filter_reasons(old, thresholds, minimum)
            b = regional.filter_reasons(new, thresholds, minimum)
            decisions[name] = {'gmted_reasons': a, 'srtm_reasons': b,
                               'changed': (bool(a) != bool(b)) if enough else None}
        output.append({'cell_m': cell, 'status': 'compared_exploratory' if enough else 'insufficient_coverage',
            'candidate_source_wasserstein_deg': float(wasserstein_distance(gdist[cell], sdist[cell])) if enough else None,
            'slope_distance_delta_deg': new['slope_wasserstein_deg']-old['slope_wasserstein_deg'] if enough else None,
            'relief_difference_delta_m': new['candidate_minus_reference_relief_m']-old['candidate_minus_reference_relief_m'] if enough else None,
            'filter_decisions': decisions})
    return output


def run(config_path=CONFIG):
    started = time.perf_counter()
    cfg = load_config(config_path)
    previous_config = checked_previous('../../specs/search/busqueda-regional-v1.json')
    release = json.loads(checked_previous('candidatas.json').read_text())
    checked_previous('procesamiento.json')
    if release['config'] != json.loads(previous_config.read_text()) or release['config']['window_m'] != cfg['window_m']:
        raise ValueError('Incompatible phase-4 footprint/config')
    source_manifest = json.loads((ROOT/'docs/evidencia-fase-2/manifest-local.json').read_text())
    source_entry = next(e for e in source_manifest['files'] if e['file'] == '../../specs/analysis/primer-caso-fase2.json')
    if SOURCE_CONFIG.stat().st_size != source_entry['bytes'] or terrain.digest(SOURCE_CONFIG) != source_entry['sha256']:
        raise ValueError('Reviewed source configuration changed')
    known = json.loads(SOURCE_CONFIG.read_text())['sites']
    # Only reviewed SRTM identities are eligible, even if other local files exist.
    tiles = {s['input']: s for s in known if s['body'] == 'Earth'}
    def available(plan):
        return len(plan['tiles']) == 1 and all(t['local_file'] in tiles and (ROOT/t['local_file']).is_file() for t in plan['tiles'])
    cohort, strata = select_cohort(release, cfg, available)
    eval_cfg = {**release['config'], **{k: cfg[k] for k in ('window_m', 'margin_m', 'scales_m')}}
    reference, ref_path = regional.reference_site()
    ref_crop = terrain.read_crop(ref_path, reference, eval_cfg)
    ref_stats, ref_dist = regional.measurements(ref_crop[:5], eval_cfg)
    if any(min(m['elevation_coverage'], m['slope_coverage']) < eval_cfg['min_coverage'] for m in ref_stats):
        raise ValueError('Insufficient reference coverage')
    source = next(s for s in release['config']['sources'] if s['role'] == 'screening')
    terrain.acquire(source, False)
    inputs = {source['input']: {'file': source['input'], 'bytes': source['bytes'], 'sha256': source['sha256']},
              reference['input']: {'file': reference['input'], 'bytes': reference['bytes'], 'sha256': reference['sha256']}}
    out = ROOT/cfg['output']
    normalized = ROOT/'data/normalized/fase5'
    normalized.mkdir(parents=True, exist_ok=True)
    rows = []
    with rasterio.open(regional.archive_uri(source)) as global_ds:
        for site, selection in cohort:
            plan = detail_plan(site, cfg)
            row = {**{k: site[k] for k in ('id', 'name', 'role', 'area_id', 'latitude', 'longitude', 'area')},
                   'selection': selection, 'plan': plan, 'regional_metrics': site['metrics'],
                   'status': 'pending_detail', 'local_metrics': None, 'source_contrasts': None,
                   'missing_tiles': [t['filename'] for t in plan['tiles'] if t['local_file'] not in tiles or not (ROOT/t['local_file']).is_file()]}
            if available(plan):
                paths = [terrain.acquire(tiles[t['local_file']], False) for t in plan['tiles']]
                crop = read_detail(paths, site, eval_cfg)
                local_path = normalized/f"{site['id']}-srtm.tif"
                terrain.save_raster(local_path, crop[0], crop[3], crop[2])
                stats, dist = regional.measurements(crop, eval_cfg)
                metrics = regional.compare(stats, dist, ref_stats, ref_dist)
                for metric in metrics:
                    if not adequate(metric, eval_cfg['min_coverage']):
                        metric.update(slope_wasserstein_deg=None, candidate_minus_reference_relief_m=None,
                                      status='insufficient_data')
                coarse_cfg = {**eval_cfg, 'scales_m': release['config']['scales_m']}
                coarse_stats, coarse_dist = regional.measurements(regional.read_local(global_ds, site, coarse_cfg), coarse_cfg)
                coarse_metrics = regional.compare(coarse_stats, coarse_dist,
                    [m for m in ref_stats if m['cell_m'] in coarse_cfg['scales_m']], ref_dist)
                # Verify direct archive reads reproduce the released regional crop.
                for measured, old in zip(coarse_metrics, site['metrics']):
                    for key in ('slope_wasserstein_deg', 'candidate_minus_reference_relief_m', 'elevation_coverage', 'slope_coverage'):
                        if not np.isclose(measured[key], old[key], atol=1e-7, rtol=0):
                            raise ValueError(f'Phase-4 reproduction mismatch: {site["id"]}/{key}')
                contrasts = source_contrast(site['metrics'], metrics, coarse_dist, dist, ref_stats,
                                            eval_cfg['profiles'], eval_cfg['min_coverage'])
                enough = all(adequate(m, eval_cfg['min_coverage']) for m in metrics)
                row.update(status='evaluated_exploratory' if enough else 'insufficient_detail_coverage',
                           local_metrics=metrics, source_contrasts=contrasts,
                           crop={'file': str(local_path.relative_to(ROOT)), 'sha256': terrain.digest(local_path)},
                           inputs=[{'file': str(p.relative_to(ROOT)), 'bytes': p.stat().st_size, 'sha256': terrain.digest(p),
                                    'url': tiles[str(p.relative_to(ROOT))]['url'],
                                    'vertical_reference': tiles[str(p.relative_to(ROOT))]['vertical_reference']} for p in paths])
                for item in row['inputs']:
                    inputs[item['file']] = item
            rows.append(row)
            print(site['id'], row['status'], flush=True)
    summary = []
    for cell in release['config']['scales_m']:
        for profile in eval_cfg['profiles']:
            comparisons = [next(c for c in r['source_contrasts'] if c['cell_m'] == cell)['filter_decisions'][profile]['changed']
                           for r in rows if r['source_contrasts'] is not None]
            summary.append({'cell_m': cell, 'profile': profile, 'paired_count': sum(c is not None for c in comparisons),
                            'changed_count': sum(c is True for c in comparisons)})
    result = {'scenario': cfg, 'window_m': cfg['window_m'], 'reference': {**reference, 'metrics': ref_stats},
              'source_catalog_sha256': terrain.digest(PREVIOUS/'candidatas.json'), 'strata': strata,
              'candidates': rows, 'summary': summary, 'limitations': LIMITATIONS,
              'method': {'source_comparison': 'Misma ventana, celda y referencia; SRTM menos GMTED en las diferencias frente a Jezero. Wasserstein adicional entre pendientes terrestres de ambos productos.',
                         'scale_comparison': 'SRTM y DTM HiRISE agregados de nuevo a cada escala; 60/120 m sin filtros heredados.',
                         'native_grid': 'Recorte por ventanas nativas, sin desplazar el origen de píxel al crear mosaicos. No sustituye el detalle de fase 4, que usó merge con límites geográficos.',
                         'missing': 'Pendiente o insuficiente produce null, nunca cero ni mala semejanza.',
                         'selection': cfg['selection_policy'], 'score': 'Sin puntuación combinada ni etiquetas de analogía.'},
              'expansion_decisions': [
                  {'id': 'scenario', 'status': 'implemented', 'reason': 'Pregunta explícita, fuentes locales verificadas y contraste pareado reproducible.'},
                  {'id': 'moon_and_polar', 'status': 'deferred', 'reason': 'Esta evidencia no establece una pregunta lunar/polar ni comparabilidad y cobertura local verificadas.'},
                  {'id': 'ml', 'status': 'deferred', 'reason': 'Sin etiquetas independientes, partición geográfica ni evaluación que demuestre mejora sobre la línea base.'},
                  {'id': 'distributed_infrastructure', 'status': 'deferred', 'reason': 'La fase 4 midió unos 9,3 s para 970 ventanas; este lote acotado no demuestra necesidad de distribución.'}]}
    regional.atomic_json(out/'resultados.json', result)
    regional.atomic_json(out/'procesamiento.json', {'config_sha256': terrain.digest(config_path),
        'source_catalog_sha256': result['source_catalog_sha256'], 'inputs': list(inputs.values()),
        'reference_crop': ref_crop[5], 'elapsed_seconds': round(time.perf_counter()-started, 3),
        'resources': {'selected': len(rows), 'evaluated': sum(r['status'] == 'evaluated_exploratory' for r in rows),
                      'pending': sum(r['status'] == 'pending_detail' for r in rows), 'network_requests': 0,
                      'crop_bytes': sum(p.stat().st_size for p in normalized.glob('*-srtm.tif'))},
        'versions': {'python': platform.python_version(), 'numpy': np.__version__, 'rasterio': rasterio.__version__, 'gdal': rasterio.__gdal_version__}})
    paths = [out/'resultados.json', out/'procesamiento.json', config_path, SOURCE_CONFIG, Path(__file__),
             ROOT/'scripts/buscar_candidatas.py', ROOT/'scripts/analizar_primer_caso.py']
    regional.atomic_json(out/'manifest-local.json', {'scope': 'Identidad local; no autenticidad ni validación científica.',
        'files': [{'file': os.path.relpath(p, out), 'bytes': p.stat().st_size, 'sha256': terrain.digest(p)} for p in paths]})
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=CONFIG)
    args = parser.parse_args()
    run(args.config.resolve())
