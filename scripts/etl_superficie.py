#!/usr/bin/env python3
"""Official surface dimensions on demand (`enrichment_surface`, audit 2026-11-14 §2.2 and §3).

Measures aridity (IMERG), soil moisture (SMAP), snow persistence (MOD10A1), permafrost (ESA CCI),
silicate emissivity (ASTER GED), C-band backscatter (OPERA RTC-S1) and MODIS apparent thermal
inertia over the topographic candidates (Jezero and Haworth rankings, as in `etl_puentes.py`)
and over explicit `--site` windows.

Sites are processed in batches of `--batch-size`; each batch is written to the store as soon
as it ends, so an interrupted run resumes with `--skip-measured`. A run that fetches only some
dimensions keeps the values already stored for the others.

Selection bias mitigation (docs/01-vigentes/etapa-actual-armonizacion/Plan de mitigacion del sesgo
de seleccion topografica.md):
  --background-sample N         stratified random windows (all dimensions but the fine ATI)
  --background-cluster-tiles K  K random MODIS tiles x --background-per-tile windows, fine ATI only
  --retriever vista=K           shortlist of K windows proposed by each view (pipelines/etl_retrieval.py)
  --no-topographic-candidates   skip the topographic candidates (e.g. a query with topography at 0)
Every enriched window gets a row in `enrichment_selection` (reason, design, stratum, probability).

Needs `EARTHDATA_TOKEN` (all but permafrost), h5py (`bash scripts/ejecutar_minerales.sh ...`)
and the `libgdal-hdf4` plugin of the Pixi environment for MODIS.

  bash scripts/ejecutar_minerales.sh scripts/etl_superficie.py --dimension aridity --dimension permafrost
"""
from __future__ import annotations

import argparse
from datetime import date
import json
import math
import os
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipelines import etl_sampling as sampling
from pipelines import etl_surface_fetch as fetch
from pipelines.etl_store import FeatureStore
from pipelines.etl_surface_schema import SURFACE_DIMENSIONS

DEFAULT_STORE = Path(os.environ.get('ANALOGOS_FEATURE_STORE_DIR') or (ROOT / 'data/feature_store_v1'))
DEFAULT_EVIDENCE = ROOT / 'docs/evidencia-superficie-oficial/resultados.json'
DIMENSIONS = tuple(SURFACE_DIMENSIONS)


def parse_site(text: str) -> fetch.Site:
    region_id, lon, lat = text.rsplit(':', 2)
    return fetch.Site(region_id, float(lon), float(lat))


ATI = 'apparent_thermal_inertia'
CANDIDATE_DESIGN = 'candidates-topographic-v1'


def store_candidates(store: FeatureStore, arid_limit: int, polar_limit: int) -> list[fetch.Site]:
    from scripts.etl_puentes import candidate_sites
    return [fetch.Site.from_row(r) for r in candidate_sites(store, arid_limit, polar_limit)]


def parse_retriever(text: str) -> tuple[str, int]:
    view, k = text.split('=', 1)
    return view.strip(), int(k)


def parse_weight(text: str) -> tuple[str, float]:
    view, w = text.split('=', 1)
    return view.strip(), float(w)


def plan_jobs(args: argparse.Namespace, store: FeatureStore, dims: list[str]) -> list[dict]:
    """Groups of (sites, dimensions, selection metadata) to enrich, in order."""
    jobs: list[dict] = []
    if args.site:
        jobs.append({'sites': list(args.site), 'dims': dims, 'reason': 'explicit', 'design_id': 'explicit-sites',
                     'meta': {}})
    if not args.sites_only and not args.no_topographic_candidates:
        jobs.append({'sites': store_candidates(store, args.arid_limit, args.polar_limit), 'dims': dims,
                     'reason': 'candidate', 'design_id': CANDIDATE_DESIGN, 'meta': {}})
    counts = dict(args.retriever or [])
    if args.retrieval_total and not args.sites_only:
        from pipelines import etl_retrieval as retrieval
        from pipelines import similarity_ml as sim
        body = retrieval.load_spec()['profiles'].get(args.retrieval_profile, {}).get('body', 'Mars')
        weights = sim.normalize_weights(dict(args.weight or []), sim.load_spec(), body)
        for view, k in retrieval.allocate_by_weights(args.retrieval_total, weights).items():
            counts.setdefault(view, k)
        print(f'Listas cortas por pesos {weights}: {counts}', flush=True)
    if counts and not args.sites_only:
        from pipelines import etl_retrieval as retrieval
        shortlists = retrieval.shortlists(store, counts, profile=args.retrieval_profile,
                                          ref_json=args.retrieval_ref_json, targets=args.target,
                                          check_coverage=args.check_coverage, seed=args.background_seed)
        for view, items in shortlists.items():
            jobs.append({'sites': [fetch.Site.from_row(i) for i in items], 'dims': dims, 'reason': 'retrieval',
                         'design_id': retrieval.design_id(view, args.retrieval_profile),
                         'meta': {i['region_id']: i | {'view': view} for i in items}})
    if (args.background_sample or args.background_cluster_tiles) and not args.sites_only:
        frame = sampling.load_frame(store)
        print(f'Marco de muestreo de fondo: {len(frame)} ventanas', flush=True)
        if args.background_sample:
            items = sampling.stratified_sample(frame, args.background_sample, args.background_seed)
            bg_dims = [d for d in dims if d != ATI or args.background_include_ati]
            if bg_dims:
                jobs.append({'sites': [fetch.Site.from_row(i) for i in items], 'dims': bg_dims, 'reason': 'background',
                             'design_id': sampling.stratified_design_id(args.background_sample, args.background_seed),
                             'meta': {i['region_id']: i for i in items}})
        if args.background_cluster_tiles and ATI in dims:
            items = sampling.cluster_sample(frame, args.background_cluster_tiles, args.background_per_tile,
                                            args.background_seed)
            jobs.append({'sites': [fetch.Site.from_row(i) for i in items], 'dims': [ATI],
                         'reason': 'background_cluster',
                         'design_id': sampling.cluster_design_id(args.background_cluster_tiles,
                                                                 args.background_per_tile, args.background_seed),
                         'meta': {i['region_id']: i for i in items}})
    for job in jobs:
        job['sites'] = list({s.region_id: s for s in job['sites']}.values())
    return jobs


def stored_rows(store: FeatureStore, region_ids: list[str]) -> dict[str, dict]:
    if not region_ids or not any((store.root / 'enrichment' / 'surface').glob('*.parquet')):
        return {}
    with store._connect() as conn:
        cur = conn.execute('SELECT * EXCLUDE (updated_at) FROM enrichment_surface_latest '
                           'WHERE region_id IN (SELECT unnest(?))',
                           [region_ids])
        cols = [c[0] for c in cur.description]
        return {r[0]: dict(zip(cols, r)) for r in cur.fetchall()}


def merge_with_stored(row: dict, previous: dict | None, fetched: set[str]) -> dict:
    """Keep stored values of the dimensions this run did not fetch."""
    if not previous:
        return row
    for dim, cols in SURFACE_DIMENSIONS.items():
        if dim in fetched or previous.get(f'{dim}_status') in (None, 'on_demand_fetchable'):
            continue
        for col in (*cols, f'{dim}_valid_fraction', f'{dim}_status'):
            if col in previous:
                row[col] = previous[col]
    return row


def pending(sites: list[fetch.Site], stored: dict[str, dict], dims: list[str]) -> list[fetch.Site]:
    def done(site: fetch.Site) -> bool:
        prev = stored.get(site.region_id)
        return bool(prev) and all(prev.get(f'{d}_status') not in (None, 'on_demand_fetchable') for d in dims)
    return [s for s in sites if not done(s)]


def run_fetchers(sites: list[fetch.Site], dims: list[str], args: argparse.Namespace) -> list[fetch.FetchResult]:
    start, end = date.fromisoformat(args.start), date.fromisoformat(args.end)
    cache = Path(args.cache_dir)
    calls = {
        'aridity': lambda: fetch.fetch_aridity(sites, start, end, workers=args.workers),
        'soil_moisture': lambda: fetch.fetch_soil_moisture(sites, start, end, step_days=args.smap_step_days,
                                                           workers=args.workers),
        'snow_persistence': lambda: fetch.fetch_snow(sites, start, end, cache, step_days=args.snow_step_days,
                                                     workers=args.workers),
        'permafrost': lambda: fetch.fetch_permafrost(sites, args.permafrost_year),
        'thermal_emissivity': lambda: fetch.fetch_emissivity(sites, workers=args.workers),
        'sar_backscatter': lambda: fetch.fetch_sar(sites, start, end, max_scenes=args.max_scenes,
                                                   workers=args.workers),
        'apparent_thermal_inertia': lambda: fetch.fetch_apparent_thermal_inertia(
            sites, *fetch.season_range(args.ati_year), cache, lst_step_days=args.lst_step_days,
            albedo_step_days=args.albedo_step_days, workers=args.workers),
    }
    results = []
    for dim in dims:
        try:
            result = calls[dim]()
        except Exception as exc:  # a failing product leaves its dimension on_demand_fetchable
            result = fetch.FetchResult(dim, errors=[f'{type(exc).__name__}: {exc}'])
        print(f'  {dim}: {len(result.inputs)}/{len(sites)} ventanas, {len(result.granules)} gránulos'
              + (f', {len(result.errors)} errores' if result.errors else ''), flush=True)
        for error in result.errors[:5]:
            print(f'    ! {error}', flush=True)
        results.append(result)
    return results


def _jsonable(value):
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, (np.floating, np.integer)):
        value = value.item()
    if isinstance(value, float) and math.isnan(value):
        return None
    if hasattr(value, 'isoformat'):
        return value.isoformat()
    return value


def update_evidence(path: Path | None, rows: list[dict], results: list[fetch.FetchResult]) -> None:
    if not path:
        return
    evidence = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {'sites': {}, 'runs': []}
    for row in rows:
        evidence['sites'][row['region_id']] = _jsonable(row)
    evidence['runs'].append(_jsonable({
        'updated_at': fetch.utc_now(),
        'dimensions': {r.dimension: {'period': r.period, 'support': r.support, 'granules': len(r.granules),
                                     'measured_windows': len(r.inputs), 'errors': r.errors[:20]}
                       for r in results},
    }))
    evidence['runs'] = evidence['runs'][-50:]
    path.parent.mkdir(parents=True, exist_ok=True)
    staged = path.with_suffix('.tmp')
    staged.write_text(json.dumps(evidence, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    staged.replace(path)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--store-dir', default=str(DEFAULT_STORE))
    parser.add_argument('--memory-limit', default='4GB')
    parser.add_argument('--threads', type=int, default=os.cpu_count() or 4)
    parser.add_argument('--evidence', default=str(DEFAULT_EVIDENCE), help="Ruta JSON de evidencia ('' para omitir)")
    parser.add_argument('--dimension', action='append', choices=DIMENSIONS, help='Repetible; por defecto todas')
    parser.add_argument('--site', action='append', type=parse_site, help='region_id:lon:lat (repetible)')
    parser.add_argument('--sites-only', action='store_true', help='Solo las ventanas de --site')
    parser.add_argument('--arid-limit', type=int, default=8)
    parser.add_argument('--polar-limit', type=int, default=12)
    parser.add_argument('--skip-measured', action='store_true', help='Omitir ventanas ya medidas en esas dimensiones')
    parser.add_argument('--batch-size', type=int, default=10)
    parser.add_argument('--workers', type=int, default=8)
    parser.add_argument('--start', default='2019-01-01', help='Inicio del periodo (IMERG, SMAP, MOD10A1, OPERA)')
    parser.add_argument('--end', default='2023-12-31')
    parser.add_argument('--smap-step-days', type=int, default=8)
    parser.add_argument('--snow-step-days', type=int, default=4)
    parser.add_argument('--permafrost-year', type=int, default=2023)
    parser.add_argument('--ati-year', type=int, default=2023, help='Año climatológico dic(año-1)-nov(año)')
    parser.add_argument('--lst-step-days', type=int, default=1)
    parser.add_argument('--albedo-step-days', type=int, default=8)
    parser.add_argument('--max-scenes', type=int, default=12)
    parser.add_argument('--cache-dir', default=str(fetch.default_cache_dir()))
    bias = parser.add_argument_group('mitigación del sesgo de selección')
    bias.add_argument('--no-topographic-candidates', action='store_true',
                      help='No incluir las candidatas topográficas (Jezero / Haworth)')
    bias.add_argument('--background-sample', type=int, default=0, help='Ventanas de fondo estratificadas')
    bias.add_argument('--background-include-ati', action='store_true',
                      help='Medir también la ATI fina en la muestra estratificada (caro: ~6 GB por tesela)')
    bias.add_argument('--background-cluster-tiles', type=int, default=0,
                      help='Teselas MODIS al azar para la ATI fina por conglomerados')
    bias.add_argument('--background-per-tile', type=int, default=5)
    bias.add_argument('--background-seed', type=int, default=20261114)
    bias.add_argument('--retriever', action='append', type=parse_retriever, help='vista=K (repetible)')
    bias.add_argument('--retrieval-total', type=int, default=0,
                      help='Repartir N ventanas entre las vistas según los pesos del motor (--weight)')
    bias.add_argument('--weight', action='append', type=parse_weight,
                      help='vista_del_motor=peso (repetible); las no indicadas usan el peso por defecto')
    bias.add_argument('--retrieval-profile', default='arid_mars_surface_v2')
    bias.add_argument('--retrieval-ref-json', help='Referencia con percentiles por feature (motor de similitud)')
    bias.add_argument('--target', action='append', help='vista:columna=percentil (repetible)')
    bias.add_argument('--check-coverage', action='store_true',
                      help='Comprobar en CMR la cobertura del producto de la vista (EMIT para espectral)')
    args = parser.parse_args(argv)

    dims = args.dimension or list(DIMENSIONS)
    store = FeatureStore(Path(args.store_dir), memory_limit=args.memory_limit, threads=args.threads)
    evidence_path = Path(args.evidence) if args.evidence else None
    jobs = plan_jobs(args, store, dims)
    done_in_run: dict[str, set[str]] = {}
    for job in jobs:
        # The design records every selected window, also those measured earlier or by another job.
        store.append_enrichment('selection', sampling.selection_rows(
            [job['meta'].get(s.region_id, {'region_id': s.region_id}) for s in job['sites']],
            job['design_id'], job['reason'], fetch.utc_now(),
            seed=args.background_seed if job['reason'].startswith('background') else None))
        sites = [s for s in job['sites'] if not set(job['dims']) <= done_in_run.get(s.region_id, set())]
        stored = stored_rows(store, [s.region_id for s in sites])
        if args.skip_measured:
            sites = pending(sites, stored, job['dims'])
        print(f"{job['reason']} ({job['design_id']}): {len(sites)} ventanas por medir de {len(job['sites'])}; "
              f"dimensiones: {', '.join(job['dims'])}", flush=True)
        for i in range(0, len(sites), max(args.batch_size, 1)):
            batch = sites[i:i + args.batch_size]
            print(f'Lote {i // args.batch_size + 1}: {len(batch)} ventanas', flush=True)
            results = run_fetchers(batch, job['dims'], args)
            now = fetch.utc_now()
            manifest_id, manifests = fetch.build_manifests(results, now)
            fetched = {r.dimension for r in results}
            stored = stored | stored_rows(store, [s.region_id for s in batch])
            rows = [merge_with_stored(row, stored.get(row['region_id']), fetched)
                    for row in fetch.build_rows(batch, results, manifest_id, now)]
            store.append_enrichment('surface', rows, manifests)
            update_evidence(evidence_path, rows, results)
            for s in batch:
                done_in_run.setdefault(s.region_id, set()).update(job['dims'])
            for row in rows:
                print(f"  {row['region_id']}: " + ' '.join(f"{d}={row[f'{d}_status']}" for d in job['dims']),
                      flush=True)
    store.compact_if_needed('surface')
    store.compact_if_needed('selection')


if __name__ == '__main__':
    main()
