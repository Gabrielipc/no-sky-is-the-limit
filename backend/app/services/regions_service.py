"""Search and filter logic for historical prototype regions."""
from typing import Callable, Dict

from fastapi import HTTPException

from app.repositories import regions_repository as repo
from app.schemas.search import Search

# Fixed scales make differences interpretable, not statistically validated thresholds.
SCALES = {'slope_deg': 10.0, 'relief_m': 300.0}


def get_regions(load_fn: Callable[[], list[dict]] | None = None) -> list[dict]:
    fn = load_fn if load_fn is not None else repo.load_regions
    return fn()


def get_region(region_id: str, regions_fn: Callable[[], list[dict]] | None = None) -> dict:
    fn = regions_fn if regions_fn is not None else repo.load_regions
    region = next((r for r in fn() if r['id'] == region_id), None)
    if region is None:
        raise HTTPException(404, 'Región no encontrada')
    return region


def search(request: Search, regions_fn: Callable[[], list[dict]] | None = None) -> dict:
    fn = regions_fn if regions_fn is not None else repo.load_regions
    ref = get_region(request.reference_id, regions_fn=fn)
    if ref['body'] != 'Mars':
        raise HTTPException(422, 'La referencia debe ser marciana')
    weights = request.weights.model_dump()
    if not any(weights.values()):
        raise HTTPException(422, 'Seleccione al menos un peso positivo')
    results = []
    for candidate in fn():
        if candidate['body'] != 'Earth':
            continue
        breakdown: Dict[str, dict] = {}
        weighted, available_weight = 0.0, 0.0
        for metric, scale in SCALES.items():
            a, b, weight = ref['metrics'].get(metric), candidate['metrics'].get(metric), weights[metric]
            similarity = None if a is None or b is None else max(0.0, 1.0 - abs(a - b) / scale)
            if similarity is not None and weight > 0:
                weighted += weight * similarity
                available_weight += weight
            breakdown[metric] = {
                'reference': a, 'candidate': b, 'weight': weight,
                'similarity': similarity, 'scale': scale,
            }
        score = weighted / available_weight if available_weight else None
        results.append({
            'region': candidate, 'score': score, 'breakdown': breakdown,
            'available_weight_fraction': available_weight / sum(weights.values()),
        })
    # Incomplete comparisons follow complete ones; missing values never produce a match.
    results.sort(key=lambda x: (
        x['available_weight_fraction'] < 1, x['score'] is None, -(x['score'] or 0),
    ))
    return {
        'reference': ref,
        'weights': weights,
        'results': results,
        'method': 'Similitud = máx(0, 1 − diferencia absoluta / escala); media ponderada de dimensiones disponibles. Comparaciones incompletas al final.',
    }
