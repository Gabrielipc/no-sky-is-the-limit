"""Frozen sampling frame and comparable EMIT/CRISM observations for the Jezero pilot."""
from __future__ import annotations

from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit

import numpy as np
from shapely import points
from shapely.geometry import box, shape
from shapely.strtree import STRtree

from pipelines import etl_sampling, similarity_ml as sim, spectral_bridge as bridge
from pipelines import spectral_params, spectral_readers
from pipelines.etl_store import eligibility_expression

SPECTRAL_SIDE = 1800
TOPOGRAPHIC_SIDE = 3000
MOJAVE = {'id': 'mojave', 'bbox': [-117.5, 34.5, -115.5, 36.0]}
INDICATORS = {'BD530_2': 0.05, 'BD2210_2': 0.005, 'BD2290': 0.005}
PROFILES = ('arid_mars_surface_v2', 'paleolake_margin_v1')
PROXY_COLUMNS = ('emis_quartz_index_cmg', 'emis_mafic_index_cmg', 'emis_carbonate_index_cmg',
                 'precip_annual_mm_cmg')
# Outward buffer at EMIT latitudes for a 3 km square including its corner radius.
SPATIAL_BUFFER_DEG = 0.04


def design_sample(rows: list[dict], n: int, seed: int) -> dict[str, dict]:
    """Proportional allocation by geographic block, aridity and relief tercile."""
    if not rows:
        return {}
    relief = np.array([r['relief_p95_p05_m'] for r in rows], dtype=float)
    edges = np.quantile(relief[np.isfinite(relief)], [1 / 3, 2 / 3])
    labels = []
    for row, value in zip(rows, relief):
        precip = row['precip_annual_mm_cmg']
        aridity = next((name for upper, name in etl_sampling.ARIDITY_CLASSES
                        if precip is not None and precip < upper), 'unknown')
        labels.append(f"{row['block']}|{aridity}|r{1 + np.searchsorted(edges, value)}")
    sizes = dict(sorted(Counter(labels).items()))
    if n < len(sizes):
        raise ValueError(f'El diseño requiere al menos {len(sizes)} ventanas para cubrir sus estratos')
    counts = etl_sampling.allocate(sizes, min(n, len(rows)), min_per_stratum=0)
    for key in counts:
        if counts[key] == 0:
            donor = max(counts, key=counts.get)
            counts[donor] -= 1
            counts[key] = 1
    rng = np.random.default_rng(seed)
    groups = np.asarray(labels)
    selected = {}
    for label, count in counts.items():
        indexes = np.flatnonzero(groups == label)
        for i in rng.choice(indexes, size=count, replace=False):
            selected[rows[i]['region_id']] = {
                'stratum': label, 'inclusion_probability': count / sizes[label],
            }
    return selected


def earth_frame(store: Path, scenes: list[dict], extra_holdouts: list[dict], profile: str) -> list[dict]:
    """Intersect windows with EMIT footprints and keep entire holdout scenes out of fit."""
    if profile not in PROFILES or len(extra_holdouts) != 2:
        raise ValueError('Se requieren dos bloques adicionales a Mojave y un perfil de Jezero válido')
    blocks = [MOJAVE, *extra_holdouts]
    if len({b['id'] for b in blocks}) != 3:
        raise ValueError('Identificadores de bloques repetidos')
    boxes = [box(*b['bbox']) for b in blocks]
    buffered = [b.buffer(SPATIAL_BUFFER_DEG) for b in boxes]
    for i, boundary in enumerate(buffered):
        if any(boundary.intersects(other) for other in buffered[:i]):
            raise ValueError('Los bloques reservados deben ser geográficamente independientes')

    scenes = sorted(scenes, key=lambda scene: scene['id'])
    if len({s['id'] for s in scenes}) != len(scenes):
        raise ValueError('Identificadores EMIT repetidos')
    geometries = [shape(s['geometry']) for s in scenes]
    if any(g.is_empty or not g.is_valid or g.geom_type not in ('Polygon', 'MultiPolygon') for g in geometries):
        raise ValueError('Huella EMIT inválida')
    touched = [[i for i, b in enumerate(buffered) if g.intersects(b)] for g in geometries]
    if any(len(hits) > 1 for hits in touched):
        raise ValueError('Una escena EMIT cruza varios bloques reservados')
    tree = STRtree(geometries)
    eligible = eligibility_expression(profile)
    query = f"""SELECT region_id, longitude, latitude, relief_p95_p05_m, {', '.join(PROXY_COLUMNS)},
                       ({eligible}) AS eligibility
                FROM features_unified WHERE body = 'Earth' AND qa_status = 'rankable'
                AND isfinite(relief_p95_p05_m) ORDER BY region_id"""
    frame = []
    from pipelines.etl_eligibility import get_profile
    expected = get_profile(profile).eligible_status
    with sim.connect(store) as conn:
        cursor = conn.execute(query)
        columns = [col[0] for col in cursor.description]
        while batch := cursor.fetchmany(20000):
            coords = points([r[1] for r in batch], [r[2] for r in batch])
            hits = {}
            for row_index, scene_index in tree.query(coords, predicate='intersects').T:
                hits.setdefault(row_index, []).append(scene_index)
            for row_index, indexes in hits.items():
                row = dict(zip(columns, batch[row_index]))
                if row['eligibility'] != expected:
                    continue
                point = coords[row_index]
                test_block = next((i for i, b in enumerate(boxes) if b.covers(point)), None)
                if test_block is None:
                    if any(touched[i] for i in indexes) or any(b.covers(point) for b in buffered):
                        continue
                    block = f"{int(np.floor(row['longitude'] / 20))}:{int(np.floor(row['latitude'] / 10))}"
                    partition = 'fit'
                else:
                    indexes = [i for i in indexes if touched[i] == [test_block]]
                    block, partition = blocks[test_block]['id'], 'test'
                if indexes:
                    frame.append(row | {'scene_ids': [scenes[i]['id'] for i in sorted(indexes)],
                                        'block': block, 'partition': partition,
                                        'body': 'Earth', 'role': 'background'})
    if {r['block'] for r in frame if r['partition'] == 'test'} != {b['id'] for b in blocks}:
        raise ValueError('Cada bloque reservado, incluido Mojave, requiere ventanas elegibles con huella EMIT')
    return sorted(frame, key=lambda row: row['region_id'])


def indicator_records(sample: bridge.FootprintSample) -> dict:
    cube = spectral_params.Cube(sample.reflectance, sample.wavelengths, sample.kernel_mode)
    records = {}
    for name, floor in INDICATORS.items():
        record = bridge.summarize_indicator(cube, sample, name, floor)
        # Validity is required per indicator, not just on the reflectance cube as a whole.
        fraction = record['n_valid'] / sample.footprint_cells if sample.footprint_cells else 0.0
        if record['status'] in bridge.MEASURED_STATUSES and fraction < bridge.MIN_VALID_FRACTION:
            record.update(status='insufficient_coverage', p50=None, p95=None, active_fraction=None)
        records[name] = record | {'valid_fraction': fraction}
    return records


def measure(row: dict, scene: dict, input_root: Path, token: str | None) -> dict:
    lon, lat = row['longitude'], row['latitude']
    if row['body'] == 'Earth':
        for key in ('reflectance_url', 'mask_url'):
            url = urlsplit(scene[key])
            if url.scheme != 'https' or url.netloc != 'data.lpdaac.earthdatacloud.nasa.gov':
                raise ValueError('Las credenciales Earthdata se reservan para el archivo HTTPS de LP DAAC')
        sample = spectral_readers.emit_footprint(
            scene['reflectance_url'], scene['mask_url'], lon, lat, SPECTRAL_SIDE, token, scene['id'])
    else:
        source = spectral_readers.EnviBsqRemote(scene['reflectance_url'], input_root / scene['header'])
        sample = spectral_readers.crism_footprint(
            source, input_root / scene['mask'], lon, lat, SPECTRAL_SIDE, list(INDICATORS),
            input_root / 'if_cache', scene['id'])
    return {
        **{k: row[k] for k in ('region_id', 'body', 'block', 'partition', 'role', 'longitude', 'latitude')},
        'geologic_unit': row.get('geologic_unit'),
        'inclusion_probability': row.get('inclusion_probability'),
        'scene_id': scene['id'], 'spectral_side_m': SPECTRAL_SIDE,
        'topographic_side_m': TOPOGRAPHIC_SIDE, 'sample': bridge.sample_record(sample),
        'indicators': indicator_records(sample),
    }
