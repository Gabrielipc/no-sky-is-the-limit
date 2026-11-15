"""Verified local mirror of the Moon and Mars rasters behind the reference sites.

The manifest (`specs/sources/espejo-referencias-v1.json`, in Git) lists every product with its URL,
size and hash. The files live under `data/raw/espejo/` (ignored by Git) or `ANALOGOS_MIRROR_DIR`.

- `plan`   what is present, partial or missing, and how many bytes remain.
- `fetch`  resumable HTTPS download with a byte budget, checked against size and hash.
- `verify` re-hash the local copies.
- `local_copy(asset_id)` is what the ETL calls: the mirror path if the file is complete, else None.

Only URLs of the manifest are downloaded, over HTTPS, so the mirror cannot be pointed elsewhere.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / 'specs/sources/espejo-referencias-v1.json'
CHUNK = 1024 * 1024
HASHES = ('sha256', 'md5')


def load_manifest(path: Path = MANIFEST_PATH) -> dict:
    manifest = json.loads(Path(path).read_text(encoding='utf-8'))
    seen = set()
    for item in manifest['products']:
        if item['id'] in seen:
            raise ValueError(f'Producto duplicado en el manifiesto: {item["id"]}')
        seen.add(item['id'])
        if urllib.parse.urlsplit(item['url']).scheme != 'https':
            raise ValueError(f'El espejo solo admite HTTPS: {item["id"]}')
        if not isinstance(item.get('bytes'), int) or item['bytes'] <= 0:
            raise ValueError(f'Falta el tamaño de {item["id"]}')
        rel = Path(item['path'])
        if rel.is_absolute() or '..' in rel.parts:
            raise ValueError(f'Ruta fuera del espejo: {item["id"]}')
    return manifest


def mirror_root() -> Path:
    return Path(os.environ.get('ANALOGOS_MIRROR_DIR') or ROOT / 'data/raw/espejo')


def products(manifest: dict, tiers: list[int] | None = None, ids: list[str] | None = None) -> list[dict]:
    wanted = [p for p in manifest['products'] if (not tiers or p['tier'] in tiers) and (not ids or p['id'] in ids)]
    unknown = set(ids or []) - {p['id'] for p in manifest['products']}
    if unknown:
        raise ValueError(f'Productos desconocidos: {sorted(unknown)}')
    return wanted


def target(item: dict, root: Path) -> Path:
    return Path(root) / item['path']


def state(item: dict, root: Path) -> dict:
    path = target(item, root)
    part = path.with_name(path.name + '.part')
    if path.is_file():
        size = path.stat().st_size
        status = 'present' if size == item['bytes'] else 'wrong_size'
        return {'id': item['id'], 'status': status, 'have': size, 'bytes': item['bytes']}
    have = part.stat().st_size if part.is_file() else 0
    return {'id': item['id'], 'status': 'partial' if have else 'missing', 'have': have, 'bytes': item['bytes']}


def local_copy(asset_id: str | None, root: Path | None = None, manifest: dict | None = None) -> Path | None:
    """Path of a complete mirrored copy (right size) of the product with this asset id, or None."""
    if not asset_id:
        return None
    try:
        manifest = manifest or load_manifest()
    except (OSError, ValueError, KeyError):
        return None
    for item in manifest['products']:
        if item.get('asset_id') == asset_id or item['id'] == asset_id:
            path = target(item, root or mirror_root())
            return path if path.is_file() and path.stat().st_size == item['bytes'] else None
    return None


def plan(manifest: dict, root: Path, tiers: list[int] | None = None, ids: list[str] | None = None) -> dict:
    rows = []
    for item in products(manifest, tiers, ids):
        s = state(item, root)
        s.update(body=item['body'], tier=item['tier'], remaining=0 if s['status'] == 'present' else item['bytes'] - (
            s['have'] if s['status'] == 'partial' else 0))
        rows.append(s)
    return {'root': str(root), 'products': rows, 'remaining_bytes': sum(r['remaining'] for r in rows),
            'total_bytes': sum(r['bytes'] for r in rows)}


def digest(path: Path, algorithm: str = 'sha256') -> str:
    h = hashlib.new(algorithm)
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(CHUNK), b''):
            h.update(block)
    return h.hexdigest()


def expected_hash(item: dict) -> tuple[str, str] | None:
    for algorithm in HASHES:
        if item.get(algorithm):
            return algorithm, item[algorithm].lower()
    return None


def verify_item(item: dict, root: Path) -> dict:
    path = target(item, root)
    if not path.is_file():
        return {'id': item['id'], 'ok': False, 'reason': 'missing'}
    if path.stat().st_size != item['bytes']:
        return {'id': item['id'], 'ok': False, 'reason': f'size {path.stat().st_size} != {item["bytes"]}'}
    want = expected_hash(item)
    sha = digest(path, 'sha256')
    got = sha if not want or want[0] == 'sha256' else digest(path, want[0])
    if want and got != want[1]:
        return {'id': item['id'], 'ok': False, 'reason': f'{want[0]} mismatch', 'sha256': sha}
    return {'id': item['id'], 'ok': True, 'checked': bool(want), 'sha256': sha}


def verify(manifest: dict, root: Path, tiers=None, ids=None, workers: int = 2) -> list[dict]:
    with ThreadPoolExecutor(max(1, workers)) as ex:
        return list(ex.map(lambda i: verify_item(i, root), products(manifest, tiers, ids)))


class _HttpsOnly(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if urllib.parse.urlsplit(newurl).scheme != 'https':
            raise urllib.error.URLError(f'Redirección a un esquema no HTTPS: {newurl}')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _open(url: str, headers: dict, timeout: float, opener=None):
    opener = opener or urllib.request.build_opener(_HttpsOnly())
    return opener.open(urllib.request.Request(url, headers=headers), timeout=timeout)


def fetch_item(item: dict, root: Path, *, timeout: float = 60.0, attempts: int = 4, opener=None,
               log=lambda _m: None) -> dict:
    """Download one product, resuming a partial file, and check size and hash. Returns its state."""
    path = target(item, root)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file() and path.stat().st_size == item['bytes']:
        return {'id': item['id'], 'status': 'present', 'downloaded': 0}
    part = path.with_name(path.name + '.part')
    downloaded = 0
    last: Exception | None = None
    for attempt in range(1, attempts + 1):
        have = part.stat().st_size if part.is_file() else 0
        if have > item['bytes']:
            part.unlink()
            have = 0
        try:
            if have < item['bytes']:
                headers = {'Range': f'bytes={have}-'} if have else {}
                with _open(item['url'], headers, timeout, opener) as resp:
                    if have and resp.status != 206:  # the server ignored the range: start over
                        have = 0
                    with open(part, 'ab' if have else 'wb') as out:
                        for block in iter(lambda: resp.read(CHUNK), b''):
                            out.write(block)
                            downloaded += len(block)
            size = part.stat().st_size
            if size != item['bytes']:
                raise OSError(f'tamaño {size} != {item["bytes"]}')
            break
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            last = exc
            log(f'{item["id"]}: intento {attempt}/{attempts} falló ({exc})')
            if attempt == attempts:
                return {'id': item['id'], 'status': 'failed', 'downloaded': downloaded, 'error': str(exc)}
            time.sleep(min(2.0 * attempt, 10.0))
    want = expected_hash(item)
    sha = digest(part, 'sha256')
    got = sha if not want or want[0] == 'sha256' else digest(part, want[0])
    if want and got != want[1]:
        part.unlink()
        return {'id': item['id'], 'status': 'hash_mismatch', 'downloaded': downloaded, 'sha256': sha}
    part.replace(path)
    return {'id': item['id'], 'status': 'fetched', 'downloaded': downloaded, 'sha256': sha,
            'hash_checked': bool(want), 'last_error': str(last) if last else None}


def fetch(manifest: dict, root: Path, *, tiers=None, ids=None, max_bytes: int | None = None, workers: int = 4,
          opener=None, log=lambda _m: None) -> list[dict]:
    """Fetch what is missing, lightest first, until the byte budget is spent."""
    todo, budget = [], max_bytes
    for item in sorted(products(manifest, tiers, ids), key=lambda i: i['bytes']):
        s = state(item, root)
        if s['status'] == 'present':
            continue
        need = item['bytes'] - (s['have'] if s['status'] == 'partial' else 0)
        if budget is not None and need > budget:
            log(f'{item["id"]}: omitido, necesita {need} bytes y quedan {budget} del presupuesto')
            continue
        todo.append(item)
        budget = None if budget is None else budget - need
    with ThreadPoolExecutor(max(1, workers)) as ex:
        return list(ex.map(lambda i: fetch_item(i, root, opener=opener, log=log), todo))


def record_hashes(manifest_path: Path, results: list[dict]) -> int:
    """Write the hashes of freshly fetched files into the manifest. Returns how many were added."""
    manifest = json.loads(Path(manifest_path).read_text(encoding='utf-8'))
    by_id = {p['id']: p for p in manifest['products']}
    added = 0
    for r in results:
        item = by_id.get(r['id'])
        if item and r.get('sha256') and not item.get('sha256') and r.get('ok', r.get('status') == 'fetched'):
            item['sha256'] = r['sha256']
            added += 1
    if added:
        Path(manifest_path).write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    return added


def write_evidence(path: Path, body: str, checked: list[dict], manifest: dict) -> dict:
    """Record the hashes of the verified local copies of one body, to adopt them into the manifest later.

    The mirror files live on a VM and are not in Git; this small JSON is what travels (the cloud sync uploads
    `docs/evidencia-*`), so the manifest can pin the exact bytes that were downloaded.
    """
    items = {p['id']: p for p in manifest['products']}
    doc = {'spec_id': 'espejo-evidencia-v1', 'body': body, 'verified_at': datetime.now(timezone.utc).isoformat(),
           'products': {r['id']: {'sha256': r['sha256'], 'bytes': items[r['id']]['bytes'], 'url': items[r['id']]['url']}
                        for r in checked if r.get('ok') and r['id'] in items}}
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(doc, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    return doc


def adopt_hashes(manifest_path: Path, evidence_paths: list[Path]) -> dict:
    """Pin the hashes of evidence files into the manifest. Never overwrites a different hash or size.

    Returns {'added': [...], 'unchanged': [...], 'conflicts': [{id, reason}]}.
    """
    manifest = json.loads(Path(manifest_path).read_text(encoding='utf-8'))
    items = {p['id']: p for p in manifest['products']}
    out: dict = {'added': [], 'unchanged': [], 'conflicts': []}
    for evidence in evidence_paths:
        doc = json.loads(Path(evidence).read_text(encoding='utf-8'))
        if doc.get('spec_id') != 'espejo-evidencia-v1':
            raise ValueError(f'{evidence}: no es evidencia de espejo')
        for pid, rec in doc['products'].items():
            item = items.get(pid)
            if item is None:
                out['conflicts'].append({'id': pid, 'reason': 'producto desconocido en el manifiesto'})
            elif rec['bytes'] != item['bytes'] or rec['url'] != item['url']:
                out['conflicts'].append({'id': pid, 'reason': 'el tamaño o la URL difieren del manifiesto'})
            elif item.get('sha256') and item['sha256'] != rec['sha256']:
                out['conflicts'].append({'id': pid, 'reason': 'el sha256 difiere del ya fijado'})
            elif item.get('sha256'):
                out['unchanged'].append(pid)
            else:
                item['sha256'] = rec['sha256']
                out['added'].append(pid)
    if out['added']:
        Path(manifest_path).write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    return out
