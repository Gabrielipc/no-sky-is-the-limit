"""HTTP routes for /api/regions and /api/search."""
import sys

from fastapi import APIRouter

from app.schemas.search import Search, Weights
from app.services import regions_service as service

router = APIRouter()

# Re-exported so tests can patch regions on this module or import Search, Weights, search
SCALES = service.SCALES


def _this():
    return sys.modules[__name__]


def regions():
    return service.get_regions()


def get_region(region_id: str):
    m = _this()
    return service.get_region(region_id, regions_fn=m.regions)


@router.get('/api/regions')
def list_regions():
    m = _this()
    return m.regions()


@router.get('/api/regions/{region_id}')
def region_detail(region_id: str):
    return get_region(region_id)


@router.post('/api/search', deprecated=True, summary='Prototipo histórico: puntuación ilustrativa')
def search(request: Search):
    m = _this()
    return service.search(request, regions_fn=m.regions)
