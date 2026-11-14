"""HTTP routes for /api/regional-search/..."""
import sys
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse

from app.repositories import regional_repository as _repo
from app.services import regional_service as service

router = APIRouter(prefix='/api/regional-search', tags=['Búsqueda regional exploratoria'])

# Re-exported so tests can patch EVIDENCE on this module.
EVIDENCE = _repo.EVIDENCE
FILES = service.FILES


def _this():
    return sys.modules[__name__]


@router.get('')
def summary():
    return service.get_summary(evidence_dir=_this().EVIDENCE)


@router.get('/candidates')
def candidates(
    area_id: str = 'utah',
    cell_m: int = 300,
    profile: Literal['strict', 'baseline', 'relaxed'] = 'baseline',
    include_excluded: bool = False,
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
):
    return service.get_candidates(area_id, cell_m, profile, include_excluded, offset, limit,
                                  evidence_dir=_this().EVIDENCE)


@router.get('/candidates/{candidate_id}')
def candidate_detail(candidate_id: str):
    return service.get_candidate_detail(candidate_id, evidence_dir=_this().EVIDENCE)


@router.get('/export')
def export(
    area_id: str = 'utah',
    cell_m: int = 300,
    profile: Literal['strict', 'baseline', 'relaxed'] = 'baseline',
    include_excluded: bool = False,
):
    data = service.get_geojson_export(area_id, cell_m, profile, include_excluded,
                                      evidence_dir=_this().EVIDENCE)
    return JSONResponse(
        data,
        media_type='application/geo+json',
        headers={'Content-Disposition': f'attachment; filename="{area_id}-{cell_m}m-{profile}.geojson"'},
    )


@router.get('/evidence/{filename}')
def evidence(filename: str):
    m = _this()
    if filename not in m.FILES:
        raise HTTPException(404, 'Evidencia no disponible')
    return FileResponse(_repo.evidence_path(filename, m.EVIDENCE),
                        headers={'X-Content-Type-Options': 'nosniff'})
