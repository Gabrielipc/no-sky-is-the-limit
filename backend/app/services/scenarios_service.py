"""Build comparison views for phase-2 scenario evidence."""
from pathlib import Path
from typing import Callable

from fastapi import HTTPException

from app.repositories import scenarios_repository as repo

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
ASSETS = frozenset((
    *CORE_FILES,
    'manifest-local.json', 'verificacion.json', 'fuentes-y-conflictos.json', 'ortoimagen-qa.json',
    'distribuciones-pendiente.png', 'jezero-ortoimagen-qa.png',
    *(f'{site}{suffix}'
      for site in (REFERENCE_ID, 'earth-utah', 'earth-atacama')
      for suffix in ('-qa.png', '-60m.png', '-120m.png')),
))


def _evidence_url(filename: str) -> str:
    return f'/api/evidence/{filename}'


def _site_view(site: dict, cell_m: int, results: dict, processing: dict, geometries: dict) -> dict:
    measurements = next(r for r in results['results'] if r['site_id'] == site['id'] and r['cell_m'] == cell_m)
    source = next(p for p in processing['inputs'] if p['product_id'] == site['product_id'])
    return {
        **{k: site[k] for k in ('id', 'name', 'body', 'latitude', 'longitude', 'limitations')},
        'radius_m': site.get('radius_m'),
        'measurements': measurements,
        'area': geometries[site['id']],
        'source': {
            **{k: site[k] for k in ('product_id', 'url', 'version', 'sha256', 'bytes', 'vertical_reference', 'observation_dates')},
            'native_step_at_center_m': source['native_step_at_center_m'],
        },
        'figures': {
            'analysis': _evidence_url(f"{site['id']}-{cell_m}m.png"),
            'native': _evidence_url(f"{site['id']}-qa.png"),
        },
    }


def get_comparison(reference_id: str, cell_m: int, candidate_id: str,
                   evidence_dir: Path | None = None,
                   config_path: Path | None = None,
                   digest_fn: Callable | None = None) -> dict:
    if reference_id != REFERENCE_ID:
        raise HTTPException(422, 'Referencia no evaluada en este escenario')
    if cell_m not in SCENARIO['scales_m']:
        raise HTTPException(422, 'Escala no evaluada; selecciona 60 o 120 m')
    _digest = digest_fn if digest_fn is not None else repo.digest
    base = evidence_dir if evidence_dir is not None else repo.EVIDENCE
    config, results, processing, geometries = repo.load_case(evidence_dir, config_path, digest_fn)
    try:
        sites = {s['id']: _site_view(s, cell_m, results, processing, geometries) for s in config['sites']}
        candidates = []
        for site in config['sites']:
            if site['body'] != 'Earth':
                continue
            difference = next(
                c for c in results['comparisons']
                if c['candidate'] == site['id'] and c['cell_m'] == cell_m and c['reference'] == reference_id
            )
            sensitivity = [c for c in results['comparisons'] if c['candidate'] == site['id'] and c['reference'] == reference_id]
            candidates.append({'site': sites[site['id']], 'comparison': difference, 'sensitivity': sensitivity})
        return {
            'case_id': results['case_id'],
            'scenario': SCENARIO,
            'cell_m': cell_m,
            'evidence_identity': _digest(base / 'resultados.json'),
            'reference': sites[reference_id],
            'candidates': candidates,
            'method': METHOD,
            'limitations': LIMITATIONS,
            'not_evaluated': [
                {'id': key, 'name': DIMENSIONS[key], 'status': 'not_evaluated', 'value': None}
                for key in results['dimensions_not_evaluated']
            ],
            'missing_dimension_policy': 'No evaluado: no equivale a cero ni aporta evidencia de semejanza.',
            'evidence': {filename: _evidence_url(filename) for filename in CORE_FILES},
            'distributions_figure': _evidence_url('distribuciones-pendiente.png'),
            'orthoimage_figure': _evidence_url('jezero-ortoimagen-qa.png'),
        }
    except (KeyError, StopIteration, TypeError, ValueError) as exc:
        raise HTTPException(503, 'La evidencia está incompleta para este recorrido.') from exc
