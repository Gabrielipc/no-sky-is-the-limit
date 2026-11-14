"""Reviewed multidimensional release. Requests do not download or process rasters."""
import hashlib
import json
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT/'docs/evidencia-dimensiones'
CONFIG = ROOT/'specs/scenarios/superficie-multidimensional-v1.json'
SCENARIO_ID = 'superficie-multidimensional'
REFERENCE_ID = 'mars-jezero-fan'
SCENARIO = {
    'id': SCENARIO_ID, 'name': 'Superficie · dimensiones y evidencia',
    'question': '¿Cómo difieren la irregularidad y las formas del terreno, y qué evidencia existe para otras propiedades?',
    'status': 'exploratory', 'body': 'Mars', 'view': 'dimensions',
    'references': [{'id': REFERENCE_ID, 'name': 'Jezero — abanico sedimentario'}],
    'scales_m': [60, 120], 'window_m': 1800,
    'scope': 'Geometría a escala común; inercia térmica solo en Jezero. Materiales y obstáculos pendientes de evaluación.',
    'comparison_route': '/api/multidimensional',
}
FILES = frozenset(('resultados.json', 'procesamiento.json', 'manifest-local.json'))
router = APIRouter(prefix='/api/multidimensional', tags=['Dimensiones de superficie'])


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_release():
    try:
        manifest = json.loads((EVIDENCE/'manifest-local.json').read_text())
        entries = {item['file']: item for item in manifest['files']}
        expected = {EVIDENCE/'resultados.json', EVIDENCE/'procesamiento.json', CONFIG,
                    ROOT/'specs/analysis/primer-caso-fase2.json',
                    ROOT/'docs/investigacion-dimensiones/catalogo-fuentes.json',
                    ROOT/'scripts/analizar_dimensiones.py', ROOT/'scripts/analizar_primer_caso.py'}
        paths = {(EVIDENCE/key).resolve() for key in entries}
        if manifest['schema'] != 1 or paths != {p.resolve() for p in expected} or len(entries) != len(expected):
            raise ValueError('Manifest inventory mismatch')
        for key, item in entries.items():
            path = (EVIDENCE/key).resolve()
            if path.stat().st_size != item['bytes'] or digest(path) != item['sha256']:
                raise ValueError('Evidence identity mismatch')
        cfg = json.loads(CONFIG.read_text())
        result = json.loads((EVIDENCE/'resultados.json').read_text())
        processing = json.loads((EVIDENCE/'procesamiento.json').read_text())
        if (cfg['scenario_id'] != SCENARIO_ID or result['scenario_id'] != SCENARIO_ID
                or cfg['scales_m'] != SCENARIO['scales_m'] or result['scales_m'] != cfg['scales_m']
                or result['window_m'] != cfg['window_m'] or processing['config'] != cfg
                or processing['config_sha256'] != digest(CONFIG)):
            raise ValueError('Configuration mismatch')
        return result
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise HTTPException(503, 'La evidencia multidimensional falta o cambió. Ejecuta scripts/analizar_dimensiones.py y revisa su resultado.') from exc


def comparison_view(cell_m, candidate_id, reference_id=REFERENCE_ID):
    if reference_id != REFERENCE_ID or cell_m not in SCENARIO['scales_m']:
        raise HTTPException(422, 'Referencia o escala no evaluada en este escenario')
    if candidate_id not in ('earth-utah', 'earth-atacama'):
        raise HTTPException(422, 'Candidata no evaluada en este escenario')
    result = load_release()
    try:
        def selected(site_id):
            site = next(s for s in result['sites'] if s['id'] == site_id)
            return {**{k: v for k, v in site.items() if k != 'scales'},
                    'scale': next(s for s in site['scales'] if s['cell_m'] == cell_m)}
        return {'scenario': SCENARIO, 'cell_m': cell_m, 'window_m': result['window_m'],
                'neighborhood_radius_m': result['neighborhood_radius_m'], 'min_coverage': result['min_coverage'],
                'reference': selected(reference_id), 'candidate': selected(candidate_id),
                'comparison': next(c for c in result['comparisons'] if c['cell_m'] == cell_m and c['candidate_id'] == candidate_id),
                'metrics': result['metrics'], 'sources': result['sources'], 'limitations': result['limitations'],
                'combined_score': None, 'evidence_identity': digest(EVIDENCE/'resultados.json'),
                'evidence': {name: '/api/multidimensional/evidence/'+name for name in sorted(FILES)}}
    except (KeyError, StopIteration, TypeError) as exc:
        raise HTTPException(503, 'La evidencia multidimensional está incompleta para esta selección.') from exc


@router.get('')
def comparison(cell_m: int = Query(60), candidate_id: str = 'earth-utah', reference_id: str = REFERENCE_ID):
    return comparison_view(cell_m, candidate_id, reference_id)


@router.get('/sources')
def sources():
    return {'sources': load_release()['sources'], 'note': 'Catálogo de investigación; disponibilidad no equivale a evaluación científica.'}


@router.get('/evidence/{filename}')
def evidence(filename: str):
    if filename not in FILES:
        raise HTTPException(404, 'Evidencia no disponible')
    load_release()
    return FileResponse(EVIDENCE/filename, headers={'X-Content-Type-Options': 'nosniff'})
