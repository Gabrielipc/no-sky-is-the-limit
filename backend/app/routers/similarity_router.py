"""Routes of the similarity search (`/api/similarity`)."""
import json
import os
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from fastapi.concurrency import run_in_threadpool

from app.schemas.similarity import SearchRequest
from app.services.similarity_service import SimilarityService, Unavailable, service

router = APIRouter(prefix='/api/similarity', tags=['Similitud ML'])


async def available_service() -> SimilarityService:
    svc = service()
    try:
        await run_in_threadpool(svc.ensure)
    except Unavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    return svc


@router.get('/status')
async def status():
    return service().status()


def read_jezero_pilot(mode: str, limit: int) -> dict:
    directory = os.getenv('REGOLITH_JEZERO_PILOT_DIR')
    if not directory:
        raise HTTPException(503, 'El piloto espectral de Jezero está pendiente de validación.')
    try:
        report = json.loads((Path(directory) / 'jezero.json').read_text(encoding='utf-8'))
        if (report['format'] != 'jezero-multivista-v1' or report['status'] != 'experimental'
                or not all(report[key]['pass'] is True for key in ('support', 'relevance', 'retrieval', 'stability'))):
            raise ValueError('El piloto aún no cumple los criterios de publicación')
        results = report['rankings'][mode]
        return {
            'version': report['version'], 'status': report['status'], 'mode': mode,
            'reference': report['reference'], 'profile': report['profile'], 'coverage': report['coverage'],
            'weights': report['weights'] if mode == 'combined' else {'topografia': 1.0},
            'candidates_ranked': len(results), 'results': results[:limit],
            'warnings': ['Piloto de similitud de materiales dentro de la cobertura EMIT evaluada.'],
        }
    except (OSError, KeyError, TypeError, ValueError) as exc:
        raise HTTPException(503, 'No hay una publicación válida del piloto de Jezero.') from exc


@router.get('/jezero-pilot')
async def jezero_pilot(mode: Literal['combined', 'topography'] = 'combined',
                       limit: int = Query(25, ge=1, le=100)):
    return await run_in_threadpool(read_jezero_pilot, mode, limit)


@router.get('/references')
async def references():
    svc = await available_service()
    engine = svc.engine
    return {'references': await run_in_threadpool(svc.catalog),
            'default_weights': engine.spec['default_weights'],
            'views': {vid: {'fitted': v['fitted'], 'kind': v['kind']} for vid, v in engine.model['views'].items()},
            'engine_status': engine.spec['status']}


@router.get('/references/{reference_id}')
async def reference(reference_id: str):
    svc = await available_service()
    entry = svc.references.get(reference_id)
    if entry is None:
        raise HTTPException(404, 'Referencia desconocida')
    return svc._public(entry, detail=True)


@router.post('/search')
async def search(req: SearchRequest):
    svc = await available_service()
    try:
        return await run_in_threadpool(svc.search, req)
    except KeyError as exc:
        raise HTTPException(404, exc.args[0]) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
