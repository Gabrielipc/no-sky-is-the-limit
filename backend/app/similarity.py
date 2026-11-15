"""Similarity search of Earth analogues of a Moon or Mars reference (`/api/similarity`).

The unsupervised ML engine lives in `pipelines/similarity_ml.py`. This module keeps it resident:
the model and the Earth candidates (with their normal scores) are loaded once per process, so a
query only pays for the distances and the fusion. Responses follow `specs/api/motor-busqueda-v1`
plus `query_id` and `timings`.
"""
import hashlib
import json
import os
import sys
import threading
import time
from collections import OrderedDict
from pathlib import Path
from typing import Dict, List, Literal, Optional, Union

from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, ConfigDict, Field

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:  # `pipelines/` is a sibling of `backend/`
    sys.path.insert(0, str(ROOT))

router = APIRouter(prefix='/api/similarity', tags=['Similitud ML'])

CATALOG_PATH = ROOT / 'specs/analysis/referencias-v1.json'
DEFAULT_PROFILE = 'arid_mars_surface_v2'
PROFILES = ('arid_mars_surface_v2', 'paleolake_margin_v1', 'polar_cold_v1')
CACHE_SIZE = int(os.environ.get('ANALOGOS_SIMILARITY_CACHE', '256'))
MAX_CONCURRENT = int(os.environ.get('ANALOGOS_SIMILARITY_CONCURRENCY', '4'))


class ReferenceInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: Optional[str] = Field(None, max_length=96)
    name: Optional[str] = Field(None, max_length=200)
    body: Literal['Mars', 'Moon', 'Earth']
    features: Dict[str, Optional[float]] = Field(default_factory=dict, max_length=64)
    percentiles: Dict[str, float] = Field(default_factory=dict, max_length=64)


class SearchRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    reference: Union[str, ReferenceInput]
    weights: Optional[Dict[str, float]] = None
    profile: Literal['arid_mars_surface_v2', 'paleolake_margin_v1', 'polar_cold_v1'] = DEFAULT_PROFILE
    only_eligible: bool = True
    limit: int = Field(25, ge=1, le=1000)
    missing_policy: Optional[Literal['neutral', 'renormalize', 'require']] = None
    fusion: Optional[Literal['weighted', 'rrf']] = None
    bbox: Optional[List[float]] = Field(None, min_length=4, max_length=4)


class Unavailable(Exception):
    """The engine cannot run in this deployment (missing model or store)."""


class SimilarityService:
    """Model, candidate pools per profile, resolved references and a bounded result cache."""

    def __init__(self, store_root: Path, model_path: Path) -> None:
        self.store_root = Path(store_root)
        self.model_path = Path(model_path)
        self.engine = None
        self.pools: Dict[str, object] = {}
        self.references: Dict[str, dict] = {}
        self.loaded_at: Optional[float] = None
        self.load_seconds: Optional[float] = None
        self._lock = threading.Lock()
        self._cache: 'OrderedDict[str, dict]' = OrderedDict()
        self._cache_lock = threading.Lock()
        self._gate = threading.BoundedSemaphore(MAX_CONCURRENT)

    # -- loading ---------------------------------------------------------
    def load(self) -> None:
        with self._lock:
            if self.engine is not None:
                return
            from pipelines import similarity_ml as sim
            if not self.model_path.is_file():
                raise Unavailable('El modelo del motor de similitud no está disponible en este servidor')
            if not (self.store_root / 'base').is_dir():
                raise Unavailable('El almacén de features no está disponible en este servidor')
            t0 = time.perf_counter()
            engine = sim.SimilarityEngine.load(self.model_path)
            self.pools[DEFAULT_PROFILE] = engine.build_pool(self.store_root, DEFAULT_PROFILE)
            self.references = self._resolve_catalog(engine, self.pools[DEFAULT_PROFILE])
            self.engine = engine
            self.load_seconds = round(time.perf_counter() - t0, 3)
            self.loaded_at = time.time()

    def _resolve_catalog(self, engine, pool) -> Dict[str, dict]:
        """Resolve every named reference once; an unresolvable one is listed as unavailable."""
        from pipelines import similarity_ml as sim
        out = {}
        for ref_id, named in engine.spec['references'].items():
            entry = {'id': ref_id, 'name': named.get('name', ref_id), 'body': named['body'],
                     'source': named.get('source') or named.get('region_id')}
            cursor = pool.conn.cursor()
            try:
                ref = sim.resolve_reference(ref_id, self.store_root, engine.spec, conn=cursor)
                entry.update(available=True, reference=ref,
                             features={k: round(v, 6) for k, v in ref.values.items()},
                             percentiles=dict(ref.percentiles))
            except ValueError as exc:
                entry.update(available=False, reason=str(exc), reference=None, features={}, percentiles={})
            finally:
                cursor.close()
            out[ref_id] = entry
        return out

    def ensure(self):
        if self.engine is None:
            self.load()
        return self.engine

    def pool(self, profile: str):
        engine = self.ensure()
        pool = self.pools.get(profile)
        if pool is None:
            with self._lock:
                pool = self.pools.get(profile)
                if pool is None:
                    pool = engine.build_pool(self.store_root, profile)
                    self.pools[profile] = pool
        return pool

    def close(self) -> None:
        for pool in self.pools.values():
            pool.close()
        self.pools.clear()
        self.engine = None

    # -- catalog ---------------------------------------------------------
    def catalog(self) -> List[dict]:
        self.ensure()
        return [self._public(e) for e in self.references.values()]

    def _public(self, entry: dict, detail: bool = False) -> dict:
        meta = load_catalog_meta().get(entry['id'], {})
        out = {'id': entry['id'], 'name': entry['name'], 'body': entry['body'],
               'available': entry['available'], 'source': entry.get('source'), 'views': self._view_status(entry),
               'kind': meta.get('kind'), 'status': meta.get('status'), 'center': meta.get('center'),
               'sources': meta.get('sources', []), 'limitations': meta.get('limitations', [])}
        if not entry['available']:
            out['reason'] = entry['reason']
        if detail:
            out.update(features=entry['features'], percentiles=entry['percentiles'])
        return out

    def _view_status(self, entry: dict) -> Dict[str, str]:
        """For each fitted view: `reference_has_data` when the reference carries any of its features."""
        engine = self.engine
        values = entry['features']
        out = {}
        for vid, view in engine.model['views'].items():
            if not view['fitted']:
                out[vid] = 'not_fitted'
            elif any(f in values or f in entry['percentiles'] for f in view['features']):
                out[vid] = 'reference_has_data'
            else:
                out[vid] = 'reference_missing'
        return out

    # -- search ----------------------------------------------------------
    def resolve(self, ref_spec, profile: str):
        from pipelines import similarity_ml as sim
        engine = self.ensure()
        if isinstance(ref_spec, str):
            entry = self.references.get(ref_spec)
            if entry is not None:
                if not entry['available']:
                    raise KeyError(f"Referencia no disponible: {entry['reason']}")
                return entry['reference']
            pool = self.pool(profile)
            cursor = pool.conn.cursor()
            try:
                return sim.resolve_reference(ref_spec, self.store_root, engine.spec, conn=cursor)
            except ValueError as exc:
                raise KeyError(str(exc)) from exc
            finally:
                cursor.close()
        data = ref_spec.model_dump(exclude_none=False)
        data['features'] = {k: v for k, v in data['features'].items() if v is not None}
        return sim.reference_from_dict({k: v for k, v in data.items() if v is not None}, engine.spec)

    def canonical_key(self, req: SearchRequest, ref) -> str:
        """Hash of the normalised request: equivalent requests share a query id."""
        from pipelines import similarity_ml as sim
        engine = self.engine
        weights = sim.normalize_weights(req.weights, engine.spec, ref.body)
        total = sum(weights.values())
        scfg = engine.spec['search']
        payload = {
            'reference': {'body': ref.body, 'region_id': ref.region_id,
                          'values': {k: round(v, 9) for k, v in sorted(ref.values.items())},
                          'percentiles': {k: round(v, 9) for k, v in sorted(ref.percentiles.items())}},
            'weights': {k: round(v / total, 9) for k, v in sorted(weights.items())},
            'profile': req.profile, 'only_eligible': req.only_eligible, 'limit': req.limit,
            'missing_policy': req.missing_policy or scfg['default_missing_policy'],
            'fusion': req.fusion or scfg['default_fusion'],
            'bbox': [round(float(v), 9) for v in req.bbox] if req.bbox else None,
            'model': engine.model['fitted_at'], 'spec': engine.model['spec_hash'],
        }
        encoded = json.dumps(payload, sort_keys=True, allow_nan=False)
        return hashlib.sha256(encoded.encode()).hexdigest()

    def search(self, req: SearchRequest) -> dict:
        t_start = time.perf_counter()
        engine = self.ensure()
        ref = self.resolve(req.reference, req.profile)
        if req.bbox is not None:
            west, south, east, north = req.bbox
            if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
                raise ValueError('bbox debe ser [oeste, sur, este, norte] en grados, con oeste < este y sur < norte')
        query_id = self.canonical_key(req, ref)
        with self._cache_lock:
            cached = self._cache.get(query_id)
            if cached is not None:
                self._cache.move_to_end(query_id)
        if cached is not None:
            return {**cached, 'query_id': query_id,
                    'timings': {'engine_ms': 0.0, 'total_ms': round((time.perf_counter() - t_start) * 1000, 2),
                                'cache_hit': True}}
        pool = self.pool(req.profile)
        with self._gate:
            t_engine = time.perf_counter()
            response = engine.search(self.store_root, ref, weights=req.weights, profile=req.profile,
                                     only_eligible=req.only_eligible, limit=req.limit,
                                     missing_policy=req.missing_policy, fusion=req.fusion, bbox=req.bbox,
                                     pool=pool)
            engine_ms = (time.perf_counter() - t_engine) * 1000
        with self._cache_lock:
            self._cache[query_id] = response
            while len(self._cache) > CACHE_SIZE:
                self._cache.popitem(last=False)
        return {**response, 'query_id': query_id,
                'timings': {'engine_ms': round(engine_ms, 2),
                            'total_ms': round((time.perf_counter() - t_start) * 1000, 2), 'cache_hit': False}}

    def status(self) -> dict:
        return {'loaded': self.engine is not None, 'load_seconds': self.load_seconds,
                'model_fitted_at': self.engine.model['fitted_at'] if self.engine else None,
                'engine_status': self.engine.spec['status'] if self.engine else None,
                'profiles_loaded': {p: len(pool) for p, pool in self.pools.items()},
                'cached_queries': len(self._cache), 'references': len(self.references)}


def load_catalog_meta() -> Dict[str, dict]:
    """Per-reference kind, limitations and sources (`specs/analysis/referencias-v1.json`)."""
    try:
        return json.loads(CATALOG_PATH.read_text(encoding='utf-8'))['references']
    except (OSError, KeyError, ValueError):
        return {}


def default_store() -> Path:
    return Path(os.environ.get('ANALOGOS_FEATURE_STORE_DIR') or ROOT / 'data/feature_store_v1')


def default_model() -> Path:
    return Path(os.environ.get('ANALOGOS_SIMILARITY_MODEL')
                or ROOT / 'data/features/modelos-similitud/motor-similitud-ml-v1.joblib')


_service: Optional[SimilarityService] = None
_service_lock = threading.Lock()


def service() -> SimilarityService:
    global _service
    with _service_lock:
        if _service is None:
            _service = SimilarityService(default_store(), default_model())
        return _service


def configure(store_root: Optional[Path] = None, model_path: Optional[Path] = None) -> SimilarityService:
    """Replace the process-wide service (tests, or a deployment with explicit paths)."""
    global _service
    with _service_lock:
        if _service is not None:
            _service.close()
        _service = SimilarityService(store_root or default_store(), model_path or default_model())
        return _service


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
    return {'references': await run_in_threadpool(svc.catalog)}


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
