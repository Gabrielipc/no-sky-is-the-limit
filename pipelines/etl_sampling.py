"""Background samples for unbiased enrichment (phase B of the selection bias mitigation plan).

The bridge views of the similarity engine compare by within-body rank, so they must be fitted on
a population that represents Earth, not on the topographic candidates. This module draws that
population from the windows of the store and records, for each sampled window, its stratum and
inclusion probability (`enrichment_selection`), so the engine can weight it by 1/p.

- `stratified_sample`: latitude band x surface environment (coarse aridity / snow from
  `enrichment_global`) x relief tercile, proportional allocation with a floor per stratum.
- `cluster_sample`: two-stage sample by MODIS tile (random tiles, then windows inside each tile),
  for products whose cost is per tile (fine apparent thermal inertia: ~6 GB per tile and year).

The Mojave holdout basin of the engine spec is always excluded.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np

from pipelines import etl_surface_fetch as fetch

LAT_BANDS = ((0.0, 23.5, 'tropical'), (23.5, 40.0, 'subtropical'), (40.0, 55.0, 'temperate'),
             (55.0, 66.5, 'boreal'), (66.5, 90.01, 'polar'))
ARIDITY_CLASSES = ((250.0, 'arid'), (500.0, 'semiarid'), (1000.0, 'subhumid'), (np.inf, 'humid'))
SNOW_FRACTION_CLASS = 0.5
FRAME_COLUMNS = ('region_id', 'longitude', 'latitude', 'relief_p95_p05_m', 'precip_annual_mm_cmg',
                 'snow_months_fraction_cmg')


@dataclass
class Frame:
    """Sampling frame: Earth rankable windows outside the holdout basins."""
    region_id: np.ndarray
    longitude: np.ndarray
    latitude: np.ndarray
    relief: np.ndarray
    precip: np.ndarray
    snow: np.ndarray

    def __len__(self) -> int:
        return len(self.region_id)


def _bbox_sql(b) -> str:
    return f'(longitude BETWEEN {float(b[0])} AND {float(b[2])} AND latitude BETWEEN {float(b[1])} AND {float(b[3])})'


def load_frame(store, holdout_bboxes: list | None = None, extra_where: str = '') -> Frame:
    """Windows eligible for any background design (Earth, rankable, outside holdouts)."""
    if holdout_bboxes is None:
        from pipelines import similarity_ml as sim
        holdout_bboxes = [b['bbox'] for b in sim.load_spec()['fit']['holdout_basins']]
    where = ["body = 'Earth'", "qa_status = 'rankable'"] + [f'NOT {_bbox_sql(b)}' for b in holdout_bboxes]
    if extra_where:
        where.append(f'({extra_where})')
    with store._connect() as conn:
        rows = conn.execute(f"SELECT {', '.join(FRAME_COLUMNS)} FROM features_unified WHERE {' AND '.join(where)} "
                            'ORDER BY region_id').fetchall()
    if not rows:
        empty = np.array([], dtype=float)
        return Frame(np.array([], dtype=object), empty, empty, empty, empty, empty)
    cols = list(zip(*rows))
    f = lambda i: np.array([np.nan if v is None else float(v) for v in cols[i]])  # noqa: E731
    return Frame(np.array(cols[0], dtype=object), f(1), f(2), f(3), f(4), f(5))


def strata(frame: Frame) -> np.ndarray:
    """Stratum label per window: latitude band | environment | relief tercile."""
    n = len(frame)
    lat = np.abs(frame.latitude)
    band = np.full(n, 'polar', dtype=object)
    for low, high, name in LAT_BANDS:
        band[(lat >= low) & (lat < high)] = name
    env = np.full(n, 'unknown', dtype=object)
    for limit, name in ARIDITY_CLASSES[::-1]:
        env[np.isfinite(frame.precip) & (frame.precip < limit)] = name
    env[np.isfinite(frame.snow) & (frame.snow >= SNOW_FRACTION_CLASS)] = 'snow'
    relief = np.full(n, 'r?', dtype=object)
    ok = np.isfinite(frame.relief)
    if ok.any():
        t1, t2 = np.quantile(frame.relief[ok], [1 / 3, 2 / 3])
        relief[ok] = np.where(frame.relief[ok] <= t1, 'r1', np.where(frame.relief[ok] <= t2, 'r2', 'r3'))
    return np.array([f'{b}|{e}|{r}' for b, e, r in zip(band, env, relief)], dtype=object)


def allocate(sizes: dict[str, int], n: int, min_per_stratum: int = 1) -> dict[str, int]:
    """Proportional allocation (largest remainder) with a floor, capped by each stratum size."""
    total = sum(sizes.values())
    if total == 0 or n <= 0:
        return {k: 0 for k in sizes}
    raw = {k: n * v / total for k, v in sizes.items()}
    alloc = {k: min(v, max(min_per_stratum, int(np.floor(raw[k])))) for k, v in sizes.items()}
    remaining = n - sum(alloc.values())
    for k in sorted(sizes, key=lambda k: raw[k] - np.floor(raw[k]), reverse=True):
        if remaining <= 0:
            break
        if alloc[k] < sizes[k]:
            alloc[k] += 1
            remaining -= 1
    return alloc


def stratified_sample(frame: Frame, n: int, seed: int, min_per_stratum: int = 1) -> list[dict]:
    """Stratified random sample; each item carries its stratum and inclusion probability n_h / N_h."""
    labels = strata(frame)
    rng = np.random.default_rng(seed)
    uniq, counts = np.unique(labels, return_counts=True)
    alloc = allocate(dict(zip(uniq.tolist(), counts.tolist())), n, min_per_stratum)
    out = []
    for label in sorted(alloc):
        idx = np.flatnonzero(labels == label)
        k = alloc[label]
        if k == 0:
            continue
        chosen = np.sort(rng.choice(idx, size=k, replace=False))
        p = k / len(idx)
        out.extend({'region_id': str(frame.region_id[i]), 'longitude': float(frame.longitude[i]),
                    'latitude': float(frame.latitude[i]), 'stratum': label, 'inclusion_probability': p}
                   for i in chosen)
    return out


def cluster_sample(frame: Frame, n_clusters: int, per_cluster: int, seed: int) -> list[dict]:
    """Two-stage sample by MODIS tile; p = (k / K) * (m_c / N_c)."""
    if not len(frame):
        return []
    tiles = np.array([f'h{h:02d}v{v:02d}' for h, v in
                      (fetch.modis_tile(lon, lat) for lon, lat in zip(frame.longitude, frame.latitude))], dtype=object)
    uniq = np.unique(tiles)
    rng = np.random.default_rng(seed)
    k = min(n_clusters, len(uniq))
    chosen_tiles = np.sort(rng.choice(uniq, size=k, replace=False))
    out = []
    for tile in chosen_tiles:
        idx = np.flatnonzero(tiles == tile)
        m = min(per_cluster, len(idx))
        chosen = np.sort(rng.choice(idx, size=m, replace=False))
        p = (k / len(uniq)) * (m / len(idx))
        out.extend({'region_id': str(frame.region_id[i]), 'longitude': float(frame.longitude[i]),
                    'latitude': float(frame.latitude[i]), 'stratum': f'tile:{tile}', 'inclusion_probability': p}
                   for i in chosen)
    return out


def stratified_design_id(n: int, seed: int) -> str:
    return f'background-strat-v1-n{n}-s{seed}'


def cluster_design_id(k: int, m: int, seed: int) -> str:
    return f'background-cluster-v1-k{k}-m{m}-s{seed}'


def selection_rows(items: list[dict], design_id: str, reason: str, updated_at: datetime, *,
                   view: str | None = None, seed: int | None = None) -> list[dict]:
    return [{'region_id': it['region_id'], 'design_id': design_id, 'selection_reason': reason,
             'view': it.get('view', view), 'stratum': it.get('stratum'),
             'inclusion_probability': it.get('inclusion_probability'), 'seed': seed, 'updated_at': updated_at}
            for it in items]


def background_weights(store) -> dict[str, float]:
    """region_id -> inclusion probability of the background designs (max over designs)."""
    edir = Path(store.root) / 'enrichment' / 'selection'
    if not any(edir.glob('*.parquet')):
        return {}
    with store._connect() as conn:
        rows = conn.execute("SELECT region_id, max(inclusion_probability) FROM enrichment_selection_latest "
                            "WHERE selection_reason IN ('background', 'background_cluster') "
                            'AND inclusion_probability > 0 GROUP BY region_id').fetchall()
    return {r[0]: float(r[1]) for r in rows}
