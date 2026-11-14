"""Filter, sort, and assemble regional search results."""
from pathlib import Path

from fastapi import HTTPException

from app.repositories import regional_repository as repo

FILES = frozenset(('auditoria-gmted.json', 'manifiesto-gmted.json', 'candidatas.json',
                   'procesamiento.json', 'manifest-local.json'))


def _rows_for(release: dict, area_id: str, cell_m: int, profile: str) -> list[dict]:
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
        rows.append({
            **{k: site[k] for k in ('id', 'name', 'area_id', 'latitude', 'longitude', 'evaluation_status')},
            'metric': metric,
            'filter_reasons': reasons,
            'passes_filter': not reasons,
        })
    rows.sort(key=lambda r: (
        not r['passes_filter'],
        r['metric']['slope_wasserstein_deg'] is None,
        r['metric']['slope_wasserstein_deg'] if r['metric']['slope_wasserstein_deg'] is not None else float('inf'),
        r['id'],
    ))
    return rows


def get_summary(evidence_dir: Path | None = None) -> dict:
    release = repo.load_release(evidence_dir)
    base = evidence_dir if evidence_dir is not None else repo.EVIDENCE
    return {
        **{k: release[k] for k in ('search_id', 'config', 'reference', 'sensitivity',
                                    'control_filter_outcomes', 'area_summaries', 'limitations', 'documentation')},
        'local_evaluations': [
            s['id'] for s in release['candidates']
            if (base / 'detalle' / f"{s['id']}.json").is_file()
            and repo.load_candidate_detail(s, base)['evaluation_status'] == 'locally_evaluated_exploratory'
        ],
    }


def get_candidates(area_id: str, cell_m: int, profile: str,
                   include_excluded: bool, offset: int, limit: int,
                   evidence_dir: Path | None = None) -> dict:
    release = repo.load_release(evidence_dir)
    base = evidence_dir if evidence_dir is not None else repo.EVIDENCE
    all_rows = _rows_for(release, area_id, cell_m, profile)
    visible = all_rows if include_excluded else [r for r in all_rows if r['passes_filter']]
    page = visible[offset:offset + limit]
    for row in page:
        if (base / 'detalle' / f"{row['id']}.json").exists():
            site = next(s for s in release['candidates'] if s['id'] == row['id'])
            row['evaluation_status'] = repo.load_candidate_detail(site, base)['evaluation_status']
    return {
        'search_id': release['search_id'],
        'area_id': area_id,
        'cell_m': cell_m,
        'profile': profile,
        'thresholds': release['config']['profiles'][profile],
        'min_coverage': release['config']['min_coverage'],
        'generated': len(all_rows),
        'accepted': sum(r['passes_filter'] for r in all_rows),
        'insufficient': sum(
            any(x in r['filter_reasons'] for x in ('insufficient_coverage', 'missing_measurements'))
            for r in all_rows
        ),
        'total': len(visible),
        'offset': offset,
        'limit': limit,
        'include_excluded': include_excluded,
        'items': page,
    }


def get_candidate_detail(candidate_id: str, evidence_dir: Path | None = None) -> dict:
    release = repo.load_release(evidence_dir)
    site = next((s for s in release['candidates'] if s['id'] == candidate_id), None)
    if site is None:
        raise HTTPException(404, 'Candidata no incluida en el barrido')
    base = evidence_dir if evidence_dir is not None else repo.EVIDENCE
    return {**site, 'local_detail': repo.load_candidate_detail(site, base)}


def get_geojson_export(area_id: str, cell_m: int, profile: str,
                       include_excluded: bool, evidence_dir: Path | None = None) -> dict:
    release = repo.load_release(evidence_dir)
    rows = _rows_for(release, area_id, cell_m, profile)
    sites = {s['id']: s for s in release['candidates']}
    features = []
    for row in rows:
        if include_excluded or row['passes_filter']:
            features.append({
                'type': 'Feature',
                'geometry': sites[row['id']]['area']['geometry'],
                'properties': {**row, 'cell_m': cell_m, 'profile': profile,
                               'window_m': release['config']['window_m']},
            })
    return {'type': 'FeatureCollection', 'search_id': release['search_id'], 'features': features}
