#!/usr/bin/env python3
"""Adquisición acotada de THEMIS, 3DEP, HiRISE y dos gránulos EMIT seleccionados.

discover no descarga rásteres. fetch limita bytes nuevos, conserva parciales,
no sobrescribe originales y recibe EARTHDATA_TOKEN solo desde el entorno.
"""
import argparse
import json
import os
from pathlib import Path
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parent))
import recolectar_datos as transport

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT/'docs/investigacion-dimensiones/catalogo-fuentes.json'
DEFAULT_PLAN = ROOT/'data/manifests/dimensiones.json'
SOURCES = ('themis', '3dep-utah', 'hirise-ortho', 'emit')
PUBLIC_HOSTS = {'zenodo.org', 'prd-tnm.s3.amazonaws.com', 'www.uahirise.org', 'cmr.earthdata.nasa.gov'}
EARTHDATA_HOST = 'data.lpdaac.earthdatacloud.nasa.gov'


class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if urllib.parse.urlsplit(newurl).scheme != 'https':
            raise ValueError('Se rechaza una redirección fuera de HTTPS')
        redirected = super().redirect_request(req, fp, code, msg, headers, newurl)
        if redirected and urllib.parse.urlsplit(req.full_url).netloc != urllib.parse.urlsplit(newurl).netloc:
            redirected.remove_header('Authorization')
        return redirected


def request(url, method='GET', headers=None):
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != 'https' or parsed.hostname not in PUBLIC_HOSTS | {EARTHDATA_HOST} or parsed.username or parsed.password or parsed.port not in (None, 443):
        raise ValueError('URL fuera de los proveedores admitidos')
    h = {'User-Agent': 'Analogos-Dimensiones/1.0', 'Accept-Encoding': 'identity', **(headers or {})}
    if parsed.hostname == EARTHDATA_HOST:
        token = os.environ.get('EARTHDATA_TOKEN')
        if not token:
            raise ValueError('EMIT requiere EARTHDATA_TOKEN en el entorno; no se guarda en el manifiesto')
        if any(ord(c) < 32 for c in token):
            raise ValueError('El token contiene caracteres inválidos')
        h['Authorization'] = 'Bearer '+token
    return urllib.request.build_opener(SafeRedirect()).open(urllib.request.Request(url, headers=h, method=method), timeout=45)


# Reuse tested size limits, range validation, retries, safe paths and checksums.
# This module is a separate CLI; the historical downloader remains unchanged.
transport.request = request


def selected_products(catalog, sources):
    indexed = {s['id']: s for s in catalog['sources']}
    files = []
    for key, catalog_id, folder in [('themis', 'themis-jezero-ti', 'themis'),
                                     ('3dep-utah', 'usgs-3dep-utah-1m', '3dep'),
                                     ('hirise-ortho', 'hirise-ortho-a', 'hirise')]:
        if key not in sources:
            continue
        s = indexed[catalog_id]
        url = s['urls']['download']
        filename = Path(urllib.parse.urlsplit(url).path).name
        if key == 'themis':
            filename = Path(s['local_path']).name
        files.append({'source': key, 'product_id': s['product_id'] if 'product_id' in s else s['id'],
                      'url': url, 'path': folder+'/'+filename, 'bytes': s['bytes'],
                      'expected_sha256': s.get('sha256'), 'authentication': 'none', 'status': 'planned'})
        # Acquiring an image without its PDS label loses calibration/georeference.
        if key == 'hirise-ortho':
            files.append({'source': key, 'product_id': s['product_id']+'-label',
                          'url': url.rsplit('.', 1)[0]+'.LBL', 'path': folder+'/'+filename.rsplit('.', 1)[0]+'.LBL',
                          'bytes': None, 'expected_sha256': None, 'authentication': 'none', 'status': 'planned'})
    if 'emit' in sources:
        for site in indexed['emit-l2b-min']['site_queries']:
            # The investigation selected one example per initial Earth candidate.
            example = site['examples'][0]
            for url in example['data_urls']:
                filename = Path(urllib.parse.urlsplit(url).path).name
                files.append({'source': 'emit', 'site_id': site['site'], 'product_id': example['product_id'],
                              'url': url, 'path': 'emit/'+filename, 'bytes': None,
                              'expected_sha256': None, 'authentication': 'earthdata_token',
                              'status': 'awaiting_auth' if not os.environ.get('EARTHDATA_TOKEN') else 'planned',
                              'coverage_note': 'Catalog point overlap only; full footprint and pixel quality pending.'})
    return files


def discover(sources, refresh=False):
    catalog = json.loads(CATALOG.read_text())
    files = selected_products(catalog, sources)
    for entry in files:
        path = transport.safe_path(entry['path'])
        if path.is_file() and entry.get('expected_sha256'):
            if path.stat().st_size != entry['bytes'] or transport.digest(path) != entry['expected_sha256']:
                raise ValueError('Original local distinto del documentado; no se sobrescribe')
            entry.update(status='verified_local', sha256=entry['expected_sha256'])
        if refresh and entry['status'] not in ('verified_local', 'awaiting_auth'):
            try:
                inspect(entry)
            except (OSError, ValueError) as exc:
                entry.update(status='unavailable', error=error_message(exc))
    return {'schema': 2, 'created_utc': transport.now(), 'catalog_sha256': transport.digest(CATALOG),
            'note': 'Explicit source selection; missing/authenticated data do not become scientific measurements.',
            'files': files}


def inspect_remote(url):
    if urllib.parse.urlsplit(url).hostname != EARTHDATA_HOST:
        return transport.inspect_url(url)
    # LP DAAC redirects to a signed CloudFront GET URL. Reusing it for HEAD can
    # return 403 even when the token is valid. Probe one byte without downloading
    # the product; Content-Length here is 1, not the size of the complete file.
    with request(url, headers={'Range': 'bytes=0-0'}) as response:
        status = getattr(response, 'status', None)
        if status == 206:
            match = re.fullmatch(r'bytes 0-0/([1-9][0-9]*)', response.headers.get('Content-Range', ''))
            length = response.headers.get('Content-Length')
            if not match or (length is not None and length != '1') or len(response.read(2)) != 1:
                raise ValueError('EMIT no confirmó el rango de un byte y su tamaño total')
            size = int(match.group(1))
        elif status == 200:
            # Some providers ignore Range. Inspect headers and close immediately;
            # do not read their full body during the budget preflight.
            length = response.headers.get('Content-Length', '')
            size = int(length) if length.isdigit() and int(length) > 0 else None
        else:
            raise ValueError('Respuesta inesperada al comprobar el archivo EMIT')
        return {'bytes': size, 'etag': response.headers.get('ETag'),
                'last_modified': response.headers.get('Last-Modified'),
                'content_type': response.headers.get('Content-Type')}


def inspect(entry):
    observed = inspect_remote(entry['url'])
    if observed['bytes'] is None:
        raise ValueError('El proveedor no informó tamaño exacto; descarga pendiente')
    if entry.get('bytes') is not None and observed['bytes'] != entry['bytes']:
        raise ValueError('El tamaño remoto cambió; revisar selección antes de descargar')
    if 'text/html' in (observed.get('content_type') or '').lower():
        raise ValueError('El proveedor devolvió HTML, no un archivo científico')
    entry.update(observed, status='ready')


def error_message(exc):
    if isinstance(exc, urllib.error.HTTPError):
        return f'HTTP {exc.code}: revisar acceso/autenticación o disponibilidad del proveedor'
    message = str(exc)
    token = os.environ.get('EARTHDATA_TOKEN')
    return message.replace(token, '[REDACTED]') if token else message


def pending_bytes(entry):
    path = transport.safe_path(entry['path'])
    part = path.with_name(path.name+'.part')
    size = part.stat().st_size if part.exists() else 0
    if size > entry['bytes']:
        raise ValueError('Parcial mayor que el tamaño esperado; se conserva')
    return entry['bytes']-size


def fetch(plan, sources, max_new_gb, on_update=None):
    if not 0 < max_new_gb <= 10:
        raise ValueError('--max-new-gb debe estar entre 0 y 10')
    initial = transport.used_bytes()
    ceiling = initial+int(max_new_gb*1e9)
    selected = [f for f in plan['files'] if f['source'] in sources]
    if not selected:
        raise ValueError('La selección no contiene archivos en este plan')
    ready, failures = [], 0
    for entry in selected:
        try:
            path = transport.safe_path(entry['path'])
            if path.exists():
                expected = entry.get('sha256') or entry.get('expected_sha256')
                if not expected or path.stat().st_size != entry['bytes'] or transport.digest(path) != expected:
                    raise ValueError('Archivo existente sin identidad verificada; no se sobrescribe')
                entry.update(status='verified_local', sha256=expected)
                print('verified_local', entry['path'])
                continue
            if entry.get('authentication') == 'earthdata_token' and not os.environ.get('EARTHDATA_TOKEN'):
                raise ValueError('EMIT requiere EARTHDATA_TOKEN en el entorno')
            inspect(entry)
            ready.append(entry)
        except (OSError, ValueError) as exc:
            failures += 1
            entry.update(status='awaiting_auth' if entry.get('authentication') == 'earthdata_token' and not os.environ.get('EARTHDATA_TOKEN') else 'error', error=error_message(exc))
            print(entry['status'], entry['path'], entry['error'], file=sys.stderr)
        finally:
            if on_update:
                on_update()
    remaining = sum(pending_bytes(entry) for entry in ready)
    if remaining > max_new_gb*1e9:
        raise ValueError('El lote completo excede el presupuesto de bytes nuevos; no se inició la transferencia')
    for entry in ready:
        try:
            transport.fetch_with_retries(entry, ceiling)
            entry.pop('error', None)
            print(entry['status'], entry['path'], flush=True)
        except (OSError, ValueError) as exc:
            failures += 1
            entry.update(status='error', error=error_message(exc))
            print('error', entry['path'], entry['error'], file=sys.stderr)
        finally:
            if on_update:
                on_update()
    return failures


def verify(plan, sources):
    failures = 0
    selected = [e for e in plan['files'] if e['source'] in sources]
    if not selected:
        raise ValueError('La selección no contiene archivos en este plan')
    for entry in selected:
        path = transport.safe_path(entry['path'])
        expected = entry.get('sha256') or entry.get('expected_sha256')
        ok = path.is_file() and expected and path.stat().st_size == entry.get('bytes') and transport.digest(path) == expected
        print('OK' if ok else 'NO VERIFICADO', entry['path'])
        failures += not bool(ok)
    return failures


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('discover', 'fetch', 'verify'))
    parser.add_argument('--sources', nargs='+', choices=SOURCES, default=['themis', '3dep-utah', 'emit'])
    parser.add_argument('--plan', type=Path, default=DEFAULT_PLAN)
    parser.add_argument('--refresh', action='store_true', help='HEAD de disponibilidad y tamaños durante discover')
    parser.add_argument('--max-new-gb', type=float, default=1, help='Presupuesto de bytes nuevos del lote, no de todo data/raw')
    args = parser.parse_args()
    if args.command == 'discover':
        if args.plan.exists():
            raise ValueError('El plan existe; usa --plan con otro nombre para conservar las identidades anteriores')
        plan = discover(args.sources, args.refresh)
        transport.save(args.plan, plan)
        print(f'Plan: {args.plan}; {len(plan["files"])} archivos. Ningún ráster descargado.')
        return 0
    plan = json.loads(args.plan.read_text())
    if plan.get('schema') != 2 or plan.get('catalog_sha256') != transport.digest(CATALOG):
        raise ValueError('Plan o catálogo cambió; revisar y generar un plan nuevo')
    if args.command == 'verify':
        return bool(verify(plan, args.sources))
    try:
        return bool(fetch(plan, args.sources, args.max_new_gb, lambda: transport.save(args.plan, plan)))
    finally:
        transport.save(args.plan, plan)


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (OSError, ValueError, KeyError) as exc:
        print('Error:', error_message(exc), file=sys.stderr)
        sys.exit(1)
