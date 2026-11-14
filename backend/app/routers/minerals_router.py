"""Serve reviewed EMIT and CRISM derivatives without opening original rasters."""
import hashlib
import json
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

ROOT = Path(__file__).resolve().parents[3]
EVIDENCE = ROOT / 'docs/evidencia-minerales'
JEZERO_EVIDENCE = ROOT / 'docs/evidencia-crism'
CONFIG = ROOT / 'specs/analysis/minerales-emit-v1.json'
FILES = frozenset(('resultados.json', 'procesamiento.json', 'manifest-local.json'))
router = APIRouter(prefix='/api/minerals', tags=['Minerales e indicadores espectrales'])


def verified_files(directory, expected):
    manifest = json.loads((directory / 'manifest-local.json').read_text())
    entries = manifest['files']
    if manifest['schema'] != 1 or len(entries) != len(expected) or {ROOT / e['file'] for e in entries} != expected:
        raise ValueError('Inventario de evidencia distinto')
    contents = {}
    for entry in entries:
        path = ROOT / entry['file']
        content = path.read_bytes()
        if len(content) != entry['bytes'] or hashlib.sha256(content).hexdigest() != entry['sha256']:
            raise ValueError('Identidad de evidencia distinta')
        contents[path] = content
    return contents


def load_release():
    try:
        expected = {CONFIG, ROOT / 'scripts/analizar_minerales.py', ROOT / 'requirements-minerales.txt',
                    ROOT / 'docs/evidencia-fase-2/areas-tierra.geojson', ROOT / 'docs/evidencia-fase-2/resultados.json',
                    *(ROOT / f'docs/evidencia-fase-2/{site}-60m-slope.tif' for site in ('earth-utah', 'earth-atacama')),
                    EVIDENCE / 'resultados.json', EVIDENCE / 'procesamiento.json'}
        contents = verified_files(EVIDENCE, expected)
        result = json.loads(contents[EVIDENCE / 'resultados.json'])
        cfg = json.loads(contents[CONFIG])
        if result['release_id'] != cfg['release_id'] or result['window_m'] != cfg['window_m']:
            raise ValueError('Configuración mineral distinta')
        if {site['id'] for site in result['sites']} != {'earth-utah', 'earth-atacama'}:
            raise ValueError('Sitios minerales incompletos')
        return result
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise HTTPException(503, 'La evidencia mineral falta o cambió. Genera y revisa scripts/analizar_minerales.py.') from exc


def load_jezero():
    result_file = JEZERO_EVIDENCE / 'resultados.json'
    expected = {result_file, ROOT / 'scripts/analizar_crism.py',
                ROOT / 'docs/evidencia-fase-2/areas-marte.json',
                ROOT / 'docs/investigacion-marte/adquisicion-crism.json'}
    try:
        return json.loads(verified_files(JEZERO_EVIDENCE, expected)[result_file])
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise HTTPException(503, 'La evidencia CRISM falta o cambió. Genera y revisa scripts/analizar_crism.py.') from exc


@router.get('')
def minerals(candidate_id: str = 'earth-utah'):
    if candidate_id not in ('earth-utah', 'earth-atacama'):
        raise HTTPException(422, 'Candidata mineral no disponible')
    release = load_release()
    mars = dict(release['mars'], endpoint='/api/minerals/jezero')
    try:
        load_jezero()
        mars.update(status='indicators_available',
                    reason='Jezero tiene indicadores CRISM. La comparación de identificaciones minerales requiere un método común.')
    except HTTPException:
        mars.update(status='unavailable', reason='No se pudo verificar la evidencia CRISM de Jezero.')
    return {**{key: release[key] for key in ('release_id', 'window_m', 'quality_note', 'documentation', 'limitations')},
            'mars': mars,
            'candidate': next(s for s in release['sites'] if s['id'] == candidate_id),
            'evidence': {name: '/api/minerals/evidence/' + name for name in sorted(FILES)}}


@router.get('/jezero')
def jezero():
    return {**load_jezero(),
            'evidence': {name: '/api/minerals/jezero/evidence/' + name
                         for name in ('resultados.json', 'manifest-local.json')}}


@router.get('/jezero/evidence/{filename}')
def jezero_evidence(filename: str):
    if filename not in ('resultados.json', 'manifest-local.json'):
        raise HTTPException(404, 'Evidencia CRISM no disponible')
    load_jezero()
    return FileResponse(JEZERO_EVIDENCE / filename, headers={'X-Content-Type-Options': 'nosniff'})


@router.get('/evidence/{filename}')
def evidence(filename: str):
    if filename not in FILES:
        raise HTTPException(404, 'Evidencia mineral no disponible')
    load_release()
    return FileResponse(EVIDENCE / filename, headers={'X-Content-Type-Options': 'nosniff'})
