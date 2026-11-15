"""The backend/frontend contracts stay in sync with the code and the engine output matches its schema."""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

import pyarrow.parquet as pq

from pipelines import etl_publish as publish
from pipelines import similarity_ml as sim
from scripts import exportar_contratos as exporter
from tests.test_selection_engine import EngineSelectionTest

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads((ROOT / 'specs/api/motor-busqueda-v1.schema.json').read_text(encoding='utf-8'))
TYPES = {'object': dict, 'array': list, 'string': str, 'boolean': bool, 'null': type(None)}


def validate(value, schema: dict, path: str = '$', root: dict = SCHEMA) -> list[str]:
    """Small JSON Schema subset (type, required, properties, additionalProperties, items, enum, const,
    minimum/maximum, minItems/maxItems, oneOf, local $ref, propertyNames.enum)."""
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
        for key, item in value.items():
            if 'propertyNames' in schema and 'enum' in schema['propertyNames'] and key not in schema['propertyNames']['enum']:
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


class ContractFilesTest(unittest.TestCase):
    def test_data_contracts_match_the_code(self) -> None:
        for name, doc in exporter.build_contracts().items():
            committed = (ROOT / 'specs/api' / name).read_text(encoding='utf-8')
            self.assertEqual(committed, exporter.render(doc),
                             f'{name} desactualizado: ejecuta scripts/exportar_contratos.py')

    def test_every_release_column_is_documented(self) -> None:
        release = exporter.build_contracts()['release-atlas30-v1.json']
        self.assertEqual([c['name'] for c in release['windows_columns'] if not c['description']], [])
        names = [c['name'] for c in release['windows_columns']]
        for legacy in ('region_id', 'relief_m', 'slope_p50_deg', 'bare_fraction', 'eligibility'):
            self.assertIn(legacy, names)  # columns the API already reads
        self.assertIn('precip_annual_mm_cmg', names)

    def test_validator_rejects_broken_responses(self) -> None:
        errors = validate({'engine_id': 'otro', 'results': [{'rank': 0}]}, SCHEMA['$defs']['SearchResponse'])
        self.assertTrue(any('falta reference' in e for e in errors))
        self.assertTrue(any('otro' in e for e in errors))
        self.assertTrue(any('results[0]' in e for e in errors))

    def test_engine_views_in_schema_match_the_spec(self) -> None:
        self.assertEqual(set(SCHEMA['$defs']['ViewId']['enum']), set(sim.view_ids(sim.load_spec())))


class EngineOutputTest(EngineSelectionTest):
    """Reuses the store of the selection tests (global layer, radar bridge, background sample)."""

    def test_search_output_validates(self) -> None:
        for ref, kw in (('jezero', {}), ('w0010', {'weights': {'entorno_superficial': 1.0}, 'only_eligible': False}),
                        ('jezero', {'weights': {'radar': 1.0}, 'fusion': 'rrf', 'missing_policy': 'require'})):
            res = self.engine.search(self.root, ref, limit=5, memory_limit='512MB', threads=2, **kw)
            data = json.loads(json.dumps(res, default=float))
            self.assertEqual(validate(data, SCHEMA['$defs']['SearchResponse']), [], (ref, kw))

    def test_release_carries_contract_columns_and_similarity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            model, _ = sim.save_model(self.model, Path(tmp) / 'model.joblib')
            self.store._write_manifests([{
                'source_manifest_id': 'm', 'product_id': 'copernicus-glo30', 'asset_id': 'dem.tif',
                'access_mode': 'cache', 'sha256_or_etag': 'x', 'native_resolution_m': 30.0,
                'effective_resolution_m': 30.0, 'observation_period': 'static',
                'created_at': __import__('datetime').datetime(2026, 11, 14)}])
            manifest = publish.publish_release(self.store, 'contract-r1', root=Path(tmp) / 'releases',
                                               similarity_model=model, similarity_limit=5)
            release = Path(tmp) / 'releases' / 'contract-r1'
            columns = pq.read_schema(release / 'windows' / 'windows.parquet').names
            expected = [c['name'] for c in exporter.build_contracts()['release-atlas30-v1.json']['windows_columns']]
            self.assertEqual(columns, expected)
            self.assertEqual(manifest['release_contract'], 'atlas30-release-v1')
            jezero = manifest['similarity']['references']['jezero']
            self.assertEqual(jezero['status'], 'published')
            data = json.loads((release / jezero['file']).read_text())
            self.assertEqual(validate(data, SCHEMA['$defs']['SearchResponse']), [])
            self.assertEqual(manifest['similarity']['references']['haworth-fondo']['status'], 'failed')


if __name__ == '__main__':
    unittest.main()
