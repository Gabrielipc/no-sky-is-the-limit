"""Coordinate EMIT and CRISM mineral data into API-ready payloads."""
from pathlib import Path
from types import ModuleType

from fastapi import HTTPException

from app.repositories import minerals_repository as repo

_FILES = frozenset(('resultados.json', 'procesamiento.json', 'manifest-local.json'))
_VALID_CANDIDATES = frozenset(('earth-utah', 'earth-atacama'))


def get_minerals(candidate_id: str,
                 evidence_dir: Path | None = None,
                 jezero_dir: Path | None = None,
                 hashlib_mod: ModuleType | None = None) -> dict:
    if candidate_id not in _VALID_CANDIDATES:
        raise HTTPException(422, 'Candidata mineral no disponible')
    release = repo.load_emit_release(evidence_dir, hashlib_mod)
    mars = dict(release['mars'], endpoint='/api/minerals/jezero')
    try:
        repo.load_jezero_release(jezero_dir, hashlib_mod)
        mars.update(
            status='indicators_available',
            reason='Jezero tiene indicadores CRISM. La comparación de identificaciones minerales requiere un método común.',
        )
    except HTTPException:
        mars.update(status='unavailable', reason='No se pudo verificar la evidencia CRISM de Jezero.')
    return {
        **{key: release[key] for key in ('release_id', 'window_m', 'quality_note', 'documentation', 'limitations')},
        'mars': mars,
        'candidate': next(s for s in release['sites'] if s['id'] == candidate_id),
        'evidence': {name: '/api/minerals/evidence/' + name for name in sorted(_FILES)},
    }


def get_jezero(jezero_dir: Path | None = None,
               hashlib_mod: ModuleType | None = None) -> dict:
    result = repo.load_jezero_release(jezero_dir, hashlib_mod)
    return {
        **result,
        'evidence': {name: '/api/minerals/jezero/evidence/' + name
                     for name in ('resultados.json', 'manifest-local.json')},
    }
