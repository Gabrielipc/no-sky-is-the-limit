"""Check that a published Atlas release honours the backend/frontend contracts (docs/contratos/).

- `validate(value, schema)`: dependency-free subset of JSON Schema used for `motor-busqueda-v1`.
- `verify_release(path)`: manifest, `windows.parquet` columns and values, sources and the optional
  similarity files (schema, region ids present in the release, packaged model).
"""
from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
MOTOR_SCHEMA_PATH = ROOT / 'specs/api/motor-busqueda-v1.schema.json'
RELEASE_CONTRACT_PATH = ROOT / 'specs/api/release-atlas30-v1.json'
TYPES = {'object': dict, 'array': list, 'string': str, 'boolean': bool, 'null': type(None)}


def load_motor_schema() -> dict:
    return json.loads(MOTOR_SCHEMA_PATH.read_text(encoding='utf-8'))


def validate(value, schema: dict, path: str = '$', root: dict | None = None) -> list[str]:
    """Errors of `value` against a JSON Schema subset (type, required, properties, additionalProperties,
    items, enum, const, minimum/maximum, minItems/maxItems, oneOf, local $ref, propertyNames.enum)."""
    root = root if root is not None else schema
    if '$ref' in schema:
        target = root
        for part in schema['$ref'].lstrip('#/').split('/'):
            target = target[part]
        return validate(value, target, path, root)
    if 'oneOf' in schema:
        matches = [validate(value, s, path, root) for s in schema['oneOf']]
        return [] if any(not m for m in matches) else matches[0]
    errors = []
    types = schema.get('type')
    if types:
        types = [types] if isinstance(types, str) else types
        ok = any((t == 'number' and isinstance(value, (int, float)) and not isinstance(value, bool))
                 or (t == 'integer' and isinstance(value, int) and not isinstance(value, bool))
                 or (t in TYPES and isinstance(value, TYPES[t])) for t in types)
        if not ok:
            return [f'{path}: tipo {type(value).__name__} no es {types}']
    if 'const' in schema and value != schema['const']:
        errors.append(f'{path}: {value!r} != {schema["const"]!r}')
    if 'enum' in schema and value not in schema['enum']:
        errors.append(f'{path}: {value!r} fuera de {schema["enum"]}')
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if 'minimum' in schema and value < schema['minimum'] - 1e-9:
            errors.append(f'{path}: {value} < {schema["minimum"]}')
        if 'maximum' in schema and value > schema['maximum'] + 1e-9:
            errors.append(f'{path}: {value} > {schema["maximum"]}')
    if isinstance(value, dict):
        for key in schema.get('required', []):
            if key not in value:
                errors.append(f'{path}: falta {key}')
        props = schema.get('properties', {})
        allowed = schema.get('propertyNames', {}).get('enum')
        for key, item in value.items():
            if allowed is not None and key not in allowed:
                errors.append(f'{path}: clave {key} no permitida')
            if key in props:
                errors += validate(item, props[key], f'{path}.{key}', root)
            elif isinstance(schema.get('additionalProperties'), dict):
                errors += validate(item, schema['additionalProperties'], f'{path}.{key}', root)
            elif schema.get('additionalProperties') is False:
                errors.append(f'{path}: propiedad no declarada {key}')
    if isinstance(value, list):
        if 'minItems' in schema and len(value) < schema['minItems']:
            errors.append(f'{path}: menos de {schema["minItems"]} elementos')
        if 'maxItems' in schema and len(value) > schema['maxItems']:
            errors.append(f'{path}: más de {schema["maxItems"]} elementos')
        if 'items' in schema:
            for i, item in enumerate(value):
                errors += validate(item, schema['items'], f'{path}[{i}]', root)
    return errors


def validate_search_response(data: dict) -> list[str]:
    schema = load_motor_schema()
    return validate(data, schema['$defs']['SearchResponse'], root=schema)


def verify_release(release: Path) -> dict:
    """Report {'errors': [...], 'warnings': [...], 'summary': {...}} for one release directory."""
    release = Path(release)
    errors: list[str] = []
    warnings: list[str] = []
    summary: dict = {'release': str(release)}
    manifest_path = release / 'manifest.json'
    if not manifest_path.is_file():
        return {'errors': [f'falta {manifest_path}'], 'warnings': [], 'summary': summary}
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    contract = json.loads(RELEASE_CONTRACT_PATH.read_text(encoding='utf-8'))
    if manifest.get('release_contract') != contract['contract_id']:
        errors.append(f"release_contract {manifest.get('release_contract')!r} != {contract['contract_id']!r}")
    if manifest.get('version') != release.name:
        errors.append(f"version del manifiesto {manifest.get('version')!r} != carpeta {release.name!r}")
    if manifest.get('cell_m') != 30:
        errors.append('cell_m debe ser 30 (lo exige backend/app/atlas_store.load_release)')

    windows = release / 'windows' / 'windows.parquet'
    if not windows.is_file():
        errors.append('falta windows/windows.parquet')
        return {'errors': errors, 'warnings': warnings, 'summary': summary}
    columns = pq.read_schema(windows).names
    expected = [c['name'] for c in contract['windows_columns']]
    missing = [c for c in expected if c not in columns]
    extra = [c for c in columns if c not in expected]
    if missing:
        errors.append(f'columnas que faltan: {missing}')
    if extra:
        warnings.append(f'columnas fuera del contrato: {extra}')
    path = str(windows).replace("'", "''")
    with duckdb.connect() as conn:
        n, distinct, rankable, eligible, bad_coords, null_status = conn.execute(f"""
            SELECT count(*), count(DISTINCT region_id), count(*) FILTER (WHERE status = 'rankable'),
                   count(*) FILTER (WHERE status = 'rankable' AND eligibility = ?),
                   count(*) FILTER (WHERE longitude NOT BETWEEN -180 AND 180 OR latitude NOT BETWEEN -90 AND 90),
                   count(*) FILTER (WHERE status IS NULL)
            FROM read_parquet('{path}')""", [manifest.get('search_eligibility')]).fetchone()
        cmg = {}
        if 'imerg_cmg_status' in columns:
            for col in [c for c in columns if c.endswith('_cmg_status')]:
                cmg[col] = dict(conn.execute(f"SELECT {col}, count(*) FROM read_parquet('{path}') GROUP BY 1").fetchall())
        ids = {r[0] for r in conn.execute(f"SELECT region_id FROM read_parquet('{path}')").fetchall()}
    summary.update(windows=n, rankable=rankable, eligible=eligible, global_layer_status=cmg)
    if n == 0:
        errors.append('la release no tiene ventanas')
    if distinct != n:
        errors.append(f'region_id repetidos: {n - distinct}')
    if bad_coords:
        errors.append(f'{bad_coords} ventanas con coordenadas fuera de rango')
    if null_status:
        errors.append(f'{null_status} ventanas sin status')
    if eligible == 0:
        warnings.append('ninguna ventana elegible para la búsqueda simple de /api/atlas/search')
    if manifest.get('counts') and sum(manifest['counts'].values()) != n:
        errors.append('manifest.counts no suma el número de ventanas')
    if not (release / 'sources.json').is_file():
        errors.append('falta sources.json')

    sim = manifest.get('similarity')
    if sim:
        for key in ('model_file', 'model_report'):
            if sim.get(key) and not (release / sim[key]).is_file():
                errors.append(f'falta {sim[key]}')
        summary['similarity'] = {}
        for ref, entry in sim.get('references', {}).items():
            if entry.get('status') != 'published':
                warnings.append(f"similitud {ref}: {entry.get('status')} ({entry.get('error', '')})")
                summary['similarity'][ref] = entry.get('status')
                continue
            data = json.loads((release / entry['file']).read_text(encoding='utf-8'))
            problems = validate_search_response(data)
            errors += [f'{entry["file"]}: {p}' for p in problems[:10]]
            unknown = [r.get('region_id') for r in data.get('results', []) if r.get('region_id') not in ids]
            if unknown:
                errors.append(f"{entry['file']}: {len(unknown)} region_id que no están en windows.parquet")
            summary['similarity'][ref] = {'results': len(data.get('results', [])), 'warnings': data.get('warnings'),
                                          'top': [r.get('region_id') for r in data.get('results', [])[:3]]}
    else:
        warnings.append('la release no incluye resultados del motor (publica con --similarity-model)')
    return {'errors': errors, 'warnings': warnings, 'summary': summary}
