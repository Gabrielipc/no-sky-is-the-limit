"""Disk access for EMIT and CRISM mineral evidence."""
import hashlib
import json
from pathlib import Path
from types import ModuleType

from fastapi import HTTPException

ROOT = Path(__file__).resolve().parents[3]
EVIDENCE = ROOT / 'docs/evidencia-minerales'
JEZERO_EVIDENCE = ROOT / 'docs/evidencia-crism'
CONFIG = ROOT / 'specs/analysis/minerales-emit-v1.json'

_EMIT_CORE = {
    CONFIG,
    ROOT / 'scripts/analizar_minerales.py',
    ROOT / 'requirements-minerales.txt',
    ROOT / 'docs/evidencia-fase-2/areas-tierra.geojson',
    ROOT / 'docs/evidencia-fase-2/resultados.json',
    *(ROOT / f'docs/evidencia-fase-2/{site}-60m-slope.tif' for site in ('earth-utah', 'earth-atacama')),
}

_JEZERO_CORE = {
    ROOT / 'scripts/analizar_crism.py',
    ROOT / 'docs/evidencia-fase-2/areas-marte.json',
    ROOT / 'docs/investigacion-marte/adquisicion-crism.json',
}


def _verified_files(directory: Path, expected: set, hashlib_mod: ModuleType) -> dict:
    manifest = json.loads((directory / 'manifest-local.json').read_text())
    entries = manifest['files']
    if manifest['schema'] != 1 or len(entries) != len(expected) or {ROOT / e['file'] for e in entries} != expected:
        raise ValueError('Inventario de evidencia distinto')
    contents = {}
    for entry in entries:
        path = ROOT / entry['file']
        content = path.read_bytes()
        if len(content) != entry['bytes'] or hashlib_mod.sha256(content).hexdigest() != entry['sha256']:
            raise ValueError('Identidad de evidencia distinta')
        contents[path] = content
    return contents


def load_emit_release(evidence_dir: Path | None = None,
                      hashlib_mod: ModuleType | None = None) -> dict:
    """Load verified EMIT results. Raises HTTP 503 on failure."""
    base = evidence_dir if evidence_dir is not None else EVIDENCE
    hlib = hashlib_mod if hashlib_mod is not None else hashlib
    expected = _EMIT_CORE | {base / 'resultados.json', base / 'procesamiento.json'}
    try:
        contents = _verified_files(base, expected, hlib)
        result = json.loads(contents[base / 'resultados.json'])
        cfg = json.loads(contents[CONFIG])
        if result['release_id'] != cfg['release_id'] or result['window_m'] != cfg['window_m']:
            raise ValueError('Configuración mineral distinta')
        if {site['id'] for site in result['sites']} != {'earth-utah', 'earth-atacama'}:
            raise ValueError('Sitios minerales incompletos')
        return result
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise HTTPException(
            503,
            'La evidencia mineral falta o cambió. Genera y revisa scripts/analizar_minerales.py.',
        ) from exc


def load_jezero_release(jezero_dir: Path | None = None,
                        hashlib_mod: ModuleType | None = None) -> dict:
    """Load verified CRISM/Jezero results. Raises HTTP 503 on failure."""
    base = jezero_dir if jezero_dir is not None else JEZERO_EVIDENCE
    hlib = hashlib_mod if hashlib_mod is not None else hashlib
    result_file = base / 'resultados.json'
    expected = _JEZERO_CORE | {result_file}
    try:
        contents = _verified_files(base, expected, hlib)
        return json.loads(contents[result_file])
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise HTTPException(
            503,
            'La evidencia CRISM falta o cambió. Genera y revisa scripts/analizar_crism.py.',
        ) from exc
