"""Scientific gates and rankings for the opt-in Jezero spectral pilot."""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass

import numpy as np
from scipy.stats import spearmanr
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from pipelines import jezero_spectral as spectral, similarity_ml as sim
from pipelines.spectral_bridge import MEASURED_STATUSES

MIN_EARTH = 200
MIN_MARS = 100
MIN_REPEAT_PAIRS = 10
MIN_REPEAT_RHO = 0.7
TOP_WEIGHTS = {'escabrosidad': .35, 'forma_hipsometrica': .25, 'organizacion': .10,
               'regimen_morfologico': .15}
COMBINED = {'topografia': .75, 'espectral': .25}
SEED = 20261114
STABILITY_SEEDS = tuple(range(1, 11))


def spectrum(row: dict) -> list[float]:
    records = row['indicators']
    return [rec['p50'] if (rec := records[f])['status'] in MEASURED_STATUSES else np.nan
            for f in spectral.INDICATORS]


def repeatability(rows: list[dict]) -> dict:
    """Independent revisits of mineral controls in both bodies, excluding test windows."""
    groups = defaultdict(list)
    for row in rows:
        if row['role'] == 'control' and row['partition'] == 'fit':
            groups[(row['body'], row['region_id'])].append(row)
    result = {}
    for body in ('Earth', 'Mars'):
        result[body] = {}
        for i, name in enumerate(spectral.INDICATORS):
            pairs = []
            for (planet, _), group in groups.items():
                if planet != body:
                    continue
                distinct = {r['scene_id']: spectrum(r)[i] for r in sorted(group, key=lambda r: r['scene_id'])}
                good = [v for v in distinct.values() if np.isfinite(v)]
                if len(good) >= 2:
                    pairs.append(good[:2])
            values = np.asarray(pairs).reshape(-1, 2)
            varying = len(values) >= MIN_REPEAT_PAIRS and np.all(np.ptp(values, axis=0) > 0)
            rho = float(spearmanr(values[:, 0], values[:, 1]).statistic) if varying else None
            result[body][name] = {'pairs': len(pairs), 'spearman': rho,
                                  'pass': rho is not None and rho >= MIN_REPEAT_RHO}
    return result


@dataclass
class SpectralMetric:
    columns: list[int]
    earth: list[sim.QuantileNormal]
    mars_reference: np.ndarray
    covariance: np.ndarray

    def score(self, rows: list[dict]) -> np.ndarray:
        if not rows:
            return np.empty(0)
        raw = np.array([spectrum(row) for row in rows])
        scores = np.column_stack([q.normal(raw[:, i]) for i, q in zip(self.columns, self.earth)])
        distances, _ = sim.mahalanobis_view(scores, self.mars_reference, self.covariance, 2)
        return distances


def fit_spectral(rows: list[dict], seed: int = SEED) -> tuple[SpectralMetric | None, dict]:
    """Fit on unique background windows, with inverse-probability resampling after support checks."""
    reference = [r for r in rows if r['body'] == 'Mars' and r['role'] == 'reference']
    duplicate_keys = Counter((r['body'], r['region_id']) for r in rows if r['role'] != 'control')
    if any(n > 1 for n in duplicate_keys.values()):
        raise ValueError('Cada ventana de referencia o de fondo requiere una sola medición')
    earth = [r for r in rows if r['body'] == 'Earth' and r['partition'] == 'fit' and r['role'] == 'background']
    mars = [r for r in rows if r['body'] == 'Mars' and r['role'] == 'background' and r['partition'] == 'fit']
    raw_e, raw_m = (np.asarray([spectrum(r) for r in group], dtype=float).reshape(-1, len(spectral.INDICATORS))
                    for group in (earth, mars))
    if any(not 0 < (r.get('inclusion_probability') or 0) <= 1 for r in earth):
        raise ValueError('Probabilidad de inclusión de fondo inválida')
    checks = repeatability(rows)
    ref = spectrum(reference[0]) if len(reference) == 1 else [np.nan] * len(spectral.INDICATORS)
    names, columns, transforms, mars_z = list(spectral.INDICATORS), [], [], []
    report = {'repeatability': checks, 'support': {}, 'reference_scene': reference[0]['scene_id'] if reference else None}
    weights = np.array([1 / r['inclusion_probability'] for r in earth])
    rng = np.random.default_rng(seed)
    for i, name in enumerate(names):
        e, m = raw_e[:, i], raw_m[:, i]
        fitted_e, fitted_m = np.isfinite(e), np.isfinite(m)
        mars_scenes = len({r['scene_id'] for r, ok in zip(mars, fitted_m) if ok})
        mars_units = len({r['geologic_unit'] for r, ok in zip(mars, fitted_m) if ok and r.get('geologic_unit')})
        ok = (fitted_e.sum() >= MIN_EARTH and fitted_m.sum() >= MIN_MARS and mars_scenes >= 2
              and mars_units >= 2 and np.isfinite(ref[i]) and np.unique(e[fitted_e]).size >= 2
              and all(checks[b][name]['pass'] for b in ('Earth', 'Mars')))
        report['support'][name] = {'earth': int(fitted_e.sum()), 'mars': int(fitted_m.sum()),
                                   'mars_scenes': mars_scenes, 'mars_units': mars_units, 'usable': bool(ok)}
        if ok:
            w = weights[fitted_e]
            sampled = rng.choice(e[fitted_e], size=4096, p=w / w.sum())
            columns.append(i)
            transforms.append(sim.QuantileNormal.fit(sampled, 1000))
            values = m[fitted_m]
            p = ((values < ref[i]).sum() + .5 * (values == ref[i]).sum()) / len(values)
            mars_z.append(float(sim.normal_from_percentile(p)))
    if len(columns) < 2:
        return None, report | {'pass': False, 'reason': 'Sin dos indicadores con soporte y repetibilidad'}
    z = np.column_stack([q.normal(raw_e[:, i]) for i, q in zip(columns, transforms)])
    complete = np.isfinite(z).all(axis=1)
    cov = np.eye(len(columns))
    if complete.sum() >= MIN_EARTH:
        w = weights[complete]
        sample = rng.choice(z[complete], size=4096, p=w / w.sum(), axis=0)
        cov, _ = sim.robust_covariance(sample, {'estimator': 'ledoit_wolf', 'max_rows': 4096,
                                               'shrinkage_to_diagonal': .05}, seed)
    return SpectralMetric(columns, transforms, np.asarray(mars_z), cov), report | {
        'pass': True, 'complete_earth': int(complete.sum()), 'covariance': cov.tolist(),
    }


def proxy_scores(frame: list[dict], earth_distances: dict[str, float]) -> dict[str, float]:
    """Predict a shortlist using coarse context fitted strictly outside the holdouts."""
    x = np.array([[row[k] for k in spectral.PROXY_COLUMNS] for row in frame], dtype=float)
    y = np.array([earth_distances.get(r['region_id'], np.nan) if r['partition'] == 'fit' else np.nan
                  for r in frame])
    good = np.isfinite(y) & np.isfinite(x).any(axis=1)
    candidates = np.isfinite(x).any(axis=1)
    if good.sum() < MIN_EARTH:
        return {}
    model = make_pipeline(SimpleImputer(strategy='median', keep_empty_features=True),
                          StandardScaler(), Ridge(alpha=10))
    model.fit(x[good], y[good], ridge__sample_weight=[1 / frame[i]['inclusion_probability']
                                                     for i in np.flatnonzero(good)])
    return {frame[i]['region_id']: float(d) for i, d in zip(np.flatnonzero(candidates), model.predict(x[candidates]))}


def rank(distances: dict[str, float]) -> list[str]:
    return sorted(distances, key=lambda rid: (distances[rid], rid))


def proposal_union(frame: list[dict], topo: dict, proxy: dict, budget: int, seed: int,
                   topographic: bool = True) -> list[str]:
    """Equal unique budget, with redistribution when lists overlap or exhaust their coverage."""
    ids = {r['region_id'] for r in frame}
    exploration = sorted(frame, key=lambda r: r['region_id'])
    rng = np.random.default_rng(seed)
    groups = defaultdict(list)
    for row in exploration:
        groups[row.get('stratum', row['block'])].append(row['region_id'])
    for group in groups.values():
        rng.shuffle(group)
    order = rng.permutation(sorted(groups))
    explore = [groups[group][i] for i in range(max(map(len, groups.values()), default=0))
               for group in order if i < len(groups[group])]
    sources = [iter(r for r in rank(topo) if r in ids)] if topographic else []
    sources.extend((iter(r for r in rank(proxy) if r in ids), iter(explore)))
    selected = {}
    while sources and len(selected) < budget:
        for source in sources[:]:
            fresh = next((rid for rid in source if rid not in selected), None)
            if fresh is None:
                sources.remove(source)
            else:
                selected[fresh] = None
            if len(selected) == budget:
                break
    return list(selected)


def retrieval_metrics(frame: list[dict], topo: dict, proxy: dict, observed: dict,
                      budget: int, seed: int = SEED) -> dict:
    """Replay the actual lists, including missing proxy and catalog coverage, on the held-out frame."""
    union = proposal_union(frame, topo, proxy, budget, seed)
    eligible = {r['region_id']: r for r in frame}
    baseline = [r for r in rank(topo) if r in eligible][:budget]
    spec_only = proposal_union(frame, topo, proxy, budget, seed, topographic=False)
    measured = [i for i in rank(observed) if i in eligible]
    weights_measured = np.asarray([1 / eligible[i]['inclusion_probability'] for i in measured])
    count = int(np.searchsorted(np.cumsum(weights_measured), .05 * weights_measured.sum())) if measured else 0
    cutoff = observed[measured[count]] if measured else -np.inf
    top = [i for i in measured if observed[i] <= cutoff]
    weights = {i: 1 / eligible[i]['inclusion_probability'] for i in top}
    total = sum(weights.values())
    report = {'budget': budget, 'measured': len(measured), 'top_5pct': len(top), 'seed': seed}
    for name, indexes in (('topography', baseline), ('union', union), ('zero_topography', spec_only)):
        ids = set(indexes)
        report[name] = {'unique': len(ids), 'recall': sum(w for i, w in weights.items() if i in ids) / total
                        if total else None}
    report['outside_topography'] = len(set(spec_only) - set(baseline))
    report['pass'] = bool(total and set(proxy).intersection(eligible) and len(baseline) == len(union) == budget
                          and report['outside_topography']
                          and report['union']['recall'] > report['topography']['recall'])
    return report


def ndcg(scores: dict[str, float], relevance: dict[str, float], k: int = 20) -> float:
    n = min(k, len(scores))
    discount = 1 / np.log2(np.arange(2, n + 2))
    dcg = (np.exp2([relevance[r] for r in rank(scores)[:n]]) - 1) @ discount
    ideal = (np.exp2(sorted(relevance.values(), reverse=True)[:n]) - 1) @ discount
    return float(dcg / ideal) if ideal else 0.0


def relevance_metrics(frame: list[dict], rankings: dict[str, dict], reviews: list[dict]) -> dict:
    """Paired nDCG on each independent geographic block, bootstrapped by block."""
    ids = set.intersection({r['region_id'] for r in frame}, *(set(v) for v in rankings.values()))
    reviews_by_id = defaultdict(dict)
    for review in reviews:
        score, rid, reviewer = review['score'], review['region_id'], review['reviewer']
        if rid not in ids:
            continue
        if (not reviewer or isinstance(score, bool) or score not in (0, 1, 2, 3)
                or not review.get('source') or reviewer in reviews_by_id[rid]):
            raise ValueError('Revisión ciega inválida o duplicada')
        reviews_by_id[rid][reviewer] = score
    reviewers = {name for values in reviews_by_id.values() for name in values}
    if len(reviewers) != 2 or any(set(reviews_by_id[rid]) != reviewers for rid in ids):
        return {'pass': False, 'reason': 'Faltan dos evaluaciones independientes por ventana',
                'windows': len(ids), 'reviewed_by_two': sum(len(v) == 2 for v in reviews_by_id.values())}
    blocks = defaultdict(dict)
    for row in frame:
        rid = row['region_id']
        if rid in ids:
            blocks[row['block']][rid] = float(np.mean(list(reviews_by_id[rid].values())))
    if len(blocks) < 3 or any(len(values) < 20 for values in blocks.values()):
        return {'pass': False, 'reason': 'Se requieren 20 ventanas comparables por bloque reservado',
                'block_sizes': {block: len(values) for block, values in blocks.items()}}
    scores = {block: {name: ndcg({r: distances[r] for r in truth}, truth)
                      for name, distances in rankings.items()} for block, truth in sorted(blocks.items())}
    delta = np.array([block['combined'] - block['topography'] for block in scores.values()])
    rng = np.random.default_rng(SEED)
    replicates = rng.choice(delta, size=(10000, len(delta)), replace=True).mean(axis=1)
    interval = np.quantile(replicates, [.025, .975]).tolist()
    return {'pass': interval[0] > 0, 'delta_ndcg20': float(delta.mean()), 'ci95': interval, 'blocks': scores}


def topo_weights(spec: dict, with_gmm: bool) -> dict:
    weights = dict.fromkeys(spec['views'], 0.0) | TOP_WEIGHTS
    if not with_gmm:
        weights['regimen_morfologico'] = 0
    return weights


def combine(topography: dict[str, float], spectroscopy: dict[str, float]) -> dict[str, float]:
    return {rid: COMBINED['topografia'] * topography[rid] + COMBINED['espectral'] * score
            for rid, score in spectroscopy.items() if rid in topography}
