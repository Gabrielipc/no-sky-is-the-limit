"""Phase D: bridge views fitted on the weighted background sample, coverage warnings and recall."""
from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

import numpy as np

from pipelines import etl_sampling as sampling
from pipelines import selection_recall as recall
from pipelines import similarity_ml as sim
from tests.test_etl_selection_bias import NOW, make_store
from tests.test_similarity_ml import make_spec


def radar_row(region_id: str, cpr: float) -> dict:
    return {'region_id': region_id, 'instrument': 'RCM', 'product_id': 'p', 'observation_period': None,
            'scenes_found': 1, 'n_scenes': 1, 'rcm_cpr_p50': cpr, 'rcm_cpr_p90': cpr * 1.2, 'rcm_s1_p50_db': -12.0,
            'rcm_dop_p50': 0.5, 'rcm_local_incidence_p50_deg': 35.0, 'rcm_valid_fraction': 1.0,
            'radar_status': 'measured', 'source_manifest_id': 'm', 'updated_at': NOW}


class BridgeRowsTest(unittest.TestCase):
    def test_resampling_follows_inverse_probability(self) -> None:
        ids = np.array(['a', 'b', 'c'], dtype=object)
        idx, info = sim.bridge_rows(ids, {'a': 0.5, 'b': 0.05}, {'mode': 'background_weighted',
                                                                 'min_background_rows': 2}, 100000, 0)
        self.assertEqual(info['mode'], 'background_weighted')
        self.assertNotIn(2, set(idx.tolist()))  # 'c' is not in the background sample
        share_b = np.mean(idx == 1)
        self.assertAlmostEqual(share_b, 10 / 11, delta=0.02)  # weights 2 vs 20

    def test_too_few_background_rows_fall_back_and_flag_bias(self) -> None:
        ids = np.array(['a', 'b', 'c'], dtype=object)
        idx, info = sim.bridge_rows(ids, {'a': 0.5}, {'mode': 'background_weighted', 'min_background_rows': 2},
                                    10, 0)
        self.assertEqual(info['mode'], 'biased_enriched_only')
        self.assertEqual(sorted(idx.tolist()), [0, 1, 2])


class EngineSelectionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name) / 'store'
        cls.store = make_store(cls.root)
        rng = np.random.default_rng(1)
        frame = sampling.load_frame(cls.store)
        items = sampling.stratified_sample(frame, 120, seed=4)
        bg_ids = {it['region_id'] for it in items}
        radar = [radar_row(rid, float(rng.uniform(0.1, 1.5))) for rid in sorted(bg_ids)]
        # Topographic candidates with extreme CPR: must not shape the Earth transform.
        others = [r for r in frame.region_id if r not in bg_ids][:40]
        radar += [radar_row(rid, 5.0) for rid in others]
        cls.store.append_enrichment('radar', radar)
        cls.store.append_enrichment('selection', sampling.selection_rows(items, 'bg', 'background', NOW, seed=4)
                                    + sampling.selection_rows([{'region_id': r} for r in others], 'cand',
                                                              'candidate', NOW))
        cls.spec = make_spec()
        cls.spec['fit']['bridge_population']['min_background_rows'] = 50
        cls.model = sim.fit_model(cls.root, cls.spec, sample_size=5000, memory_limit='512MB', threads=2)
        cls.engine = sim.SimilarityEngine(cls.model, cls.spec)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def test_bridge_view_fitted_on_background_only(self) -> None:
        radar = self.model['views']['radar']
        self.assertEqual(radar['fit_population']['mode'], 'background_weighted')
        self.assertEqual(radar['fit_population']['n_measured'], len(self.store_radar_ids()))
        qn = self.model['features']['cpr_p50']['transform']
        self.assertLess(float(qn.percentile([1.6])[0]), 1.0 + 1e-9)
        self.assertTrue(qn.outside(5.0))  # the candidates' CPR lies outside the fitted Earth range

    def store_radar_ids(self) -> list[str]:
        with self.store._connect() as conn:
            return [r[0] for r in conn.execute("SELECT region_id FROM enrichment_radar_latest").fetchall()]

    def test_environment_view_is_fitted_from_global_layer(self) -> None:
        self.assertTrue(self.model['views']['entorno_superficial']['fitted'])
        res = self.engine.search(self.root, 'w0010', weights={v: 0.0 for v in sim.view_ids(self.spec)} |
                                 {'entorno_superficial': 1.0}, only_eligible=False, limit=5,
                                 memory_limit='512MB', threads=2)
        ids = [r['region_id'] for r in res['results']]
        self.assertTrue(all(abs(int(r[1:]) - 10) <= 6 for r in ids if r.startswith('w')), ids)
        self.assertGreater(res['views']['entorno_superficial']['coverage_fraction'], 0.99)  # Mojave row has no layer

    def test_mars_reference_has_no_environment_view(self) -> None:
        res = self.engine.search(self.root, 'jezero', weights={'entorno_superficial': 1.0}, limit=3,
                                 only_eligible=False, memory_limit='512MB', threads=2)
        self.assertEqual(res['views']['entorno_superficial']['status'], 'reference_missing')

    def test_coverage_warning_for_sparse_heavy_view(self) -> None:
        report = {'radar': {'coverage_fraction': 0.004, 'candidates_with_view': 4},
                  'termica': {'coverage_fraction': 0.5, 'fit_population': {'mode': 'biased_enriched_only'}}}
        warnings = sim.coverage_warnings(report, {'radar': 0.6, 'termica': 0.1},
                                         self.spec['search']['coverage_warning'])
        self.assertEqual(len(warnings), 2)
        self.assertIn('no es global', warnings[0])
        self.assertIn('sesgo de selección', warnings[1])

    def test_recall_of_environment_shortlist(self) -> None:
        weights = {v: 0.0 for v in sim.view_ids(self.spec)} | {'entorno_superficial': 1.0}
        dry = recall.estimate_recall(self.engine, self.store, self.root, 'w0000', counts={'entorno': 60},
                                     weights=weights, profile='arid_mars_surface_v2', top_fraction=0.1,
                                     memory_limit='512MB', threads=2)
        self.assertEqual(dry['status'], 'estimated')
        self.assertGreater(dry['recall'], 0.5)
        humid = recall.estimate_recall(self.engine, self.store, self.root, 'w0299', counts={'entorno': 60},
                                       weights=weights, profile='arid_mars_surface_v2', top_fraction=0.1,
                                       memory_limit='512MB', threads=2)
        self.assertLess(humid['recall'], dry['recall'])  # an arid shortlist misses humid analogues
        self.assertTrue(humid['unproposed_examples'])


if __name__ == '__main__':
    unittest.main()
