"""Read-only application view of the reviewed phase-2 evidence.

No raster processing or prototype scoring takes place in this route.
"""
import hashlib
import json
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / 'docs' / 'evidencia-fase-2'
CONFIG = ROOT / 'specs' / 'analysis' / 'primer-caso-fase2.json'
SCENARIO_ID = 'relieve-regional'
REFERENCE_ID = 'mars-jezero-fan'
SCENARIO = {
    'id': SCENARIO_ID,
    'name': 'Relieve regional para exploración robótica',
    'question': '¿Cómo difieren las pendientes y el relieve de estas ventanas terrestres respecto al abanico de Jezero?',
    'status': 'exploratory',
    'body': 'Mars',
    'references': [{'id': REFERENCE_ID, 'name': 'Jezero — abanico sedimentario'}],
    'scales_m': [60, 120],
    'window_m': 1800,
    'scope': 'Descriptores regionales en áreas acotadas; no evalúan obstáculos ni transitabilidad.',
}
DIMENSIONS = {
    'geology_and_materials': 'Geología y materiales',
    'thermal_properties': 'Propiedades térmicas',
    'rocks_and_obstacles': 'Rocas y obstáculos',
    'dust': 'Polvo',
    'water_and_ice': 'Agua y hielo',
}
LIMITATIONS = [
    'Resultados exploratorios: no validan análogos, seguridad de conducción ni idoneidad de una misión.',
    'Cobertura de valores válidos no equivale a observaciones independientes ni excluye interpolaciones o rellenos.',
    'La cuadrícula común no iguala la resolución efectiva, los sensores ni sus incertidumbres.',
    'La distancia de distribuciones no describe la disposición espacial de laderas, canales u obstáculos.',
    'Sin controles físicos independientes ni errores locales cuantificados; la revisión visual no sustituye validación experta.',
    'Las conclusiones se limitan a las ventanas y escalas analizadas. La evaluación local de Mojave y el soporte lunar siguen pendientes en este recorrido.',
]
METHOD = {
    'elevation': 'Promedio espacial de elevación y máscara de soporte independiente; solo soporte completo (tolerancia 10⁻⁶).',
    'slope': 'Diferencias centrales después de agregar: centro y cuatro vecinos válidos. Percentiles lineales p10/p50/p90.',
    'slope_comparison': 'Distancia de Wasserstein 1D en grados; cero indica distribuciones iguales según esta métrica.',
    'relief': 'p95 − p5 de elevaciones agregadas, en metros. Diferencia = candidata − Jezero; el signo indica mayor o menor relieve.',
    'coordinates': 'AEQD local por sitio; WGS84 para Tierra y esfera local del producto para Marte. Sin transformación vertical entre cuerpos.',
    'score_policy': 'Sin porcentaje de similitud, pesos ni puntuación combinada.',
}
CORE_FILES = ('resultados.json', 'procesamiento.json', 'areas-marte.json', 'areas-tierra.geojson')
ASSETS = frozenset((*CORE_FILES, 'manifest-local.json', 'verificacion.json',
                    'fuentes-y-conflictos.json', 'ortoimagen-qa.json',
                    'distribuciones-pendiente.png', 'jezero-ortoimagen-qa.png',
                    *(f'{site}{suffix}' for site in (REFERENCE_ID, 'earth-utah', 'earth-atacama')
                      for suffix in ('-qa.png', '-60m.png', '-120m.png'))))
router = APIRouter(prefix='/api')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def manifest_entries():
    return {item['file']: item for item in json.loads((EVIDENCE / 'manifest-local.json').read_text())['files']}


def verify(path, entry):
    if path.stat().st_size != entry['bytes'] or digest(path) != entry['sha256']:
        raise ValueError('Evidence identity mismatch')


def load_case():
    """Fail closed on changed evidence; never fall back to illustrative scores."""
    try:
        entries = manifest_entries()
        for filename in CORE_FILES:
            verify(EVIDENCE / filename, entries[filename])
        verify(CONFIG, entries['../../specs/analysis/primer-caso-fase2.json'])
        config = json.loads(CONFIG.read_text())
        results = json.loads((EVIDENCE / 'resultados.json').read_text())
        processing = json.loads((EVIDENCE / 'procesamiento.json').read_text())
        if (config['case_id'] != results['case_id'] or processing['config_sha256'] != digest(CONFIG)
                or config['scales_m'] != SCENARIO['scales_m'] or config['window_m'] != SCENARIO['window_m']):
            raise ValueError('Case/config mismatch')
        geometries = {}
        for filename in ('areas-marte.json', 'areas-tierra.geojson'):
            for feature in json.loads((EVIDENCE / filename).read_text())['features']:
                geometries[feature['properties']['site_id']] = feature
        return config, results, processing, geometries
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise HTTPException(503, 'La evidencia de fase 2 falta o cambió. Verifica el análisis y su manifiesto antes de servirlo.') from exc


def evidence_url(filename):
    return f'/api/evidence/{filename}'


@router.get('/scenarios')
def list_scenarios():
    from app.expansion import SCENARIO as STABILITY
    from app.dimensions import SCENARIO as DIMENSIONS_SCENARIO
    return [SCENARIO, STABILITY, DIMENSIONS_SCENARIO]


@router.get('/scenarios/{scenario_id}/comparison')
def comparison(scenario_id: str, reference_id: str = REFERENCE_ID, cell_m: int = Query(60), candidate_id: str = 'earth-utah'):
    from app import expansion, dimensions
    if scenario_id == dimensions.SCENARIO_ID:
        return dimensions.comparison_view(cell_m, candidate_id, reference_id)
    if scenario_id == expansion.SCENARIO['id']:
        if reference_id != REFERENCE_ID or cell_m not in expansion.SCENARIO['scales_m']:
            raise HTTPException(422, 'Referencia o escala no evaluada en este escenario')
        return {**expansion.load_release(), 'cell_m': cell_m}
    if scenario_id != SCENARIO_ID:
        raise HTTPException(404, 'Escenario no disponible')
    if reference_id != REFERENCE_ID:
        raise HTTPException(422, 'Referencia no evaluada en este escenario')
    if cell_m not in SCENARIO['scales_m']:
        raise HTTPException(422, 'Escala no evaluada; selecciona 60 o 120 m')
    config, results, processing, geometries = load_case()

    def site_view(site):
        measurements = next(r for r in results['results'] if r['site_id'] == site['id'] and r['cell_m'] == cell_m)
        source = next(p for p in processing['inputs'] if p['product_id'] == site['product_id'])
        return {
            **{k: site[k] for k in ('id', 'name', 'body', 'latitude', 'longitude', 'limitations')},
            'radius_m': site.get('radius_m'),
            'measurements': measurements,
            'area': geometries[site['id']],
            'source': {**{k: site[k] for k in ('product_id', 'url', 'version', 'sha256', 'bytes', 'vertical_reference', 'observation_dates')},
                       'native_step_at_center_m': source['native_step_at_center_m']},
            'figures': {'analysis': evidence_url(f"{site['id']}-{cell_m}m.png"),
                        'native': evidence_url(f"{site['id']}-qa.png")},
        }

    try:
        sites = {s['id']: site_view(s) for s in config['sites']}
        candidates = []
        # Catalogue order is explicit, not an overall similarity ranking.
        for site in config['sites']:
            if site['body'] != 'Earth':
                continue
            difference = next(c for c in results['comparisons']
                              if c['candidate'] == site['id'] and c['cell_m'] == cell_m and c['reference'] == reference_id)
            sensitivity = [c for c in results['comparisons'] if c['candidate'] == site['id'] and c['reference'] == reference_id]
            candidates.append({'site': sites[site['id']], 'comparison': difference, 'sensitivity': sensitivity})
        return {
            'case_id': results['case_id'], 'scenario': SCENARIO, 'cell_m': cell_m,
            'evidence_identity': digest(EVIDENCE / 'resultados.json'),
            'reference': sites[reference_id], 'candidates': candidates,
            'method': METHOD, 'limitations': LIMITATIONS,
            'not_evaluated': [{'id': key, 'name': DIMENSIONS[key], 'status': 'not_evaluated', 'value': None}
                              for key in results['dimensions_not_evaluated']],
            'missing_dimension_policy': 'No evaluado: no equivale a cero ni aporta evidencia de semejanza.',
            'evidence': {filename: evidence_url(filename) for filename in CORE_FILES},
            'distributions_figure': evidence_url('distribuciones-pendiente.png'),
            'orthoimage_figure': evidence_url('jezero-ortoimagen-qa.png'),
        }
    except (KeyError, StopIteration, TypeError, ValueError) as exc:
        raise HTTPException(503, 'La evidencia está incompleta para este recorrido.') from exc


@router.get('/evidence/{filename}')
def evidence(filename: str):
    if filename not in ASSETS:
        raise HTTPException(404, 'Archivo de evidencia no disponible')
    path = EVIDENCE / filename
    try:
        if filename != 'manifest-local.json':
            verify(path, manifest_entries()[filename])
        elif not path.is_file():
            raise FileNotFoundError(filename)
    except (OSError, KeyError, ValueError, TypeError) as exc:
        raise HTTPException(503, 'Archivo ausente o distinto de la evidencia revisada.') from exc
    return FileResponse(path, headers={'X-Content-Type-Options': 'nosniff'})
