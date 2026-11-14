"""Prepare original inputs for the atlas context layers, without raster processing."""
import json
import os
import re
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from pipelines import atlas_sources as sources, atlas_temporal as temporal, atlas_topography as topo

SPEC = sources.ROOT / 'specs/sources/contexto-atlas-2024.json'
LAYERS = ('worldcover', 'jrc', 'hls', 'landsat')
EARTHDATA = 'data.lpdaac.earthdatacloud.nasa.gov'
MIRROR = 'landsateuwest.blob.core.windows.net'


class EarthdataRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        origin, target = urlsplit(req.full_url), urlsplit(newurl)
        if target.scheme != 'https':
            raise OSError('Earthdata solicitó una redirección sin HTTPS')
        redirected = super().redirect_request(req, fp, code, msg, headers, newurl)
        if redirected is not None and target.netloc != origin.netloc:
            redirected.remove_header('Authorization')
        return redirected


def open_earthdata(url, method='GET', headers=None):
    request = Request(url, method=method, headers={**(headers or {}),
                                                   'Authorization': 'Bearer ' + os.environ['EARTHDATA_TOKEN']})
    try:
        return build_opener(EarthdataRedirect()).open(request, timeout=30)
    except HTTPError as exc:
        raise HTTPError(url, exc.code, 'Respuesta de Earthdata', exc.headers, exc.fp) from None
    except OSError:
        raise OSError('No se pudo acceder al activo HLS') from None


def open_mirror(url, method='GET', headers=None):
    # The signed request URL is transient. Hide it even when urllib raises.
    try:
        return sources.request(url + '?' + temporal.landsat_token(), method, headers)
    except HTTPError as exc:
        raise HTTPError(url, exc.code, 'Respuesta de Landsat', exc.headers, exc.fp) from None
    except OSError:
        raise OSError('No se pudo acceder a la copia de Landsat') from None


def scene_assets(layer, scene):
    if layer == 'hls':
        match = re.fullmatch(r'HLS\.([LS]30)\.T\d{2}[A-Z]{3}\.\d{7}T\d{6}\.v2\.0', scene)
        if not match:
            raise ValueError(f'ID de escena HLS inválido: {scene}')
        product = 'HLS' + match.group(1)
        bands = temporal.HLS[product + '.v2.0']
        base = f'https://{EARTHDATA}/lp-prod-protected/{product}.020/{scene}/'
        names = [f'{scene}.{band}.tif' for band in bands]
    else:
        match = re.fullmatch(r'LC0[89]_L2SP_(\d{3})(\d{3})_(\d{4})\d{4}_\d{8}_02_T[12]_ST', scene)
        if not match:
            raise ValueError(f'ID de escena Landsat inválido: {scene}')
        path, row, year = match.groups()
        product = scene.removesuffix('_ST')
        base = f'https://{MIRROR}/landsat-c2/level-2/standard/oli-tirs/{year}/{path}/{row}/{product}/'
        names = [f'{product}_{band}.TIF' for band in ('ST_B10', 'QA_PIXEL', 'ST_QA')]
    return [{**sources.asset(layer, name, base + name), 'scene_id': scene} for name in names]


def inputs(layers, areas):
    spec = json.loads(SPEC.read_text())
    entries = {}
    gaps = []
    for batch in topo.benchmark_batches():
        area = batch.label
        if area not in areas:
            continue
        selected = []
        margin = topo.WINDOW / 2 + topo.HALO + topo.CELL
        w, s, e, n = batch.bounds
        boxes = topo.geographic_boxes(batch.zone, (w - margin, s - margin, e + margin, n + margin))
        for layer in layers:
            if layer == 'worldcover':
                selected.extend(sources.worldcover_asset(*key) for key in topo.tile_keys(boxes, 3))
            elif layer == 'jrc':
                selected.extend(sources.jrc_asset(*key) for key in topo.tile_keys(boxes, 10))
            else:
                scenes = spec['areas'][area][layer]
                if not scenes:
                    gaps.append({'area': area, 'source': layer, 'status': 'no_scene_in_pilot'})
                for scene in scenes:
                    selected.extend(scene_assets(layer, scene))
        for asset in selected:
            key = (asset['source'], asset['id'])
            entry = entries.setdefault(key, {**asset, 'areas': []})
            entry['areas'].append(area)
    return list(entries.values()), gaps


def inspect(entry):
    if entry['source'] == 'hls':
        if not os.environ.get('EARTHDATA_TOKEN'):
            return {**entry, 'status': 'earthdata_login_required', 'bytes': None}
        return sources.remote_identity(entry, open_earthdata, ranged=True)
    if entry['source'] == 'landsat':
        return sources.remote_identity(entry, open_mirror)
    return sources.remote_identity(entry)


def download(entry):
    if entry['source'] == 'hls':
        return sources.transfer(entry, open_earthdata)
    if entry['source'] == 'landsat':
        return sources.transfer(entry, open_mirror)
    return sources.transfer(entry)


def prepare(layers, areas, fetch, max_gb):
    entries, gaps = inputs(layers, areas)
    if fetch:
        results = sources.fetch(entries, int(max_gb * 10**9), inspect=inspect, download=download)
    else:
        results = [sources.local_identity(entry) or inspect(entry) for entry in entries]
    # Use this selection's spatial scope even if an asset was first cached for a different area.
    results = [{**result, 'areas': entry['areas']} for entry, result in zip(entries, results)]
    summary = {}
    for layer in layers:
        selected = [item for item in results if item['source'] == layer]
        summary[layer] = {
            'assets': len(selected),
            'new_bytes': sum(item['bytes'] or 0 for item in selected if item['status'] == 'available'),
            'verified_bytes': sum(item['bytes'] for item in selected if item['status'] == 'verified_local'),
            'unavailable': sum(item['status'] not in ('available', 'verified_local') for item in selected),
        }
    report = {'areas': areas, 'layers': summary, 'assets': results, 'gaps': gaps}
    area_label = 'all' if set(areas) == set(topo.BENCHMARK) else '-'.join(sorted(areas))
    path = sources.MANIFESTS / f'context-{"-".join(sorted(layers))}-{area_label}.json'
    sources.atomic_json(path, report)
    report['path'] = str(path.relative_to(sources.ROOT))
    return report
