"""Offline tests of phases B (background samples) and C (per-view shortlists)."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import numpy as np

from pipelines import etl_retrieval as retrieval
from pipelines import etl_sampling as sampling
from pipelines import etl_surface_fetch as fetch
from pipelines.etl_global_schema import GLOBAL_LAYERS
from pipelines.etl_store import FeatureStore
from tests.test_similarity_ml import base_row, random_topo

NOW = datetime(2026, 11, 14, tzinfo=timezone.utc)


def global_row(region_id: str, **values) -> dict:
    row = {'region_id': region_id, 'global_layers_version': 'global-layers-v1', 'source_manifest_id': 'g',
           'updated_at': NOW}
    for layer, cfg in GLOBAL_LAYERS.items():
        for col in cfg['columns']:
            row[col] = values.get(col)
        measured = any(values.get(col) is not None for col in cfg['columns'])
        row[f'{layer}_cmg_status'] = 'measured' if measured else 'on_demand_fetchable'
    return row


def make_store(root: Path, n: int = 300) -> FeatureStore:
    store = FeatureStore(root, memory_limit='512MB', threads=2)
    rng = np.random.default_rng(3)
    rows, grows = [], []
    for i in range(n):
        lat = -60 + 120 * i / n
        lon = -170 + 340 * ((i * 37) % n) / n
        rows.append(base_row(f'w{i:04d}', lon, lat, random_topo(rng)))
        grows.append(global_row(f'w{i:04d}', precip_annual_mm_cmg=float(10 + 6 * i), dry_months_fraction_cmg=
                                float(max(0.0, 1 - i / n)), snow_cover_mean_pct_cmg=0.0,
                                soil_moisture_mean_cmg=float(0.02 + 0.3 * i / n),
                                ati_cmg_per_k=float(0.01 + 0.04 * i / n),
                                emis_mean_b10_b14_cmg=0.95, emis_quartz_index_cmg=1.0,
                                emis_mafic_index_cmg=1.0, emis_carbonate_index_cmg=1.0))
    rows.append(base_row('mojave_holdout', -116.5, 35.0, random_topo(rng)))
    store.write_base_batch('b', rows)
    store.append_enrichment('global', grows)
    return store


class SamplingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.store = make_store(Path(self.tmp.name) / 'store')
        self.frame = sampling.load_frame(self.store)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_frame_excludes_holdout(self) -> None:
        self.assertEqual(len(self.frame), 300)
        self.assertNotIn('mojave_holdout', set(self.frame.region_id))

    def test_strata_use_global_layer(self) -> None:
        labels = sampling.strata(self.frame)
        self.assertTrue(all(l.count('|') == 2 for l in labels))
        self.assertIn('arid', {l.split('|')[1] for l in labels})
        self.assertIn('humid', {l.split('|')[1] for l in labels})

    def test_allocate_floor_and_total(self) -> None:
        alloc = sampling.allocate({'a': 1000, 'b': 10, 'c': 1}, 50, min_per_stratum=1)
        self.assertEqual(alloc['c'], 1)
        self.assertGreaterEqual(alloc['b'], 1)
        # The floor per stratum may exceed n by at most the number of floored strata.
        self.assertGreaterEqual(sum(alloc.values()), 50)
        self.assertLessEqual(sum(alloc.values()), 52)
        self.assertEqual(sum(sampling.allocate({'a': 600, 'b': 400}, 50).values()), 50)

    def test_stratified_sample_is_reproducible_and_weights_recover_population(self) -> None:
        a = sampling.stratified_sample(self.frame, 60, seed=1)
        b = sampling.stratified_sample(self.frame, 60, seed=1)
        self.assertEqual([x['region_id'] for x in a], [x['region_id'] for x in b])
        self.assertEqual(len({x['region_id'] for x in a}), len(a))
        self.assertAlmostEqual(sum(1 / x['inclusion_probability'] for x in a), len(self.frame), delta=1e-6)

    def test_cluster_sample_probabilities(self) -> None:
        items = sampling.cluster_sample(self.frame, 3, 2, seed=5)
        tiles = {x['stratum'] for x in items}
        self.assertEqual(len(tiles), 3)
        self.assertTrue(all(0 < x['inclusion_probability'] <= 1 for x in items))
        self.assertTrue(all(len([y for y in items if y['stratum'] == t]) <= 2 for t in tiles))

    def test_selection_rows_round_trip_and_background_weights(self) -> None:
        items = sampling.stratified_sample(self.frame, 20, seed=2)
        rows = sampling.selection_rows(items, 'd1', 'background', NOW, seed=2)
        rows += sampling.selection_rows([{'region_id': items[0]['region_id']}], 'cand', 'candidate', NOW)
        self.store.append_enrichment('selection', rows)
        weights = sampling.background_weights(self.store)
        self.assertEqual(len(weights), len(items))
        with self.store._connect() as conn:
            n = conn.execute('SELECT count(*) FROM enrichment_selection_latest').fetchone()[0]
        self.assertEqual(n, len(items) + 1)  # one row per (window, design)


class RetrievalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        cls.store = make_store(Path(cls.tmp.name) / 'store')
        cls.spec = retrieval.load_spec()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def test_percentile_ranks_ties_take_mid_rank(self) -> None:
        p = retrieval.percentile_ranks(np.array([0.0, 0.0, 1.0, 2.0, np.nan]))
        self.assertAlmostEqual(p[0], 0.25)
        self.assertAlmostEqual(p[3], 0.875)
        self.assertTrue(np.isnan(p[4]))

    def test_allocate_by_weights_follows_engine_views(self) -> None:
        alloc = retrieval.allocate_by_weights(20, {'escabrosidad': 0.0, 'termica': 0.5, 'entorno_superficial': 0.5})
        self.assertEqual(alloc, {'termica': 10, 'entorno': 10})
        self.assertNotIn('topografica', alloc)  # topography at 0 proposes nothing

    def test_entorno_prefers_dry_windows_without_topography(self) -> None:
        out = retrieval.shortlists(self.store, {'entorno': 5}, profile='arid_mars_surface_v2', log=lambda m: None)
        ids = [x['region_id'] for x in out['entorno']]
        self.assertEqual(len(ids), 5)
        self.assertTrue(all(int(r[1:]) < 40 for r in ids), ids)  # lowest precipitation / soil moisture

    def test_thermal_needs_a_target(self) -> None:
        out = retrieval.shortlists(self.store, {'termica': 4}, log=lambda m: None)
        self.assertNotIn('termica', out)
        out = retrieval.shortlists(self.store, {'termica': 4}, targets=['termica:ati_cmg_per_k=1.0'],
                                   log=lambda m: None)
        self.assertTrue(all(int(x['region_id'][1:]) >= 290 for x in out['termica']))

    def test_reference_percentile_sets_thermal_target(self) -> None:
        ref = Path(self.tmp.name) / 'ref.json'
        ref.write_text('{"id": "r", "body": "Mars", "features": {}, "percentiles": {"thermal_inertia_rank": 0.0}}')
        out = retrieval.shortlists(self.store, {'termica': 3}, ref_json=str(ref), log=lambda m: None)
        self.assertTrue(all(int(x['region_id'][1:]) < 10 for x in out['termica']))

    def test_spectral_exploration_with_coverage_check(self) -> None:
        calls = []

        def covers(product, lon, lat):
            calls.append(product)
            return lat > 0

        out = retrieval.shortlists(self.store, {'espectral': 4}, check_coverage=True, coverage_fn=covers,
                                   log=lambda m: None)
        self.assertTrue(calls and set(calls) == {'EMITL2ARFL'})
        self.assertTrue(all(x['latitude'] > 0 and x['method'] == 'exploration' for x in out['espectral']))
        self.assertLessEqual(len(out['espectral']), 4)

    def test_retriever_ranks_cover_every_window(self) -> None:
        frame = retrieval.load_proxy_frame(self.store, 'arid_mars_surface_v2', self.spec)
        ranks = retrieval.retriever_ranks(frame, 'entorno', self.spec['profiles']['arid_mars_surface_v2']['entorno'],
                                          self.spec)
        finite = np.sort(ranks[np.isfinite(ranks)])
        self.assertEqual(finite[0], 1)
        self.assertEqual(len(np.unique(finite)), len(finite))


class SurfaceJobsTest(unittest.TestCase):
    def test_jobs_write_selection_and_skip_duplicate_fetches(self) -> None:
        from scripts import etl_superficie as cli
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'store'
            store = make_store(root)
            fetched: list[tuple[tuple[str, ...], tuple[str, ...]]] = []

            def fake_run(batch, dims, args):
                fetched.append((tuple(s.region_id for s in batch), tuple(dims)))
                return []

            cands = [fetch.Site('w0001', -170.0, -59.6), fetch.Site('w0002', -168.0, -59.2)]
            with mock.patch.object(cli, 'run_fetchers', fake_run), \
                    mock.patch.object(cli, 'store_candidates', lambda *a: cands):
                cli.main(['--store-dir', str(root), '--memory-limit', '512MB', '--threads', '2', '--evidence', '',
                          '--dimension', 'aridity', '--dimension', 'apparent_thermal_inertia',
                          '--background-sample', '12', '--background-cluster-tiles', '2',
                          '--background-per-tile', '2', '--retriever', 'entorno=3'])
            reasons = [f[1] for f in fetched]
            self.assertIn(('aridity', 'apparent_thermal_inertia'), reasons)
            self.assertIn(('aridity',), reasons)                    # stratified background skips the fine ATI
            self.assertIn(('apparent_thermal_inertia',), reasons)   # cluster design measures only the fine ATI
            with store._connect() as conn:
                by_reason = dict(conn.execute('SELECT selection_reason, count(*) FROM enrichment_selection_latest '
                                              'GROUP BY 1').fetchall())
                probs = conn.execute("SELECT min(inclusion_probability) FROM enrichment_selection_latest "
                                     "WHERE selection_reason = 'background'").fetchone()[0]
            self.assertEqual(by_reason['candidate'], 2)
            self.assertEqual(by_reason['retrieval'], 3)
            self.assertGreaterEqual(by_reason['background'], 12)
            self.assertGreaterEqual(by_reason['background_cluster'], 2)
            self.assertGreater(probs, 0)


if __name__ == '__main__':
    unittest.main()
