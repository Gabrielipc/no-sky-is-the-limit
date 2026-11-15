"""Recall of the enrichment shortlists (phase D of the selection bias mitigation plan).

The background sample is scored with every view; its best windows (top `top_fraction`) are the ones a
perfect search would want enriched. For each of them we ask whether some shortlist would have proposed
it: deterministic retrievers propose their top K; exploration proposes a window with probability
K / |eligible pool|. Windows are weighted by 1 / inclusion probability, so the estimate refers to Earth.
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np

from pipelines import etl_retrieval as retrieval
from pipelines import etl_sampling as sampling


def proposal_probabilities(store, frame: retrieval.ProxyFrame, counts: dict[str, int], *, profile: str,
                           reference: dict | None, targets: list[str] | None, spec: dict | None = None) -> dict:
    """region_id -> probability of being proposed, per retriever."""
    spec = spec or retrieval.load_spec()
    cli_targets = retrieval.parse_targets(targets)
    out: dict[str, dict[str, float]] = {}
    for view, k in counts.items():
        if k <= 0 or view in spec.get('no_retrieval', {}) or view not in spec['views']:
            continue
        method = spec['views'][view]['method']
        if method == 'topographic_rank':
            from scripts.etl_puentes import candidate_sites
            arid, polar = (k, 0) if profile != 'polar_cold_v1' else (0, k)
            out[view] = {r['region_id']: 1.0 for r in candidate_sites(store, arid, polar)}
            continue
        tgt = retrieval.resolve_targets(spec, view, profile, cli_targets, reference)
        if tgt:
            ranks = retrieval.retriever_ranks(frame, view, tgt, spec)
            out[view] = {str(r): 1.0 for r in frame.region_id[ranks <= k]}
        elif method == 'proxy_target_or_exploration':
            filt = spec['views'][view].get('exploration_filter', {})
            mask = frame.eligible.copy()
            if 'bare_or_sparse_fraction_min' in filt:
                mask &= frame.columns['bare_or_sparse_fraction'] >= filt['bare_or_sparse_fraction_min']
            if 'precip_annual_mm_cmg_max' in filt:
                mask &= ~(frame.columns['precip_annual_mm_cmg'] > filt['precip_annual_mm_cmg_max'])
            p = min(1.0, k / max(int(mask.sum()), 1))
            out[view] = {str(r): p for r in frame.region_id[mask]}
    return out


def estimate_recall(engine, store, store_root: Path, reference, *, counts: dict[str, int], weights: dict | None,
                    profile: str, reference_json: dict | None = None, targets: list[str] | None = None,
                    top_fraction: float = 0.05, memory_limit: str = '2GB', threads: int = 4) -> dict:
    bg = sampling.background_weights(store)
    if not bg:
        return {'status': 'no_background_sample', 'note': 'Sin muestra de fondo en enrichment_selection'}
    res = engine.search(store_root, reference, weights=weights, region_ids=sorted(bg), only_eligible=False,
                        limit=len(bg), missing_policy='renormalize', memory_limit=memory_limit, threads=threads)
    ranked = res['results']
    if not ranked:
        return {'status': 'no_scored_background', 'warnings': res['warnings']}
    n_top = max(1, math.ceil(top_fraction * len(ranked)))
    top = ranked[:n_top]
    frame = retrieval.load_proxy_frame(store, profile)
    probs = proposal_probabilities(store, frame, counts, profile=profile, reference=reference_json, targets=targets)
    w = np.array([1.0 / bg[r['region_id']] for r in top])
    proposed_any = []
    by_view = {v: [] for v in probs}
    for r in top:
        miss = 1.0
        for v, pv in probs.items():
            p = pv.get(r['region_id'], 0.0)
            by_view[v].append(p)
            miss *= 1.0 - p
        proposed_any.append(1.0 - miss)
    proposed_any = np.array(proposed_any)
    unproposed = [r for r, p in zip(top, proposed_any) if p == 0.0]
    return {
        'status': 'estimated',
        'background_windows': len(bg),
        'background_scored': len(ranked),
        'top_fraction': top_fraction,
        'top_windows': n_top,
        'retrievers': counts,
        'recall': round(float((w * proposed_any).sum() / w.sum()), 6),
        'recall_by_retriever': {v: round(float((w * np.array(p)).sum() / w.sum()), 6) for v, p in by_view.items()},
        'unproposed_examples': [{'region_id': r['region_id'], 'longitude': r['longitude'], 'latitude': r['latitude'],
                                 'score': r['score'], 'missing_views': r['missing_views']} for r in unproposed[:20]],
        'weights_effective': res['weights_effective'],
        'warnings': res['warnings'],
    }
