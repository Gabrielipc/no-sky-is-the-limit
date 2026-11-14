"""Disk access for the phase-2 scenario evidence."""
import hashlib
import json
from pathlib import Path
from typing import Callable

from fastapi import HTTPException

ROOT = Path(__file__).resolve().parents[3]
EVIDENCE = ROOT / 'docs' / 'evidencia-fase-2'
CONFIG = ROOT / 'specs' / 'analysis' / 'primer-caso-fase2.json'

CORE_FILES = ('resultados.json', 'procesamiento.json', 'areas-marte.json', 'areas-tierra.geojson')


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _manifest_entries(evidence_dir: Path) -> dict:
    return {item['file']: item for item in json.loads((evidence_dir / 'manifest-local.json').read_text())['files']}


def _verify(path: Path, entry: dict, digest_fn: Callable) -> None:
    if path.stat().st_size != entry['bytes'] or digest_fn(path) != entry['sha256']:
        raise ValueError('Evidence identity mismatch')


def load_case(evidence_dir: Path | None = None,
              config_path: Path | None = None,
              digest_fn: Callable | None = None) -> tuple[dict, dict, dict, dict]:
    """Return (config, results, processing, geometries). Raises HTTP 503 on failure."""
    base = evidence_dir if evidence_dir is not None else EVIDENCE
    cfg_path = config_path if config_path is not None else CONFIG
    _digest = digest_fn if digest_fn is not None else digest
    try:
        entries = _manifest_entries(base)
        for filename in CORE_FILES:
            _verify(base / filename, entries[filename], _digest)
        _verify(cfg_path, entries['../../specs/analysis/primer-caso-fase2.json'], _digest)
        config = json.loads(cfg_path.read_text())
        results = json.loads((base / 'resultados.json').read_text())
        processing = json.loads((base / 'procesamiento.json').read_text())
        geometries: dict = {}
        for filename in ('areas-marte.json', 'areas-tierra.geojson'):
            for feature in json.loads((base / filename).read_text())['features']:
                geometries[feature['properties']['site_id']] = feature
        return config, results, processing, geometries
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise HTTPException(
            503,
            'La evidencia de fase 2 falta o cambió. Verifica el análisis y su manifiesto antes de servirlo.',
        ) from exc


def evidence_path(filename: str,
                  evidence_dir: Path | None = None,
                  digest_fn: Callable | None = None) -> Path:
    """Return a verified path for a served evidence file. Raises HTTP 503 on failure."""
    base = evidence_dir if evidence_dir is not None else EVIDENCE
    _digest = digest_fn if digest_fn is not None else digest
    path = base / filename
    try:
        entries = _manifest_entries(base)
        if filename != 'manifest-local.json':
            _verify(path, entries[filename], _digest)
        elif not path.is_file():
            raise FileNotFoundError(filename)
    except (OSError, KeyError, ValueError, TypeError) as exc:
        raise HTTPException(503, 'Archivo ausente o distinto de la evidencia revisada.') from exc
    return path
