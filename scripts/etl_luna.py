#!/usr/bin/env python3
"""Lunar references in the feature store (audit 2026-11-14, section 2.1).

  referencia  Measure the topographic contract and the lunar dimensions of the sites in
              `specs/sources/luna-polar-sur-v1.json` and write them to the store.
  rank        Rank Earth windows against a stored lunar reference with the same features.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys

import rasterio

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipelines import etl_eligibility as eligibility
from pipelines import etl_lunar as lunar
from pipelines.etl_store import FeatureStore

DEFAULT_STORE = ROOT / 'data/feature_store_v1'
DEFAULT_EVIDENCE = ROOT / 'docs/evidencia-luna-polar/resultados.json'
GDAL_ENV = dict(GDAL_DISABLE_READDIR_ON_OPEN='EMPTY_DIR', GDAL_HTTP_MAX_RETRY=5, GDAL_HTTP_RETRY_DELAY=2,
                GDAL_HTTP_TIMEOUT=60, GDAL_HTTP_MULTIRANGE='SINGLE_GET', CPL_VSIL_CURL_ALLOWED_EXTENSIONS='.TIF,.tif')
REFERENCE_FIELDS = (
    'relief_p95_p05_m', 'slope_240m_p50_deg', 'slope_240m_p90_deg', 'roughness_360m_p50_m',
    *lunar.extractors.SHAPE_FEATURE_KEYS,
)


def _jsonable(row: dict) -> dict:
    return {k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in row.items()}


def measure_site(site: dict, spec: dict, now: datetime) -> tuple[dict, dict, list[dict], dict]:
    dem = {**spec['sources'][site['dem_source']], 'id': site['dem_source']}
    base, manifests, base_diag = lunar.extract_lunar_window(site, dem, now)
    dims, dim_manifests, dim_diag = lunar.extract_lunar_dimensions(site, base, spec, now)
    position = lunar.check_site_position(site, spec)
    return base, dims, manifests + dim_manifests, {'base': base_diag, 'dimensions': dim_diag,
                                                   'site_position_check': position}


def run_reference(args: argparse.Namespace) -> None:
    spec = lunar.load_spec(Path(args.spec))
    sites = [lunar.site_by_id(spec, s) for s in args.site] if args.site else spec['sites']
    if not sites:
        raise SystemExit('La especificación no define sitios lunares')
    store = FeatureStore(Path(args.store_dir), memory_limit=args.memory_limit, threads=args.threads)
    now = datetime.now(timezone.utc)
    out = Path(args.evidence) if args.evidence else None
    # Merge into existing evidence: re-measured sites are replaced, other sites and keys kept.
    evidence = json.loads(out.read_text(encoding='utf-8')) if out and out.exists() else {}
    evidence.update(spec_id=spec['spec_id'], measured_at=now.isoformat())
    measured = {s['id'] for s in sites}
    evidence['sites'] = [e for e in evidence.get('sites', []) if e['site']['id'] not in measured]
    with rasterio.Env(**GDAL_ENV):
        for site in sites:
            base, dims, manifests, diag = measure_site(site, spec, now)
            store.write_base_batch(base['batch_id'], [base], [m for m in manifests if m['source_manifest_id'] == base['source_manifest_id']])
            store.append_enrichment('lunar', [dims], [m for m in manifests if m['source_manifest_id'] == dims['source_manifest_id']])
            evidence['sites'].append({'site': site, 'base_window': _jsonable(base), 'lunar_dimensions': _jsonable(dims),
                                      'diagnostics': diag})
            print(f"{base['region_id']}: {base['qa_status']} relieve={base['relief_p95_p05_m']} "
                  f"P50={base['slope_240m_p50_deg']} P90={base['slope_240m_p90_deg']} "
                  f"PSR={dims['psr_fraction']} -> {dims['lunar_site_status']}", flush=True)
    if out:
        evidence['sites'].sort(key=lambda e: e['site']['id'])
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(evidence, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
        print(f'Evidencia: {out}', flush=True)


def reference_vector(store: FeatureStore, region_id: str) -> dict:
    with store._connect() as conn:
        cur = conn.execute(
            f"SELECT body, qa_status, {', '.join(REFERENCE_FIELDS)} FROM base_windows WHERE region_id = ?",
            [region_id],
        )
        found = cur.fetchone()
        if found is None:
            raise SystemExit(f'No existe la referencia {region_id}; ejecuta primero `referencia`')
        row = dict(zip([c[0] for c in cur.description], found))
    if row['body'] != 'Moon' or row['qa_status'] != 'rankable':
        raise SystemExit(f"{region_id} no es una referencia lunar medible ({row['body']}, {row['qa_status']})")
    return row


def run_rank(args: argparse.Namespace) -> None:
    store = FeatureStore(Path(args.store_dir), memory_limit=args.memory_limit, threads=args.threads)
    ref = reference_vector(store, lunar.region_id(args.site))
    results = store.rank_similar(
        ref_relief_m=ref['relief_p95_p05_m'], ref_slope_p50_deg=ref['slope_240m_p50_deg'],
        ref_slope_p90_deg=ref['slope_240m_p90_deg'], limit=args.limit,
        only_eligible=not args.include_ineligible, profile=args.profile,
        ref_hypsometric_integral=ref['hypsometric_integral'],
    )
    print(json.dumps({'reference': {'region_id': lunar.region_id(args.site), **ref},
                      'profile': args.profile, 'candidates': results}, indent=2, ensure_ascii=False, default=str))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--store-dir', default=str(DEFAULT_STORE))
    parser.add_argument('--memory-limit', default='6GB')
    parser.add_argument('--threads', type=int, default=os.cpu_count() or 4)
    sub = parser.add_subparsers(dest='command', required=True)

    p_ref = sub.add_parser('referencia', help='Medir sitios lunares y guardarlos en el almacén')
    p_ref.add_argument('--spec', default=str(lunar.SPEC_PATH))
    p_ref.add_argument('--site', action='append', help='Id de sitio (repetible); por defecto todos')
    p_ref.add_argument('--evidence', default=str(DEFAULT_EVIDENCE), help="Ruta JSON de evidencia ('' para omitir)")

    p_rank = sub.add_parser('rank', help='Ventanas terrestres frente a una referencia lunar')
    p_rank.add_argument('--site', required=True)
    p_rank.add_argument('--profile', choices=tuple(eligibility.PROFILES), default='polar_cold_v1')
    p_rank.add_argument('--limit', type=int, default=15)
    p_rank.add_argument('--include-ineligible', action='store_true')

    args = parser.parse_args()
    {'referencia': run_reference, 'rank': run_rank}[args.command](args)


if __name__ == '__main__':
    main()
