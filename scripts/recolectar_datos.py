#!/usr/bin/env python3
"""Descubrimiento y descarga conservadora de fuentes públicas del proyecto."""
import argparse
import datetime as dt
import hashlib
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import shutil
import sys
import time
import http.client
import socket
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / 'data' / 'raw'
MANIFESTS = ROOT / 'data' / 'manifests'
PDS = 'https://pds-geosciences.wustl.edu'
MOLA = PDS + '/mgs/urn-nasa-pds-mgs_mola_topography_derived/'
LOLA = PDS + '/lro/lro-l-lola-3-rdr-v1/lrolol_1xxx/data/lola_gdr/cylindrical/float_img/'
GMTED = 'https://edcintl.cr.usgs.gov/downloads/sciweb1/shared/topo/downloads/GMTED/Grid_ZipFiles/'
SOURCES = {
    'mola': {'index': MOLA + 'meg128/', 'pattern': r'meg[ct].*hb\.(?:img|lbl|xml|hdr)', 'folder': 'mola_meg128'},
    'mola_polar': {'index': MOLA + 'polar/', 'pattern': r'meg[ct]_[ns]_128[^/]*\.(?:img|lbl|xml|hdr)', 'folder': 'mola_polar'},
    'lola': {'index': LOLA, 'pattern': r'ldem_64_float\.(?:img|lbl|xml)', 'folder': 'lola_gdr'},
    'gmted': {'urls': [GMTED + 'mn75_grd.zip', GMTED + 'mn30_grd.zip'], 'folder': 'gmted2010'},
    'arcticdem': {'urls': ['https://data.pgc.umn.edu/elev/dem/setsm/ArcticDEM/mosaic/v4.1/500m/arcticdem_mosaic_500m_v4.1.tar.gz'], 'folder': 'arcticdem_v4_1'},
    'rema': {'urls': ['https://data.pgc.umn.edu/elev/dem/setsm/REMA/mosaic/v2.0/500m/rema_mosaic_500m_v2.0.tar.gz'], 'folder': 'rema_v2_0'},
}
NOTE = ('Cobertura polar efectiva y huecos aún no verificados; '
        'GMTED 30 segundos es de menor resolución; ArcticDEM y REMA son complementos candidatos. '
        'La media GMTED es una selección inicial de adquisición, no una validación científica. '
        'LOLA soporte de observación y documentación MOLA adicional pendientes.')
UA = 'AnalogosPlanetarios-DataRetrieval/1.0'


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def request(url, method='GET', headers=None):
    h = {'User-Agent': UA, 'Accept-Encoding': 'identity'}
    h.update(headers or {})
    return urllib.request.urlopen(urllib.request.Request(url, headers=h, method=method), timeout=45)


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    os.replace(tmp, path)


def inspect_url(url):
    with request(url, 'HEAD') as res:
        length = res.headers.get('Content-Length')
        return {'bytes': int(length) if length and length.isdigit() else None,
                'etag': res.headers.get('ETag'), 'last_modified': res.headers.get('Last-Modified'),
                'content_type': res.headers.get('Content-Type')}


def classify(exc):
    if isinstance(exc, urllib.error.HTTPError) and exc.code in (401, 403):
        return f'HTTP {exc.code}: acceso denegado; verificar condiciones o autenticación del proveedor'
    return str(exc)


class IndexLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() == 'a':
            self.links.extend(value for key, value in attrs if key.lower() == 'href' and value)


def index_urls(html, index, pattern):
    parser = IndexLinks()
    parser.feed(html)
    base = urllib.parse.urlsplit(index)
    found = set()
    for href in parser.links:
        url = urllib.parse.urljoin(index, href)
        parsed = urllib.parse.urlsplit(url)
        name = urllib.parse.unquote(parsed.path.rsplit('/', 1)[-1])
        if (parsed.scheme == base.scheme and parsed.netloc == base.netloc
                and parsed.path.startswith(base.path) and not parsed.query and not parsed.fragment
                and re.fullmatch(pattern, name, re.I)):
            found.add(url)
    return sorted(found)


def discover(selected):
    plan = {'schema': 1, 'created_utc': now(), 'note': NOTE, 'sources': {}, 'files': []}
    for key in selected:
        spec = SOURCES[key]
        try:
            if 'index' in spec:
                with request(spec['index']) as res:
                    html = res.read(8 * 1024 * 1024).decode('utf-8', 'replace')
                urls = index_urls(html, spec['index'], spec['pattern'])
                if not urls:
                    raise ValueError('índice sin archivos coincidentes; revisar respuesta y cambios del proveedor')
            else:
                urls = spec['urls']
            expected_images = {'mola': 32, 'mola_polar': 4, 'lola': 1, 'gmted': 0, 'arcticdem': 0, 'rema': 0}[key]
            images = sum(url.lower().endswith('.img') for url in urls)
            missing = []
            if 'index' in spec:
                available = {u.rsplit('/', 1)[-1].lower() for u in urls}
                for name in sorted(n for n in available if n.endswith('.img')):
                    for ext in (('.lbl', '.xml', '.hdr') if key.startswith('mola') else ('.lbl', '.xml')):
                        if name[:-4] + ext not in available:
                            missing.append(name[:-4] + ext)
            complete = images == expected_images and not missing
            plan['sources'][key] = {'status': 'discovered' if complete else 'incomplete',
                                    'count': len(urls), 'images': images, 'expected_images': expected_images,
                                    'missing_labels': missing, 'index': spec.get('index')}
            for url in urls:
                entry = {'source': key, 'url': url, 'path': spec['folder'] + '/' + url.rsplit('/', 1)[-1],
                         'status': 'pending', 'license': 'pendiente de verificar', 'expected_sha256': None}
                try:
                    entry.update(inspect_url(url))
                except Exception as e:
                    entry.update({'bytes': None, 'discovery_error': classify(e)})
                plan['files'].append(entry)
        except Exception as e:
            plan['sources'][key] = {'status': 'error', 'error': classify(e)}
    return plan


def safe_path(relative):
    p = (RAW / relative).resolve()
    if not p.is_relative_to(RAW.resolve()):
        raise ValueError('ruta fuera de data/raw')
    return p


def used_bytes():
    return sum(p.stat().st_size for p in RAW.rglob('*') if p.is_file() and not p.is_symlink()) if RAW.exists() else 0


def validator(entry):
    etag = entry.get('etag')
    if etag and not etag.startswith('W/'):
        return etag
    return entry.get('last_modified')


def checked_response(entry, start=None, end=None):
    headers = {}
    if start is not None:
        token = validator(entry)
        if not token:
            raise ValueError('servidor sin ETag fuerte ni Last-Modified; no se puede reanudar con seguridad')
        headers = {'Range': f'bytes={start}-' + (str(end) if end is not None else ''), 'If-Range': token}
    res = request(entry['url'], headers=headers)
    try:
        typ = (res.headers.get('Content-Type') or '').lower()
        if 'text/html' in typ:
            raise ValueError('el servidor devolvió HTML en lugar del archivo')
        if entry.get('etag') and res.headers.get('ETag') != entry['etag']:
            raise ValueError('ETag cambió o falta; no se modifica el parcial')
        if entry.get('last_modified') and res.headers.get('Last-Modified') != entry['last_modified']:
            raise ValueError('Last-Modified cambió o falta; no se modifica el parcial')
        if start is not None:
            code = getattr(res, 'status', None)
            expected_end = end if end is not None else entry['bytes'] - 1
            if code != 206 or res.headers.get('Content-Range') != f'bytes {start}-{expected_end}/{entry["bytes"]}':
                raise ValueError('el servidor no confirmó el rango solicitado; parcial conservado')
        return res
    except Exception:
        res.close()
        raise


def check_existing_partial(entry, part):
    """Parciales heredados sin identidad: comparar cada byte antes de reutilizarlos."""
    offset = part.stat().st_size
    if not offset:
        return
    print(f'Comprobando {offset} bytes del parcial existente contra el proveedor...', flush=True)
    with checked_response(entry, 0, offset - 1) as remote, part.open('rb') as local:
        remaining = offset
        while remaining:
            block = remote.read(min(1024 * 1024, remaining))
            if not block:
                raise OSError('comparación del parcial interrumpida')
            if local.read(len(block)) != block:
                raise ValueError('el parcial difiere del proveedor; se conserva sin modificar')
            remaining -= len(block)


def fetch_one(entry, limit):
    path = safe_path(entry['path'])
    path.parent.mkdir(parents=True, exist_ok=True)
    size = entry.get('bytes')
    if size is None:
        raise ValueError('tamaño desconocido: ejecutar discover cuando el proveedor lo facilite')
    if path.exists():
        if entry.get('sha256') and path.stat().st_size == size and digest(path) == entry['sha256']:
            entry['status'] = 'verified_local'
            return
        raise ValueError('destino existente sin coincidencia verificada; no se sobrescribe')
    part = path.with_name(path.name + '.part')
    meta = path.with_name(path.name + '.part.json')
    offset = part.stat().st_size if part.exists() else 0
    if offset > size:
        raise ValueError('parcial más grande que el archivo remoto; se conserva')
    remaining = size - offset
    if used_bytes() + remaining > limit:
        raise ValueError('límite de almacenamiento excedido')
    if shutil.disk_usage(path.parent).free < remaining + 1024**3:
        raise ValueError('espacio libre insuficiente (se reserva 1 GiB)')
    identity = {'url': entry['url'], 'bytes': size, 'etag': entry.get('etag'), 'last_modified': entry.get('last_modified')}
    if offset:
        if meta.exists():
            if json.loads(meta.read_text()) != identity:
                raise ValueError('identidad del parcial distinta al plan; se conserva sin modificar')
        else:
            check_existing_partial(entry, part)
    save(meta, identity)
    if offset < size:
        with checked_response(entry, offset if offset else None) as res:
            with part.open('ab' if offset else 'xb') as out:
                count = offset
                last_report = offset
                print(f'Descargando {entry["path"]}: {count}/{size} bytes', flush=True)
                while True:
                    block = res.read(1024 * 1024)
                    if not block:
                        break
                    count += len(block)
                    if count > size or used_bytes() + len(block) > limit:
                        raise ValueError('respuesta o presupuesto excedido; parcial conservado')
                    out.write(block)
                    if count - last_report >= 64 * 1024 * 1024:
                        print(f'{entry["path"]}: {count}/{size} bytes ({100 * count / size:.1f}%)', flush=True)
                        last_report = count
                if count != size:
                    raise OSError(f'descarga incompleta ({count}/{size}); parcial conservado')
    entry['sha256'] = digest(part)
    if entry.get('expected_sha256') and entry['sha256'] != entry['expected_sha256']:
        entry.pop('sha256', None)
        raise ValueError('SHA-256 no coincide con el proveedor; parcial conservado')
    os.link(part, path)
    part.unlink()
    meta.unlink(missing_ok=True)
    entry.update(status='downloaded', downloaded_utc=now())


def fetch_with_retries(entry, limit, attempts=5):
    for attempt in range(attempts):
        try:
            return fetch_one(entry, limit)
        except (OSError, http.client.IncompleteRead, TimeoutError, urllib.error.URLError) as exc:
            if isinstance(exc, urllib.error.HTTPError) and exc.code not in (408, 429, 500, 502, 503, 504):
                raise
            if attempt == attempts - 1:
                raise
            delay = min(2 ** attempt, 16)
            print(f'Conexión interrumpida: {classify(exc)}. Reintentando en {delay} s; parcial conservado.', file=sys.stderr, flush=True)
            time.sleep(delay)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('doctor')
    d = sub.add_parser('discover')
    d.add_argument('--sources', nargs='+', choices=SOURCES, default=list(SOURCES))
    d.add_argument('--out', type=Path, default=MANIFESTS / 'plan.json')
    f = sub.add_parser('fetch')
    f.add_argument('--plan', type=Path, default=MANIFESTS / 'plan.json')
    f.add_argument('--sources', nargs='+', choices=SOURCES)
    f.add_argument('--max-gb', type=float, default=50, help='límite decimal en GB para todo data/raw (máximo 100)')
    v = sub.add_parser('verify')
    v.add_argument('--plan', type=Path, default=MANIFESTS / 'plan.json')
    args = parser.parse_args()
    if args.command == 'doctor':
        print(f'Espacio libre: {shutil.disk_usage(ROOT).free / 1e9:.2f} GB; data/raw: {used_bytes() / 1e9:.2f} GB')
        for name, url in [('PDS', PDS), ('USGS', 'https://topotools.cr.usgs.gov/')]:
            try:
                with request(url) as res:
                    print(f'{name}: HTTP {res.status}')
            except Exception as e:
                print(f'{name}: {classify(e)}')
        print(NOTE)
        return
    if args.command == 'discover':
        if args.out.exists():
            previous = json.loads(args.out.read_text(encoding='utf-8'))
            if any(item.get('sha256') for item in previous.get('files', [])):
                raise ValueError('el plan contiene hashes de descargas; usa --out para crear otro plan sin perderlos')
        plan = discover(args.sources)
        save(args.out, plan)
        known = sum(x.get('bytes') or 0 for x in plan['files'])
        unknown = sum(x.get('bytes') is None for x in plan['files'])
        print(f"Plan: {args.out}; archivos: {len(plan['files'])}; tamaño conocido: {known / 1e9:.3f} GB; desconocido: {unknown}")
        for name, state in plan['sources'].items():
            print(name, state)
        print(NOTE)
        if any(x['status'] != 'discovered' for x in plan['sources'].values()) or unknown:
            sys.exit(1)
        return
    plan = json.loads(args.plan.read_text(encoding='utf-8'))
    if plan.get('schema') != 1:
        raise ValueError('versión de manifiesto desconocida')
    selected_sources = args.sources if args.command == 'fetch' and args.sources else list(plan['sources'])
    failures = sum(1 for name in selected_sources if name not in plan['sources'] or plan['sources'][name]['status'] != 'discovered')
    if failures:
        print('Hay fuentes ausentes o incompletas en el plan.', file=sys.stderr)
    if args.command == 'fetch':
        if not 0 < args.max_gb <= 100:
            raise ValueError('--max-gb debe ser mayor que 0 y como máximo 100')
        for entry in plan['files']:
            if args.sources and entry['source'] not in args.sources:
                continue
            if plan['sources'][entry['source']]['status'] != 'discovered':
                failures += 1
                print('fuente incompleta:', entry['source'], file=sys.stderr)
                continue
            try:
                fetch_with_retries(entry, int(args.max_gb * 1e9))
                entry.pop('error', None)
                print(entry['status'], entry['path'], flush=True)
            except Exception as e:
                failures += 1
                entry.update(status='error', error=classify(e))
                print('error', entry['path'], entry['error'], file=sys.stderr, flush=True)
            save(args.plan, plan)
    else:
        for entry in plan['files']:
            path = safe_path(entry['path'])
            ok = bool(entry.get('sha256') and path.is_file() and path.stat().st_size == entry.get('bytes') and digest(path) == entry['sha256'])
            print(('OK' if ok else 'NO VERIFICADO'), entry['path'])
            failures += not ok
    if failures:
        sys.exit(1)


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f'Error: {exc}', file=sys.stderr)
        sys.exit(1)
