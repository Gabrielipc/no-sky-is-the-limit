"""HTTP routes for /api/scenarios/... and /api/evidence/..."""
import sys

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from app.repositories import scenarios_repository as _repo
from app.services import scenarios_service as service
from app.services.scenarios_service import ASSETS, REFERENCE_ID, SCENARIO_ID

router = APIRouter(prefix='/api')

# Re-exported so tests can patch these on this module and they propagate.
EVIDENCE = _repo.EVIDENCE
CONFIG = _repo.CONFIG
digest = _repo.digest


def _this():
    return sys.modules[__name__]


@router.get('/scenarios')
def list_scenarios():
    from app.routers.expansion_router import SCENARIO as STABILITY
    from app.routers.dimensions_router import SCENARIO as DIMENSIONS_SCENARIO
    return [service.SCENARIO, STABILITY, DIMENSIONS_SCENARIO]


@router.get('/scenarios/{scenario_id}/comparison')
def comparison(
    scenario_id: str,
    reference_id: str = REFERENCE_ID,
    cell_m: int = Query(60),
    candidate_id: str = 'earth-utah',
):
    from app.routers import dimensions_router as dimensions
    from app.routers import expansion_router as expansion
    from app.services import dimensions_service, expansion_service

    m = _this()
    if scenario_id == dimensions.SCENARIO_ID:
        dm = sys.modules['app.routers.dimensions_router']
        return dimensions_service.get_comparison(cell_m, candidate_id, reference_id,
                                                  evidence_dir=dm.EVIDENCE, digest_fn=dm.digest)
    if scenario_id == expansion.SCENARIO['id']:
        em = sys.modules['app.routers.expansion_router']
        from app.routers import regional_router as regional
        return expansion_service.get_comparison(reference_id, cell_m,
                                                 evidence_dir=em.EVIDENCE, config_path=em.CONFIG,
                                                 regional_evidence_dir=regional.EVIDENCE)
    if scenario_id != SCENARIO_ID:
        raise HTTPException(404, 'Escenario no disponible')
    return service.get_comparison(reference_id, cell_m, candidate_id,
                                   evidence_dir=m.EVIDENCE, config_path=m.CONFIG, digest_fn=m.digest)


@router.get('/evidence/{filename}')
def evidence(filename: str):
    m = _this()
    if filename not in ASSETS:
        raise HTTPException(404, 'Archivo de evidencia no disponible')
    return FileResponse(_repo.evidence_path(filename, m.EVIDENCE, m.digest),
                        headers={'X-Content-Type-Options': 'nosniff'})
