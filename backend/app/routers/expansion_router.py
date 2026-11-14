"""Read-only phase-5 source/scale sensitivity evidence; no raster or network IO."""
import hashlib
import json
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.routers import regional_router as regional

ROOT = Path(__file__).resolve().parents[3]
EVIDENCE = ROOT/'docs/evidencia-fase-5'
CONFIG = ROOT/'specs/scenarios/estabilidad-topografica-v1.json'
SCENARIO = {
    'id': 'estabilidad-topografica',
    'name': 'Reconocimiento topográfico · sensibilidad a fuente y escala',
    'question': '¿Se conservan las decisiones regionales al cambiar de producto y qué cambia con la escala?',
    'status': 'exploratory', 'body': 'Mars', 'view': 'stability',
    'references': [{'id': 'mars-jezero-fan', 'name': 'Jezero — abanico sedimentario'}],
    'scales_m': [60, 120, 300, 600], 'window_m': 3000,
    'scope': 'Muestra estratificada de fase 4; sensibilidad entre productos, sin validación de movilidad.',
    'comparison_route': '/api/expansion',
}
FILES = frozenset(('resultados.json', 'procesamiento.json', 'manifest-local.json'))
router = APIRouter(prefix='/api/expansion', tags=['Expansión condicionada'])


def verify(path, entry):
    if path.stat().st_size != entry['bytes'] or hashlib.sha256(path.read_bytes()).hexdigest() != entry['sha256']:
        raise ValueError('Phase-5 evidence identity mismatch')


def load_release():
    try:
        entries = {e['file']: e for e in json.loads((EVIDENCE/'manifest-local.json').read_text())['files']}
        for name in ('resultados.json', 'procesamiento.json'):
            verify(EVIDENCE/name, entries[name])
        verify(CONFIG, entries['../../specs/scenarios/estabilidad-topografica-v1.json'])
        verify(ROOT/'specs/analysis/primer-caso-fase2.json', entries['../../specs/analysis/primer-caso-fase2.json'])
        cfg = json.loads(CONFIG.read_text())
        result = json.loads((EVIDENCE/'resultados.json').read_text())
        processing = json.loads((EVIDENCE/'procesamiento.json').read_text())
        previous = regional.load_release()
        catalog_hash = hashlib.sha256((regional.EVIDENCE/'candidatas.json').read_bytes()).hexdigest()
        if (result['scenario'] != cfg or cfg['scenario_id'] != SCENARIO['id']
                or cfg['scales_m'] != SCENARIO['scales_m'] or cfg['window_m'] != SCENARIO['window_m']
                or processing['config_sha256'] != hashlib.sha256(CONFIG.read_bytes()).hexdigest()
                or result['source_catalog_sha256'] != catalog_hash
                or processing['source_catalog_sha256'] != catalog_hash
                or result['window_m'] != previous['config']['window_m']):
            raise ValueError('Phase-5 provenance mismatch')
        return {**result, 'processing': processing,
                'evidence': {name: f'/api/expansion/evidence/{name}' for name in sorted(FILES)}}
    except (OSError, ValueError, KeyError, TypeError, StopIteration) as exc:
        raise HTTPException(503, 'La evidencia de fase 5 falta o cambió. Reproduce y revisa la expansión antes de servirla.') from exc


@router.get('')
def comparison():
    return load_release()


@router.get('/evidence/{filename}')
def evidence(filename: str):
    if filename not in FILES:
        raise HTTPException(404, 'Evidencia no disponible')
    load_release()
    return FileResponse(EVIDENCE/filename, headers={'X-Content-Type-Options': 'nosniff'})
