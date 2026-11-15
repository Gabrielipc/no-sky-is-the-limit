#!/usr/bin/env python3
"""Análogos planetarios en Nicaragua, con foco en las zonas volcánicas.

    python scripts/analogos_nicaragua.py boundary  --shp ne_10m_admin_0_countries.shp
    python scripts/analogos_nicaragua.py volcanoes --gvp gvp-nicaragua.json
    python scripts/analogos_nicaragua.py densify   [--radius-km 10] [--stride-m 2000]
    python scripts/analogos_nicaragua.py compute   [--radius-km 10]

`boundary` recorta y simplifica el contorno de Nicaragua de Natural Earth 1:10 m (dominio público) en
`data/nicaragua/frontera-ne10m.geojson`. `volcanoes` guarda los volcanes holocenos del Global Volcanism
Program (Smithsonian) en `data/nicaragua/volcanes-gvp.json`. Ambos se ejecutan una sola vez; sus
salidas se versionan para que `compute` no descargue nada.

El almacén global solo tiene una ventana de 3 km cada 10 km, demasiado poco para un volcán. `densify` calcula,
con el mismo extractor del ETL (`pipelines/etl_extractors.extract_base_window`: Copernicus GLO-30, WorldCover y
JRC leídos por rangos HTTP), ventanas cada `--stride-m` metros a `--radius-km` o menos de cada volcán, más una
ventana centrada en cada cumbre y en cada sitio conocido. Las guarda en `data/normalized/nicaragua/` (fuera de
Git) y no toca el almacén ni el ajuste del motor.

`compute` usa el motor de similitud sobre todas las ventanas terrestres clasificables (sin el filtro de
aridez: casi toda Nicaragua está cubierta de bosque o agua) y guarda, para cada ventana dentro del país,
su distancia a cada referencia y su puesto entre todas las ventanas de la Tierra. Las referencias son las
planetarias del motor y los análogos conocidos de `data/nicaragua/sitios-conocidos.json` usados como
referencias terrestres («lugares con un relieve parecido a Cerro Negro»). Escribe
`frontend/public/analysis/nicaragua/analogos-nicaragua-v1.json`, que la vista `/?view=nicaragua` lee sin
backend.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

DATA = ROOT / 'data/nicaragua'
BOUNDARY_PATH = DATA / 'frontera-ne10m.geojson'
VOLCANOES_PATH = DATA / 'volcanes-gvp.json'
SITES_PATH = DATA / 'sitios-conocidos.json'
DENSE_PATH = ROOT / 'data/normalized/nicaragua/ventanas-densas-v1.json'
OUT_PATH = ROOT / 'frontend/public/analysis/nicaragua/analogos-nicaragua-v1.json'
STORE = ROOT / 'data/feature_store_v1'
MODEL = ROOT / 'data/features/modelos-similitud/motor-similitud-ml-v1.joblib'
PROFILE = 'arid_mars_surface_v2'
PLANETARY_REFERENCES = ('jezero', 'haworth-fondo', 'de-gerlache-cresta')
DEFAULT_RADIUS_KM = 10.0
DEFAULT_STRIDE_M = 2000
DENSE_PREFIX = 'nic-v1'
# Ventanas a menos de esta distancia de un sitio usado como referencia terrestre se excluyen de su ranking:
# comparten relieve con la referencia y no son hallazgos.
SELF_EXCLUSION_KM = 5.0
EARTH_RADIUS_KM = 6371.0088
WINDOW_COLUMNS = ('relief_p95_p05_m', 'slope_240m_p50_deg', 'slope_240m_p90_deg', 'roughness_360m_p50_m',
                  'hypsometric_integral', 'trees_fraction', 'bare_or_sparse_fraction', 'built_fraction',
                  'permanent_water_fraction', 'land_fraction')
SPEC_ID = 'analogos-nicaragua-v1'


# ---------------------------------------------------------------------------
# Geometría
# ---------------------------------------------------------------------------
def haversine_km(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(min(1.0, math.sqrt(a)))


def load_boundary(path: Path = BOUNDARY_PATH):
    from shapely.geometry import shape
    return shape(json.loads(path.read_text(encoding='utf-8'))['geometry'])


def inside(geom, lon: float, lat: float) -> bool:
    from shapely.geometry import Point
    return geom.covers(Point(lon, lat))


def nearest_volcano(lon: float, lat: float, volcanoes: list[dict]) -> tuple[dict | None, float]:
    best, best_km = None, math.inf
    for v in volcanoes:
        d = haversine_km(lon, lat, v['longitude'], v['latitude'])
        if d < best_km:
            best, best_km = v, d
    return best, best_km


# ---------------------------------------------------------------------------
# Preparación (una vez)
# ---------------------------------------------------------------------------
def prepare_boundary(shp: Path, tolerance: float = 0.005) -> dict:
    import geopandas as gpd
    from shapely.geometry import mapping
    countries = gpd.read_file(shp)
    rows = countries[countries['ADM0_A3'] == 'NIC']
    if len(rows) != 1:
        raise SystemExit('No se encontró Nicaragua (ADM0_A3 = NIC) en el shapefile')
    geom = rows.geometry.iloc[0].simplify(tolerance, preserve_topology=True)

    def rnd(obj):
        if isinstance(obj, (list, tuple)):
            return [rnd(o) for o in obj]
        return round(obj, 4)

    gj = mapping(geom)
    return {'type': 'Feature',
            'properties': {'name': 'Nicaragua', 'source': 'Natural Earth 1:10m Admin 0 – Countries (dominio público)',
                           'source_url': 'https://www.naturalearthdata.com/downloads/10m-cultural-vectors/',
                           'simplify_tolerance_deg': tolerance,
                           'note': 'Contorno de referencia para recortar ventanas; no es un límite oficial. '
                                   'Incluye el Lago Cocibolca y el de Managua dentro del polígono.'},
            'geometry': {'type': gj['type'], 'coordinates': rnd(gj['coordinates'])}}


def prepare_volcanoes(gvp: Path) -> dict:
    data = json.loads(gvp.read_text(encoding='utf-8'))
    out = []
    for f in data['features']:
        p = f['properties']
        if p.get('Country') != 'Nicaragua':
            continue
        lon, lat = f['geometry']['coordinates']
        out.append({'id': str(p['Volcano_Number']), 'name': p['Volcano_Name'], 'longitude': lon, 'latitude': lat,
                    'type': p.get('Primary_Volcano_Type'), 'landform': p.get('Volcanic_Landform'),
                    'last_eruption_year': p.get('Last_Eruption_Year'), 'rock': p.get('Major_Rock_Type'),
                    'elevation_m': p.get('Elevation'),
                    'url': f"https://volcano.si.edu/volcano.cfm?vn={p['Volcano_Number']}"})
    out.sort(key=lambda v: -v['latitude'])
    return {'source': 'Global Volcanism Program, Smithsonian Institution · Volcanoes of the World (volcanes holocenos)',
            'source_url': 'https://volcano.si.edu/', 'volcanoes': out}


# ---------------------------------------------------------------------------
# Densificación de las zonas volcánicas
# ---------------------------------------------------------------------------
def dense_sites(boundary, volcanoes: list[dict], known: list[dict], radius_km: float, stride_m: int) -> list[dict]:
    """Centros de ventana: rejilla UTM cada `stride_m` cerca de los volcanes, cumbres y sitios conocidos."""
    from pipelines import atlas_topography as topo
    sites: dict[str, dict] = {}

    def add(region_id: str, lon: float, lat: float, label: str, x=None, y=None, zone=None):
        zone = zone or topo.owner(lon, lat)
        if x is None:
            x, y = topo.projection(4326, zone).transform(lon, lat)
        sites.setdefault(region_id, {'region_id': region_id, 'batch': DENSE_PREFIX, 'area': 'nicaragua',
                                     'zone': zone, 'x': float(x), 'y': float(y), 'longitude': float(lon),
                                     'latitude': float(lat), 'label': label})

    for s in known:
        add(f"{DENSE_PREFIX}-sitio-{s['id']}", s['longitude'], s['latitude'], 'known_site')
    for v in volcanoes:
        add(f"{DENSE_PREFIX}-volcan-{v['id']}", v['longitude'], v['latitude'], 'volcano_summit')
    for v in volcanoes:
        zone = topo.owner(v['longitude'], v['latitude'])
        fwd, inv = topo.projection(4326, zone), topo.projection(zone, 4326)
        cx, cy = fwd.transform(v['longitude'], v['latitude'])
        r = radius_km * 1000
        for row in range(math.floor((cy - r) / stride_m), math.ceil((cy + r) / stride_m) + 1):
            for col in range(math.floor((cx - r) / stride_m), math.ceil((cx + r) / stride_m) + 1):
                x, y = col * stride_m, row * stride_m
                if math.hypot(x - cx, y - cy) > r:
                    continue
                lon, lat = inv.transform(x, y)
                if inside(boundary, lon, lat):
                    add(f'{DENSE_PREFIX}-{stride_m}-{zone}-{row}-{col}', lon, lat, 'grid', x, y, zone)
    return list(sites.values())


def densify(radius_km: float, stride_m: int, log=print, out: Path = DENSE_PATH) -> dict:
    """Extrae las ventanas densas; reanuda desde `out` si ya existe con los mismos parámetros."""
    from contextlib import ExitStack
    import rasterio
    from pipelines import atlas_sources as sources
    from pipelines import atlas_topography as topo
    from pipelines import etl_extractors as extractors
    boundary = load_boundary()
    volcanoes = json.loads(VOLCANOES_PATH.read_text(encoding='utf-8'))['volcanoes']
    known = json.loads(SITES_PATH.read_text(encoding='utf-8'))['sites']
    sites = dense_sites(boundary, volcanoes, known, radius_km, stride_m)
    params = {'radius_km': radius_km, 'stride_m': stride_m, 'feature_version': extractors.FEATURE_VERSION,
              'window_m': extractors.WINDOW_M, 'cell_m': extractors.CELL_M}
    done: dict[str, dict] = {}
    if out.is_file():
        prev = json.loads(out.read_text(encoding='utf-8'))
        if prev.get('params') == params:
            done = {r['region_id']: r for r in prev['rows'] if r['qa_status'] != 'dem_fetch_failed'}
    todo = [s for s in sites if s['region_id'] not in done]
    log(f'{len(sites)} ventanas densas; {len(done)} ya calculadas; {len(todo)} por calcular')
    land, inventory = topo.Land(), sources.glo_inventory()
    keep = ('region_id', 'longitude', 'latitude', 'qa_status', 'analog_surface_eligibility', 'cover_status',
            'land_fraction', 'topo_valid_fraction', 'relief_p95_p05_m', 'slope_240m_p50_deg', 'slope_240m_p90_deg',
            'roughness_360m_p50_m', 'hypsometric_integral', 'elevation_skew_p95_p05',
            'aspect_240m_resultant_length', 'slope_240m_gt15_fraction', 'slope_240m_gt25_fraction',
            'trees_fraction', 'bare_or_sparse_fraction', 'built_fraction', 'permanent_water_fraction',
            'source_manifest_id')

    def save():
        out.parent.mkdir(parents=True, exist_ok=True)
        rows = sorted(done.values(), key=lambda r: r['region_id'])
        out.write_text(json.dumps({'params': params, 'rows': rows}, ensure_ascii=False, allow_nan=False),
                       encoding='utf-8')

    t0 = time.perf_counter()
    with ExitStack() as stack:
        stack.enter_context(rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN='EMPTY_DIR', GDAL_HTTP_MAX_RETRY=2,
                                         GDAL_HTTP_TIMEOUT=30, GDAL_CACHEMAX=256 * 1024 ** 2))
        rasters = topo.Rasters(stack, 'range')
        for i, site in enumerate(todo, 1):
            row, _ = extractors.extract_base_window(site, land, rasters, inventory)
            rec = {k: (None if isinstance(row.get(k), float) and not math.isfinite(row[k]) else row.get(k))
                   for k in keep}
            rec['label'] = site['label']
            done[site['region_id']] = rec
            if i % 50 == 0 or i == len(todo):
                save()
                log(f'  {i}/{len(todo)} · {time.perf_counter() - t0:.0f} s · {rasters.read_bytes / 1e6:.0f} MB leídos')
    save()
    qa: dict[str, int] = {}
    for r in done.values():
        qa[r['qa_status']] = qa.get(r['qa_status'], 0) + 1
    log(f'Estados: {qa}')
    return {'params': params, 'rows': list(done.values())}


# ---------------------------------------------------------------------------
# Cálculo
# ---------------------------------------------------------------------------
def fetch_windows(conn, bbox: tuple[float, float, float, float]) -> list[dict]:
    """Todas las ventanas terrestres del recuadro, clasificables o no, con lo que la vista necesita."""
    present = {r[0] for r in conn.execute('DESCRIBE features_unified').fetchall()}
    cols = [c for c in WINDOW_COLUMNS if c in present]
    w, s, e, n = bbox
    rows = conn.execute(
        f"SELECT region_id, longitude, latitude, qa_status, analog_surface_eligibility, {', '.join(cols)} "
        "FROM features_unified WHERE body = 'Earth' AND longitude BETWEEN ? AND ? AND latitude BETWEEN ? AND ? "
        'ORDER BY region_id', [w, e, s, n]).fetchall()
    keys = ['region_id', 'longitude', 'latitude', 'qa_status', 'eligibility', *cols]
    return [dict(zip(keys, r)) for r in rows]


def classify_windows(windows: list[dict], boundary, volcanoes: list[dict], radius_km: float) -> list[dict]:
    """Ventanas con centro dentro de Nicaragua, con su volcán más cercano y si caen en zona volcánica."""
    out = []
    for w in windows:
        if not inside(boundary, w['longitude'], w['latitude']):
            continue
        v, d = nearest_volcano(w['longitude'], w['latitude'], volcanoes)
        out.append({**w, 'volcano_id': v['id'] if v else None, 'volcano_km': d,
                    'volcanic': bool(v) and d <= radius_km})
    return out


WATER_DOMINATED = 0.5
DUPLICATE_KM = 0.2
# Columnas de ventana que la vista usa; lo demás se queda en el almacén y en la salida de `densify`.
OUTPUT_COLUMNS = ('region_id', 'source', 'longitude', 'latitude', 'qa_status', 'eligibility', 'volcano_id',
                  'volcano_km', 'volcanic', 'water_dominated', 'relief_p95_p05_m', 'slope_240m_p50_deg',
                  'slope_240m_p90_deg', 'hypsometric_integral', 'trees_fraction', 'bare_or_sparse_fraction')
DECIMALS = {'longitude': 4, 'latitude': 4, 'volcano_km': 2, 'relief_p95_p05_m': 1, 'slope_240m_p50_deg': 2,
            'slope_240m_p90_deg': 2, 'hypsometric_integral': 3, 'trees_fraction': 3, 'bare_or_sparse_fraction': 3}


def dedupe_dense(dense_rows: list[dict], atlas_rows: list[dict]) -> list[dict]:
    """Quita las ventanas de la rejilla densa que coinciden con una del atlas (la rejilla de 10 km es múltiplo
    de la densa): se conserva la del atlas. Las de sitios y cumbres se mantienen siempre."""
    out = []
    for w in dense_rows:
        if w['source'] == 'grid' and any(
                abs(a['latitude'] - w['latitude']) < 0.01 and abs(a['longitude'] - w['longitude']) < 0.01
                and haversine_km(a['longitude'], a['latitude'], w['longitude'], w['latitude']) < DUPLICATE_KM
                for a in atlas_rows):
            continue
        out.append(w)
    return out


def score_map(response: dict) -> dict[str, dict]:
    return {r['region_id']: r for r in response['results']}


def summarize_reference(rid: str, response: dict, kind: str, extra: dict | None = None) -> dict:
    ref = response['reference']
    return {'id': rid, 'name': ref['name'], 'body': ref['body'], 'kind': kind,
            'weights_effective': response['weights_effective'], 'warnings': response['warnings'],
            'earth_windows_ranked': response['candidates_ranked'], **(extra or {})}


def dense_pool(engine, base_pool, rows: list[dict]):
    """`CandidatePool` con las ventanas densas, sobre la conexión del pool global (no la cierra)."""
    import numpy as np
    from pipelines import similarity_ml as sim
    rows = [r for r in rows if r['qa_status'] == 'rankable']
    data = {'region_id': np.array([r['region_id'] for r in rows], dtype=object),
            'longitude': np.array([r['longitude'] for r in rows], dtype='float64'),
            'latitude': np.array([r['latitude'] for r in rows], dtype='float64'),
            'utm_zone_band': np.array(['nicaragua-densa'] * len(rows), dtype=object),
            'scenario_eligibility': np.array([r['analog_surface_eligibility'] for r in rows], dtype=object)}
    for fdef in engine.features.values():
        col = fdef.column('Earth')
        if col and rows and col in rows[0]:
            data[col] = np.array([np.nan if r.get(col) is None else r[col] for r in rows], dtype='float64')
    cand_raw, cand_z = engine.candidate_scores(data)
    return sim.CandidatePool(profile=PROFILE, conn=base_pool.conn, present=base_pool.present, data=data,
                             cand_raw=cand_raw, cand_z=cand_z, eligible=np.ones(len(rows), dtype=bool))


def global_rank(sorted_scores, score: float | None) -> int | None:
    """Puesto que tendría `score` entre todas las ventanas clasificables de la Tierra (1 = la más parecida)."""
    import numpy as np
    if score is None:
        return None
    return int(np.searchsorted(sorted_scores, score, side='left')) + 1


def reference_from_window(row: dict, site: dict, engine) -> dict:
    features = {}
    for fdef in engine.features.values():
        col = fdef.column('Earth')
        if col and row.get(col) is not None:
            features[col] = row[col]
    return {'id': f"sitio:{site['id']}", 'name': f"Relieve parecido a {site['name']}", 'body': 'Earth',
            'features': features}


def compute(radius_km: float = DEFAULT_RADIUS_KM, log=print, dense_path: Path = DENSE_PATH) -> dict:
    import numpy as np
    from pipelines import similarity_ml as sim
    boundary = load_boundary()
    volcanoes = json.loads(VOLCANOES_PATH.read_text(encoding='utf-8'))
    sites = json.loads(SITES_PATH.read_text(encoding='utf-8'))
    if not dense_path.is_file():
        raise SystemExit(f'Falta {dense_path.relative_to(ROOT)}: ejecuta primero `densify`')
    dense = json.loads(dense_path.read_text(encoding='utf-8'))
    engine = sim.SimilarityEngine.load(MODEL)
    t0 = time.perf_counter()
    pool = engine.build_pool(STORE, PROFILE)
    log(f'{len(pool)} ventanas terrestres clasificables cargadas en {time.perf_counter() - t0:.1f} s')
    minx, miny, maxx, maxy = boundary.bounds
    cursor = pool.conn.cursor()
    try:
        raw = fetch_windows(cursor, (minx - 0.05, miny - 0.05, maxx + 0.05, maxy + 0.05))
    finally:
        cursor.close()
    for w in raw:
        w['source'] = 'atlas'
    dense_rows = []
    for r in dense['rows']:
        w = {k: r.get(k) for k in ('region_id', 'longitude', 'latitude', 'qa_status', *WINDOW_COLUMNS)}
        w.update(eligibility=r['analog_surface_eligibility'], source=r['label'])
        dense_rows.append(w)
    windows = classify_windows(raw + dedupe_dense(dense_rows, raw), boundary, volcanoes['volcanoes'], radius_km)
    for w in windows:
        # Las densas están en zona volcánica por construcción (la rejilla mide el radio en UTM, no en geodésica).
        w['volcanic'] = w['volcanic'] or w['source'] != 'atlas'
        w['water_dominated'] = (w.get('permanent_water_fraction') or 0) >= WATER_DOMINATED
    log(f"{len(windows)} ventanas con centro en Nicaragua ({len(raw)} del atlas en el recuadro, "
        f"{len(dense_rows)} densas); {sum(w['volcanic'] for w in windows)} en zona volcánica")

    by_region = {r['region_id']: r for r in dense['rows']}
    known = []
    for site in sites['sites']:
        row = by_region.get(f"{DENSE_PREFIX}-sitio-{site['id']}")
        known.append({**site, 'window_id': row['region_id'] if row else None,
                      'window_rankable': bool(row and row['qa_status'] == 'rankable')})

    dpool = dense_pool(engine, pool, dense['rows'])
    mars_weights = engine.spec['default_weights']['Mars']
    queries = [(rid, rid, None, 'planetary', {}) for rid in PLANETARY_REFERENCES]
    for site in known:
        if not site['window_rankable']:
            log(f"  {site['id']}: su ventana no es clasificable; no se usa como referencia")
            continue
        ref = reference_from_window(by_region[site['window_id']], site, engine)
        queries.append((ref['id'], ref, mars_weights, 'earth_analog',
                        {'name': ref['name'], 'site_id': site['id'], 'window_id': site['window_id'],
                         'excluded_near_km': SELF_EXCLUSION_KM}))
    references, scores, sorted_global = [], {}, {}
    for rid, ref, weights, kind, extra in queries:
        t = time.perf_counter()
        response = engine.search(STORE, ref, weights=weights, profile=PROFILE, only_eligible=False,
                                 limit=len(pool), pool=pool)
        by_id = score_map(response)
        sorted_global[rid] = np.sort(np.array([r['score'] for r in response['results']], dtype='float64'))
        dresp = engine.search(STORE, ref, weights=weights, profile=PROFILE, only_eligible=False,
                              limit=max(1, len(dpool)), pool=dpool)
        by_id.update(score_map(dresp))
        if kind == 'earth_analog':
            site = next(s for s in known if s['id'] == extra['site_id'])
            near = [w['region_id'] for w in windows if haversine_km(
                w['longitude'], w['latitude'], site['longitude'], site['latitude']) < SELF_EXCLUSION_KM]
            for region_id in near:
                by_id.pop(region_id, None)
            extra = {**extra, 'excluded_windows': len(near)}
        references.append(summarize_reference(rid, response, kind, extra))
        scores[rid] = by_id
        log(f'  {rid}: {time.perf_counter() - t:.1f} s')
    pool.close()

    columns = list(OUTPUT_COLUMNS)
    rows = []
    for w in windows:
        row = []
        for c in columns:
            v = w.get(c)
            if isinstance(v, float):
                v = None if not math.isfinite(v) else round(v, DECIMALS.get(c, 4))
            row.append(v)
        rows.append(row)
    rankings = {}
    for ref in references:
        by_id = scores[ref['id']]
        out = {k: [] for k in ('score', 'coverage', 'global_rank')}
        for w in windows:
            r = None if w['water_dominated'] else by_id.get(w['region_id'])
            out['score'].append(round(r['score'], 4) if r else None)
            out['coverage'].append(round(r['coverage'], 3) if r else None)
            out['global_rank'].append(global_rank(sorted_global[ref['id']], r['score']) if r else None)
        rankings[ref['id']] = out

    return {
        'spec_id': SPEC_ID,
        'generated_at': datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        'engine': {'id': engine.model['engine_id'], 'fitted_at': engine.model['fitted_at'],
                   'status': engine.spec['status'], 'profile': PROFILE, 'only_eligible': False,
                   'fusion': engine.spec['search']['default_fusion'],
                   'missing_policy': engine.spec['search']['default_missing_policy'],
                   'earth_windows_ranked': len(pool)},
        'method': {
            'window_m': 3000, 'cell_m': 30, 'volcanic_radius_km': radius_km,
            'dense_stride_m': dense['params']['stride_m'], 'self_exclusion_km': SELF_EXCLUSION_KM,
            'water_dominated_fraction': WATER_DOMINATED,
            'notes': [
                'El motor compara la forma del relieve (escabrosidad, forma hipsométrica, organización de las '
                'pendientes y régimen morfológico). Las vistas espectral y térmica aún no están ajustadas para la '
                'Tierra, así que la mineralogía no entra en la distancia.',
                'No se aplica el filtro de superficie árida: casi todo Nicaragua tiene bosque, cultivos o agua. '
                'La cobertura de cada ventana se muestra aparte y no cambia la distancia; con más de un 5 % de '
                'árboles la rugosidad no se mide y esa feature queda ausente.',
                f"Zona volcánica: centro de ventana a {radius_km:g} km o menos de un volcán holoceno del GVP. "
                f"Ahí se añadieron ventanas cada {dense['params']['stride_m'] / 1000:g} km con el mismo extractor del "
                'atlas global (Copernicus GLO-30 a 30 m); fuera, solo hay una ventana cada 10 km.',
                f'Las ventanas con al menos un {WATER_DOMINATED:.0%} de agua permanente (lagos y lagunas) no se '
                'clasifican.',
                'Los análogos conocidos lo son por la literatura (mineralogía y procesos hidrotermales); el motor '
                'solo indica si su relieve también se parece a la referencia.',
                'Distancia menor = más parecido. El puesto mundial compara con todas las ventanas terrestres '
                'clasificables del atlas, no solo con Nicaragua.',
            ],
        },
        'boundary': json.loads(BOUNDARY_PATH.read_text(encoding='utf-8')),
        'volcanoes': volcanoes,
        'known_sites': {'sources': sites['sources'], 'sites': known},
        'references': references,
        'windows': {'columns': columns, 'rows': rows},
        'rankings': rankings,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='command', required=True)
    b = sub.add_parser('boundary', help='contorno de Nicaragua desde Natural Earth')
    b.add_argument('--shp', type=Path, required=True)
    b.add_argument('--tolerance', type=float, default=0.005)
    v = sub.add_parser('volcanoes', help='volcanes holocenos del GVP')
    v.add_argument('--gvp', type=Path, required=True, help='GeoJSON del servicio WFS del GVP filtrado a Nicaragua')
    d = sub.add_parser('densify', help='ventanas densas alrededor de los volcanes (lee DEM por HTTP)')
    d.add_argument('--radius-km', type=float, default=DEFAULT_RADIUS_KM)
    d.add_argument('--stride-m', type=int, default=DEFAULT_STRIDE_M)
    c = sub.add_parser('compute', help='rankings precalculados con el motor')
    c.add_argument('--radius-km', type=float, default=DEFAULT_RADIUS_KM)
    c.add_argument('--out', type=Path, default=OUT_PATH)
    args = ap.parse_args()

    if args.command == 'boundary':
        DATA.mkdir(parents=True, exist_ok=True)
        BOUNDARY_PATH.write_text(json.dumps(prepare_boundary(args.shp, args.tolerance), ensure_ascii=False) + '\n',
                                 encoding='utf-8')
        print(f'Escrito {BOUNDARY_PATH.relative_to(ROOT)}')
    elif args.command == 'volcanoes':
        DATA.mkdir(parents=True, exist_ok=True)
        data = prepare_volcanoes(args.gvp)
        VOLCANOES_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print(f"Escrito {VOLCANOES_PATH.relative_to(ROOT)} ({len(data['volcanoes'])} volcanes)")
    elif args.command == 'densify':
        densify(args.radius_km, args.stride_m, log=lambda m: print(m, file=sys.stderr, flush=True))
        print(f'Escrito {DENSE_PATH.relative_to(ROOT)}')
    else:
        result = compute(args.radius_km, log=lambda m: print(m, file=sys.stderr, flush=True))
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(result, ensure_ascii=False, separators=(',', ':'), allow_nan=False) + '\n',
                            encoding='utf-8')
        print(f'Escrito {args.out.relative_to(ROOT)} ({args.out.stat().st_size / 1e3:.0f} kB)')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
