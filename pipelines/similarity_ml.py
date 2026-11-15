"""Unsupervised ML similarity engine: Earth analogues of a Mars or Moon window.

Implements the viable paradigm of the ML feasibility analysis (2026-11-14): no supervised
"analogue score" (there are no independent labels), but metric learning and unsupervised
structure fitted on the Earth catalogue, fused per query with user-chosen view weights.

- Each *view* (dimension) learns its metric without labels: every feature is mapped to
  normal scores through quantiles fitted on Earth windows, and a robust covariance
  (Minimum Covariance Determinant, shrunk towards its diagonal) is estimated in that
  space. The Mahalanobis distance therefore discounts collinearity: the five ruggedness
  descriptors (rank rho 0.89-0.96) do not count five times. The squared distance is
  mapped through the chi-square CDF of its degrees of freedom, so views with different
  numbers of available features yield comparable distances in [0, 1].
- Bridge features (`functional_contract_bridge`: spectral, thermal, radar) differ in
  instrument and units between bodies, so they are compared by within-body percentile:
  the Earth side by its fitted quantiles, the reference by its own body population (or
  an explicit percentile), never by raw value.
- A Gaussian mixture (components chosen by BIC) over the direct topographic features
  finds landform regimes; the `regimen_morfologico` view is 1 - Bhattacharyya
  coefficient between candidate and reference posteriors.
- Structured missingness: a feature that is absent is never imputed. Distances use the
  marginal covariance of the features both sides have; a missing view is handled by an
  explicit policy and widens the score interval.
- Weights can be calibrated from blind pairwise preferences (Bradley-Terry, non-negative
  coefficients) once Paso 7 labels exist; until then they are a stated prior.

Spec: `specs/analysis/motor-similitud-ml-v1.json`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import contextlib
import hashlib
import json
import math
from pathlib import Path
from typing import Callable, Iterable

import duckdb
import joblib
import numpy as np
from scipy import optimize, stats
from sklearn.covariance import LedoitWolf, MinCovDet
from sklearn.mixture import GaussianMixture

from pipelines import etl_contract as contract
from pipelines import etl_eligibility as eligibility

ROOT = Path(__file__).resolve().parents[1]
SPEC_PATH = ROOT / 'specs/analysis/motor-similitud-ml-v1.json'
DEFAULT_MODEL_DIR = ROOT / 'data/features/modelos-similitud'
MODEL_FORMAT = 1
P_EPS = 1e-4  # normal scores are clipped to about +-3.72
DIRECT = 'direct_metric'
BRIDGE = 'functional_contract_bridge'
MISSING_POLICIES = ('neutral', 'renormalize', 'require')
FUSIONS = ('weighted', 'rrf')
_SQL_IDENT = set('abcdefghijklmnopqrstuvwxyz0123456789_')


def load_spec(path: Path = SPEC_PATH) -> dict:
    return json.loads(Path(path).read_text(encoding='utf-8'))


def spec_hash(spec: dict) -> str:
    return hashlib.sha256(json.dumps(spec, sort_keys=True).encode('utf-8')).hexdigest()[:16]


def _display_path(path: Path) -> str:
    """Repo-relative path when possible, so reports do not leak local home directories."""
    p = Path(path).resolve()
    try:
        return str(p.relative_to(ROOT))
    except ValueError:
        return p.name


def _ident(name: str) -> str:
    if not name or set(name) - _SQL_IDENT:
        raise ValueError(f'Identificador de columna inválido: {name!r}')
    return name


# ---------------------------------------------------------------------------
# Spec parsing
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class FeatureDef:
    id: str
    view: str
    comparability: str
    columns: dict[str, str]
    status_columns: dict[str, str] = field(default_factory=dict)

    def column(self, body: str) -> str | None:
        return self.columns.get(body)


def parse_features(spec: dict) -> dict[str, FeatureDef]:
    out: dict[str, FeatureDef] = {}
    for view_id, view in spec['views'].items():
        if view['kind'] != 'metric':
            continue
        comp = view['comparability']
        for item in view['features']:
            if isinstance(item, str):
                fdef = FeatureDef(item, view_id, comp, {b: item for b in contract.BODY_ENUM})
            else:
                fdef = FeatureDef(item['id'], view_id, comp, dict(item['columns']),
                                  dict(item.get('status_columns', {})))
            if fdef.id in out:
                raise ValueError(f'Feature duplicada en el motor: {fdef.id}')
            out[fdef.id] = fdef
    return out


def view_ids(spec: dict) -> tuple[str, ...]:
    return tuple(spec['views'])


# ---------------------------------------------------------------------------
# Learned per-feature transform
# ---------------------------------------------------------------------------
@dataclass
class QuantileNormal:
    """Empirical CDF fitted on Earth values, mapped to standard normal scores."""

    quantiles: np.ndarray
    probs: np.ndarray
    n_fit: int

    @classmethod
    def fit(cls, values: np.ndarray, n_quantiles: int) -> 'QuantileNormal':
        v = np.asarray(values, dtype='float64')
        v = v[np.isfinite(v)]
        probs = np.linspace(0.0, 1.0, max(2, min(n_quantiles, v.size)))
        return cls(np.quantile(v, probs), probs, int(v.size))

    def percentile(self, x) -> np.ndarray:
        x = np.atleast_1d(np.asarray(x, dtype='float64'))
        q, p = self.quantiles, self.probs
        # Average of forward and backward interpolation so ties map to their mid-rank (as sklearn).
        out = 0.5 * (np.interp(x, q, p) - np.interp(-x, -q[::-1], -p[::-1]))
        out[~np.isfinite(x)] = np.nan
        return out

    def normal(self, x) -> np.ndarray:
        p = self.percentile(x)
        return stats.norm.ppf(np.clip(p, P_EPS, 1 - P_EPS))

    def outside(self, x: float) -> bool:
        return bool(np.isfinite(x) and (x < self.quantiles[0] or x > self.quantiles[-1]))


def normal_from_percentile(p) -> np.ndarray:
    return stats.norm.ppf(np.clip(np.asarray(p, dtype='float64'), P_EPS, 1 - P_EPS))


def robust_covariance(z: np.ndarray, cfg: dict, seed: int) -> tuple[np.ndarray, str]:
    """Robust covariance of complete normal-score rows, shrunk towards its diagonal."""
    n, k = z.shape
    if k == 1:
        return np.array([[float(np.var(z[:, 0])) or 1.0]]), 'variance'
    rng = np.random.default_rng(seed)
    if n > cfg['max_rows']:
        z = z[rng.choice(n, cfg['max_rows'], replace=False)]
    if z.shape[0] >= cfg['fallback_below_rows']:
        cov, name = MinCovDet(random_state=seed).fit(z).covariance_, 'min_cov_det'
    else:
        cov, name = LedoitWolf().fit(z).covariance_, 'ledoit_wolf'
    lam = cfg['shrinkage_to_diagonal']
    cov = (1 - lam) * cov + lam * np.diag(np.diag(cov))
    return cov, name


# ---------------------------------------------------------------------------
# Store access
# ---------------------------------------------------------------------------
def connect(store_root: Path, memory_limit: str = '2GB', threads: int = 4) -> duckdb.DuckDBPyConnection:
    spec = contract.load_store_spec()
    conn = duckdb.connect()
    spill = Path(store_root) / spec['duckdb_out_of_core']['temp_directory_name']
    contract.configure_duckdb(conn, spill, memory_limit=memory_limit, threads=threads)
    contract.register_unified_views(conn, Path(store_root))
    return conn


def unified_columns(conn: duckdb.DuckDBPyConnection) -> set[str]:
    return {r[0] for r in conn.execute('DESCRIBE features_unified').fetchall()}


def _bbox_sql(bbox: Iterable[float]) -> str:
    w, s, e, n = (float(v) for v in bbox)
    return f'(longitude BETWEEN {w} AND {e} AND latitude BETWEEN {s} AND {n})'


def _fetch(conn, sql: str, params: list | None = None) -> dict[str, np.ndarray]:
    return conn.execute(sql, params or []).fetchnumpy()


def _float(arr) -> np.ndarray:
    a = np.ma.filled(np.ma.asarray(arr).astype('float64'), np.nan) if np.ma.isMaskedArray(arr) else arr
    return np.asarray(a, dtype='float64')


def _masked_values(data: dict, column: str, status_column: str | None) -> np.ndarray:
    vals = _float(data[column]).copy()
    if status_column:
        st = np.asarray(data[status_column], dtype=object)
        vals[st != 'measured'] = np.nan
    return vals


# ---------------------------------------------------------------------------
# Fitting
# ---------------------------------------------------------------------------
def fit_model(store_root: Path, spec: dict | None = None, *, sample_size: int | None = None,
              seed: int | None = None, memory_limit: str = '2GB', threads: int = 4,
              log: Callable[[str], None] = lambda _m: None) -> dict:
    """Fit per-view metrics and the landform GMM on Earth windows outside holdout basins."""
    spec = spec or load_spec()
    fcfg = spec['fit']
    seed = fcfg['seed'] if seed is None else seed
    sample_size = sample_size or fcfg['sample_size']
    features = parse_features(spec)
    holdout = [b['bbox'] for b in fcfg['holdout_basins']]
    where = [f"body = '{fcfg['body']}'", f"qa_status = '{fcfg['qa_status']}'"]
    where += [f'NOT {_bbox_sql(b)}' for b in holdout]
    where_sql = ' AND '.join(where)

    with connect(store_root, memory_limit, threads) as conn:
        present = unified_columns(conn)
        pool_n = conn.execute(f'SELECT count(*) FROM features_unified WHERE {where_sql}').fetchone()[0]
        direct = [f for f in features.values() if f.comparability == DIRECT and f.column('Earth') in present]
        bridges = [f for f in features.values() if f.comparability == BRIDGE
                   and f.column('Earth') in present and f.status_columns.get('Earth') in present]
        log(f'Conjunto de ajuste: {pool_n} ventanas terrestres rankables fuera de cuencas reservadas')
        values: dict[str, np.ndarray] = {}
        if direct and pool_n:
            cols = ', '.join(_ident(f.column('Earth')) for f in direct)
            data = _fetch(conn, f"""
                SELECT {cols} FROM (SELECT * FROM features_unified WHERE {where_sql}) t
                USING SAMPLE reservoir({int(sample_size)} ROWS) REPEATABLE ({int(seed)})""")
            for f in direct:
                values[f.id] = _float(data[f.column('Earth')])
        # Bridge enrichments are on demand and sparse: fit them on the background sample
        # (weighted by 1/inclusion probability) so they describe Earth, not the candidates.
        bridge_views: dict[str, list[FeatureDef]] = {}
        for f in bridges:
            bridge_views.setdefault(f.view, []).append(f)
        pop_cfg = fcfg.get('bridge_population', {'mode': 'all_enriched'})
        weights = _background_weights(conn, pop_cfg) if pop_cfg.get('mode') == 'background_weighted' else {}
        bridge_fit: dict[str, dict] = {}
        for view_id, fdefs in bridge_views.items():
            cols = sorted({_ident(f.column('Earth')) for f in fdefs} | {_ident(f.status_columns['Earth']) for f in fdefs})
            any_measured = ' OR '.join(f"{_ident(f.status_columns['Earth'])} = 'measured'" for f in fdefs)
            data = _fetch(conn, f"""
                SELECT region_id, {', '.join(cols)} FROM features_unified WHERE {where_sql} AND ({any_measured})
                ORDER BY region_id""")
            idx, info = bridge_rows(np.asarray(data['region_id'], dtype=object), weights, pop_cfg,
                                    int(fcfg['bridge_sample_size']), seed)
            bridge_fit[view_id] = info
            log(f"Vista puente {view_id}: {info['mode']} ({info['n_measured']} medidas, "
                f"{info['n_background']} de la muestra de fondo)")
            for f in fdefs:
                values[f.id] = _masked_values(data, f.column('Earth'), f.status_columns['Earth'])[idx]

    model = build_model(spec, values, seed=seed, log=log)
    for view_id, info in bridge_fit.items():
        if view_id in model['views']:
            model['views'][view_id]['fit_population'] = info
    model['fit_pool'] = {'windows': int(pool_n), 'sample_size': int(sample_size),
                         'holdout_basins': [b['id'] for b in fcfg['holdout_basins']],
                         'store_root': _display_path(store_root)}
    return model


def _background_weights(conn, pop_cfg: dict) -> dict[str, float]:
    reasons = ', '.join(f"'{r}'" for r in pop_cfg.get('selection_reasons', ['background', 'background_cluster']))
    try:
        rows = conn.execute(f'SELECT region_id, max(inclusion_probability) FROM enrichment_selection_latest '
                            f'WHERE selection_reason IN ({reasons}) AND inclusion_probability > 0 '
                            'GROUP BY region_id').fetchall()
    except duckdb.Error:
        return {}
    return {r[0]: float(r[1]) for r in rows}


def bridge_rows(region_ids: np.ndarray, weights: dict[str, float], pop_cfg: dict, sample_size: int,
                seed: int) -> tuple[np.ndarray, dict]:
    """Row indices used to fit a bridge view and a description of that population.

    With enough measured background windows, they are resampled with probability proportional to
    1/inclusion probability (Horvitz-Thompson weights); otherwise every measured row is used (up to
    `sample_size`) and the population is flagged as biased.
    """
    rng = np.random.default_rng(seed)
    n = len(region_ids)
    bg = np.array([i for i, r in enumerate(region_ids) if r in weights], dtype=int)
    info = {'n_measured': int(n), 'n_background': int(bg.size)}
    if pop_cfg.get('mode') == 'background_weighted' and bg.size >= int(pop_cfg.get('min_background_rows', 100)):
        w = np.array([1.0 / weights[region_ids[i]] for i in bg])
        size = int(min(sample_size, max(20 * bg.size, 1000)))
        idx = rng.choice(bg, size=size, replace=True, p=w / w.sum())
        return idx, info | {'mode': 'background_weighted', 'resampled_rows': size}
    idx = np.arange(n) if n <= sample_size else np.sort(rng.choice(n, size=sample_size, replace=False))
    mode = 'all_enriched' if pop_cfg.get('mode') != 'background_weighted' else 'biased_enriched_only'
    return idx, info | {'mode': mode, 'resampled_rows': int(idx.size)}


def build_model(spec: dict, values: dict[str, np.ndarray], *, seed: int,
                log: Callable[[str], None] = lambda _m: None) -> dict:
    """Fit transforms, view covariances and GMM from per-feature Earth samples.

    `values[feature_id]` holds Earth values (NaN where unmeasured). Rows are aligned
    within a view's sample (direct features share one sample; each bridge view has its own).
    """
    fcfg = spec['fit']
    features = parse_features(spec)
    min_rows = fcfg['min_fit_rows']
    feat_models: dict[str, dict] = {}
    for fid, fdef in features.items():
        v = values.get(fid)
        n = int(np.isfinite(v).sum()) if v is not None else 0
        if n < min_rows:
            feat_models[fid] = {'view': fdef.view, 'fitted': False, 'n_fit': n,
                                'reason': 'no_earth_measurements' if n == 0 else 'insufficient_earth_measurements'}
            continue
        qn = QuantileNormal.fit(v, fcfg['n_quantiles'])
        if not np.nanstd(qn.normal(v)) > 1e-6:  # a constant feature carries no metric (singular covariance)
            feat_models[fid] = {'view': fdef.view, 'fitted': False, 'n_fit': n, 'reason': 'constant_on_earth'}
            continue
        feat_models[fid] = {'view': fdef.view, 'fitted': True, 'n_fit': qn.n_fit, 'transform': qn}

    views: dict[str, dict] = {}
    for view_id, vspec in spec['views'].items():
        if vspec['kind'] != 'metric':
            continue
        fids = [f.id for f in features.values() if f.view == view_id and feat_models[f.id]['fitted']]
        if not fids:
            views[view_id] = {'kind': 'metric', 'fitted': False, 'features': [], 'reason': 'no_fitted_features'}
            log(f'Vista {view_id}: sin datos terrestres para ajustar')
            continue
        z = np.column_stack([feat_models[f]['transform'].normal(values[f]) for f in fids])
        complete = np.isfinite(z).all(axis=1)
        if complete.sum() >= min_rows:
            cov, estimator = robust_covariance(z[complete], fcfg['covariance'], seed)
        else:
            cov, estimator = np.eye(len(fids)), 'identity_insufficient_overlap'
        corr = cov / np.sqrt(np.outer(np.diag(cov), np.diag(cov)))
        eig = np.sort(np.linalg.eigvalsh(corr))[::-1]
        views[view_id] = {
            'kind': 'metric', 'fitted': True, 'features': fids, 'covariance': cov,
            'covariance_estimator': estimator, 'n_complete': int(complete.sum()),
            'min_features': min(vspec.get('min_features', 1), len(fids)),
            'effective_dof': float(eig.sum() ** 2 / (eig ** 2).sum()),
            'correlation': corr,
        }
        log(f'Vista {view_id}: {len(fids)} features, {int(complete.sum())} filas completas, '
            f'{estimator}, grados de libertad efectivos {views[view_id]["effective_dof"]:.2f}')

    for view_id, vspec in spec['views'].items():
        if vspec['kind'] == 'gmm':
            views[view_id] = fit_gmm(spec, vspec, feat_models, values, seed, log)

    return {
        'format': MODEL_FORMAT,
        'engine_id': spec['engine_id'],
        'spec_hash': spec_hash(spec),
        'fitted_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'seed': seed,
        'features': feat_models,
        'views': views,
    }


def fit_gmm(spec: dict, vspec: dict, feat_models: dict, values: dict, seed: int, log) -> dict:
    gcfg, min_rows = spec['fit']['gmm'], spec['fit']['min_fit_rows']
    fids = [f for f, m in feat_models.items()
            if m['fitted'] and m['view'] in vspec['source_views']]
    if not fids:
        return {'kind': 'gmm', 'fitted': False, 'features': [], 'reason': 'no_fitted_source_features'}
    z = np.column_stack([feat_models[f]['transform'].normal(values[f]) for f in fids])
    # Drop the sparsest feature until enough complete rows remain.
    while fids and np.isfinite(z).all(axis=1).sum() < min_rows:
        worst = int(np.argmin(np.isfinite(z).sum(axis=0)))
        fids.pop(worst)
        z = np.delete(z, worst, axis=1)
    if not fids:
        return {'kind': 'gmm', 'fitted': False, 'features': [], 'reason': 'insufficient_complete_rows'}
    z = z[np.isfinite(z).all(axis=1)]
    rng = np.random.default_rng(seed)
    if z.shape[0] > gcfg['max_rows']:
        z = z[rng.choice(z.shape[0], gcfg['max_rows'], replace=False)]
    best, bics = None, {}
    for k in gcfg['components']:
        if k * (len(fids) + 1) * 10 > z.shape[0]:
            continue
        gm = GaussianMixture(k, covariance_type=gcfg['covariance_type'], n_init=gcfg['n_init'],
                             reg_covar=gcfg['reg_covar'], random_state=seed).fit(z)
        bics[k] = float(gm.bic(z))
        if best is None or bics[k] < bics[best[0]]:
            best = (k, gm)
    if best is None:
        return {'kind': 'gmm', 'fitted': False, 'features': fids, 'reason': 'too_few_rows_for_components'}
    k, gm = best
    log(f'GMM regimen_morfologico: {k} familias sobre {fids} (BIC {bics})')
    return {'kind': 'gmm', 'fitted': True, 'features': fids, 'n_components': k, 'bic': bics,
            'weights': gm.weights_, 'means': gm.means_, 'covariances': gm.covariances_,
            'n_fit': int(z.shape[0])}


def save_model(model: dict, path: Path) -> tuple[Path, Path]:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    staged = path.with_suffix('.joblib.tmp')
    joblib.dump(model, staged)
    staged.replace(path)
    report = path.with_suffix('.json')
    report.write_text(json.dumps(model_report(model), indent=2, ensure_ascii=False), encoding='utf-8')
    return path, report


def load_model(path: Path) -> dict:
    model = joblib.load(Path(path))
    if model.get('format') != MODEL_FORMAT:
        raise ValueError(f'Formato de modelo no soportado: {model.get("format")}')
    return model


def model_report(model: dict) -> dict:
    """JSON-safe summary of a fitted model (no quantile arrays)."""
    feats = {f: {k: v for k, v in m.items() if k != 'transform'} for f, m in model['features'].items()}
    views = {}
    for vid, v in model['views'].items():
        r = {k: v[k] for k in ('kind', 'fitted', 'features', 'reason', 'covariance_estimator', 'n_complete',
                                'effective_dof', 'n_components', 'bic', 'n_fit') if k in v}
        if 'correlation' in v:
            r['correlation'] = np.round(v['correlation'], 4).tolist()
        if 'weights' in v:
            r['component_weights'] = np.round(v['weights'], 4).tolist()
        views[vid] = r
    return {k: model[k] for k in ('format', 'engine_id', 'spec_hash', 'fitted_at', 'seed') if k in model} | {
        'fit_pool': model.get('fit_pool'), 'features': feats, 'views': views}


# ---------------------------------------------------------------------------
# Distances
# ---------------------------------------------------------------------------
def _group_patterns(avail: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Unique availability patterns (rows of a boolean matrix) and the pattern index of each row.

    Equivalent to `np.unique(avail, axis=0, return_inverse=True)` but sorts one integer key per row
    instead of whole rows, which is several times faster on millions of candidates.
    """
    n, k = avail.shape
    if n == 0 or k > 62:
        patterns, inverse = np.unique(avail, axis=0, return_inverse=True)
        return patterns, inverse.reshape(-1)
    keys = avail.astype(np.int64) @ (np.int64(1) << np.arange(k, dtype=np.int64))
    uniq, inverse = np.unique(keys, return_inverse=True)
    patterns = ((uniq[:, None] >> np.arange(k, dtype=np.int64)[None, :]) & 1).astype(bool)
    return patterns, inverse.reshape(-1)


def mahalanobis_view(zc: np.ndarray, zref: np.ndarray, cov: np.ndarray, min_features: int
                     ) -> tuple[np.ndarray, np.ndarray]:
    """Per-candidate chi-square-calibrated distance in [0, 1] and number of features used.

    Each missingness pattern uses the marginal covariance of the features both sides have.
    """
    n, k = zc.shape
    delta = zc - zref[None, :]
    avail = np.isfinite(delta)
    dist = np.full(n, np.nan)
    used = avail.sum(axis=1)
    if n == 0:
        return dist, used
    patterns, inverse = _group_patterns(avail)
    for pi, pattern in enumerate(patterns):
        kk = int(pattern.sum())
        if kk < max(1, min_features):
            continue
        rows = inverse == pi
        sub = delta[np.ix_(rows, pattern)]
        inv = np.linalg.pinv(cov[np.ix_(pattern, pattern)])
        m2 = np.einsum('ij,jk,ik->i', sub, inv, sub)
        dist[rows] = stats.chi2.cdf(m2, kk)
    return dist, used


def feature_shares(delta: np.ndarray, cov: np.ndarray) -> np.ndarray:
    """Exact additive decomposition of the squared Mahalanobis distance by feature."""
    ok = np.isfinite(delta)
    out = np.full(delta.shape, np.nan)
    if not ok.any():
        return out
    d = delta[ok]
    contrib = d * (np.linalg.pinv(cov[np.ix_(ok, ok)]) @ d)
    total = contrib.sum()
    out[ok] = contrib / total if total > 0 else 0.0
    return out


def _gmm_log_resp(z: np.ndarray, gmm: dict, cols: np.ndarray) -> np.ndarray:
    """Log posterior of each component using the marginal mixture on `cols`."""
    lw = np.log(gmm['weights'])
    out = np.empty((z.shape[0], len(lw)))
    for c in range(len(lw)):
        mu = gmm['means'][c][cols]
        cov = gmm['covariances'][c][np.ix_(cols, cols)]
        out[:, c] = lw[c] + stats.multivariate_normal(mu, cov, allow_singular=True).logpdf(z)
    out -= out.max(axis=1, keepdims=True)
    out -= np.log(np.exp(out).sum(axis=1, keepdims=True))
    return out


def gmm_view(zc: np.ndarray, zref: np.ndarray, gmm: dict) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Regime distance (1 - Bhattacharyya coefficient), candidate component, its posterior, ref posterior."""
    n = zc.shape[0]
    dist, comp, pmax = np.full(n, np.nan), np.full(n, -1), np.full(n, np.nan)
    ref_post = np.full(len(gmm['weights']), np.nan)
    avail = np.isfinite(zc) & np.isfinite(zref)[None, :]
    # The reference posterior does not depend on the candidates: an empty pool (a profile with no
    # eligible windows) must still report it, never NaN (which is not valid JSON).
    full = np.isfinite(zref)
    if full.any():
        ref_post = np.exp(_gmm_log_resp(zref[full][None, :], gmm, np.flatnonzero(full)))[0]
    if n == 0:
        return dist, comp, pmax, ref_post
    patterns, inverse = _group_patterns(avail)
    for pi, pattern in enumerate(patterns):
        if not pattern.any():
            continue
        cols = np.flatnonzero(pattern)
        rows = inverse == pi
        post = np.exp(_gmm_log_resp(zc[np.ix_(rows, pattern)], gmm, cols))
        rpost = np.exp(_gmm_log_resp(zref[pattern][None, :], gmm, cols))[0]
        dist[rows] = np.clip(1.0 - np.sqrt(post * rpost[None, :]).sum(axis=1), 0.0, 1.0)
        comp[rows] = post.argmax(axis=1)
        pmax[rows] = post.max(axis=1)
    return dist, comp, pmax, ref_post


# ---------------------------------------------------------------------------
# References
# ---------------------------------------------------------------------------
@dataclass
class Reference:
    id: str
    name: str
    body: str
    values: dict[str, float]          # feature_id -> raw value in its body's units
    percentiles: dict[str, float]     # feature_id -> within-body percentile (bridges)
    region_id: str | None = None
    notes: list[str] = field(default_factory=list)


def reference_from_dict(data: dict, spec: dict) -> Reference:
    """Reference from a JSON-like dict: {id, name, body, features: {id|column: value}, percentiles}."""
    body = data.get('body')
    if body not in ('Mars', 'Moon', 'Earth'):
        raise ValueError('La referencia necesita body Mars, Moon o Earth')
    features = parse_features(spec)
    by_column = {f.column(body): fid for fid, f in features.items() if f.column(body)}
    values = {}
    for key, val in (data.get('features') or {}).items():
        fid = key if key in features else by_column.get(key)
        if fid is None:
            raise ValueError(f'Feature de referencia desconocida: {key}')
        if val is not None and math.isfinite(float(val)):
            values[fid] = float(val)
    percentiles = {}
    for key, p in (data.get('percentiles') or {}).items():
        if key not in features or features[key].comparability != BRIDGE:
            raise ValueError(f'Solo las features puente admiten percentil explícito: {key}')
        if not 0.0 <= float(p) <= 1.0:
            raise ValueError(f'Percentil fuera de [0, 1] para {key}')
        percentiles[key] = float(p)
    return Reference(data.get('id', 'custom'), data.get('name', data.get('id', 'custom')), body,
                     values, percentiles, data.get('region_id'))


def reference_from_store(store_root: Path, region_id: str, spec: dict, conn=None, **conn_kw) -> Reference:
    features = parse_features(spec)
    with contextlib.nullcontext(conn) if conn is not None else connect(store_root, **conn_kw) as conn:
        present = unified_columns(conn)
        head = conn.execute('SELECT body FROM features_unified WHERE region_id = ?', [region_id]).fetchone()
        if head is None:
            raise ValueError(f'Ventana de referencia no encontrada en el almacén: {region_id}')
        body = head[0]
        pairs = [(fid, f.column(body), f.status_columns.get(body)) for fid, f in features.items()
                 if f.column(body) in present]
        cols = sorted({_ident(c) for _, c, _ in pairs} | {_ident(s) for _, _, s in pairs if s and s in present})
        data = _fetch(conn, f"SELECT {', '.join(cols)} FROM features_unified WHERE region_id = ?", [region_id])
    values = {}
    for fid, col, st in pairs:
        v = _masked_values(data, col, st if st in data else None)[0]
        if np.isfinite(v):
            values[fid] = float(v)
    return Reference(region_id, region_id, body, values, {}, region_id)


def resolve_reference(ref, store_root: Path, spec: dict, conn=None, **conn_kw) -> Reference:
    """Named reference from the spec, store region_id, dict, or Reference."""
    if isinstance(ref, Reference):
        return ref
    if isinstance(ref, dict):
        return reference_from_dict(ref, spec)
    named = spec['references'].get(ref)
    if named is None:
        return reference_from_store(store_root, ref, spec, conn=conn, **conn_kw)
    if 'region_id' in named:
        r = reference_from_store(store_root, named['region_id'], spec, conn=conn, **conn_kw)
        r.id, r.name = ref, named['name']
        return r
    return reference_from_dict({'id': ref, **named}, spec)


def body_percentile(conn, fdef: FeatureDef, body: str, value: float, min_population: int,
                    present: set[str] | None = None) -> tuple[float | None, int]:
    col, st = fdef.column(body), fdef.status_columns.get(body)
    present = unified_columns(conn) if present is None else present
    if col not in present:
        return None, 0
    cond = f"body = ? AND {_ident(col)} IS NOT NULL"
    if st and st in present:
        cond += f" AND {_ident(st)} = 'measured'"
    n, below, equal = conn.execute(
        f'SELECT count(*), count(*) FILTER (WHERE {col} < ?), count(*) FILTER (WHERE {col} = ?) '
        f'FROM features_unified WHERE {cond}', [value, value, body]).fetchone()
    if n < min_population:
        return None, int(n)
    return (below + 0.5 * equal) / n, int(n)


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------
def normalize_weights(weights: dict | None, spec: dict, body: str) -> dict[str, float]:
    views = view_ids(spec)
    base = dict(spec['default_weights'].get(body) or {v: 1.0 for v in views})
    if weights:
        unknown = set(weights) - set(views)
        if unknown:
            raise ValueError(f'Vistas desconocidas en los pesos: {sorted(unknown)}; válidas: {list(views)}')
        base.update(weights)
    out = {v: float(base.get(v, 0.0)) for v in views}
    if any(w < 0 or not math.isfinite(w) for w in out.values()):
        raise ValueError('Los pesos deben ser finitos y no negativos')
    if sum(out.values()) <= 0:
        raise ValueError('Al menos una vista necesita peso positivo')
    return out


def coverage_warnings(view_report: dict, eff_w: dict[str, float], cfg: dict) -> list[str]:
    """Warn when a heavily weighted view covers few candidates or was fitted on a biased population."""
    out = []
    min_cov, min_w = float(cfg.get('min_view_coverage', 0.01)), float(cfg.get('min_effective_weight', 0.2))
    for v, wv in eff_w.items():
        rep = view_report.get(v, {})
        cov = rep.get('coverage_fraction')
        if wv >= min_w and cov is not None and cov < min_cov:
            out.append(f'Vista {v} con peso efectivo {wv:.2f} solo está medida en el {100 * cov:.2f} % de las '
                       f'candidatas ({rep.get("candidates_with_view")}): su ranking no es global')
        if rep.get('fit_population', {}).get('mode') == 'biased_enriched_only':
            out.append(f'Vista {v} ajustada sin muestra de fondo suficiente (solo ventanas enriquecidas): '
                       'su percentil terrestre hereda el sesgo de selección')
    return out


POOL_COLUMNS = ('region_id', 'longitude', 'latitude', 'utm_zone_band', 'scenario_eligibility')


def _share_strings(values: np.ndarray) -> np.ndarray:
    """Same strings, but repeated values point to one object instead of one object per row."""
    table: dict = {}
    out = np.empty(len(values), dtype=object)
    for i, v in enumerate(values):
        out[i] = table.setdefault(v, v)
    return out


@dataclass
class CandidatePool:
    """Earth candidates of one eligibility profile, held in memory for repeated queries."""
    profile: str
    conn: duckdb.DuckDBPyConnection
    present: set
    data: dict
    cand_raw: dict
    cand_z: dict
    eligible: np.ndarray

    def __len__(self) -> int:
        return len(self.data['region_id'])

    def select(self, only_eligible: bool, bbox=None, region_ids=None) -> tuple[dict, dict, dict]:
        """Rows that pass the same filters as the SQL path, in the same order."""
        mask = self.eligible.copy() if only_eligible else np.ones(len(self), dtype=bool)
        if bbox:
            w, s, e, n = (float(v) for v in bbox)
            lon, lat = _float(self.data['longitude']), _float(self.data['latitude'])
            mask &= (lon >= w) & (lon <= e) & (lat >= s) & (lat <= n)
        if region_ids:
            mask &= np.isin(np.asarray(self.data['region_id'], dtype=object), list(region_ids))
        if mask.all():
            return self.data, self.cand_raw, self.cand_z
        take = lambda d: {k: v[mask] for k, v in d.items()}  # noqa: E731
        return take(self.data), take(self.cand_raw), take(self.cand_z)

    def close(self) -> None:
        self.conn.close()


class SimilarityEngine:
    """Ranks Earth windows against a Mars/Moon reference with per-query view weights."""

    def __init__(self, model: dict, spec: dict | None = None) -> None:
        self.model = model
        self.spec = spec or load_spec()
        if model['spec_hash'] != spec_hash(self.spec):
            # The views and features must match what was fitted; the weights/policies may change.
            fitted = set(model['features'])
            if fitted != set(parse_features(self.spec)):
                raise ValueError('El modelo se ajustó con otras features; vuelve a ejecutar `fit`')
        self.features = parse_features(self.spec)

    @classmethod
    def load(cls, path: Path, spec: dict | None = None) -> 'SimilarityEngine':
        return cls(load_model(path), spec)

    # -- reference ---------------------------------------------------------
    def reference_scores(self, ref: Reference, conn, present: set[str] | None = None
                         ) -> tuple[dict[str, float], dict[str, dict]]:
        """Normal score of each reference feature plus provenance notes."""
        fcfg = self.spec['fit']
        scores, info = {}, {}
        for fid, fdef in self.features.items():
            fm = self.model['features'][fid]
            if not fm['fitted']:
                continue
            if fdef.comparability == DIRECT:
                if fid in ref.values:
                    qn: QuantileNormal = fm['transform']
                    scores[fid] = float(qn.normal(ref.values[fid])[0])
                    info[fid] = {'value': ref.values[fid], 'earth_percentile': float(qn.percentile(ref.values[fid])[0]),
                                 'outside_earth_range': qn.outside(ref.values[fid])}
                continue
            p, source, n = ref.percentiles.get(fid), 'explicit_percentile', None
            if p is None and fid in ref.values and fdef.column(ref.body):
                if ref.body == 'Earth':
                    p, source = float(fm['transform'].percentile(ref.values[fid])[0]), 'earth_fit'
                else:
                    p, n = body_percentile(conn, fdef, ref.body, ref.values[fid], fcfg['min_body_population'],
                                           present)
                    source = 'body_population'
            if p is not None:
                scores[fid] = float(normal_from_percentile(p))
                info[fid] = {'value': ref.values.get(fid), 'within_body_percentile': p, 'source': source}
            elif fid in ref.values:
                info[fid] = {'value': ref.values[fid], 'within_body_percentile': None,
                             'reason': f'población de {ref.body} insuficiente ({n}) para el rango intra-cuerpo'}
        return scores, info

    # -- candidates --------------------------------------------------------
    def _candidate_sql(self, present: set[str], profile: str, only_eligible: bool, bbox, region_ids) -> tuple[str, list, list]:
        from pipelines.etl_store import eligibility_expression  # local: etl_store pulls heavy deps
        p = eligibility.get_profile(profile)
        elig = eligibility_expression(profile)
        cols = set()
        for fid, fdef in self.features.items():
            if not self.model['features'][fid]['fitted']:
                continue
            c, s = fdef.column('Earth'), fdef.status_columns.get('Earth')
            if c in present:
                cols.add(_ident(c))
            if s and s in present:
                cols.add(_ident(s))
        where = ["body = 'Earth'", "qa_status = 'rankable'"]
        params: list = []
        if only_eligible:
            where.append(f"({elig}) = '{p.eligible_status}'")
        if bbox:
            where.append(_bbox_sql(bbox))
        if region_ids:
            where.append(f"region_id IN ({', '.join('?' for _ in region_ids)})")
            params.extend(region_ids)
        sql = (f"SELECT region_id, longitude, latitude, utm_zone_band, ({elig}) AS scenario_eligibility"
               f"{''.join(', ' + c for c in sorted(cols))} FROM features_unified WHERE {' AND '.join(where)}"
               ' ORDER BY region_id')  # fixed row order: ties in the RRF ranks must not depend on the scan
        return sql, params, sorted(cols)

    def candidate_scores(self, data: dict) -> tuple[dict[str, np.ndarray], dict[str, np.ndarray]]:
        """Raw values and normal scores of every fitted feature for the candidates in `data`."""
        cand_raw, cand_z = {}, {}
        for fid, fdef in self.features.items():
            fm = self.model['features'][fid]
            col = fdef.column('Earth')
            if not fm['fitted'] or col not in data:
                continue
            st = fdef.status_columns.get('Earth')
            raw = _masked_values(data, col, st if st in data else None)
            cand_raw[fid] = raw
            cand_z[fid] = fm['transform'].normal(raw)
        return cand_raw, cand_z

    def build_pool(self, store_root: Path, profile: str = eligibility.DEFAULT_PROFILE,
                   memory_limit: str = '2GB', threads: int = 4, serve_memory_limit: str = '512MB') -> 'CandidatePool':
        """Load every rankable Earth window once and precompute what does not depend on the query.

        The pool keeps only what `search()` reads (the identity columns and the normal scores), shares the
        repeated strings, and lowers the DuckDB memory limit once loaded: the scan needs `memory_limit`, serving
        queries does not.
        """
        conn = connect(store_root, memory_limit, threads)
        present = unified_columns(conn)
        sql, params, _ = self._candidate_sql(present, profile, False, None, None)
        data = _fetch(conn, sql, params)
        cand_raw, cand_z = self.candidate_scores(data)
        eligible_status = eligibility.get_profile(profile).eligible_status
        data = {key: _share_strings(data[key]) if data[key].dtype == object else data[key]
                for key in POOL_COLUMNS}
        eligible = np.asarray(data['scenario_eligibility'], dtype=object) == eligible_status
        conn.execute(f"SET memory_limit = '{serve_memory_limit}'")
        return CandidatePool(profile=profile, conn=conn, present=present, data=data, cand_raw=cand_raw,
                             cand_z=cand_z, eligible=eligible)

    def search(self, store_root: Path, reference, *, weights: dict | None = None,
               profile: str = eligibility.DEFAULT_PROFILE, only_eligible: bool = True, limit: int = 25,
               missing_policy: str | None = None, fusion: str | None = None, bbox=None,
               region_ids: list[str] | None = None, memory_limit: str = '2GB', threads: int = 4,
               pool: 'CandidatePool | None' = None) -> dict:
        """Rank Earth windows against `reference`.

        With a `CandidatePool` (see `build_pool`) the Earth candidates and their normal scores are
        already in memory, so a query only pays for the distances and the fusion.
        """
        scfg = self.spec['search']
        missing_policy = missing_policy or scfg['default_missing_policy']
        fusion = fusion or scfg['default_fusion']
        if missing_policy not in MISSING_POLICIES:
            raise ValueError(f'Política de ausencia inválida: {missing_policy}')
        if fusion not in FUSIONS:
            raise ValueError(f'Fusión inválida: {fusion}')
        if pool is not None:
            if pool.profile != profile:
                raise ValueError(f'El pool se construyó con el perfil {pool.profile}, no con {profile}')
            cursor = pool.conn.cursor()
            try:
                ref = resolve_reference(reference, store_root, self.spec, conn=cursor)
                w = normalize_weights(weights, self.spec, ref.body)
                zref_map, ref_info = self.reference_scores(ref, cursor, pool.present)
            finally:
                cursor.close()
            data, cand_raw, cand_z = pool.select(only_eligible, bbox, region_ids)
        else:
            ref = resolve_reference(reference, store_root, self.spec, memory_limit=memory_limit, threads=threads)
            w = normalize_weights(weights, self.spec, ref.body)
            with connect(store_root, memory_limit, threads) as conn:
                zref_map, ref_info = self.reference_scores(ref, conn)
                present = unified_columns(conn)
                sql, params, _ = self._candidate_sql(present, profile, only_eligible, bbox, region_ids)
                data = _fetch(conn, sql, params)
            cand_raw, cand_z = self.candidate_scores(data)
        n = len(data['region_id'])

        view_dist: dict[str, np.ndarray] = {}
        view_report: dict[str, dict] = {}
        extra: dict[str, np.ndarray] = {}
        for vid, vm in self.model['views'].items():
            rep = {'weight': w.get(vid, 0.0), 'kind': vm['kind']}
            view_report[vid] = rep
            if not vm['fitted']:
                rep.update(status='not_fitted', reason=vm.get('reason'))
                continue
            fids = vm['features']
            zref = np.array([zref_map.get(f, np.nan) for f in fids])
            if not np.isfinite(zref).any():
                rep.update(status='reference_missing', reason='la referencia no tiene ninguna feature de esta vista')
                continue
            zc = np.column_stack([cand_z.get(f, np.full(n, np.nan)) for f in fids]) if n else np.empty((0, len(fids)))
            if vm['kind'] == 'metric':
                d, used = mahalanobis_view(zc, zref, vm['covariance'], vm['min_features'])
            else:
                d, comp, pmax, ref_post = gmm_view(zc, zref, vm)
                extra.update(regime_component=comp, regime_posterior=pmax)
                rep['reference_posterior'] = np.round(ref_post, 4).tolist()
                rep['reference_component'] = int(np.nanargmax(ref_post)) if np.isfinite(ref_post).any() else None
            avail = np.isfinite(d)
            rep.update(status='used' if avail.any() else 'no_candidate_coverage',
                       features=fids, reference_features=[f for f, z in zip(fids, zref) if np.isfinite(z)],
                       candidates_with_view=int(avail.sum()),
                       coverage_fraction=round(float(avail.sum()) / n, 6) if n else 0.0)
            if vm.get('fit_population'):
                rep['fit_population'] = vm['fit_population']
            if avail.any():
                view_dist[vid] = d

        active = [v for v in view_dist if w.get(v, 0) > 0]
        dropped = [v for v, wt in w.items() if wt > 0 and v not in view_dist]
        warnings = [f'Vista {v} con peso {w[v]:.3g} excluida: {view_report[v].get("status")}' for v in dropped]
        if not active:
            return self._envelope(ref, ref_info, w, {}, view_report, missing_policy, fusion, profile,
                                  only_eligible, n, 0, [], warnings + ['Ninguna vista con peso positivo es utilizable'])
        wsum = sum(w[v] for v in active)
        eff_w = {v: w[v] / wsum for v in active}
        warnings += coverage_warnings(view_report, eff_w, scfg.get('coverage_warning', {}))
        D = np.column_stack([view_dist[v] for v in active])
        W = np.array([eff_w[v] for v in active])
        avail = np.isfinite(D)
        coverage = (avail * W).sum(axis=1)
        neutral = np.array([float(np.nanmedian(view_dist[v])) if np.isfinite(view_dist[v]).sum() >= 30 else 0.5
                            for v in active])
        low = (np.where(avail, D, 0.0) * W).sum(axis=1)
        high = (np.where(avail, D, 1.0) * W).sum(axis=1)
        keep = avail.any(axis=1)
        if missing_policy == 'require':
            keep &= avail.all(axis=1)
            score = low
        elif missing_policy == 'renormalize':
            score = np.where(coverage > 0, low / np.maximum(coverage, 1e-12), np.nan)
        else:
            score = (np.where(avail, D, neutral[None, :]) * W).sum(axis=1)
        rrf = np.zeros(len(score))
        k_rrf = scfg['rrf_k']
        for j in range(len(active)):
            col = D[:, j]
            order = np.argsort(np.where(np.isfinite(col), col, np.inf), kind='stable')
            ranks = np.empty(len(col))
            ranks[order] = np.arange(1, len(col) + 1)
            rrf += np.where(np.isfinite(col), W[j] / (k_rrf + ranks), 0.0)

        idx = np.flatnonzero(keep)
        rid = np.asarray(data['region_id'], dtype=object)
        if fusion == 'rrf':
            order = idx[np.lexsort((rid[idx], -coverage[idx], -rrf[idx]))]
        else:
            order = idx[np.lexsort((rid[idx], -coverage[idx], score[idx]))]
        top = order[:limit]

        min_pool = scfg['min_pool_for_percentile']
        pct = {}
        for v in view_dist:
            col = view_dist[v]
            ok = np.isfinite(col)
            if ok.sum() >= min_pool:
                sorted_vals = np.sort(col[ok])
                pct[v] = sorted_vals
        results = []
        for rank, i in enumerate(top, 1):
            views_out = {}
            for v, col in view_dist.items():
                dv = col[i]
                entry = {'distance': None if not np.isfinite(dv) else round(float(dv), 6),
                         'weight': round(eff_w.get(v, 0.0), 6), 'available': bool(np.isfinite(dv))}
                if np.isfinite(dv) and v in pct:
                    entry['pool_percentile'] = round(float(np.searchsorted(pct[v], dv, side='right') / len(pct[v])), 6)
                vm = self.model['views'][v]
                if vm['kind'] == 'metric' and np.isfinite(dv):
                    entry['features'] = self._explain(i, vm, zref_map, cand_z, cand_raw, ref)
                if vm['kind'] == 'gmm' and 'regime_component' in extra:
                    entry['component'] = int(extra['regime_component'][i])
                    entry['posterior'] = round(float(extra['regime_posterior'][i]), 4)
                views_out[v] = entry
            results.append({
                'rank': rank,
                'region_id': rid[i],
                'longitude': float(data['longitude'][i]),
                'latitude': float(data['latitude'][i]),
                'utm_zone_band': str(data['utm_zone_band'][i]),
                'scenario_eligibility': str(data['scenario_eligibility'][i]),
                'score': round(float(score[i]), 6),
                'score_low': round(float(low[i]), 6),
                'score_high': round(float(high[i]), 6),
                'rrf_score': round(float(rrf[i]), 8),
                'coverage': round(float(coverage[i]), 6),
                'missing_views': [v for j, v in enumerate(active) if not avail[i, j]],
                'views': views_out,
            })
        return self._envelope(ref, ref_info, w, eff_w, view_report, missing_policy, fusion, profile,
                              only_eligible, n, int(keep.sum()), results, warnings)

    def _explain(self, i: int, vm: dict, zref_map: dict, cand_z: dict, cand_raw: dict, ref: Reference) -> dict:
        fids = vm['features']
        zr = np.array([zref_map.get(f, np.nan) for f in fids])
        zc = np.array([cand_z[f][i] if f in cand_z else np.nan for f in fids])
        delta = zc - zr
        shares = feature_shares(delta, vm['covariance'])
        out = {}
        for j, f in enumerate(fids):
            if not np.isfinite(delta[j]):
                continue
            out[f] = {'candidate': round(float(cand_raw[f][i]), 6), 'reference': ref.values.get(f),
                      'z_delta': round(float(delta[j]), 4), 'share': round(float(shares[j]), 4)}
        return out

    def _envelope(self, ref, ref_info, weights, eff_w, view_report, missing_policy, fusion, profile,
                  only_eligible, pool, ranked, results, warnings) -> dict:
        return {
            'engine_id': self.model['engine_id'],
            'model_fitted_at': self.model['fitted_at'],
            'status': self.spec['status'],
            'reference': {'id': ref.id, 'name': ref.name, 'body': ref.body, 'region_id': ref.region_id,
                          'features': ref_info},
            'weights_requested': weights,
            'weights_effective': {k: round(v, 6) for k, v in eff_w.items()},
            'missing_policy': missing_policy,
            'fusion': fusion,
            'profile': profile,
            'only_eligible': only_eligible,
            'candidates_in_pool': pool,
            'candidates_ranked': ranked,
            'views': view_report,
            'warnings': warnings,
            'results': results,
        }

    def pair_view_distances(self, store_root: Path, reference, region_ids: list[str], **kw) -> dict[str, dict]:
        """View distances of specific windows (for pairwise calibration)."""
        res = self.search(store_root, reference, region_ids=region_ids, only_eligible=False,
                          limit=len(region_ids), missing_policy='renormalize',
                          weights={v: 1.0 for v in view_ids(self.spec)}, **kw)
        return {r['region_id']: {v: e['distance'] for v, e in r['views'].items()} for r in res['results']}


# ---------------------------------------------------------------------------
# Pairwise calibration (Learning-to-Rank, Bradley-Terry with non-negative weights)
# ---------------------------------------------------------------------------
def calibrate_weights(diffs: np.ndarray, views: list[str], l2: float = 0.01, min_pairs: int = 50) -> dict:
    """Fit non-negative view weights from blind pairwise preferences.

    `diffs[p, v] = d_v(other) - d_v(preferred)`; NaN (view missing on either side) adds
    no evidence. Maximises sum log sigmoid(w . x) - l2 ||w||^2 subject to w >= 0.
    """
    x = np.nan_to_num(np.asarray(diffs, dtype='float64'), nan=0.0)
    if x.ndim != 2 or x.shape[1] != len(views):
        raise ValueError('diffs debe ser una matriz (pares x vistas)')
    if x.shape[0] == 0:
        raise ValueError('Se necesita al menos un par etiquetado')

    def objective(w):
        m = x @ w
        loss = np.logaddexp(0.0, -m).mean() + l2 * (w @ w)
        grad = -(x * stats.logistic.cdf(-m)[:, None]).mean(axis=0) + 2 * l2 * w
        return loss, grad

    w0 = np.full(len(views), 1.0)
    res = optimize.minimize(objective, w0, jac=True, method='L-BFGS-B', bounds=[(0, None)] * len(views))
    w = res.x
    total = w.sum()
    acc = float(((x @ w) > 0).mean()) if total > 0 else 0.0
    return {
        'method': 'bradley_terry_nonnegative',
        'n_pairs': int(x.shape[0]),
        'status': 'calibrated' if x.shape[0] >= min_pairs else 'insufficient_pairs',
        'raw_coefficients': {v: round(float(c), 6) for v, c in zip(views, w)},
        'weights': {v: round(float(c / total), 6) if total > 0 else 0.0 for v, c in zip(views, w)},
        'train_pairwise_accuracy': round(acc, 4),
        'converged': bool(res.success),
    }
