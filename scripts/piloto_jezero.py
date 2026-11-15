#!/usr/bin/env python3
"""Prepare, measure, evaluate and package the opt-in Jezero pilot."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile

import httpx
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipelines import jezero_context, jezero_evaluation as evaluation, jezero_spectral as spectral, similarity_ml as sim
from pipelines.etl_store import eligibility_expression
from pipelines.spectral_bridge import MEASURED_STATUSES

FORMAT = 'jezero-multivista-v1'
CMR = 'https://cmr.earthdata.nasa.gov/search/granules.umm_json'


def read(path: Path):
    return json.loads(path.read_text(encoding='utf-8'))


def write(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        try:
            json.dump(data, stream, ensure_ascii=False, allow_nan=False, indent=2)
            stream.write('\n')
            stream.close()
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)


def download_catalog(boxes: list[list[float]]) -> list[dict]:
    """Find concrete L2A v002 reflectance/mask pairs and their published polygons."""
    with httpx.Client(timeout=30) as client:
        results = {}
        for bbox in boxes:
            params = {'version': '002', 'bounding_box': ','.join(map(str, bbox)), 'page_size': 200}
            catalogs = {}
            for short in ('EMITL2ARFL', 'EMITL2AMASK'):
                after = {}
                entries = []
                while True:
                    response = client.get(CMR, params=params | {'short_name': short}, headers=after)
                    response.raise_for_status()
                    items = response.json()['items']
                    entries.extend(item['umm'] for item in items)
                    cursor = response.headers.get('CMR-Search-After')
                    if not cursor or len(items) < params['page_size']:
                        break
                    after = {'CMR-Search-After': cursor}
                catalogs[short] = entries

            def asset(umm: dict, prefix: str) -> str | None:
                return next((r['URL'] for r in umm['RelatedUrls'] if r['Type'] == 'GET DATA'
                             and Path(r['URL']).name.startswith(prefix) and r['URL'].endswith('.nc')), None)

            masks = {}
            for scene in catalogs['EMITL2AMASK']:
                url = asset(scene, 'EMIT_L2A_MASK_002_')
                if url:
                    masks[Path(url).name.split('_')[4]] = url
            for scene in catalogs['EMITL2ARFL']:
                url = asset(scene, 'EMIT_L2A_RFL_002_')
                if not url:
                    continue
                scene_id = Path(url).stem
                mask = masks.get(scene_id.split('_')[4])
                geo = scene['SpatialExtent']['HorizontalSpatialDomain']['Geometry']
                polygons = []
                for poly in geo.get('GPolygons', []):
                    coords = [[p['Longitude'], p['Latitude']] for p in poly['Boundary']['Points']]
                    if coords and coords[0] != coords[-1]:
                        coords.append(coords[0])
                    if len(coords) >= 4:
                        polygons.append([coords])
                if mask and polygons:
                    results[scene_id] = {'id': scene_id, 'body': 'Earth', 'reflectance_url': url, 'mask_url': mask,
                                         'geometry': {'type': 'MultiPolygon', 'coordinates': polygons}}
    return [results[k] for k in sorted(results)]


def design(args) -> dict:
    inventory = read(args.inventory)
    earth_scenes = [s for s in inventory['scenes'] if s['body'] == 'Earth']
    frame = spectral.earth_frame(args.store, earth_scenes, inventory['holdouts'], args.profile)
    groups = {key: [r for r in frame if r['partition'] == key] for key in ('fit', 'test')}
    sampled = spectral.design_sample(groups['fit'], args.train_count, evaluation.SEED)
    sampled.update(spectral.design_sample(groups['test'], args.test_count, evaluation.SEED + 1))
    for row in frame:
        row.update(sampled.get(row['region_id'], {}))
    manual = inventory['sites']
    scenes = {s['id']: s for s in inventory['scenes']}
    if len(scenes) != len(inventory['scenes']):
        raise ValueError('Identificadores de escena repetidos')
    if len([r for r in manual if r['role'] == 'reference' and r['body'] == 'Mars']) != 1:
        raise ValueError('Se requiere una única referencia marciana')
    if len({r['region_id'] for r in manual}) != len(manual):
        raise ValueError('Identificadores de sitio repetidos')
    earth_blocked_scenes = {s for row in groups['test'] for s in row['scene_ids']}
    from shapely.geometry import Point, box, shape
    buffered = [box(*b['bbox']).buffer(spectral.SPATIAL_BUFFER_DEG)
                for b in [spectral.MOJAVE, *inventory['holdouts']]]
    for row in manual:
        if not row['scene_ids'] or any(scenes[s]['body'] != row['body'] for s in row['scene_ids']):
            raise ValueError('Escena incompatible con el cuerpo del sitio')
        if row['body'] == 'Earth':
            if row['role'] != 'control' or any(b.covers(Point(row['longitude'], row['latitude'])) for b in buffered):
                raise ValueError('Los controles terrestres deben estar fuera de los bloques reservados')
            if any(s in earth_blocked_scenes or any(b.intersects(shape(scenes[s]['geometry'])) for b in buffered)
                   for s in row['scene_ids']):
                raise ValueError('Una escena de prueba no puede medir controles de ajuste')
        row.update(partition='fit', block='controls')
    return {'format': FORMAT, 'profile': args.profile, 'seed': evaluation.SEED, 'holdouts': inventory['holdouts'],
            'scenes': scenes, 'frame': frame, 'sites': manual,
            'samples': {p: sum('inclusion_probability' in r for r in g) for p, g in groups.items()}}


def measure(args) -> dict:
    plan = read(args.design)
    token = os.environ.get('EARTHDATA_TOKEN')
    rows = [r for r in plan['frame'] if 'inclusion_probability' in r] + plan['sites']
    if args.site:
        requested = set(args.site)
        rows = [r for r in rows if r['region_id'] in requested]
        if {r['region_id'] for r in rows} != requested:
            raise ValueError('Algún sitio solicitado no está en el diseño')
    if any(r['body'] == 'Earth' for r in rows) and not token:
        raise ValueError('Se requiere EARTHDATA_TOKEN para las escenas EMIT')
    observations, failures = [], []
    design_hash = digest(args.design)
    if args.output.exists():
        previous = read(args.output)
        if previous['design_sha256'] != design_hash:
            raise ValueError('Las observaciones existentes pertenecen a otro diseño')
        observations, failures = previous['observations'], previous['failures']
    done = {r['region_id'] for r in observations}
    completed_pairs = {(r['region_id'], r['scene_id']) for r in observations}
    for row in rows:
        if row['role'] != 'control' and row['region_id'] in done:
            continue
        products = []
        for scene_id in row['scene_ids']:
            if (row['region_id'], scene_id) in completed_pairs:
                continue
            try:
                observation = spectral.measure(row, plan['scenes'][scene_id], args.input_root, token)
                products.append(observation)
                if row['role'] != 'control' and all(r['status'] in MEASURED_STATUSES
                                                   for r in observation['indicators'].values()):
                    break
            except (ValueError, OSError, httpx.HTTPError) as exc:
                # Keep the error class and status, without URLs or request headers.
                failure = {'region_id': row['region_id'], 'scene_id': scene_id, 'error': type(exc).__name__}
                response = getattr(exc, 'response', None)
                if response is not None:
                    failure['http_status'] = response.status_code
                if failure not in failures:
                    failures.append(failure)
        if row['role'] == 'control':
            observations.extend(products)
        elif products:
            observations.append(max(products, key=lambda r: (
                sum(e['status'] in MEASURED_STATUSES for e in r['indicators'].values()),
                r['sample']['valid_fraction'], r['scene_id'])))
        write(args.output, {'format': FORMAT, 'design_sha256': design_hash,
                            'observations': observations, 'failures': failures})
    return {'format': FORMAT, 'design_sha256': design_hash, 'observations': observations, 'failures': failures}


def digest(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def make_reference(path: Path, expected: dict, spec: dict):
    ref = read(path)
    if any(abs(float(ref[key]) - expected[key]) > 1e-6 for key in ('longitude', 'latitude')):
        raise ValueError('El centro del DTM debe coincidir con el centro espectral de Jezero')
    features = {f.id for f in sim.parse_features(spec).values() if f.view in evaluation.TOP_WEIGHTS}
    if (ref['window_m'] != spectral.TOPOGRAPHIC_SIDE or not ref.get('source')
            or not features <= ref['features'].keys() or not all(np.isfinite(ref['features'][f]) for f in features)):
        raise ValueError('La referencia topográfica necesita procedencia y descriptores de la huella de 3 km')
    return sim.reference_from_dict({'id': 'jezero', 'name': 'Jezero — abanico sedimentario', 'body': 'Mars',
                                    'features': ref['features']}, spec)


def scores(engine, store, profile, reference, ids, with_gmm=True) -> dict:
    if ids is not None and not ids:
        return {'results': []}
    weights = evaluation.topo_weights(engine.spec, with_gmm)
    return engine.search(store, reference, weights=weights, profile=profile, limit=len(ids) if ids else 100,
                         region_ids=ids)


def distance_map(result: dict) -> dict:
    return {r['region_id']: r['score'] for r in result['results']}


def diagnostic_spec(plan: dict | None = None) -> dict:
    spec = sim.load_spec()
    spec['fit']['covariance_by_view'] = {'escabrosidad': {'estimator': 'ledoit_wolf'}}
    if plan:
        from shapely.geometry import box, shape
        holdouts = [spectral.MOJAVE, *plan['holdouts']]
        boundaries = [box(*r['bbox']).buffer(spectral.SPATIAL_BUFFER_DEG) for r in holdouts]
        held_scenes = [shape(s['geometry']) for s in plan['scenes'].values() if s['body'] == 'Earth']
        spec['fit']['holdout_basins'] = [
            {'id': b['id'], 'bbox': list(g.bounds)} for b, g in zip(holdouts, boundaries)]
        # Use enclosing bounds for the topographic fit, so scenes reserved by the
        # spectral fit cannot leak through the baseline either.
        spec['fit']['holdout_basins'] += [
            {'id': f'emit-holdout-{i}', 'bbox': list(g.buffer(spectral.SPATIAL_BUFFER_DEG).bounds)}
            for i, g in enumerate(held_scenes) if any(g.intersects(b) for b in boundaries)]
    return spec


def stability(store, spec, profile, reference, ids=None, observations=None, sample_size=None) -> dict:
    current = deepcopy(spec)
    current['fit'].pop('covariance_by_view', None)
    variants = {'r2c_method': (current, True), 'fixed': (spec, True), 'fixed_without_gmm': (spec, False)}
    report = {name: {} for name in variants} | ({'combined': {}} if observations is not None else {})
    baseline = {}
    for seed in [evaluation.SEED, *evaluation.STABILITY_SEEDS]:
        models = [sim.SimilarityEngine(sim.fit_model(store, s, seed=seed, sample_size=sample_size), s)
                  for s in (current, spec)]
        for name, (cfg, with_gmm) in variants.items():
            top = distance_map(scores(models[0 if cfg is current else 1], store, profile, reference, ids, with_gmm))
            if name == 'fixed_without_gmm':
                stable_top = top
            save_stability_rank(name, seed, top, baseline, report)
        if observations is not None:
            metric, _ = evaluation.fit_spectral(observations, seed)
            earth = [r for r in observations if r['body'] == 'Earth' and r['role'] == 'background']
            distances = metric.score(earth) if metric else np.full(len(earth), np.nan)
            spectral_scores = {r['region_id']: float(d) for r, d in zip(earth, distances) if np.isfinite(d)}
            save_stability_rank('combined', seed, evaluation.combine(stable_top, spectral_scores), baseline, report)
    target = 'combined' if observations is not None else 'fixed_without_gmm'
    return {'pass': all(v['top100'] >= 80 and v['ranked'] >= 100 for v in report[target].values()),
            'sample_size': sample_size, 'by_variant': report, 'required_top100_overlap': 80}


def save_stability_rank(name, seed, distances, baseline, report):
    ranked = evaluation.rank(distances)
    if seed == evaluation.SEED:
        baseline[name] = ranked
        return
    report[name][str(seed)] = {f'top{k}': len(set(ranked[:k]) & set(baseline[name][:k])) for k in (10, 100)}
    report[name][str(seed)].update(ranked=len(ranked), ties=len(distances) - len(set(distances.values())))


def validate_observations(plan: dict, observations: list[dict]) -> None:
    planned = {r['region_id']: r for r in plan['frame'] if 'inclusion_probability' in r}
    planned.update({r['region_id']: r for r in plan['sites']})
    keys = set()
    for measurement in observations:
        rid, scene = measurement['region_id'], measurement['scene_id']
        row = planned.get(rid)
        if row is None or scene not in row['scene_ids'] or (rid, scene) in keys:
            raise ValueError('Observación duplicada o fuera del diseño congelado')
        fields = ('body', 'block', 'partition', 'role', 'longitude', 'latitude', 'inclusion_probability',
                  'geologic_unit')
        if (any(measurement.get(k) != row.get(k) for k in fields)
                or measurement['spectral_side_m'] != spectral.SPECTRAL_SIDE):
            raise ValueError('La observación cambió de partición, coordenadas, soporte o peso de muestreo')
        keys.add((rid, scene))


def evaluate(args) -> dict:
    plan, measurements = read(args.design), read(args.measurements)
    if measurements['design_sha256'] != digest(args.design):
        raise ValueError('El diseño cambió después de medir')
    observations = measurements['observations']
    validate_observations(plan, observations)
    if args.budget < 1:
        raise ValueError('El presupuesto de recuperación debe ser positivo')
    metric, support = evaluation.fit_spectral(observations)
    evidence = {'format': FORMAT, 'profile': plan['profile'], 'status': 'diagnostic',
                'support': support, 'measurement_failures': len(measurements['failures']),
                'design_sha256': digest(args.design), 'measurements_sha256': digest(args.measurements)}
    if metric is None:
        return evidence
    spec = diagnostic_spec(plan)
    mars = next(r for r in observations if r['role'] == 'reference')
    ref = make_reference(args.aligned_reference, mars, spec)
    observed = [r for r in observations if r['body'] == 'Earth' and r['role'] == 'background']
    spectral_scores = {r['region_id']: float(d) for r, d in zip(observed, metric.score(observed)) if np.isfinite(d)}
    test = [r for r in plan['frame'] if r['partition'] == 'test' and 'inclusion_probability' in r]
    ids = [r['region_id'] for r in test]
    engine = sim.SimilarityEngine(sim.fit_model(args.store, spec), spec)
    stable = distance_map(scores(engine, args.store, plan['profile'], ref, ids, with_gmm=False))
    original = sim.SimilarityEngine.load(args.r2c_model)
    legacy = distance_map(scores(original, args.store, plan['profile'], 'jezero', ids))
    combined = evaluation.combine(stable, spectral_scores)
    evidence['proxy'] = 'Ridge entrenado fuera de la reserva con emisividad gruesa y precipitación'
    proxy = evaluation.proxy_scores(plan['frame'], spectral_scores)
    evidence['retrieval'] = evaluation.retrieval_metrics(test, stable, proxy, spectral_scores, args.budget)
    evidence['relevance'] = evaluation.relevance_metrics(
        test, {'r2c': legacy, 'topography': stable, 'spectral': spectral_scores, 'combined': combined},
        read(args.reviews) if args.reviews else [])
    if args.blind_sheet:
        ids_for_review = set(legacy) & set(combined)
        sheet = [dict(region_id=r['region_id'], longitude=r['longitude'], latitude=r['latitude'])
                 for r in test if r['region_id'] in ids_for_review]
        np.random.default_rng(evaluation.SEED).shuffle(sheet)
        write(args.blind_sheet, sheet)
    if args.run_stability:
        evidence['stability'] = stability(args.store, spec, plan['profile'], ref, ids, observations)
    elif evidence['relevance']['pass'] and evidence['retrieval']['pass']:
        evidence['stability'] = {'pass': False, 'reason': 'Falta repetir el ajuste combinado con diez semillas'}
    if all(evidence.get(key, {}).get('pass') for key in ('retrieval', 'relevance', 'stability')):
        evidence['status'] = 'publishable_experiment'
    shortlist = evaluation.proposal_union(test, stable, proxy, args.budget, evaluation.SEED)
    evidence['rankings'] = {}
    for name, distances in (('topography', stable), ('combined', combined)):
        selected = shortlist if name == 'combined' else evaluation.rank(distances)[:args.budget]
        by_id = {r['region_id']: r for r in test if r['region_id'] in selected and r['region_id'] in distances}
        evidence['rankings'][name] = [
            {'region_id': rid, 'score': distances[rid], 'longitude': by_id[rid]['longitude'],
             'latitude': by_id[rid]['latitude'], 'block': by_id[rid]['block'],
             'views': {'topografia': stable.get(rid), 'espectral': spectral_scores.get(rid)}}
            for rid in evaluation.rank({rid: distances[rid] for rid in by_id})]
    evidence['coverage'] = {'windows': len(test), 'spectral_windows': sum(i in spectral_scores for i in ids),
                            'bounds': [dict(id=b['id'], bbox=b['bbox'])
                                       for b in [spectral.MOJAVE, *plan['holdouts']]]}
    evidence['weights'] = evaluation.COMBINED
    evidence['reference'] = {'id': 'jezero', 'longitude': mars['longitude'], 'latitude': mars['latitude'],
                             'spectral_side_m': spectral.SPECTRAL_SIDE, 'topographic_side_m': spectral.TOPOGRAPHIC_SIDE}
    return evidence


def publish(args) -> dict:
    report = read(args.report)
    if (report.get('format') != FORMAT or report['status'] != 'publishable_experiment'
            or not all(report.get(k, {}).get('pass') for k in ('support', 'retrieval', 'relevance', 'stability'))):
        raise ValueError('El piloto todavía es diagnóstico y no puede servirse')
    if not re.fullmatch(r'jezero-r3-[a-z0-9-]+', args.version):
        raise ValueError('La versión debe comenzar por jezero-r3-')
    target = args.root / args.version
    if target.exists():
        raise ValueError('La versión ya existe')
    if digest(args.design) != report['design_sha256'] or digest(args.measurements) != report['measurements_sha256']:
        raise ValueError('El diseño o las mediciones cambiaron después de evaluar')
    plan, measurements = read(args.design), read(args.measurements)
    used_scenes = {r['scene_id'] for r in measurements['observations']}
    manifest = {'format': FORMAT, 'version': args.version, 'status': 'experimental',
                'baseline': 'etl-30m-r2c', 'evaluation_sha256': digest(args.report),
                'design_sha256': report['design_sha256'], 'measurements_sha256': report['measurements_sha256']}
    args.root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.jezero-', dir=args.root) as staging_root:
        staging = Path(staging_root) / args.version
        staging.mkdir()
        write(staging / 'manifest.json', manifest)
        write(staging / 'jezero.json', report | manifest)
        write(staging / 'observations.json', measurements)
        write(staging / 'provenance.json', {'holdouts': plan['holdouts'], 'sample': plan['samples'],
                                           'scenes': [plan['scenes'][s] for s in sorted(used_scenes)]})
        staging.rename(target)
    return manifest


def audit(args) -> dict:
    expr = eligibility_expression('polar_cold_v1')
    with sim.connect(args.store) as conn:
        counts = conn.execute(f"""SELECT CASE WHEN latitude < 0 THEN 'sur' ELSE 'norte' END,
                   ({expr}) AS cause, count(*) FROM features_unified
                   WHERE body = 'Earth' AND qa_status = 'rankable' GROUP BY 1, 2 ORDER BY 1, 2""").fetchall()
        lunar = conn.execute("""SELECT region_id, illumination_mean_fraction, psr_fraction, diviner_tmax_p50_k,
                                slope_240m_p90_deg FROM features_unified
                                WHERE body = 'Moon' ORDER BY region_id""").fetchall()
    return {'hemispheres': [{'hemisphere': h, 'cause': c, 'windows': n} for h, c, n in counts],
            'rankable_windows': sum(n for _, _, n in counts),
            'lunar_windows': [dict(region_id=rid, illumination_fraction=light, psr_fraction=shadow,
                                   diviner_tmax_p50_k=tmax, slope_p90_deg=slope)
                              for rid, light, shadow, tmax, slope in lunar]}


def canonical_topography() -> dict:
    site = read(ROOT / 'specs/analysis/primer-caso-fase2.json')['sites'][0]
    ref = sim.load_spec()['references']['jezero']
    return {'longitude': site['longitude'], 'latitude': site['latitude'], 'window_m': spectral.TOPOGRAPHIC_SIDE,
            'source': ref['source'], 'features': ref['features']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest='action', required=True)
    command = actions.add_parser('catalog')
    command.add_argument('--bbox', type=float, nargs=4, action='append', required=True)
    command = actions.add_parser('design')
    command.add_argument('--inventory', type=Path, required=True)
    command.add_argument('--train-count', type=int, default=1000)
    command.add_argument('--test-count', type=int, default=300)
    command.add_argument('--profile', choices=spectral.PROFILES, default=spectral.PROFILES[0])
    command = actions.add_parser('measure')
    command.add_argument('--design', type=Path, required=True)
    command.add_argument('--input-root', type=Path, required=True)
    command.add_argument('--site', action='append')
    command = actions.add_parser('evaluate')
    command.add_argument('--design', type=Path, required=True)
    command.add_argument('--measurements', type=Path, required=True)
    command.add_argument('--r2c-model', type=Path, required=True)
    command.add_argument('--aligned-reference', type=Path, required=True)
    command.add_argument('--reviews', type=Path)
    command.add_argument('--blind-sheet', type=Path)
    command.add_argument('--budget', type=int, default=100)
    command.add_argument('--run-stability', action='store_true')
    command = actions.add_parser('stability')
    command.add_argument('--sample-size', type=int)
    command = actions.add_parser('audit')
    actions.add_parser('reference')
    command = actions.add_parser('themis')
    command.add_argument('--raster', type=Path, required=True)
    command = actions.add_parser('antarctic')
    command.add_argument('--outcrops', type=Path, required=True)
    command.add_argument('--rema', required=True)
    command.add_argument('--center', nargs=2, type=float, required=True, metavar=('LON', 'LAT'))
    command = actions.add_parser('publish')
    command.add_argument('--report', type=Path, required=True)
    command.add_argument('--design', type=Path, required=True)
    command.add_argument('--measurements', type=Path, required=True)
    command.add_argument('--root', type=Path, required=True)
    command.add_argument('--version', required=True)
    for name in ('design', 'evaluate', 'stability', 'audit'):
        actions.choices[name].add_argument('--store', type=Path, required=True)
    for name in actions.choices:
        if name != 'publish':
            actions.choices[name].add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    handlers = {'catalog': lambda a: {'scenes': download_catalog(a.bbox)}, 'design': design, 'measure': measure,
                'evaluate': evaluate, 'publish': publish, 'audit': audit,
                'reference': lambda a: canonical_topography(),
                'themis': lambda a: jezero_context.themis(a.raster, *[
                    canonical_topography()[k] for k in ('longitude', 'latitude')]),
                'antarctic': lambda a: jezero_context.antarctic(a.outcrops, a.rema, *a.center),
                'stability': lambda a: stability(a.store, diagnostic_spec(), spectral.PROFILES[0],
                                                  'jezero', sample_size=a.sample_size)}
    result = handlers[args.action](args)
    if args.action != 'publish':
        write(args.output, result)
    print(json.dumps({'action': args.action, 'output': str(getattr(args, 'output', '')),
                      'status': result.get('status', 'ok')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
