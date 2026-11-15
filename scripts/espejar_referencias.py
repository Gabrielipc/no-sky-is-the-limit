#!/usr/bin/env python3
"""Verified local mirror of the Moon and Mars rasters behind the reference sites.

    python scripts/espejar_referencias.py plan   [--tier 1]
    python scripts/espejar_referencias.py fetch  [--tier 1] [--max-gb 10] [--workers 4] [--record-hashes]
    python scripts/espejar_referencias.py verify [--tier 1]
    python scripts/espejar_referencias.py adopt  --evidence docs/evidencia-espejo/moon.json [...]

The manifest is `specs/sources/espejo-referencias-v1.json`; the files go to `data/raw/espejo/` (or
`--root` / `ANALOGOS_MIRROR_DIR`). `fetch` resumes partial files and checks size and hash. `adopt` pins into
the manifest the hashes that a cloud job recorded in `docs/evidencia-espejo/` (it never overwrites a different one).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipelines import etl_mirror as mirror  # noqa: E402


def gb(n: int) -> str:
    return f'{n / 1e9:.2f} GB'


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('command', choices=['plan', 'fetch', 'verify', 'adopt'])
    ap.add_argument('--manifest', type=Path, default=mirror.MANIFEST_PATH)
    ap.add_argument('--root', type=Path, default=None, help='mirror folder (default: data/raw/espejo)')
    ap.add_argument('--tier', type=int, action='append', help='tier to include (repeatable); default: all')
    ap.add_argument('--id', action='append', help='product id (repeatable)')
    ap.add_argument('--max-gb', type=float, help='byte budget for this fetch')
    ap.add_argument('--workers', type=int, default=4)
    ap.add_argument('--evidence', type=Path, action='append', help='evidence file written by a cloud job (adopt)')
    ap.add_argument('--record-hashes', action='store_true', help='write new sha256 values into the manifest')
    ap.add_argument('--json', action='store_true')
    args = ap.parse_args()

    manifest = mirror.load_manifest(args.manifest)
    if args.command == 'adopt':
        if not args.evidence:
            ap.error('adopt necesita al menos un --evidence')
        result = mirror.adopt_hashes(args.manifest, args.evidence)
        print(f"{len(result['added'])} hashes fijados, {len(result['unchanged'])} ya estaban, {len(result['conflicts'])} conflictos")
        for c in result['conflicts']:
            print(f"  CONFLICTO {c['id']}: {c['reason']}")
        return 1 if result['conflicts'] else 0
    root = args.root or mirror.mirror_root()
    log = lambda m: print(m, file=sys.stderr, flush=True)  # noqa: E731

    if args.command == 'plan':
        report = mirror.plan(manifest, root, args.tier, args.id)
        if args.json:
            print(json.dumps(report, indent=2))
            return 0
        print(f"Espejo en {report['root']}")
        for r in report['products']:
            print(f"  {r['status']:<11}{r['id']:<30}{gb(r['bytes']):>10}  tier {r['tier']} · {r['body']}")
        print(f"Faltan {gb(report['remaining_bytes'])} de {gb(report['total_bytes'])}")
        return 0

    if args.command == 'fetch':
        budget = int(args.max_gb * 1e9) if args.max_gb else None
        results = mirror.fetch(manifest, root, tiers=args.tier, ids=args.id, max_bytes=budget,
                               workers=args.workers, log=log)
        added = mirror.record_hashes(args.manifest, results) if args.record_hashes else 0
        if args.json:
            print(json.dumps(results, indent=2))
        for r in results:
            print(f"  {r['status']:<14}{r['id']}" + (f"  {r.get('error', '')}" if r['status'] != 'fetched' else ''))
        print(f"{sum(r['status'] == 'fetched' for r in results)} descargados, "
              f"{sum(r['status'] in ('failed', 'hash_mismatch') for r in results)} con error"
              + (f", {added} hashes nuevos en el manifiesto" if added else ''))
        return 1 if any(r['status'] in ('failed', 'hash_mismatch') for r in results) else 0

    results = mirror.verify(manifest, root, args.tier, args.id, workers=min(args.workers, 4))
    if args.json:
        print(json.dumps(results, indent=2))
    for r in results:
        note = '' if r['ok'] else f"  {r['reason']}"
        flag = 'ok' if r['ok'] else 'FALLA'
        print(f"  {flag:<7}{r['id']}{note}" + ('' if r['ok'] or r['reason'] == 'missing' else ''))
    bad = [r for r in results if not r['ok']]
    print(f"{len(results) - len(bad)} verificados, {len(bad)} con problemas")
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
