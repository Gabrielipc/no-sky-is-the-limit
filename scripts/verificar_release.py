#!/usr/bin/env python3
"""Verify an Atlas release against the backend/frontend contracts before handing it over.

  python scripts/verificar_release.py releases/atlas30/etl-30m-r1
  python scripts/verificar_release.py            # the release named in releases/atlas30/current

Exit code 1 if there are errors; warnings are informative (e.g. a lunar reference without windows).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipelines.contract_check import verify_release  # noqa: E402

RELEASES = ROOT / 'releases/atlas30'


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('release', nargs='?', help='Carpeta de la release (por defecto la activa)')
    args = parser.parse_args(argv)
    release = Path(args.release) if args.release else RELEASES / (RELEASES / 'current').read_text().strip()
    report = verify_release(release)
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    print(f"\n{'OK' if not report['errors'] else 'ERRORES'}: {len(report['errors'])} errores, "
          f"{len(report['warnings'])} avisos", file=sys.stderr)
    sys.exit(1 if report['errors'] else 0)


if __name__ == '__main__':
    main()
