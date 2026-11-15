"""HTTP routes for /api/expansion/..."""
import sys

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.repositories import expansion_repository as _repo
from app.services import expansion_service as service

router = APIRouter(prefix='/api/expansion', tags=['Expansión condicionada'])

# Re-exported at module level so tests can patch these names on this module.
SCENARIO = service.SCENARIO
EVIDENCE = _repo.EVIDENCE
CONFIG = _repo.CONFIG
FILES = _repo.FILES


def _this():
    """Return this module so endpoint functions read the current (possibly patched) values."""
    return sys.modules[__name__]


def _regional_evidence():
    from app.routers import regional_router
    return regional_router.EVIDENCE
    

@router.get('')
def comparison():
    m = _this()
    return service.get_release(
        evidence_dir=m.EVIDENCE,
        config_path=m.CONFIG,
        regional_evidence_dir=_regional_evidence(),
    )


@router.get('/evidence/{filename}')
def evidence(filename: str):
    m = _this()
    if filename not in m.FILES:
        raise HTTPException(404, 'Evidencia no disponible')
    service.get_release(
        evidence_dir=m.EVIDENCE,
        config_path=m.CONFIG,
        regional_evidence_dir=_regional_evidence(),
    )
    return FileResponse(m.EVIDENCE / filename, headers={'X-Content-Type-Options': 'nosniff'})
