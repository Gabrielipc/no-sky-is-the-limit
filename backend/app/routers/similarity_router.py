"""Routes of the similarity search (`/api/similarity`)."""
from fastapi import APIRouter, HTTPException
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
