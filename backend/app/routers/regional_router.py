"""Read-only browsing of the bounded, reproducible phase-4 search release."""
import hashlib
import json
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse

ROOT = Path(__file__).resolve().parents[3]
EVIDENCE = ROOT / 'docs/evidencia-fase-4'
CONFIG = ROOT / 'specs/search/busqueda-regional-v1.json'
router = APIRouter(prefix='/api/regional-search', tags=['Búsqueda regional exploratoria'])
FILES = frozenset(('auditoria-gmted.json', 'manifiesto-gmted.json', 'candidatas.json',
                   'procesamiento.json', 'manifest-local.json'))


def checked_path(filename):
    path = EVIDENCE / filename
    if filename == 'manifest-local.json':
        if not path.is_file():
            raise FileNotFoundError(filename)
        return path
    manifest = json.loads((EVIDENCE/'manifest-local.json').read_text())
    entry = next(e for e in manifest['files'] if e['file'] == filename)
    if path.stat().st_size != entry['bytes'] or hashlib.sha256(path.read_bytes()).hexdigest() != entry['sha256']:
        raise ValueError('Release identity mismatch')
    return path


def load_release():
    try:
        checked_path('../../specs/search/busqueda-regional-v1.json')
        payload = json.loads(checked_path('candidatas.json').read_text())
        config = json.loads(CONFIG.read_text())
        if config != payload['config'] or payload['search_id'] != config['search_id']:
            raise ValueError('Release/config mismatch')
        return payload
    except (OSError, ValueError, KeyError, TypeError, StopIteration) as exc:
        raise HTTPException(503, 'La búsqueda regional falta o cambió. Ejecuta y revisa la auditoría y la generación de fase 4.') from exc


def rows_for(release, area_id, cell_m, profile):
    if area_id not in [a['id'] for a in release['config']['areas']]:
        raise HTTPException(422, 'Área no incluida en este barrido')
    if cell_m not in release['config']['scales_m'] or profile not in release['config']['profiles']:
        raise HTTPException(422, 'Escala o perfil no evaluados')
    rows = []
    for site in release['candidates']:
        if site['area_id'] != area_id or site['role'] != 'generated':
            continue
        metric = next(m for m in site['metrics'] if m['cell_m'] == cell_m)
        reasons = metric['filter_outcomes'][profile]
        rows.append({**{k: site[k] for k in ('id', 'name', 'area_id', 'latitude', 'longitude', 'evaluation_status')},
                     'metric': metric, 'filter_reasons': reasons, 'passes_filter': not reasons})
    # A single dimension determines display order; there is no combined score.
    rows.sort(key=lambda r: (not r['passes_filter'], r['metric']['slope_wasserstein_deg'] is None,
                            r['metric']['slope_wasserstein_deg'] if r['metric']['slope_wasserstein_deg'] is not None else float('inf'), r['id']))
    return rows


def detail_for(site):
    path = EVIDENCE / 'detalle' / f"{site['id']}.json"
    if not path.exists():
        return {'candidate_id': site['id'], 'evaluation_status': 'pending_detail', 'metrics': None,
                'plan': site['detail_plan']}
    try:
        detail = json.loads(checked_path(f"detalle/{site['id']}.json").read_text())
        if detail['candidate_id'] != site['id'] or detail['source_catalog_sha256'] != hashlib.sha256((EVIDENCE/'candidatas.json').read_bytes()).hexdigest():
            raise ValueError('Detail belongs to another release')
        return detail
    except (OSError, ValueError, KeyError, TypeError, StopIteration) as exc:
        raise HTTPException(503, 'La evaluación de detalle está incompleta o no corresponde al barrido actual.') from exc


@router.get('')
def summary():
    release = load_release()
    return {**{k: release[k] for k in ('search_id', 'config', 'reference', 'sensitivity',
                                      'control_filter_outcomes', 'area_summaries', 'limitations', 'documentation')},
            'local_evaluations': [s['id'] for s in release['candidates']
                                  if (EVIDENCE/'detalle'/f"{s['id']}.json").is_file()
                                  and detail_for(s)['evaluation_status'] == 'locally_evaluated_exploratory']}


@router.get('/candidates')
def candidates(area_id: str = 'utah', cell_m: int = 300,
               profile: Literal['strict', 'baseline', 'relaxed'] = 'baseline',
               include_excluded: bool = False, offset: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=100)):
    release = load_release()
    all_rows = rows_for(release, area_id, cell_m, profile)
    rows = all_rows if include_excluded else [r for r in all_rows if r['passes_filter']]
    page = rows[offset:offset+limit]
    for row in page:
        if (EVIDENCE/'detalle'/f"{row['id']}.json").exists():
            row['evaluation_status'] = detail_for(next(s for s in release['candidates'] if s['id'] == row['id']))['evaluation_status']
    return {'search_id': release['search_id'], 'area_id': area_id, 'cell_m': cell_m, 'profile': profile,
            'thresholds': release['config']['profiles'][profile], 'min_coverage': release['config']['min_coverage'],
            'generated': len(all_rows), 'accepted': sum(r['passes_filter'] for r in all_rows),
            'insufficient': sum(any(x in r['filter_reasons'] for x in ('insufficient_coverage', 'missing_measurements')) for r in all_rows),
            'total': len(rows), 'offset': offset, 'limit': limit, 'include_excluded': include_excluded, 'items': page}


@router.get('/candidates/{candidate_id}')
def candidate_detail(candidate_id: str):
    release = load_release()
    site = next((s for s in release['candidates'] if s['id'] == candidate_id), None)
    if site is None:
        raise HTTPException(404, 'Candidata no incluida en el barrido')
    return {**site, 'local_detail': detail_for(site)}


@router.get('/export')
def export(area_id: str = 'utah', cell_m: int = 300,
           profile: Literal['strict', 'baseline', 'relaxed'] = 'baseline', include_excluded: bool = False):
    release = load_release()
    rows = rows_for(release, area_id, cell_m, profile)
    sites = {s['id']: s for s in release['candidates']}
    features = []
    for row in rows:
        if include_excluded or row['passes_filter']:
            features.append({'type': 'Feature', 'geometry': sites[row['id']]['area']['geometry'],
                             'properties': {**row, 'cell_m': cell_m, 'profile': profile, 'window_m': release['config']['window_m']}})
    return JSONResponse({'type': 'FeatureCollection', 'search_id': release['search_id'], 'features': features},
                        media_type='application/geo+json',
                        headers={'Content-Disposition': f'attachment; filename="{area_id}-{cell_m}m-{profile}.geojson"'})


@router.get('/evidence/{filename}')
def evidence(filename: str):
    if filename not in FILES:
        raise HTTPException(404, 'Evidencia no disponible')
    try:
        path = checked_path(filename)
    except (OSError, ValueError, KeyError, TypeError, StopIteration) as exc:
        raise HTTPException(503, 'Archivo de evidencia ausente o modificado.') from exc
    return FileResponse(path, headers={'X-Content-Type-Options': 'nosniff'})
