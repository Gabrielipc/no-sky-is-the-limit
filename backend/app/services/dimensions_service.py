"""Build multidimensional surface comparison views."""
from pathlib import Path

from fastapi import HTTPException

from app.repositories import dimensions_repository as repo

SCENARIO_ID = 'superficie-multidimensional'
REFERENCE_ID = 'mars-jezero-fan'
SCENARIO = {
    'id': SCENARIO_ID,
    'name': 'Superficie · dimensiones y evidencia',
    'question': '¿Cómo difieren la irregularidad y las formas del terreno, y qué evidencia existe para otras propiedades?',
    'status': 'exploratory',
    'body': 'Mars',
    'view': 'dimensions',
    'references': [{'id': REFERENCE_ID, 'name': 'Jezero — abanico sedimentario'}],
    'scales_m': [60, 120],
    'window_m': 1800,
    'scope': 'Geometría a escala común; inercia térmica solo en Jezero. Materiales y obstáculos pendientes de evaluación.',
    'comparison_route': '/api/multidimensional',
}
_FILES = frozenset(('resultados.json', 'procesamiento.json', 'manifest-local.json'))
_VALID_CANDIDATES = frozenset(('earth-utah', 'earth-atacama'))


def get_comparison(cell_m: int, candidate_id: str, reference_id: str,
                   evidence_dir: Path | None = None, digest_fn=None) -> dict:
    if reference_id != REFERENCE_ID or cell_m not in SCENARIO['scales_m']:
        raise HTTPException(422, 'Referencia o escala no evaluada en este escenario')
    if candidate_id not in _VALID_CANDIDATES:
        raise HTTPException(422, 'Candidata no evaluada en este escenario')
    result = repo.load_release(evidence_dir, digest_fn)
    try:
        def selected(site_id: str) -> dict:
            site = next(s for s in result['sites'] if s['id'] == site_id)
            return {
                **{k: v for k, v in site.items() if k != 'scales'},
                'scale': next(s for s in site['scales'] if s['cell_m'] == cell_m),
            }
        return {
            'scenario': SCENARIO,
            'cell_m': cell_m,
            'window_m': result['window_m'],
            'neighborhood_radius_m': result['neighborhood_radius_m'],
            'min_coverage': result['min_coverage'],
            'reference': selected(reference_id),
            'candidate': selected(candidate_id),
            'comparison': next(c for c in result['comparisons'] if c['cell_m'] == cell_m and c['candidate_id'] == candidate_id),
            'metrics': result['metrics'],
            'sources': result['sources'],
            'limitations': result['limitations'],
            'combined_score': None,
            'evidence_identity': repo.evidence_digest(evidence_dir),
            'evidence': {name: '/api/multidimensional/evidence/' + name for name in sorted(_FILES)},
        }
    except (KeyError, StopIteration, TypeError) as exc:
        raise HTTPException(503, 'La evidencia multidimensional está incompleta para esta selección.') from exc


def get_sources(evidence_dir: Path | None = None, digest_fn=None) -> dict:
    return {
        'sources': repo.load_release(evidence_dir, digest_fn)['sources'],
        'note': 'Catálogo de investigación; disponibilidad no equivale a evaluación científica.',
    }
