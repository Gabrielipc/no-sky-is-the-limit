"""HTTP routes for /api/multidimensional/..."""
import sys

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.repositories import dimensions_repository as _repo
from app.services import dimensions_service as service

router = APIRouter(prefix='/api/multidimensional', tags=['Dimensiones de superficie'])

# Re-exported so tests can patch these on this module.
SCENARIO = service.SCENARIO
SCENARIO_ID = service.SCENARIO_ID
EVIDENCE = _repo.EVIDENCE
digest = _repo.digest  # tests patch dimensions.digest

_FILES = frozenset(('resultados.json', 'procesamiento.json', 'manifest-local.json'))


def _this():
    return sys.modules[__name__]


@router.get('')
def comparison(
    cell_m: int = 60,
    candidate_id: str = 'earth-utah',
    reference_id: str = service.REFERENCE_ID,
):
    m = _this()
    return service.get_comparison(cell_m, candidate_id, reference_id,
                                  evidence_dir=m.EVIDENCE, digest_fn=m.digest)


@router.get('/sources')
def sources():
    m = _this()
    return service.get_sources(evidence_dir=m.EVIDENCE, digest_fn=m.digest)


@router.get('/evidence/{filename}')
def evidence(filename: str):
    m = _this()
    if filename not in _FILES:
        raise HTTPException(404, 'Evidencia no disponible')
    # Verify release integrity before serving the file.
    service.get_comparison(60, 'earth-utah', service.REFERENCE_ID,
                           evidence_dir=m.EVIDENCE, digest_fn=m.digest)
    return FileResponse(m.EVIDENCE / filename, headers={'X-Content-Type-Options': 'nosniff'})
