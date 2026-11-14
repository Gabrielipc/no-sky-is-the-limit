"""HTTP routes for /api/minerals/..."""
import sys

import hashlib as hashlib  # re-exported so tests can patch minerals_router.hashlib

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.repositories import minerals_repository as _repo
from app.services import minerals_service as service

router = APIRouter(prefix='/api/minerals', tags=['Minerales e indicadores espectrales'])

# Re-exported so tests can patch these on this module.
EVIDENCE = _repo.EVIDENCE
JEZERO_EVIDENCE = _repo.JEZERO_EVIDENCE

_FILES = frozenset(('resultados.json', 'procesamiento.json', 'manifest-local.json'))
_JEZERO_FILES = frozenset(('resultados.json', 'manifest-local.json'))


def _this():
    return sys.modules[__name__]


@router.get('')
def minerals(candidate_id: str = 'earth-utah'):
    m = _this()
    return service.get_minerals(candidate_id, evidence_dir=m.EVIDENCE, jezero_dir=m.JEZERO_EVIDENCE,
                                 hashlib_mod=m.hashlib)


@router.get('/jezero')
def jezero():
    m = _this()
    return service.get_jezero(jezero_dir=m.JEZERO_EVIDENCE, hashlib_mod=m.hashlib)


@router.get('/jezero/evidence/{filename}')
def jezero_evidence(filename: str):
    m = _this()
    if filename not in _JEZERO_FILES:
        raise HTTPException(404, 'Evidencia CRISM no disponible')
    service.get_jezero(jezero_dir=m.JEZERO_EVIDENCE, hashlib_mod=m.hashlib)
    return FileResponse(m.JEZERO_EVIDENCE / filename, headers={'X-Content-Type-Options': 'nosniff'})


@router.get('/evidence/{filename}')
def evidence(filename: str):
    m = _this()
    if filename not in _FILES:
        raise HTTPException(404, 'Evidencia mineral no disponible')
    service.get_minerals('earth-utah', evidence_dir=m.EVIDENCE, jezero_dir=m.JEZERO_EVIDENCE,
                          hashlib_mod=m.hashlib)
    return FileResponse(m.EVIDENCE / filename, headers={'X-Content-Type-Options': 'nosniff'})
