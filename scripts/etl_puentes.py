#!/usr/bin/env python3
"""Laser and radar bridges (audit 2026-11-14, section 3, priority 7).

  icesat2  ICESat-2 ATL08 over the topographic candidates (Jezero and Haworth rankings) and
           the control sites of `specs/sources/puentes-laser-radar-v1.json`.
  rcm      RCM compact polarimetry (CPR) over the control sites, starting with Devon.
  resumen  Agreement between laser and DEM metrics over the measured windows.

Each site is written to the store as soon as it is measured, so an interrupted run resumes
with `--skip-measured`. Evidence is merged into `docs/evidencia-puentes-laser-radar/`.
Run with the analysis environment (h5py): `bash scripts/ejecutar_minerales.sh scripts/etl_puentes.py ...`.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

import numpy as np
import rasterio
from scipy.stats import spearmanr

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipelines import atlas_sources as sources
from pipelines import atlas_topography as topo
from pipelines import etl_altimetry as altimetry
from pipelines import etl_lunar as lunar
from pipelines import etl_radar as radar
from pipelines import etl_sampling as sampling
from pipelines.etl_store import FeatureStore
from scripts.etl_luna import reference_vector
from scripts.etl_pipeline import JEZERO_REF

SPEC_PATH = ROOT / 'specs/sources/puentes-laser-radar-v1.json'
DEFAULT_STORE = Path(os.environ.get('ANALOGOS_FEATURE_STORE_DIR') or (ROOT / 'data/feature_store_v1'))
DEFAULT_EVIDENCE = ROOT / 'docs/evidencia-puentes-laser-radar/resultados.json'
GDAL_ENV = dict(GDAL_DISABLE_READDIR_ON_OPEN='EMPTY_DIR', GDAL_HTTP_MAX_RETRY=5, GDAL_HTTP_RETRY_DELAY=2,
                GDAL_HTTP_TIMEOUT=60, GDAL_HTTP_MULTIRANGE='SINGLE_GET',
                CPL_VSIL_CURL_ALLOWED_EXTENSIONS='.tif,.TIF', GDAL_CACHEMAX=256 * 1024 ** 2)
HAWORTH_SITE = 'haworth-fondo'
CANDIDATE_FIELDS = ('region_id', 'longitude', 'latitude', 'relief_p95_p05_m', 'slope_240m_p50_deg',
                    'slope_240m_p90_deg', 'distance_score', 'scenario_eligibility')


def load_spec(path: Path = SPEC_PATH) -> dict:
    return json.loads(Path(path).read_text(encoding='utf-8'))


def _jsonable(value):
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat() if value.tzinfo else value.isoformat()
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_jsonable(v) for v in value]
    if isinstance(value, (np.floating, np.integer)):
        value = value.item()
    if isinstance(value, float) and math.isnan(value):
        return None
    return value


def candidate_sites(store: FeatureStore, arid_limit: int, polar_limit: int) -> list[dict]:
    """Union of eligible candidates against Jezero (arid) and the Haworth floor (polar)."""
    out: dict[str, dict] = {}
    arid = store.rank_similar(JEZERO_REF['relief_m'], JEZERO_REF['slope_p50_deg'], JEZERO_REF['slope_p90_deg'],
                              limit=arid_limit, profile='arid_mars_surface_v2')
    ref = reference_vector(store, lunar.region_id(HAWORTH_SITE))
    polar = store.rank_similar(ref['relief_p95_p05_m'], ref['slope_240m_p50_deg'], ref['slope_240m_p90_deg'],
                               limit=polar_limit, profile='polar_cold_v1')
    for reference, rows in (('jezero', arid), (HAWORTH_SITE, polar)):
        for rank, r in enumerate(rows, 1):
            site = out.setdefault(r['region_id'], {k: r[k] for k in CANDIDATE_FIELDS if k != 'distance_score'}
                                  | {'kind': 'candidate', 'rankings': {}})
            site['rankings'][reference] = {'rank': rank, 'distance_score': r['distance_score'],
                                           'eligibility': r['scenario_eligibility']}
    return list(out.values())


def control_sites(spec: dict, key: str, only: list[str] | None) -> list[dict]:
    sites = [s | {'kind': 'control'} for s in spec['control_sites'] if s.get(key)]
    if only:
        sites = [s for s in sites if s['id'] in only]
    return sites


def measured_regions(store: FeatureStore, subset: str, status_col: str) -> set[str]:
    edir = store.root / 'enrichment' / subset
    if not any(edir.glob('*.parquet')):
        return set()
    with store._connect() as conn:
        return {r[0] for r in conn.execute(
            f"SELECT region_id FROM enrichment_{subset}_latest WHERE {status_col} <> 'on_demand_fetchable'"
        ).fetchall()}


def load_evidence(path: Path | None) -> dict:
    return json.loads(path.read_text(encoding='utf-8')) if path and path.exists() else {}


def save_evidence(path: Path | None, evidence: dict) -> None:
    if not path:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(_jsonable(evidence), ensure_ascii=False, indent=2, allow_nan=False) + '\n'
    with TemporaryDirectory(dir=path.parent) as tmp:
        staged = Path(tmp) / path.name
        staged.write_text(payload, encoding='utf-8')
        staged.replace(path)


def merge_site(evidence: dict, section: str, entry: dict) -> None:
    rows = [e for e in evidence.get(section, []) if e['site']['region_id'] != entry['site']['region_id']]
    rows.append(entry)
    rows.sort(key=lambda e: (e['site']['kind'], e['site']['region_id']))
    evidence[section] = rows


def update_evidence_site(
    path: Path | None, spec_id: str, section: str, entry: dict, with_summary: bool = False,
) -> dict:
    """Reload evidence from disk before merging so concurrent runs do not overwrite other sections."""
    evidence = load_evidence(path)
    merge_site(evidence, section, entry)
    evidence['spec_id'] = spec_id
    evidence['updated_at'] = datetime.now(timezone.utc).isoformat()
    if with_summary:
        evidence['summary'] = summarize(evidence.get('icesat2', []))
    save_evidence(path, evidence)
    return evidence


def _parse_utc(value) -> datetime:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str) and value:
        dt = datetime.fromisoformat(value)
        return dt.astimezone(timezone.utc) if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    return datetime.min.replace(tzinfo=timezone.utc)


def _store_rows(store: FeatureStore, view_name: str) -> list[dict]:
    with store._connect() as conn:
        return conn.sql(f'SELECT * FROM {view_name}').to_arrow_table().to_pylist()


def _manifests_by_id(store: FeatureStore, manifest_ids: set[str]) -> dict[str, list[dict]]:
    mdir = store.root / 'manifests'
    ids = {m for m in manifest_ids if m and m != 'none'}
    if not ids or not any(mdir.glob('*.parquet')):
        return {}
    pattern = str(mdir / '*.parquet').replace("'", "''")
    escaped = ', '.join("'" + mid.replace("'", "''") + "'" for mid in sorted(ids))
    with store._connect() as conn:
        rows = conn.sql(
            f"SELECT * FROM read_parquet('{pattern}', union_by_name=true) "
            f"WHERE source_manifest_id IN ({escaped}) ORDER BY observation_period, asset_id"
        ).to_arrow_table().to_pylist()
    grouped: dict[str, list[dict]] = {}
    for item in rows:
        grouped.setdefault(item['source_manifest_id'], []).append(item)
    return grouped


def _known_sites_map(
    store: FeatureStore, spec: dict, arid_limit: int, polar_limit: int, region_ids: set[str],
) -> dict[str, dict]:
    by_id: dict[str, dict] = {
        s['region_id']: s
        for s in control_sites(spec, 'icesat2', None) + control_sites(spec, 'rcm', None)
    }
    try:
        for s in candidate_sites(store, arid_limit, polar_limit):
            by_id[s['region_id']] = s
    except SystemExit:
        pass
    missing = sorted(region_ids - set(by_id))
    if missing and any((store.root / 'base').rglob('*.parquet')):
        escaped = ', '.join("'" + rid.replace("'", "''") + "'" for rid in missing)
        with store._connect() as conn:
            rows = conn.sql(
                "SELECT region_id, longitude, latitude, relief_p95_p05_m, slope_240m_p50_deg, "
                "slope_240m_p90_deg, analog_surface_eligibility AS scenario_eligibility "
                f"FROM base_windows WHERE region_id IN ({escaped})"
            ).to_arrow_table().to_pylist()
        background = set(sampling.background_weights(store))
        for r in rows:
            by_id[r['region_id']] = {**r, 'kind': 'background' if r['region_id'] in background else 'candidate'}
    return by_id


def sync_evidence_from_store(
    evidence: dict, store: FeatureStore, spec: dict, arid_limit: int = 8, polar_limit: int = 12,
) -> bool:
    """Merge FeatureStore rows into `evidence` without clobbering existing live diagnostics."""
    alt_rows = _store_rows(store, 'enrichment_altimetry_latest')
    rad_rows = _store_rows(store, 'enrichment_radar_latest')
    if not alt_rows and not rad_rows:
        return False
    manifest_ids = {r['source_manifest_id'] for r in alt_rows + rad_rows}
    manifests = _manifests_by_id(store, manifest_ids)
    sites = _known_sites_map(store, spec, arid_limit, polar_limit, {r['region_id'] for r in alt_rows + rad_rows})
    changed = False
    for section, rows in (('icesat2', alt_rows), ('rcm', rad_rows)):
        existing = {e['site']['region_id']: e for e in evidence.get(section, [])}
        for row in rows:
            rid = row['region_id']
            prev = existing.get(rid)
            if prev is not None and _parse_utc(prev.get('record', {}).get('updated_at')) >= _parse_utc(row.get('updated_at')):
                continue
            site = sites.get(rid, {'region_id': rid, 'kind': 'control' if rid.startswith('control-v1:') else 'candidate'})
            assets = manifests.get(row.get('source_manifest_id', ''), [])
            diag: dict = {'reconstructed_from_store': True}
            if section == 'icesat2':
                diag['granules_found'] = row['granules_found']
                diag['granules_with_data'] = row['granules_with_data']
                diag['granules_used'] = [
                    {'id': a['asset_id'], 'date': a['observation_period'],
                     'etag': a['sha256_or_etag'], 'access_mode': a['access_mode']}
                    for a in assets
                ]
            else:
                diag['scenes_at_point'] = row['scenes_found']
                diag['n_scenes'] = row['n_scenes']
                diag['scenes_used'] = [
                    {'id': a['asset_id'], 'date': a['observation_period'], 'access_mode': a['access_mode']}
                    for a in assets
                ]
            merge_site(evidence, section, {'site': site, 'record': row, 'diagnostics': diag})
            changed = True
    if changed:
        evidence['spec_id'] = spec['spec_id']
        evidence['updated_at'] = datetime.now(timezone.utc).isoformat()
    return changed


def run_icesat2(args: argparse.Namespace) -> None:
    spec = load_spec(Path(args.spec))
    store = FeatureStore(Path(args.store_dir), memory_limit=args.memory_limit, threads=args.threads)
    sites = [] if args.controls_only else candidate_sites(store, args.arid_limit, args.polar_limit)
    sites += control_sites(spec, 'icesat2', args.site)
    now = datetime.now(timezone.utc)
    if sites:
        store.append_enrichment('selection', sampling.selection_rows(
            [{'region_id': s['region_id']} for s in sites if s.get('kind') == 'candidate'],
            'candidates-topographic-v1', 'candidate', now) + sampling.selection_rows(
            [{'region_id': s['region_id']} for s in sites if s.get('kind') == 'control'],
            f"controls-{spec['spec_id']}", 'control', now))
    if args.background_sample and not args.controls_only:
        # Unbiased population for the laser bridge (selection bias mitigation plan, phase B).
        items = sampling.stratified_sample(sampling.load_frame(store), args.background_sample, args.background_seed)
        design = sampling.stratified_design_id(args.background_sample, args.background_seed)
        store.append_enrichment('selection', sampling.selection_rows(items, design, 'background', now,
                                                                     seed=args.background_seed))
        known = {s['region_id'] for s in sites}
        sites += [it | {'kind': 'background'} for it in items if it['region_id'] not in known]
    if args.skip_measured:
        done = measured_regions(store, 'altimetry', 'altimetry_status')
        sites = [s for s in sites if s['region_id'] not in done]
    evidence_path = Path(args.evidence) if args.evidence else None
    inventory = sources.glo_inventory()
    print(f'{len(sites)} sitios para ICESat-2', flush=True)
    with ExitStack() as stack:
        stack.enter_context(rasterio.Env(**GDAL_ENV))
        rasters = topo.Rasters(stack, 'range')
        for site in sites:
            row, manifests, diag = altimetry.extract_altimetry_record(
                site, rasters, inventory, workers=args.workers, max_granules=args.max_granules, access=args.access)
            store.append_enrichment('altimetry', [row], manifests)
            update_evidence_site(evidence_path, spec['spec_id'], 'icesat2',
                                 {'site': site, 'record': row, 'diagnostics': diag}, with_summary=True)
            print(f"{site['region_id']}: {row['altimetry_status']} granulos={row['granules_with_data']}/"
                  f"{row['granules_found']} pares100={row['n_pairs_100m']} "
                  f"P50 láser/DEM={row['laser_slope_100m_p50_deg']}/{row['dem_slope_100m_p50_deg']} "
                  f"dh={row['dem_minus_laser_median_m']} ({diag['read_seconds']} s)", flush=True)
    if evidence_path:
        evidence = load_evidence(evidence_path)
        evidence['summary'] = summarize(evidence.get('icesat2', []))
        save_evidence(evidence_path, evidence)


def run_rcm(args: argparse.Namespace) -> None:
    spec = load_spec(Path(args.spec))
    store = FeatureStore(Path(args.store_dir), memory_limit=args.memory_limit, threads=args.threads)
    sites = control_sites(spec, 'rcm', args.site)
    evidence_path = Path(args.evidence) if args.evidence else None
    months = tuple(int(m) for m in args.months.split(','))
    with ExitStack() as stack:
        stack.enter_context(rasterio.Env(**GDAL_ENV))
        rasters = topo.Rasters(stack, 'range')
        for site in sites:
            row, manifests, diag = radar.extract_radar_record(site, rasters, months=months,
                                                              max_scenes=args.max_scenes, min_scenes=args.min_scenes)
            store.append_enrichment('radar', [row], manifests)
            update_evidence_site(evidence_path, spec['spec_id'], 'rcm',
                                 {'site': site, 'record': row, 'diagnostics': diag})
            print(f"{site['region_id']}: {row['radar_status']} escenas={row['n_scenes']}/{row['scenes_found']} "
                  f"CPR P50={row['rcm_cpr_p50']} P90={row['rcm_cpr_p90']} S1={row['rcm_s1_p50_db']} dB "
                  f"válido={row['rcm_valid_fraction']}", flush=True)


def summarize(entries: list[dict]) -> dict:
    """Laser vs DEM agreement over measured windows (ranks across windows and per-window gaps)."""
    rows = [e['record'] for e in entries if e['record']['altimetry_status'] == 'measured']
    pairs = {
        'slope_100m_p50': ('laser_slope_100m_p50_deg', 'dem_slope_100m_p50_deg'),
        'slope_100m_p90': ('laser_slope_100m_p90_deg', 'dem_slope_100m_p90_deg'),
        'diff_slope_200m': ('laser_diff_slope_200m_p50_deg', 'dem_diff_slope_200m_p50_deg'),
        'diff_slope_600m': ('laser_diff_slope_600m_p50_deg', 'dem_diff_slope_600m_p50_deg'),
    }
    out: dict = {'n_measured': len(rows), 'n_sites': len(entries), 'laser_vs_dem': {}}
    for name, (a, b) in pairs.items():
        vals = [(r[a], r[b]) for r in rows if r[a] is not None and r[b] is not None]
        if len(vals) < 3:
            out['laser_vs_dem'][name] = {'n': len(vals)}
            continue
        la, de = np.array(vals).T
        rho = spearmanr(la, de).statistic
        out['laser_vs_dem'][name] = {
            'n': len(vals), 'spearman_rho': float(rho),
            'median_dem_minus_laser_deg': float(np.median(de - la)),
            'median_ratio_dem_over_laser': float(np.median(de / la)) if np.all(la > 0) else None,
        }
    dh = [r['dem_minus_laser_median_m'] for r in rows if r['dem_minus_laser_median_m'] is not None]
    nmad = [r['dem_minus_laser_nmad_m'] for r in rows if r['dem_minus_laser_nmad_m'] is not None]
    out['height'] = {'median_of_window_medians_m': float(np.median(dh)) if dh else None,
                     'max_abs_window_median_m': float(np.max(np.abs(dh))) if dh else None,
                     'median_of_window_nmad_m': float(np.median(nmad)) if nmad else None}
    return out


def run_summary(args: argparse.Namespace) -> None:
    path = Path(args.evidence)
    evidence = load_evidence(path)
    store_dir = Path(args.store_dir)
    if not args.no_sync_from_store and (
        any((store_dir / 'enrichment' / 'altimetry').glob('*.parquet'))
        or any((store_dir / 'enrichment' / 'radar').glob('*.parquet'))
    ):
        spec = load_spec(Path(args.spec))
        cands_spec = spec.get('candidates', {})
        arid_limit = args.arid_limit if args.arid_limit is not None else int(cands_spec.get('arid_limit', 8))
        polar_limit = args.polar_limit if args.polar_limit is not None else int(cands_spec.get('polar_limit', 12))
        store = FeatureStore(store_dir, memory_limit=args.memory_limit, threads=args.threads)
        sync_evidence_from_store(evidence, store, spec, arid_limit=arid_limit, polar_limit=polar_limit)
    evidence['summary'] = summarize(evidence.get('icesat2', []))
    save_evidence(path, evidence)
    print(json.dumps(evidence['summary'], indent=2, ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--store-dir', default=str(DEFAULT_STORE))
    parser.add_argument('--memory-limit', default='4GB')
    parser.add_argument('--threads', type=int, default=os.cpu_count() or 4)
    parser.add_argument('--spec', default=str(SPEC_PATH))
    parser.add_argument('--evidence', default=str(DEFAULT_EVIDENCE), help="Ruta JSON de evidencia ('' para omitir)")
    sub = parser.add_subparsers(dest='command', required=True)

    p_ice = sub.add_parser('icesat2', help='ATL08 sobre candidatas y controles')
    p_ice.add_argument('--arid-limit', type=int, default=8)
    p_ice.add_argument('--polar-limit', type=int, default=12)
    p_ice.add_argument('--site', action='append', help='Id de sitio de control (repetible)')
    p_ice.add_argument('--controls-only', action='store_true')
    p_ice.add_argument('--skip-measured', action='store_true', help='Omitir ventanas ya guardadas')
    p_ice.add_argument('--background-sample', type=int, default=0,
                       help='Ventanas de fondo estratificadas (población sin sesgo topográfico)')
    p_ice.add_argument('--background-seed', type=int, default=20261114)
    p_ice.add_argument('--workers', type=int, default=16, help='Granulos leídos en paralelo')
    p_ice.add_argument('--max-granules', type=int, default=None, help='Solo los N granulos más recientes')
    p_ice.add_argument('--access', choices=altimetry.ACCESS_MODES, default='harmony',
                       help='harmony: recorte en el servidor (recomendado); direct: granulos completos por rangos')

    p_rcm = sub.add_parser('rcm', help='CPR de RCM compacto en los sitios de control')
    p_rcm.add_argument('--site', action='append', help='Id de sitio de control (repetible)')
    p_rcm.add_argument('--months', default=','.join(map(str, radar.DEFAULT_MONTHS)))
    p_rcm.add_argument('--max-scenes', type=int, default=12)
    p_rcm.add_argument('--min-scenes', type=int, default=1)

    p_res = sub.add_parser('resumen', help='Concordancia láser-DEM en la evidencia')
    p_res.add_argument('--arid-limit', type=int, default=None)
    p_res.add_argument('--polar-limit', type=int, default=None)
    p_res.add_argument('--no-sync-from-store', action='store_true',
                       help='No reconstruir entradas faltantes desde el FeatureStore')

    args = parser.parse_args()
    {'icesat2': run_icesat2, 'rcm': run_rcm, 'resumen': run_summary}[args.command](args)


if __name__ == '__main__':
    main()
