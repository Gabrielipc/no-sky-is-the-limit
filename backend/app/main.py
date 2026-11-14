from pathlib import Path
import json
from typing import Dict

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from app.scenarios import router as scenarios_router
from app.regional import router as regional_router
from app.expansion import router as expansion_router
from app.dimensions import router as dimensions_router
from app.minerals import router as minerals_router
from app.atlas import router as atlas_router

DATA = Path(__file__).resolve().parents[2] / 'data' / 'regions.json'
app = FastAPI(title='Análogos planetarios · API', version='0.5.0')
app.add_middleware(CORSMiddleware, allow_origins=['http://localhost:5173', 'http://127.0.0.1:5173'], allow_methods=['*'], allow_headers=['*'])
app.include_router(scenarios_router)
app.include_router(regional_router)
app.include_router(expansion_router)
app.include_router(dimensions_router)
app.include_router(minerals_router)
app.include_router(atlas_router)

class Weights(BaseModel):
    slope_deg: float = Field(1, ge=0, le=10)
    relief_m: float = Field(1, ge=0, le=10)

class Search(BaseModel):
    reference_id: str
    weights: Weights

# Fixed scales make differences interpretable, not statistically validated thresholds.
SCALES = {'slope_deg': 10.0, 'relief_m': 300.0}

def regions():
    return json.loads(DATA.read_text(encoding='utf-8'))

def get_region(region_id):
    region = next ( (r for r in regions() if r['id'] == region_id), None)
    if region is None:
        raise HTTPException(404, 'Región no encontrada')
    return region

@app.get('/api/regions')
def list_regions():
    return regions()

@app.get('/api/regions/{region_id}')
def region_detail(region_id: str):
    return get_region(region_id)

@app.post('/api/search', deprecated=True, summary='Prototipo histórico: puntuación ilustrativa')
def search(request: Search):
    ref = get_region(request.reference_id)
    if ref['body'] != 'Mars':
        raise HTTPException(422, 'La referencia debe ser marciana')
    weights = request.weights.model_dump()
    if not any(weights.values()):
        raise HTTPException(422, 'Seleccione al menos un peso positivo')
    results = []
    for candidate in regions():
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
            breakdown[metric] = {'reference': a, 'candidate': b, 'weight': weight, 'similarity': similarity, 'scale': scale}
        score = weighted / available_weight if available_weight else None
        results.append({'region': candidate, 'score': score, 'breakdown': breakdown,
                        'available_weight_fraction': available_weight / sum(weights.values())})
    # Incomplete comparisons follow complete ones; missing values never produce a match.
    results.sort(key=lambda x: (x['available_weight_fraction'] < 1, x['score'] is None, -(x['score'] or 0)))
    return {'reference': ref, 'weights': weights, 'results': results,
            'method': 'Similitud = máx(0, 1 − diferencia absoluta / escala); media ponderada de dimensiones disponibles. Comparaciones incompletas al final.'}
