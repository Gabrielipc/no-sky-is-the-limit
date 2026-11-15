"""CLI of the unsupervised ML similarity engine (specs/analysis/motor-similitud-ml-v1.json).

    python scripts/motor_similitud.py fit
    python scripts/motor_similitud.py search --reference jezero --weight forma_hipsometrica=0.5
    python scripts/motor_similitud.py search --reference haworth-fondo --include-ineligible --limit 10
    python scripts/motor_similitud.py search --ref-json mi_referencia.json --fusion rrf
    python scripts/motor_similitud.py calibrate --pairs pares_ciegos.json
    python scripts/motor_similitud.py views
    python scripts/motor_similitud.py recall --reference jezero --retriever topografica=20 --retriever entorno=20
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

from pipelines import etl_eligibility as eligibility  # noqa: E402
from pipelines import similarity_ml as sim  # noqa: E402

DEFAULT_STORE = Path(__import__('os').environ.get('ANALOGOS_FEATURE_STORE_DIR') or (ROOT / 'data/feature_store_v1'))
DEFAULT_MODEL = sim.DEFAULT_MODEL_DIR / 'motor-similitud-ml-v1.joblib'


def parse_weights(items: list[str] | None) -> dict[str, float] | None:
    if not items:
        return None
    out = {}
    for item in items:
        key, sep, val = item.partition('=')
        if not sep:
            raise SystemExit(f'Peso inválido {item!r}: usa vista=valor')
        out[key.strip()] = float(val)
    return out


def run_fit(args: argparse.Namespace) -> None:
    t0 = time.perf_counter()
    model = sim.fit_model(Path(args.store_dir), sample_size=args.sample_size, seed=args.seed,
                          memory_limit=args.memory_limit, threads=args.threads,
                          log=lambda m: print(m, file=sys.stderr, flush=True))
    path, report = sim.save_model(model, Path(args.model))
    print(json.dumps({'model': str(path), 'report': str(report),
                      'elapsed_s': round(time.perf_counter() - t0, 1),
                      **sim.model_report(model)}, indent=2, ensure_ascii=False))


def _reference(args: argparse.Namespace):
    if args.ref_json:
        return json.loads(Path(args.ref_json).read_text(encoding='utf-8'))
    return args.ref_region_id or args.reference


def run_search(args: argparse.Namespace) -> None:
    engine = sim.SimilarityEngine.load(Path(args.model))
    result = engine.search(
        Path(args.store_dir), _reference(args), weights=parse_weights(args.weight), profile=args.profile,
        only_eligible=not args.include_ineligible, limit=args.limit, missing_policy=args.missing_policy,
        fusion=args.fusion, bbox=tuple(args.bbox) if args.bbox else None,
        memory_limit=args.memory_limit, threads=args.threads,
    )
    text = json.dumps(result, indent=2, ensure_ascii=False, default=float)
    if args.output:
        Path(args.output).write_text(text, encoding='utf-8')
        print(f"{len(result['results'])} resultados escritos en {args.output}", file=sys.stderr)
    else:
        print(text)


def run_calibrate(args: argparse.Namespace) -> None:
    """Pairs file: [{"reference": "jezero", "preferred": "<region_id>", "other": "<region_id>"}, ...]."""
    engine = sim.SimilarityEngine.load(Path(args.model))
    pairs = json.loads(Path(args.pairs).read_text(encoding='utf-8'))
    views = list(sim.view_ids(engine.spec))
    by_ref: dict = {}
    for p in pairs:
        by_ref.setdefault(json.dumps(p['reference'], sort_keys=True), []).append(p)
    diffs, skipped = [], 0
    for ref_key, items in by_ref.items():
        ids = sorted({p['preferred'] for p in items} | {p['other'] for p in items})
        dist = engine.pair_view_distances(Path(args.store_dir), json.loads(ref_key), ids,
                                          memory_limit=args.memory_limit, threads=args.threads)
        for p in items:
            a, b = dist.get(p['preferred']), dist.get(p['other'])
            if a is None or b is None:
                skipped += 1
                continue
            diffs.append([np.nan if a[v] is None or b[v] is None else b[v] - a[v] for v in views])
    cal = engine.spec['calibration']
    result = sim.calibrate_weights(np.array(diffs).reshape(-1, len(views)), views, l2=cal['l2'],
                                   min_pairs=cal['min_pairs'])
    result['pairs_skipped'] = skipped
    print(json.dumps(result, indent=2, ensure_ascii=False))


def run_recall(args: argparse.Namespace) -> None:
    """Share of the best background windows that some shortlist would have proposed."""
    from pipelines import etl_retrieval as retrieval
    from pipelines import selection_recall as recall
    from pipelines.etl_store import FeatureStore
    engine = sim.SimilarityEngine.load(Path(args.model))
    store = FeatureStore(Path(args.store_dir), memory_limit=args.memory_limit, threads=args.threads)
    weights = parse_weights(args.weight)
    counts = dict(parse_weights(args.retriever) or {})
    counts = {k: int(v) for k, v in counts.items()}
    if args.retrieval_total:
        body = retrieval.load_spec()['profiles'].get(args.retrieval_profile, {}).get('body', 'Mars')
        for view, k in retrieval.allocate_by_weights(
                args.retrieval_total, sim.normalize_weights(weights, engine.spec, body)).items():
            counts.setdefault(view, k)
    ref_json = json.loads(Path(args.ref_json).read_text(encoding='utf-8')) if args.ref_json else None
    result = recall.estimate_recall(engine, store, Path(args.store_dir), _reference(args), counts=counts,
                                    weights=weights, profile=args.retrieval_profile, reference_json=ref_json,
                                    targets=args.target, top_fraction=args.top_fraction,
                                    memory_limit=args.memory_limit, threads=args.threads)
    text = json.dumps(result, indent=2, ensure_ascii=False, default=float)
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(text + '\n', encoding='utf-8')
    print(text)


def run_views(args: argparse.Namespace) -> None:
    spec = sim.load_spec()
    out = {'engine_id': spec['engine_id'], 'views': {v: s['description'] for v, s in spec['views'].items()},
           'default_weights': spec['default_weights'], 'references': list(spec['references'])}
    if Path(args.model).is_file():
        out['model'] = sim.model_report(sim.load_model(Path(args.model)))
    print(json.dumps(out, indent=2, ensure_ascii=False))


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description='Motor de similitud ML no supervisado (análogos terrestres)')
    parser.add_argument('--store-dir', default=str(DEFAULT_STORE))
    parser.add_argument('--model', default=str(DEFAULT_MODEL))
    parser.add_argument('--memory-limit', default='2GB')
    parser.add_argument('--threads', type=int, default=4)
    sub = parser.add_subparsers(dest='command', required=True)

    p_fit = sub.add_parser('fit', help='Ajustar métricas por vista y GMM en ventanas terrestres de desarrollo')
    p_fit.add_argument('--sample-size', type=int, default=None)
    p_fit.add_argument('--seed', type=int, default=None)

    p_search = sub.add_parser('search', help='Buscar análogos terrestres con pesos por vista')
    ref = p_search.add_mutually_exclusive_group()
    ref.add_argument('--reference', default='jezero', help='Referencia nombrada del spec')
    ref.add_argument('--ref-region-id', help='region_id de una ventana del almacén (Marte o Luna)')
    ref.add_argument('--ref-json', help='JSON con {id, name, body, features, percentiles}')
    p_search.add_argument('--weight', action='append', metavar='VISTA=PESO',
                          help='Peso de una vista; repetible. Las vistas no indicadas usan el peso por defecto del cuerpo')
    p_search.add_argument('--profile', choices=tuple(eligibility.PROFILES), default=eligibility.DEFAULT_PROFILE)
    p_search.add_argument('--include-ineligible', action='store_true')
    p_search.add_argument('--limit', type=int, default=15)
    p_search.add_argument('--missing-policy', choices=sim.MISSING_POLICIES, default=None)
    p_search.add_argument('--fusion', choices=sim.FUSIONS, default=None)
    p_search.add_argument('--bbox', type=float, nargs=4, metavar=('W', 'S', 'E', 'N'))
    p_search.add_argument('--output')

    p_cal = sub.add_parser('calibrate', help='Calibrar pesos con pares etiquetados a ciegas (Bradley-Terry)')
    p_cal.add_argument('--pairs', required=True)

    sub.add_parser('views', help='Vistas, pesos por defecto y estado del modelo ajustado')

    p_rec = sub.add_parser('recall', help='Recall de las listas cortas sobre la muestra de fondo')
    rref = p_rec.add_mutually_exclusive_group()
    rref.add_argument('--reference', default='jezero')
    rref.add_argument('--ref-region-id')
    rref.add_argument('--ref-json')
    p_rec.add_argument('--weight', action='append', metavar='VISTA=PESO')
    p_rec.add_argument('--retriever', action='append', metavar='VISTA=K', help='Lista corta de recuperación')
    p_rec.add_argument('--retrieval-total', type=int, default=0)
    p_rec.add_argument('--retrieval-profile', default='arid_mars_surface_v2')
    p_rec.add_argument('--target', action='append', help='vista:columna=percentil')
    p_rec.add_argument('--top-fraction', type=float, default=0.05)
    p_rec.add_argument('--output', default=str(ROOT / 'docs/evidencia-sesgo-seleccion/recall.json'))

    args = parser.parse_args(argv)
    {'fit': run_fit, 'search': run_search, 'calibrate': run_calibrate, 'views': run_views,
     'recall': run_recall}[args.command](args)


if __name__ == '__main__':
    main()
