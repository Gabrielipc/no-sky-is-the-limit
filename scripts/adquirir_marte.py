#!/usr/bin/env python3
"""Adquisición pública y acotada de CRISM FRT000047A3 (Jezero).

discover prepara un plan sin red; fetch adquiere SR+IN y sus etiquetas por
defecto. --package full incluye además IF y WV. verify comprueba identidades.
No requiere Earthdata ni genera identificaciones minerales o comparaciones.
"""
import argparse
import importlib.util
import json
import math
from pathlib import Path
import re
import shutil
import sys
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'specs/sources/crism-jezero-v1.json'
METADATA = ROOT / 'docs/investigacion-marte/crism-productos.json'
DEFAULT_PLAN = ROOT / 'data/manifests/crism-jezero.json'
DIRECTORY = ('https://pds-geosciences.wustl.edu/mro/mro-m-crism-5-rdr-mptargeted-v1/'
             'mrocr_4001/mtrdr/2007/2007_057/frt000047a3/')
FOLDER = 'crism/frt000047a3'

# A private transport instance avoids changing the historical downloader or the
# Earth acquisition CLI when modules are imported together (e.g. in tests).
_spec = importlib.util.spec_from_file_location('_crism_transport', ROOT / 'scripts/recolectar_datos.py')
transport = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(transport)


def validate_url(url):
    parsed = urllib.parse.urlsplit(url)
    filename = parsed.path.rsplit('/', 1)[-1]
    if (not url.startswith(DIRECTORY) or parsed.scheme != 'https'
            or parsed.netloc != 'pds-geosciences.wustl.edu' or parsed.query or parsed.fragment
            or not re.fullmatch(r'frt000047a3_07_(?:sr|in|if|wv)166j_mtr3\.(?:img|hdr|lbl|xml|tab)', filename)
            or url != DIRECTORY + filename):
        raise ValueError('URL fuera de la selección pública CRISM de Jezero')


class PublicRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def request(url, method='GET', headers=None):
    validate_url(url)
    # Never load credentials or forward a caller-supplied Authorization header.
    if any(key.lower() in ('authorization', 'cookie', 'proxy-authorization') for key in (headers or {})):
        raise ValueError('CRISM público no admite credenciales en esta descarga')
    h = {'User-Agent': 'Analogos-CRISM/1.0', 'Accept-Encoding': 'identity', **(headers or {})}
    return urllib.request.build_opener(PublicRedirect()).open(
        urllib.request.Request(url, headers=h, method=method), timeout=45)


transport.request = request


def selected_files(package):
    if package not in ('parameters', 'full'):
        raise ValueError('Paquete CRISM desconocido')
    cfg = json.loads(SOURCE.read_text())
    metadata = json.loads(METADATA.read_text())
    if cfg['observation_id'] != 'FRT000047A3' or cfg['product_directory'] != DIRECTORY:
        raise ValueError('Observación CRISM distinta de la selección implementada')
    products = list(cfg['minimum_parameter_package'])
    if package == 'full':
        products.append(cfg['full_spectral_cube'])
    records = [dict(p, expected_sha256=None) for p in products]
    prefixes = {p['file'].rsplit('.', 1)[0] for p in products}
    if package == 'full':
        prefixes.add('frt000047a3_07_wv166j_mtr3')
    for entry in metadata['metadata']:
        if entry['file'].rsplit('.', 1)[0] not in prefixes:
            continue
        local = METADATA.parent / entry['file']
        if local.stat().st_size != entry['bytes'] or transport.digest(local) != entry['sha256']:
            raise ValueError('Los metadatos CRISM de referencia cambiaron')
        records.append(dict(entry, role='metadata', expected_sha256=entry['sha256']))
    names = {r['file'] for r in records}
    for product in products:
        prefix = product['file'].rsplit('.', 1)[0]
        if not {prefix + '.hdr', prefix + '.lbl'}.issubset(names):
            raise ValueError('Faltan cabecera ENVI o etiqueta PDS de un producto')
    if package == 'full' and not {'frt000047a3_07_wv166j_mtr3.tab', 'frt000047a3_07_wv166j_mtr3.lbl'}.issubset(names):
        raise ValueError('Falta la tabla de longitudes de onda o su etiqueta')
    files = []
    for r in records:
        validate_url(r['url'])
        if r['url'] != DIRECTORY + r['file'] or not isinstance(r['bytes'], int) or r['bytes'] <= 0:
            raise ValueError('Identidad de producto CRISM inválida')
        files.append({key: r[key] for key in ('url', 'bytes', 'role', 'expected_sha256')} |
                     {'path': FOLDER + '/' + r['file'], 'status': 'planned'})
    # Download small, checksum-bound metadata first; all files still pass budget
    # and availability preflight before any full transfer starts.
    return sorted(files, key=lambda e: (e['role'] != 'metadata', e['path']))


def discover(package='parameters', reuse_plan=None):
    plan = {'schema': 1, 'source_sha256': transport.digest(SOURCE),
            'metadata_sha256': transport.digest(METADATA), 'package': package,
            'observation_id': 'FRT000047A3', 'created_utc': transport.now(),
            'note': 'Public PDS acquisition only. Mineral interpretation and valid-pixel coverage remain unevaluated.',
            'files': selected_files(package)}
    if reuse_plan is not None:
        validate_plan(reuse_plan)
        previous = {e['path']: e for e in reuse_plan['files']}
        for entry in plan['files']:
            old = previous.get(entry['path'])
            if old and local_identity(old):
                for key in ('sha256', 'etag', 'last_modified', 'downloaded_utc'):
                    if key in old:
                        entry[key] = old[key]
                entry.update(sha256=transport.digest(transport.safe_path(entry['path'])), status='verified_local')
    return plan


def validate_plan(plan):
    if (plan.get('schema') != 1 or plan.get('source_sha256') != transport.digest(SOURCE)
            or plan.get('metadata_sha256') != transport.digest(METADATA)
            or plan.get('observation_id') != 'FRT000047A3'):
        raise ValueError('El plan o sus fuentes cambiaron; conservarlo y generar otro plan')
    expected = selected_files(plan.get('package'))
    fields = ('url', 'path', 'bytes', 'role', 'expected_sha256')
    signature = lambda entries: sorted(tuple(e.get(k) for k in fields) for e in entries)
    if len(plan['files']) != len(expected) or signature(plan['files']) != signature(expected):
        raise ValueError('Inventario CRISM distinto; no se adquieren rutas o productos ajenos al plan')
    for entry in plan['files']:
        transport.safe_path(entry['path'])
        if entry.get('sha256') is not None and not re.fullmatch('[0-9a-f]{64}', entry['sha256']):
            raise ValueError('SHA-256 local inválido')
        if entry.get('expected_sha256') and entry.get('sha256') not in (None, entry['expected_sha256']):
            raise ValueError('SHA-256 local distinto de los metadatos revisados')


def inspect(entry):
    with request(entry['url'], headers={'Range': 'bytes=0-0'}) as response:
        if 'text/html' in response.headers.get('Content-Type', '').lower():
            raise ValueError('PDS devolvió HTML en vez del producto')
        if response.headers.get('Content-Encoding', 'identity').lower() != 'identity':
            raise ValueError('Respuesta comprimida incompatible con los bytes declarados')
        if response.status == 206:
            match = re.fullmatch(r'bytes 0-0/([1-9][0-9]*)', response.headers.get('Content-Range', ''))
            length = response.headers.get('Content-Length')
            if not match or length not in (None, '1') or len(response.read(2)) != 1:
                raise ValueError('PDS no confirmó el rango de un byte')
            size = int(match.group(1))
        elif response.status == 200:
            # A server that ignores Range must not trigger a complete cube read.
            length = response.headers.get('Content-Length', '')
            size = int(length) if length.isdigit() else None
        else:
            raise ValueError('Respuesta inesperada de PDS')
        if size != entry['bytes']:
            raise ValueError('Tamaño remoto distinto de los metadatos revisados')
        entry.update(etag=response.headers.get('ETag'), last_modified=response.headers.get('Last-Modified'), status='ready')


def local_identity(entry):
    path = transport.safe_path(entry['path'])
    expected = entry.get('sha256') or entry.get('expected_sha256')
    return bool(expected and path.is_file() and path.stat().st_size == entry['bytes'] and transport.digest(path) == expected)


def pending_bytes(entry):
    path = transport.safe_path(entry['path'])
    part = path.with_name(path.name + '.part')
    offset = part.stat().st_size if part.is_file() else 0
    if offset > entry['bytes']:
        raise ValueError('Parcial mayor que el archivo esperado; se conserva')
    return entry['bytes'] - offset


def error_message(exc):
    if isinstance(exc, urllib.error.HTTPError):
        return f'HTTP {exc.code}: producto PDS no disponible'
    return str(exc)


def fetch(plan, max_new_gb=.25, on_update=None):
    validate_plan(plan)
    if not math.isfinite(max_new_gb) or not 0 < max_new_gb <= 10:
        raise ValueError('--max-new-gb debe ser mayor que 0 y como máximo 10')
    budget = int(max_new_gb * 1e9)
    ready, failures = [], 0
    # Reject an oversized batch before network access, including Range probes.
    remaining = sum(pending_bytes(e) for e in plan['files'] if not transport.safe_path(e['path']).exists())
    if remaining > budget:
        raise ValueError('El lote completo excede el presupuesto de bytes nuevos; no se inició la transferencia')
    if shutil.disk_usage(ROOT).free < remaining + 1024**3:
        raise ValueError('Espacio insuficiente para el lote; se reserva 1 GiB')
    for entry in plan['files']:
        try:
            path = transport.safe_path(entry['path'])
            if path.exists():
                if not local_identity(entry):
                    raise ValueError('Archivo existente sin identidad coincidente; no se sobrescribe')
                entry.update(status='verified_local', sha256=transport.digest(path))
                print('verified_local', entry['path'], flush=True)
            else:
                inspect(entry)
                ready.append(entry)
            entry.pop('error', None)
        except (OSError, ValueError) as exc:
            failures += 1
            entry.update(status='error', error=error_message(exc))
            print('error', entry['path'], entry['error'], file=sys.stderr, flush=True)
        finally:
            if on_update:
                on_update()
    if failures:
        return failures  # Preserve the whole package until preflight succeeds.
    # Small recovery sidecars do not count as downloaded scientific payload.
    ceiling = transport.used_bytes() + budget + len(ready) * 65536
    for entry in ready:
        previous_sha = entry.get('sha256')
        try:
            # A previously recorded local identity is also binding on a re-fetch.
            original_expected = entry['expected_sha256']
            entry['expected_sha256'] = entry.get('sha256') or original_expected
            try:
                transport.fetch_with_retries(entry, ceiling)
            finally:
                entry['expected_sha256'] = original_expected
            entry.pop('error', None)
            print(entry['status'], entry['path'], flush=True)
        except (OSError, ValueError) as exc:
            if previous_sha:
                entry['sha256'] = previous_sha
            failures += 1
            entry.update(status='error', error=error_message(exc))
            print('error', entry['path'], entry['error'], file=sys.stderr, flush=True)
        finally:
            if on_update:
                on_update()
    return failures


def verify(plan, report_path=None):
    validate_plan(plan)
    failures, files = 0, []
    for entry in plan['files']:
        ok = local_identity(entry)
        print('OK' if ok else 'NO VERIFICADO', entry['path'])
        failures += not ok
        files.append({key: entry.get(key) for key in ('path', 'url', 'bytes', 'sha256', 'expected_sha256', 'role')} |
                     {'verified': ok})
    if report_path:
        transport.save(report_path, {'schema': 1, 'observation_id': plan['observation_id'], 'package': plan['package'],
            'verified_utc': transport.now(), 'source_sha256': plan['source_sha256'], 'metadata_sha256': plan['metadata_sha256'],
            'acquisition_script_sha256': transport.digest(Path(__file__).resolve()),
            'transport_script_sha256': transport.digest(ROOT / 'scripts/recolectar_datos.py'),
            'complete': not bool(failures), 'verified_bytes': sum(e['bytes'] for e in files if e['verified']), 'files': files,
            'identity_note': 'SHA-256 of science images records local identity, not an independent provider checksum. Metadata hashes match the reviewed copies.',
            'scientific_status': 'Acquisition only; valid-pixel coverage, mineral interpretation and Earth/Mars comparison remain unevaluated.'})
    return failures


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('discover', 'fetch', 'verify'))
    parser.add_argument('--plan', type=Path, default=DEFAULT_PLAN)
    parser.add_argument('--package', choices=('parameters', 'full'), default=None, help='Solo discover: parameters por defecto; full agrega IF y WV')
    parser.add_argument('--max-new-gb', type=float, default=.25, help='Bytes nuevos de archivos de este lote en GB decimales, no tráfico de red ni datos históricos')
    parser.add_argument('--report', type=Path, help='Solo verify: informe JSON con identidades y estado de adquisición')
    parser.add_argument('--reuse-plan', type=Path, help='Solo discover: reutilizar identidades locales comprobadas de otro plan CRISM')
    args = parser.parse_args()
    if args.package is not None and args.command != 'discover':
        parser.error('--package solo se usa en discover; fetch/verify respetan el paquete del plan')
    if args.report is not None and args.command != 'verify':
        parser.error('--report solo se usa en verify')
    if args.reuse_plan is not None and args.command != 'discover':
        parser.error('--reuse-plan solo se usa en discover')
    if args.command == 'discover':
        if args.plan.exists():
            raise ValueError('El plan existe; usa otra ruta --plan para conservar sus identidades')
        previous = json.loads(args.reuse_plan.read_text()) if args.reuse_plan else None
        plan = discover(args.package or 'parameters', previous)
        if args.reuse_plan:
            plan['reused_plan_sha256'] = transport.digest(args.reuse_plan)
        transport.save(args.plan, plan)
        print(f'Plan: {args.plan}; {len(plan["files"])} archivos; {sum(e["bytes"] for e in plan["files"]):,} bytes. Sin descargas.')
        return 0
    plan = json.loads(args.plan.read_text())
    if args.command == 'verify':
        return bool(verify(plan, args.report))
    validate_plan(plan)
    try:
        return bool(fetch(plan, args.max_new_gb, lambda: transport.save(args.plan, plan)))
    finally:
        transport.save(args.plan, plan)


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print('Error:', error_message(exc), file=sys.stderr)
        sys.exit(1)
