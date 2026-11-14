"""Disk access for the phase-4 regional search release."""
import hashlib
import json
from pathlib import Path

from fastapi import HTTPException

ROOT = Path(__file__).resolve().parents[3]
EVIDENCE = ROOT / 'docs/evidencia-fase-4'
CONFIG = ROOT / 'specs/search/busqueda-regional-v1.json'


def _checked_path(evidence_dir: Path, filename: str) -> Path:
    path = evidence_dir / filename
    if filename == 'manifest-local.json':
        if not path.is_file():
            raise FileNotFoundError(filename)
        return path
    manifest = json.loads((evidence_dir / 'manifest-local.json').read_text())
    entry = next(e for e in manifest['files'] if e['file'] == filename)
    if path.stat().st_size != entry['bytes'] or hashlib.sha256(path.read_bytes()).hexdigest() != entry['sha256']:
        raise ValueError('Release identity mismatch')
    return path


def load_release(evidence_dir: Path | None = None) -> dict:
    """Load and verify the regional search release.

    Args:
        evidence_dir: override the default evidence directory (used in tests).
    """
    base = evidence_dir if evidence_dir is not None else EVIDENCE
    try:
        _checked_path(base, '../../specs/search/busqueda-regional-v1.json')
        payload = json.loads(_checked_path(base, 'candidatas.json').read_text())
        config = json.loads(CONFIG.read_text())
        if config != payload['config'] or payload['search_id'] != config['search_id']:
            raise ValueError('Release/config mismatch')
        return payload
    except (OSError, ValueError, KeyError, TypeError, StopIteration) as exc:
        raise HTTPException(
            503,
            'La búsqueda regional falta o cambió. Ejecuta y revisa la auditoría y la generación de fase 4.',
        ) from exc


def load_candidate_detail(site: dict, evidence_dir: Path | None = None) -> dict:
    """Return the local detail record for a candidate, or a pending stub."""
    base = evidence_dir if evidence_dir is not None else EVIDENCE
    path = base / 'detalle' / f"{site['id']}.json"
    if not path.exists():
        return {
            'candidate_id': site['id'],
            'evaluation_status': 'pending_detail',
            'metrics': None,
            'plan': site['detail_plan'],
        }
    try:
        detail = json.loads(_checked_path(base, f"detalle/{site['id']}.json").read_text())
        catalog_hash = hashlib.sha256((base / 'candidatas.json').read_bytes()).hexdigest()
        if detail['candidate_id'] != site['id'] or detail['source_catalog_sha256'] != catalog_hash:
            raise ValueError('Detail belongs to another release')
        return detail
    except (OSError, ValueError, KeyError, TypeError, StopIteration) as exc:
        raise HTTPException(
            503,
            'La evaluación de detalle está incompleta o no corresponde al barrido actual.',
        ) from exc


def evidence_path(filename: str, evidence_dir: Path | None = None) -> Path:
    """Return a verified path for a served evidence file."""
    base = evidence_dir if evidence_dir is not None else EVIDENCE
    try:
        return _checked_path(base, filename)
    except (OSError, ValueError, KeyError, TypeError, StopIteration) as exc:
        raise HTTPException(503, 'Archivo de evidencia ausente o modificado.') from exc
