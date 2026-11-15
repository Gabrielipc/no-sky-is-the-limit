#!/usr/bin/env python3
"""Mirror job for the Moon and Mars rasters behind the reference sites. It runs on a cloud VM or locally.

    python scripts/etl_referencias.py espejo --body Moon [--tier 1] [--workers 8]
    python scripts/etl_referencias.py espejo --body Mars

It downloads the tier-1 products of the body (`specs/sources/espejo-referencias-v1.json`) into the mirror
folder, verifies size and hash, and writes the hashes to `docs/evidencia-espejo/<body>.json`, which the cloud
sync uploads next to the files. Pin them into the manifest afterwards with
`scripts/espejar_referencias.py adopt --evidence docs/evidencia-espejo/<body>.json`.

The two bodies touch different files, so the jobs can run on two clouds at once and be merged in GCS
(`cloud/referencias/README.md`). Measuring the lunar references is not done here: it is the `luna` step of
`scripts/etl_secuencia.py`, which already ran. The DTM measurement of new Mars sites does not exist yet.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipelines import etl_mirror as mirror  # noqa: E402

EVIDENCE_DIR = ROOT / 'docs/evidencia-espejo'


def body_ids(manifest: dict, body: str, tiers: list[int]) -> list[str]:
    return [p['id'] for p in mirror.products(manifest, tiers) if p['body'] == body]


def run_mirror(body: str, tiers: list[int], workers: int, root: Path | None = None,
               evidence_dir: Path | None = None) -> list[dict]:
    manifest = mirror.load_manifest()
    root = root or mirror.mirror_root()
    ids = body_ids(manifest, body, tiers)
    if not ids:
        raise SystemExit(f'No hay productos de {body} en los niveles {tiers}')
    log = lambda m: print(m, file=sys.stderr, flush=True)  # noqa: E731
    before = mirror.plan(manifest, root, ids=ids)
    log(f'Espejo de {body}: faltan {before["remaining_bytes"] / 1e9:.2f} GB de {before["total_bytes"] / 1e9:.2f} GB')
    results = mirror.fetch(manifest, root, ids=ids, workers=workers, log=log)
    for r in results:
        log(f'  {r["status"]:<14}{r["id"]}')
    bad = [r for r in results if r['status'] in ('failed', 'hash_mismatch')]
    if bad:
        raise SystemExit(f'{len(bad)} productos con error: {[r["id"] for r in bad]}')
    checked = mirror.verify(manifest, root, ids=ids, workers=min(workers, 4))
    broken = [r for r in checked if not r['ok']]
    if broken:
        raise SystemExit(f'Verificación fallida: {broken}')
    evidence = (evidence_dir or EVIDENCE_DIR) / f'{body.lower()}.json'
    mirror.write_evidence(evidence, body, checked, manifest)
    log(f'Espejo de {body} verificado ({len(checked)} productos); hashes en {evidence}')
    return checked


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='job', required=True)
    p = sub.add_parser('espejo', help='download and verify the tier-1 products of one body')
    p.add_argument('--body', required=True, choices=['Moon', 'Mars'])
    p.add_argument('--tier', type=int, action='append')
    p.add_argument('--workers', type=int, default=4)
    args = ap.parse_args()
    run_mirror(args.body, args.tier or [1], args.workers)
    return 0


if __name__ == '__main__':
    sys.exit(main())
