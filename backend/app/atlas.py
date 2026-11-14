"""The public read/search interface for the 30 m atlas."""
import hashlib
import json
import sqlite3
from contextlib import closing
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from app import atlas_store as store

router = APIRouter(prefix='/api/atlas', tags=['Atlas mundial a 30 m'])


def release_for(version=None):
    try:
        return store.load_release(store.ROOT, version)
    except FileNotFoundError as exc:
        code = 404 if version else 503
        message = 'Versión del índice desconocida' if version else 'El índice de 30 m todavía no tiene una publicación activa'
        raise HTTPException(code, message) from exc
    except (ValueError, KeyError) as exc:
        raise HTTPException(422 if version else 503, 'Manifiesto de atlas inválido') from exc


def read_optional(path, default):
    return json.loads(path.read_text()) if path.is_file() else default


def search_db():
    return closing(sqlite3.connect(store.ROOT / 'searches.sqlite', timeout=5))


def search_result(query_id, criteria, limit, offset):
    path, manifest = release_for(criteria['version'])
    try:
        total, matches = store.search(path, manifest, criteria['weights'], criteria['bare_min'],
                                      criteria['water_max'], limit, offset)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {'query_id': query_id, **criteria, 'normalization': manifest['normalization'],
            'total': total, 'limit': limit, 'offset': offset,
            'matches': [{**row, 'rank': offset + rank} for rank, row in enumerate(matches, 1)]}


@router.get('')
def summary(version: Optional[str] = None):
    path, manifest = release_for(version)
    cases = path / 'expedients'
    profile = manifest['profile']
    return {**manifest, 'profile': {key: value for key, value in profile.items() if key != 'source'},
            'context_counts': store.context_counts(path),
            'expedients': sorted(case.name for case in cases.iterdir() if (case / 'case.json').is_file())
            if cases.is_dir() else [],
            'refinement': read_optional(path / 'refinement.json', [])}


@router.get('/versions')
def versions():
    if not store.ROOT.is_dir():
        return []
    return sorted(path.name for path in store.ROOT.iterdir() if (path / 'manifest.json').is_file())


@router.get('/coverage')
def coverage(version: Optional[str] = None):
    path, manifest = release_for(version)
    return {'version': manifest['version'], 'bin_degrees': 2, 'bins': store.coverage(path)}


@router.get('/search')
def search(version: Optional[str] = None, slope: float = Query(50, ge=0, le=100),
           relief: float = Query(30, ge=0, le=100), roughness: float = Query(20, ge=0, le=100),
           bare_min: Optional[float] = Query(None, ge=0, le=1),
           water_max: Optional[float] = Query(None, ge=0, le=100),
           limit: int = Query(25, ge=1, le=100), offset: int = Query(0, ge=0)):
    _, manifest = release_for(version)
    criteria = {'version': manifest['version'], 'profile_id': manifest['profile']['profile_id'],
                'cell_m': manifest['cell_m'], 'weights': [slope, relief, roughness],
                'bare_min': bare_min, 'water_max': water_max}
    encoded = json.dumps(criteria, sort_keys=True, allow_nan=False)
    query_id = hashlib.sha256(encoded.encode()).hexdigest()
    result = search_result(query_id, criteria, limit, offset)
    with search_db() as db, db:
        db.execute('CREATE TABLE IF NOT EXISTS queries (id TEXT PRIMARY KEY, criteria TEXT NOT NULL)')
        db.execute('INSERT OR IGNORE INTO queries VALUES (?, ?)', (query_id, encoded))
    return result


@router.get('/search/{query_id}')
def replay(query_id: str, limit: int = Query(25, ge=1, le=100), offset: int = Query(0, ge=0)):
    if len(query_id) != 64 or not all(c in '0123456789abcdef' for c in query_id) or not (store.ROOT / 'searches.sqlite').is_file():
        raise HTTPException(404, 'Búsqueda desconocida')
    with search_db() as db:
        row = db.execute('SELECT criteria FROM queries WHERE id = ?', (query_id,)).fetchone()
    if not row:
        raise HTTPException(404, 'Búsqueda desconocida')
    return search_result(query_id, json.loads(row[0]), limit, offset)


@router.get('/candidates/{region_id}')
def candidate(region_id: str, version: Optional[str] = None):
    path, manifest = release_for(version)
    row = store.candidate(path, region_id)
    if not row:
        raise HTTPException(404, 'Ventana desconocida')
    case = read_optional(path / 'expedients' / region_id / 'case.json', None)
    if case:
        case['map_url'] = f'/api/atlas/candidates/{region_id}/terrain.png?version={manifest["version"]}'
    assets = read_optional(path / 'sources.json', {})
    identities = [assets[key] for key in row['asset_ids'] + row['worldcover_assets'] + row['water_assets'] if key in assets]
    return {'version': manifest['version'], 'window': row, 'expedient': case, 'assets': identities}


@router.get('/candidates/{region_id}/terrain.png')
def terrain_map(region_id: str, version: Optional[str] = None):
    path, _ = release_for(version)
    if not store.TOKEN.fullmatch(region_id):
        raise HTTPException(404, 'Mapa de terreno no disponible')
    image = path / 'expedients' / region_id / 'terrain.png'
    if not image.is_file():
        raise HTTPException(404, 'Mapa de terreno no disponible')
    return FileResponse(image, media_type='image/png')
