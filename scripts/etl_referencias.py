#!/usr/bin/env python3
"""Jobs that prepare the Moon and Mars reference sites. They run on a cloud VM or locally.

    python scripts/etl_referencias.py luna  [--workers 8] [--skip-measure]
    python scripts/etl_referencias.py marte [--workers 8]
    python scripts/etl_referencias.py espejo --body Moon --tier 1

Each job mirrors the tier-1 rasters of its body (`specs/sources/espejo-referencias-v1.json`) and then
measures the sites with them:

  luna   mirror the Moon products, then `scripts/etl_luna.py referencia` (LOLA, PSR, illumination,
         Diviner, Mini-RF) into the Feature Store.
  marte  mirror the Mars products (HiRISE DTM, THEMIS, CRISM). The DTM measurement of new Mars sites
         is not implemented until the sites are chosen; the job says so instead of pretending.

The two jobs touch different bodies and different store partitions, so they can run on two clouds at
the same time and be merged afterwards (`cloud/unir-almacen-azure-gcs.sh`).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipelines import etl_mirror as mirror  # noqa: E402


def body_ids(manifest: dict, body: str, tiers: list[int]) -> list[str]:
    return [p['id'] for p in mirror.products(manifest, tiers) if p['body'] == body]


def run_mirror(body: str, tiers: list[int], workers: int, root: Path | None = None) -> list[dict]:
    manifest = mirror.load_manifest()
    root = root or mirror.mirror_root()
    ids = body_ids(manifest, body, tiers)
    if not ids:
        raise SystemExit(f'No hay productos de {body} en los niveles {tiers}')
    log = lambda m: print(m, file=sys.stderr, flush=True)  # noqa: E731
    before = mirror.plan(manifest, root, ids=ids)
    log(f'Espejo de {body}: faltan {before["remaining_bytes"] / 1e9:.2f} GB de {before["total_bytes"] / 1e9:.2f} GB')
    results = mirror.fetch(manifest, root, ids=ids, workers=workers, log=log)
    bad = [r for r in results if r['status'] in ('failed', 'hash_mismatch')]
    for r in results:
        log(f'  {r["status"]:<14}{r["id"]}')
    if bad:
        raise SystemExit(f'{len(bad)} productos con error: {[r["id"] for r in bad]}')
    checked = mirror.verify(manifest, root, ids=ids, workers=min(workers, 4))
    broken = [r for r in checked if not r['ok']]
    if broken:
        raise SystemExit(f'Verificación fallida: {broken}')
    log(f'Espejo de {body} verificado ({len(checked)} productos)')
    return checked


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='job', required=True)
    for name in ('luna', 'marte'):
        p = sub.add_parser(name)
        p.add_argument('--workers', type=int, default=4)
        p.add_argument('--tier', type=int, action='append')
        p.add_argument('--skip-measure', action='store_true', help='only mirror, do not measure')
    p = sub.add_parser('espejo')
    p.add_argument('--body', required=True, choices=['Moon', 'Mars'])
    p.add_argument('--tier', type=int, action='append')
    p.add_argument('--workers', type=int, default=4)
    args = ap.parse_args()

    tiers = args.tier or [1]
    if args.job == 'espejo':
        run_mirror(args.body, tiers, args.workers)
        return 0
    body = 'Moon' if args.job == 'luna' else 'Mars'
    checked = run_mirror(body, tiers, args.workers)
    print(json.dumps({'job': args.job, 'mirror': {r['id']: r['sha256'] for r in checked}}))
    if args.skip_measure:
        return 0
    if args.job == 'luna':
        return subprocess.run([sys.executable, str(ROOT / 'scripts/etl_luna.py'), 'referencia']).returncode
    print('marte: el espejo está listo; la medición de DTM de sitios nuevos de Marte queda pendiente de elegir '
          'los sitios (docs/01-vigentes/operacion-y-datos/Plan - busqueda de analogos por referencia en tiempo real.md).',
          file=sys.stderr)
    return 0


if __name__ == '__main__':
    sys.exit(main())
