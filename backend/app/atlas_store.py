"""Read-only Parquet releases and reproducible 30 m queries."""
import json
import math
import re
from contextlib import contextmanager
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[2] / 'releases/atlas30'
TOKEN = re.compile(r'[a-zA-Z0-9][a-zA-Z0-9_-]{0,95}')
DEFAULT_WEIGHTS = (50, 30, 20)
DISTANCES = ('slope_distance_deg', 'relief_difference_m', 'roughness_difference_m')
DISTANCE_SQL = """
    list_sum(list_transform(list_zip(slope_cdf, ?), lambda x: abs(x[1] - x[2]))) AS slope_distance_deg,
    abs(relief_m - ?) AS relief_difference_m,
    abs(roughness_m - ?) AS roughness_difference_m
"""


def load_release(root, version=None):
    version = version or (root / 'current').read_text().strip()
    if not TOKEN.fullmatch(version):
        raise ValueError('Versión de atlas inválida')
    release = root / version
    manifest = json.loads((release / 'manifest.json').read_text())
    if manifest['version'] != version or manifest['cell_m'] != 30:
        raise ValueError('Manifiesto incompatible con el Atlas de 30 m')
    return release, manifest


@contextmanager
def connect(release):
    with duckdb.connect(config={'threads': 2, 'memory_limit': '1GB'}) as db:
        path = str(release / 'windows' / '*.parquet').replace("'", "''")
        db.execute(f"CREATE VIEW windows AS SELECT * FROM read_parquet('{path}')")
        yield db


def rows(cursor):
    keys = [column[0] for column in cursor.description]
    return [dict(zip(keys, row)) for row in cursor.fetchall()]


def reference_params(profile):
    histogram = profile['slope_histogram']
    total = sum(histogram)
    cdf = []
    cumulative = 0
    for count in histogram:
        cumulative += count
        cdf.append(cumulative / total)
    return cdf, profile['relief_m'], profile['roughness_m']


def normalization(release, profile):
    quantiles = ', '.join(f'quantile_cont({metric}, .75)' for metric in DISTANCES)
    with connect(release) as db:
        raw = db.execute(f"""
            SELECT {quantiles} FROM (
              SELECT {DISTANCE_SQL} FROM windows WHERE status = 'rankable'
            )
        """, reference_params(profile)).fetchone()
    return dict(zip(DISTANCES, (max(value or 0, floor) for value, floor in zip(raw, (.25, 5., .1)))))


def search(release, manifest, weights=DEFAULT_WEIGHTS, bare_min=None, water_max=None, limit=25, offset=0, area=None):
    if len(weights) != 3 or any(not math.isfinite(w) or w < 0 for w in weights) or sum(weights) <= 0:
        raise ValueError('Selecciona al menos un peso positivo')
    where = ["status = 'rankable'"]
    filters = []
    if area is not None:
        where.append('area = ?')
        filters.append(area)
    if bare_min is not None:
        where.append('bare_fraction >= ?')
        filters.append(bare_min)
    if water_max is not None:
        where.append('water_occurrence_pct <= ?')
        filters.append(water_max)
    criteria = ' AND '.join(where)
    normalized = [w / sum(weights) for w in weights]
    score = ' + '.join(f'{metric} * ?' for metric in DISTANCES)
    factors = [w / manifest['normalization'][name] for name, w in zip(DISTANCES, normalized)]
    with connect(release) as db:
        count = db.execute(f'SELECT count(*) FROM windows WHERE {criteria}', filters).fetchone()[0]
        results = rows(db.execute(f"""
            WITH distances AS (
              SELECT region_id, longitude, latitude, area, batch, relief_m, roughness_m, slope_p50_deg,
                     land_fraction, valid_elevation, valid_slope, valid_roughness, asset_ids,
                     bare_fraction, water_occurrence_pct, {DISTANCE_SQL}
              FROM windows WHERE {criteria}
            )
            SELECT *, {score} AS distance
            FROM distances ORDER BY distance, region_id LIMIT ? OFFSET ?
        """, (*reference_params(manifest['profile']), *filters, *factors, limit, offset)))
    return count, results


def coverage(release):
    with connect(release) as db:
        return rows(db.execute("""
            SELECT floor(longitude / 2) * 2 AS west, floor(latitude / 2) * 2 AS south,
                   count(*) AS sampled, count(*) FILTER (WHERE status = 'rankable') AS rankable,
                   count(*) FILTER (WHERE status IN ('dem_unavailable', 'insufficient_dem_support')) AS gaps,
                   count(*) FILTER (WHERE status = 'insufficient_land') AS excluded
            FROM windows GROUP BY 1, 2 ORDER BY 1, 2
        """))


def candidate(release, region_id):
    with connect(release) as db:
        found = rows(db.execute('SELECT * EXCLUDE (slope_cdf) FROM windows WHERE region_id = ?', [region_id]))
    return found[0] if found else None


def context_counts(release):
    with connect(release) as db:
        bare, water = db.execute("""
            SELECT count(bare_fraction), count(water_occurrence_pct)
            FROM windows WHERE status = 'rankable'
        """).fetchone()
    return {'bare': bare, 'water': water}
