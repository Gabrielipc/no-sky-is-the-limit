"""Per-view shortlists (phase C of the selection bias mitigation plan).

Instead of enriching only what passes a topographic filter, every view proposes its own K
windows with a cheap, global signal (`enrichment_global` or the base), and the union is enriched.
Spec: `specs/analysis/recuperacion-por-vista-v1.json`.

- `topografica`: the current relief/slope ranking (Jezero for the arid profile, Haworth for polar).
- `termica`, `entorno`: Earth percentile of each proxy; distance = mean |percentile - target| over
  the available proxies (at least `min_proxy_fraction` of them).
- `espectral`: proxy targets when given; otherwise stratified exploration among bare, dry windows
  (where EMIT observes), optionally checked in CMR.

`retriever_ranks` gives the rank of every window under a retriever, which the recall estimate of
phase D uses to ask whether a well-scored background window would have been proposed.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Callable
import urllib.parse
import urllib.request

import numpy as np

from pipelines import etl_sampling as sampling

ROOT = Path(__file__).resolve().parents[1]
SPEC_PATH = ROOT / 'specs/analysis/recuperacion-por-vista-v1.json'
CMR_GRANULES = 'https://cmr.earthdata.nasa.gov/search/granules.json'


def load_spec(path: Path = SPEC_PATH) -> dict:
    return json.loads(Path(path).read_text(encoding='utf-8'))


def design_id(view: str, profile: str) -> str:
    return f'retrieval-{view}-{profile}-v1'


def parse_targets(items: list[str] | None) -> dict[str, dict[str, float]]:
    """['termica:ati_cmg_per_k=0.7', ...] -> {'termica': {'ati_cmg_per_k': 0.7}}."""
    out: dict[str, dict[str, float]] = {}
    for item in items or []:
        view, rest = item.split(':', 1)
        col, value = rest.split('=', 1)
        p = float(value)
        if not 0.0 <= p <= 1.0:
            raise ValueError(f'Percentil fuera de [0, 1]: {item}')
        out.setdefault(view.strip(), {})[col.strip()] = p
    return out


def resolve_targets(spec: dict, view: str, profile: str, cli_targets: dict, reference: dict | None) -> dict[str, float]:
    vcfg = spec['views'][view]
    targets = dict(spec['profiles'].get(profile, {}).get(view, {}))
    percentiles = (reference or {}).get('percentiles', {})
    for col, pcfg in vcfg.get('proxies', {}).items():
        feat = pcfg.get('reference_feature')
        if feat and feat in percentiles and percentiles[feat] is not None:
            targets[col] = float(percentiles[feat])
    targets.update(cli_targets.get(view, {}))
    return {c: p for c, p in targets.items() if c in vcfg.get('proxies', {})}


def allocate_by_weights(total: int, engine_weights: dict[str, float], spec: dict | None = None) -> dict[str, int]:
    """Split `total` shortlist slots among retrievers in proportion to the weights of their engine views."""
    spec = spec or load_spec()
    w = {v: sum(engine_weights.get(ev, 0.0) for ev in cfg['engine_views']) for v, cfg in spec['views'].items()}
    w = {v: x for v, x in w.items() if x > 0}
    if not w or total <= 0:
        return {}
    s = sum(w.values())
    raw = {v: total * x / s for v, x in w.items()}
    alloc = {v: int(np.floor(r)) for v, r in raw.items()}
    for v in sorted(raw, key=lambda v: raw[v] - alloc[v], reverse=True)[: total - sum(alloc.values())]:
        alloc[v] += 1
    return {v: k for v, k in alloc.items() if k > 0}


# ---------------------------------------------------------------------------
# Frame of proxies
# ---------------------------------------------------------------------------
@dataclass
class ProxyFrame:
    region_id: np.ndarray
    longitude: np.ndarray
    latitude: np.ndarray
    eligible: np.ndarray
    columns: dict[str, np.ndarray]
    sampling_frame: sampling.Frame

    def __len__(self) -> int:
        return len(self.region_id)


def load_proxy_frame(store, profile: str, spec: dict | None = None, holdout_bboxes: list | None = None) -> ProxyFrame:
    from pipelines.etl_store import eligibility_expression
    from pipelines import etl_eligibility as eligibility
    spec = spec or load_spec()
    if holdout_bboxes is None:
        from pipelines import similarity_ml as sim
        holdout_bboxes = [b['bbox'] for b in sim.load_spec()['fit']['holdout_basins']]
    proxy_cols = sorted({c for v in spec['views'].values() for c in v.get('proxies', {})}
                        | {p['status'] for v in spec['views'].values() for p in v.get('proxies', {}).values()}
                        | {'bare_or_sparse_fraction', 'relief_p95_p05_m', 'snow_months_fraction_cmg',
                           'precip_annual_mm_cmg'})
    p = eligibility.get_profile(profile)
    where = ["body = 'Earth'", "qa_status = 'rankable'"] + [f'NOT {sampling._bbox_sql(b)}' for b in holdout_bboxes]
    sql = (f"SELECT region_id, longitude, latitude, ({eligibility_expression(profile)}) = '{p.eligible_status}' AS eligible, "
           f"{', '.join(proxy_cols)} FROM features_unified WHERE {' AND '.join(where)} ORDER BY region_id")
    with store._connect() as conn:
        cur = conn.execute(sql)
        names = [d[0] for d in cur.description]
        rows = cur.fetchall()
    data = {n: [r[i] for r in rows] for i, n in enumerate(names)}

    def num(name):
        return np.array([np.nan if v is None else float(v) for v in data[name]], dtype='float64')

    cols = {}
    for c in proxy_cols:
        if c.endswith('_status'):
            cols[c] = np.array([v or '' for v in data[c]], dtype=object)
        else:
            cols[c] = num(c)
    ids = np.array(data['region_id'], dtype=object)
    lon, lat = num('longitude'), num('latitude')
    frame = sampling.Frame(ids, lon, lat, cols['relief_p95_p05_m'], cols['precip_annual_mm_cmg'],
                           cols['snow_months_fraction_cmg'])
    return ProxyFrame(ids, lon, lat, np.array([bool(v) for v in data['eligible']]), cols, frame)


def percentile_ranks(values: np.ndarray) -> np.ndarray:
    """Mid-rank Earth percentile in [0, 1] of each finite value (ties share their mid rank)."""
    v = np.asarray(values, dtype='float64')
    out = np.full(v.shape, np.nan)
    ok = np.isfinite(v)
    n = int(ok.sum())
    if n == 0:
        return out
    sorted_v = np.sort(v[ok])
    lo = np.searchsorted(sorted_v, v[ok], side='left')
    hi = np.searchsorted(sorted_v, v[ok], side='right')
    out[ok] = ((lo + hi) / 2.0) / n
    return out


def proxy_distance(frame: ProxyFrame, targets: dict[str, float], spec: dict, view: str) -> np.ndarray:
    """Mean |percentile - target| over available proxies; NaN with too few proxies."""
    proxies = spec['views'][view]['proxies']
    dists, avail = [], []
    for col, target in targets.items():
        values = frame.columns[col].copy()
        status = frame.columns.get(proxies[col]['status'])
        if status is not None:
            values[status != 'measured'] = np.nan
        p = percentile_ranks(values)
        dists.append(np.abs(p - target))
        avail.append(np.isfinite(p))
    if not dists:
        return np.full(len(frame), np.nan)
    D = np.vstack(dists)
    A = np.vstack(avail)
    need = max(1, int(np.ceil(spec.get('min_proxy_fraction', 0.5) * len(targets))))
    with np.errstate(invalid='ignore'):
        mean = np.nanmean(np.where(A, D, np.nan), axis=0)
    return np.where(A.sum(axis=0) >= need, mean, np.nan)


def cmr_covers(short_name: str, lon: float, lat: float) -> bool:
    """True if CMR lists at least one granule of the collection over the point (metadata only)."""
    params = {'short_name': short_name, 'point': f'{lon:.5f},{lat:.5f}', 'page_size': 0}
    with urllib.request.urlopen(f'{CMR_GRANULES}?{urllib.parse.urlencode(params)}', timeout=60) as r:
        return int(r.headers.get('CMR-Hits', '0')) > 0


def retriever_ranks(frame: ProxyFrame, view: str, targets: dict[str, float], spec: dict,
                    only_eligible: bool = True) -> np.ndarray:
    """1-based rank of every window under a proxy retriever (inf where it cannot be ranked)."""
    d = proxy_distance(frame, targets, spec, view)
    if only_eligible:
        d = np.where(frame.eligible, d, np.nan)
    key = np.where(np.isfinite(d), d, np.inf)
    order = np.lexsort((frame.region_id.astype(str), key))
    ranks = np.empty(len(d))
    ranks[order] = np.arange(1, len(d) + 1)
    return np.where(np.isfinite(d), ranks, np.inf)


def _items(frame: ProxyFrame, idx, method: str, dist=None) -> list[dict]:
    return [{'region_id': str(frame.region_id[i]), 'longitude': float(frame.longitude[i]),
             'latitude': float(frame.latitude[i]), 'method': method,
             'retrieval_distance': None if dist is None else float(dist[i])} for i in idx]


def shortlists(store, counts: dict[str, int], *, profile: str = 'arid_mars_surface_v2', ref_json: str | None = None,
               targets: list[str] | None = None, check_coverage: bool = False, seed: int = 20261114,
               only_eligible: bool = True, spec: dict | None = None,
               coverage_fn: Callable[[str, float, float], bool] = cmr_covers,
               log: Callable[[str], None] = lambda m: print(m, flush=True)) -> dict[str, list[dict]]:
    """K windows per requested view."""
    spec = spec or load_spec()
    cli_targets = parse_targets(targets)
    reference = json.loads(Path(ref_json).read_text(encoding='utf-8')) if ref_json else None
    out: dict[str, list[dict]] = {}
    frame = None
    for view, k in counts.items():
        if k <= 0:
            continue
        if view in spec.get('no_retrieval', {}):
            log(f'Recuperación {view}: no disponible ({spec["no_retrieval"][view]})')
            continue
        if view not in spec['views']:
            raise ValueError(f'Vista de recuperación desconocida: {view}')
        method = spec['views'][view]['method']
        if method == 'topographic_rank':
            from scripts.etl_puentes import candidate_sites
            arid, polar = (k, 0) if profile != 'polar_cold_v1' else (0, k)
            rows = candidate_sites(store, arid, polar)
            out[view] = [{'region_id': r['region_id'], 'longitude': float(r['longitude']),
                          'latitude': float(r['latitude']), 'method': method, 'retrieval_distance': None} for r in rows]
            log(f'Recuperación {view}: {len(out[view])} ventanas por ranking topográfico')
            continue
        if frame is None:
            frame = load_proxy_frame(store, profile, spec)
        tgt = resolve_targets(spec, view, profile, cli_targets, reference)
        if tgt:
            ranks = retriever_ranks(frame, view, tgt, spec, only_eligible)
            order = np.argsort(ranks, kind='stable')
            order = order[np.isfinite(ranks[order])]
            dist = proxy_distance(frame, tgt, spec, view)
            pool = order[: k * (spec.get('coverage_candidates_factor', 5) if check_coverage else 1)]
            chosen = list(pool)
            if check_coverage and spec['views'][view].get('coverage_product'):
                prod = spec['views'][view]['coverage_product']
                chosen = [i for i in pool if coverage_fn(prod, frame.longitude[i], frame.latitude[i])]
            out[view] = _items(frame, chosen[:k], 'proxy_target', dist)
            log(f'Recuperación {view}: {len(out[view])} ventanas por objetivos {tgt}')
        elif method == 'proxy_target_or_exploration':
            filt = spec['views'][view].get('exploration_filter', {})
            mask = np.ones(len(frame), dtype=bool)
            if only_eligible:
                mask &= frame.eligible
            if 'bare_or_sparse_fraction_min' in filt:
                mask &= frame.columns['bare_or_sparse_fraction'] >= filt['bare_or_sparse_fraction_min']
            if 'precip_annual_mm_cmg_max' in filt:
                precip = frame.columns['precip_annual_mm_cmg']
                mask &= ~(precip > filt['precip_annual_mm_cmg_max'])  # unknown precipitation is kept
            idx = np.flatnonzero(mask)
            sub = sampling.Frame(*(getattr(frame.sampling_frame, f)[idx] for f in
                                   ('region_id', 'longitude', 'latitude', 'relief', 'precip', 'snow')))
            factor = spec.get('coverage_candidates_factor', 5) if check_coverage else 1
            items = sampling.stratified_sample(sub, k * factor, seed)
            if check_coverage and spec['views'][view].get('coverage_product'):
                prod = spec['views'][view]['coverage_product']
                items = [it for it in items if coverage_fn(prod, it['longitude'], it['latitude'])]
            out[view] = [it | {'method': 'exploration', 'retrieval_distance': None} for it in items[:k]]
            log(f'Recuperación {view}: {len(out[view])} ventanas por exploración estratificada')
        else:
            log(f'Recuperación {view}: sin objetivo (usa --target o una referencia con percentiles); se omite')
    return out
