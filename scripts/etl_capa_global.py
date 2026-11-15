#!/usr/bin/env python3
"""Global coarse surface layer (`enrichment_global`, phase A of the selection bias mitigation plan).

  build   Reduce each product once to a global climatological raster in --layers-dir
          (IMERG, MOD10CM, MYD11C3 + MCD43C3, AG1km, SMAP, CCI Permafrost). A built layer
          (with its layer.json) is skipped unless --force. A failing product does not stop the rest.
  sample  Sample every built layer at every Earth window of base_windows and write
          enrichment_global in blocks, plus a summary in docs/evidencia-capa-global/.
  status  List built layers, their granules and output sizes.

Needs EARTHDATA_TOKEN (all but permafrost), h5py (`bash scripts/ejecutar_minerales.sh ...`) and the
libgdal-hdf4 plugin of the Pixi environment (MOD10CM, MYD11C3, MCD43C3).

  bash scripts/ejecutar_minerales.sh scripts/etl_capa_global.py build --layer snow --layer emissivity
  bash scripts/ejecutar_minerales.sh scripts/etl_capa_global.py sample
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipelines import etl_global_layers as gl
from pipelines.etl_global_schema import GLOBAL_LAYERS, GLOBAL_LAYERS_VERSION
from pipelines.etl_store import FeatureStore

DEFAULT_STORE = Path(os.environ.get('ANALOGOS_FEATURE_STORE_DIR') or (ROOT / 'data/feature_store_v1'))
DEFAULT_LAYERS = Path(os.environ.get('ANALOGOS_GLOBAL_LAYERS_DIR') or (ROOT / 'data/global_layers'))
DEFAULT_EVIDENCE = ROOT / 'docs/evidencia-capa-global/resumen.json'


def default_cache() -> Path:
    base = os.environ.get('ATLAS_CACHE_DIR')
    return Path(base) / 'global_layers' if base else Path('/tmp/analogos-global-layers')


def earth_windows(store: FeatureStore) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    with store._connect() as conn:
        rows = conn.execute("SELECT region_id, longitude, latitude FROM base_windows WHERE body = 'Earth' "
                            'ORDER BY region_id').fetchall()
    if not rows:
        return np.array([], dtype=object), np.array([]), np.array([])
    ids, lons, lats = zip(*rows)
    return np.array(ids, dtype=object), np.array(lons, dtype=float), np.array(lats, dtype=float)


def summarize(columns: dict[str, np.ndarray], statuses: dict[str, np.ndarray], n: int) -> dict:
    out = {'windows': n, 'layers': {}}
    for layer, cfg in GLOBAL_LAYERS.items():
        st = statuses[f'{layer}_cmg_status']
        values, counts = np.unique(st.astype(str), return_counts=True)
        entry = {'status': dict(zip(values.tolist(), counts.astype(int).tolist())), 'columns': {}}
        for col in cfg['columns']:
            v = columns[col][np.isfinite(columns[col])]
            entry['columns'][col] = ({'n': int(v.size), 'p05': float(np.percentile(v, 5)),
                                      'p50': float(np.percentile(v, 50)), 'p95': float(np.percentile(v, 95))}
                                     if v.size else {'n': 0})
        out['layers'][layer] = entry
    return out


def run_build(args: argparse.Namespace) -> None:
    layers = args.layer or list(GLOBAL_LAYERS)
    ctx = gl.BuildContext(out_dir=Path(args.layers_dir), cache_dir=Path(args.cache_dir), workers=args.workers,
                          log=lambda m: print(m, flush=True))
    ctx.cache_dir.mkdir(parents=True, exist_ok=True)
    spec = gl.load_spec()
    for layer, key, value in (('imerg', 'period', args.period), ('snow', 'period', args.period),
                              ('soil_moisture', 'period', args.period)):
        if value:
            start, end = value.split('/')
            spec['layers'][layer][key] = {'start': start, 'end': end}
    if args.ati_year:
        spec['layers']['ati']['year'] = args.ati_year
    if args.permafrost_year:
        spec['layers']['permafrost']['year'] = args.permafrost_year
    if args.smap_step_days:
        spec['layers']['soil_moisture']['step_days'] = args.smap_step_days
    if args.albedo_step_days:
        spec['layers']['ati']['albedo_step_days'] = args.albedo_step_days
    report = gl.build_layers(layers, ctx, spec, force=args.force)
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)
    if args.report:
        # Merge with earlier runs so the file shows the latest status of every layer.
        path = Path(args.report)
        merged = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
        stamp = gl.utc_now().isoformat(timespec='seconds')
        merged.update({k: v | {'at': stamp} for k, v in report.items()})
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(merged, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    if any(r['status'] == 'failed' for r in report.values()) and args.strict:
        sys.exit(1)


def run_sample(args: argparse.Namespace) -> None:
    layers_dir = Path(args.layers_dir)
    built = gl.built_layers(layers_dir)
    if not built:
        sys.exit(f'No hay capas construidas en {layers_dir}: ejecuta primero `build`.')
    store = FeatureStore(Path(args.store_dir), memory_limit=args.memory_limit, threads=args.threads)
    ids, lons, lats = earth_windows(store)
    print(f'{len(ids)} ventanas terrestres; capas: {", ".join(built)}', flush=True)
    if not len(ids):
        return
    columns, statuses = gl.sample_columns(lons, lats, layers_dir, built)
    now = gl.utc_now()
    manifest_id, manifests = gl.manifests_for(layers_dir, now)
    for i in range(0, len(ids), args.block_rows):
        rows = gl.rows_from_columns(ids, columns, statuses, manifest_id, now, slice(i, i + args.block_rows))
        store.append_enrichment('global', rows, manifests if i == 0 else None)
        print(f'  {min(i + args.block_rows, len(ids))}/{len(ids)} filas escritas', flush=True)
    store.compact('global')
    summary = summarize(columns, statuses, len(ids)) | {
        'version': GLOBAL_LAYERS_VERSION, 'updated_at': now.isoformat(timespec='seconds'),
        'source_manifest_id': manifest_id,
        'layers_built': {layer: gl.read_layer_meta(layers_dir / layer) for layer in built}}
    for meta in summary['layers_built'].values():
        if meta and 'granules' in meta:
            meta['granules'] = len(meta['granules'])
    if args.evidence:
        path = Path(args.evidence)
        path.parent.mkdir(parents=True, exist_ok=True)
        staged = path.with_suffix('.tmp')
        staged.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        staged.replace(path)
    print(json.dumps({k: v['status'] for k, v in summary['layers'].items()}, ensure_ascii=False, indent=2), flush=True)


def run_status(args: argparse.Namespace) -> None:
    layers_dir = Path(args.layers_dir)
    for layer in GLOBAL_LAYERS:
        meta = gl.read_layer_meta(layers_dir / layer)
        if not meta:
            print(f'{layer}: pendiente')
            continue
        size = sum(o['bytes'] for o in meta['outputs'].values()) / 1024 ** 2
        granules = len(meta.get('granules', [])) or meta.get('granules_count', 0)
        print(f"{layer}: {granules} gránulos, {size:.1f} MB, periodo {meta.get('period')}, {meta.get('built_at')}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--layers-dir', default=str(DEFAULT_LAYERS))
    sub = parser.add_subparsers(dest='cmd', required=True)

    p_build = sub.add_parser('build', help='Construir rásteres globales')
    p_build.add_argument('--layer', action='append', choices=tuple(GLOBAL_LAYERS), help='Repetible; por defecto todas')
    p_build.add_argument('--workers', type=int, default=8)
    p_build.add_argument('--cache-dir', default=str(default_cache()))
    p_build.add_argument('--period', help='AAAA-MM-DD/AAAA-MM-DD para IMERG, MOD10CM y SMAP (por defecto el del spec)')
    p_build.add_argument('--ati-year', type=int)
    p_build.add_argument('--permafrost-year', type=int)
    p_build.add_argument('--smap-step-days', type=int)
    p_build.add_argument('--albedo-step-days', type=int)
    p_build.add_argument('--force', action='store_true', help='Reconstruir capas ya construidas')
    p_build.add_argument('--strict', action='store_true', help='Salir con error si falla alguna capa')
    p_build.add_argument('--report', default=str(ROOT / 'docs/evidencia-capa-global/build.json'),
                         help="Estado por capa ('' para omitir)")

    p_sample = sub.add_parser('sample', help='Muestrear las capas en todas las ventanas terrestres')
    p_sample.add_argument('--store-dir', default=str(DEFAULT_STORE))
    p_sample.add_argument('--memory-limit', default='4GB')
    p_sample.add_argument('--threads', type=int, default=os.cpu_count() or 4)
    p_sample.add_argument('--block-rows', type=int, default=200_000)
    p_sample.add_argument('--evidence', default=str(DEFAULT_EVIDENCE), help="Ruta JSON de resumen ('' para omitir)")

    sub.add_parser('status', help='Capas construidas')
    args = parser.parse_args(argv)
    {'build': run_build, 'sample': run_sample, 'status': run_status}[args.cmd](args)


if __name__ == '__main__':
    main()
