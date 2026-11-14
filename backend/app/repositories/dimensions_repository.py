"""Disk access for the multidimensional surface evidence."""
import hashlib
import json
from pathlib import Path

from fastapi import HTTPException

ROOT = Path(__file__).resolve().parents[3]
EVIDENCE = ROOT / 'docs/evidencia-dimensiones'
CONFIG = ROOT / 'specs/scenarios/superficie-multidimensional-v1.json'
SCENARIO_ID = 'superficie-multidimensional'
SCALES_M = [60, 120]
WINDOW_M = 1800

_EXPECTED_PATHS = {
    EVIDENCE / 'resultados.json',
    EVIDENCE / 'procesamiento.json',
    CONFIG,
    ROOT / 'specs/analysis/primer-caso-fase2.json',
    ROOT / 'docs/investigacion-dimensiones/catalogo-fuentes.json',
    ROOT / 'scripts/analizar_dimensiones.py',
    ROOT / 'scripts/analizar_primer_caso.py',
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_release(evidence_dir: Path | None = None, digest_fn=None) -> dict:
    """Return verified results.

    Args:
        evidence_dir: override the evidence directory (used in tests via patching).
        digest_fn:    override the hash function (used in tests via patching).
    """
    base = evidence_dir if evidence_dir is not None else EVIDENCE
    _digest = digest_fn if digest_fn is not None else digest
    try:
        manifest = json.loads((base / 'manifest-local.json').read_text())
        entries = {item['file']: item for item in manifest['files']}
        # Reconstruct the expected paths relative to the (possibly overridden) base.
        expected = {
            base / 'resultados.json',
            base / 'procesamiento.json',
            CONFIG,
            ROOT / 'specs/analysis/primer-caso-fase2.json',
            ROOT / 'docs/investigacion-dimensiones/catalogo-fuentes.json',
            ROOT / 'scripts/analizar_dimensiones.py',
            ROOT / 'scripts/analizar_primer_caso.py',
        }
        paths = {(base / key).resolve() for key in entries}
        if manifest['schema'] != 1 or paths != {p.resolve() for p in expected} or len(entries) != len(expected):
            raise ValueError('Manifest inventory mismatch')
        for key, item in entries.items():
            path = (base / key).resolve()
            if path.stat().st_size != item['bytes'] or _digest(path) != item['sha256']:
                raise ValueError('Evidence identity mismatch')
        cfg = json.loads(CONFIG.read_text())
        result = json.loads((base / 'resultados.json').read_text())
        processing = json.loads((base / 'procesamiento.json').read_text())
        if (cfg['scenario_id'] != SCENARIO_ID
                or result['scenario_id'] != SCENARIO_ID
                or cfg['scales_m'] != SCALES_M
                or result['scales_m'] != cfg['scales_m']
                or result['window_m'] != WINDOW_M
                or processing['config'] != cfg
                or processing['config_sha256'] != _digest(CONFIG)):
            raise ValueError('Configuration mismatch')
        return result
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise HTTPException(
            503,
            'La evidencia multidimensional falta o cambió. Ejecuta scripts/analizar_dimensiones.py y revisa su resultado.',
        ) from exc


def evidence_digest(evidence_dir: Path | None = None) -> str:
    base = evidence_dir if evidence_dir is not None else EVIDENCE
    return digest(base / 'resultados.json')
