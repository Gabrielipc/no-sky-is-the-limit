"""The backend/frontend contracts stay in sync with the code and the engine output matches its schema."""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

import pyarrow.parquet as pq

from pipelines import contract_check as check
from pipelines import etl_publish as publish
from pipelines import similarity_ml as sim
from scripts import exportar_contratos as exporter
from tests.test_selection_engine import EngineSelectionTest

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads((ROOT / 'specs/api/motor-busqueda-v1.schema.json').read_text(encoding='utf-8'))


def validate(value, schema: dict, path: str = '$', root: dict = SCHEMA) -> list[str]:
    return check.validate(value, schema, path, root)


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
            self.assertTrue((release / 'similarity' / 'model.joblib').is_file())
            self.assertTrue(sim.SimilarityEngine.load(release / 'similarity' / 'model.joblib'))

            report = check.verify_release(release)
            self.assertEqual(report['errors'], [], report)
            self.assertEqual(report['summary']['similarity']['jezero']['results'], 5)
            self.assertTrue(any('haworth-fondo' in w for w in report['warnings']))
            # A broken similarity file is caught.
            broken = json.loads((release / jezero['file']).read_text())
            broken['results'][0]['region_id'] = 'no-existe'
            del broken['warnings']
            (release / jezero['file']).write_text(json.dumps(broken))
            errors = check.verify_release(release)['errors']
            self.assertTrue(any('falta warnings' in e for e in errors))
            self.assertTrue(any('no están en windows.parquet' in e for e in errors))


if __name__ == '__main__':
    unittest.main()
