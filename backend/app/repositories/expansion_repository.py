"""Disk access for the phase-5 source/scale sensitivity evidence."""
import hashlib
import json
from pathlib import Path

from fastapi import HTTPException

ROOT = Path(__file__).resolve().parents[3]
EVIDENCE = ROOT / 'docs/evidencia-fase-5'
CONFIG = ROOT / 'specs/scenarios/estabilidad-topografica-v1.json'
SCENARIO_ID = 'estabilidad-topografica'
SCALES_M = [60, 120, 300, 600]
WINDOW_M = 3000

FILES = frozenset(('resultados.json', 'procesamiento.json', 'manifest-local.json'))


def _verify(path: Path, entry: dict) -> None:
    if path.stat().st_size != entry['bytes'] or hashlib.sha256(path.read_bytes()).hexdigest() != entry['sha256']:
        raise ValueError('Phase-5 evidence identity mismatch')


def load_release(evidence_dir: Path, config_path: Path, regional_config: dict, catalog_path: Path) -> dict:
    """Load and cross-verify the phase-5 release.

    Args:
        evidence_dir:   directory containing the phase-5 evidence JSON files.
        config_path:    path to the estabilidad-topografica config JSON.
        regional_config: the ``config`` block from the regional release.
        catalog_path:   path to ``candidatas.json`` used to compute its hash.
    """
    try:
        entries = {e['file']: e for e in json.loads((evidence_dir / 'manifest-local.json').read_text())['files']}
        for name in ('resultados.json', 'procesamiento.json'):
            _verify(evidence_dir / name, entries[name])
        _verify(config_path, entries['../../specs/scenarios/estabilidad-topografica-v1.json'])
        _verify(ROOT / 'specs/analysis/primer-caso-fase2.json', entries['../../specs/analysis/primer-caso-fase2.json'])
        cfg = json.loads(config_path.read_text())
        result = json.loads((evidence_dir / 'resultados.json').read_text())
        processing = json.loads((evidence_dir / 'procesamiento.json').read_text())
        catalog_hash = hashlib.sha256(catalog_path.read_bytes()).hexdigest()
        if (result['scenario'] != cfg
                or cfg['scenario_id'] != SCENARIO_ID
                or cfg['scales_m'] != SCALES_M
                or cfg['window_m'] != WINDOW_M
                or processing['config_sha256'] != hashlib.sha256(config_path.read_bytes()).hexdigest()
                or result['source_catalog_sha256'] != catalog_hash
                or processing['source_catalog_sha256'] != catalog_hash
                or result['window_m'] != regional_config['window_m']):
            raise ValueError('Phase-5 provenance mismatch')
        return {**result, 'processing': processing,
                'evidence': {name: f'/api/expansion/evidence/{name}' for name in sorted(FILES)}}
    except (OSError, ValueError, KeyError, TypeError, StopIteration) as exc:
        raise HTTPException(
            503,
            'La evidencia de fase 5 falta o cambió. Reproduce y revisa la expansión antes de servirla.',
        ) from exc
