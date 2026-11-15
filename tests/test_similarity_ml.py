"""Tests of the unsupervised ML similarity engine (pipelines/similarity_ml.py)."""
from __future__ import annotations

import copy
from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest

import numpy as np

from pipelines import etl_contract as contract
from pipelines import similarity_ml as sim
from pipelines.etl_store import FeatureStore

NOW = datetime(2026, 11, 14, tzinfo=timezone.utc)
SHAPE = ('hypsometric_integral', 'elevation_skew_p95_p05', 'aspect_240m_resultant_length',
         'slope_240m_gt15_fraction', 'slope_240m_gt25_fraction')


def base_row(region_id: str, lon: float, lat: float, topo: dict, *, body: str = 'Earth') -> dict:
    row = {f.name: None for f in contract.BASE_WINDOWS_SCHEMA}
    row.update({
        'region_id': region_id, 'grid_version': 'test', 'body': body,
        'utm_zone_band': 'N01' if body == 'Earth' else 'MOON_SPS', 'batch_id': 'b',
        'longitude': lon, 'latitude': lat, 'window_m': 3000, 'cell_m': 30, 'slope_base_m': 240,
        'roughness_radius_m': 360, 'land_fraction': 1.0, 'topo_valid_fraction': 1.0, 'roughness_coverage': 1.0,
        'qa_status': 'rankable', 'source_manifest_id': 'm', 'updated_at': NOW,
    })
    if body == 'Earth':
        row.update({
            'analog_surface_eligibility': 'eligible_arid_exposed', 'eligibility_profile': 'arid_mars_surface_v2',
            'cover_status': 'measured', 'cover_valid_fraction': 1.0, 'bare_or_sparse_fraction': 0.97,
            'trees_fraction': 0.0, 'built_fraction': 0.0, 'permanent_water_fraction': 0.0,
            'snow_ice_fraction': 0.0, 'moss_lichen_fraction': 0.0, 'water_occurrence_mean_pct': 0.0,
            'water_extent_gt0_fraction': 0.0, 'water_occurrence_ge50_fraction': 0.0,
        })
    else:
        row.update({'analog_surface_eligibility': 'moon_reference_surface',
                    'eligibility_profile': 'moon_reference', 'cover_status': 'not_requested'})
    row.update(topo)
    return row


def random_topo(rng: np.random.Generator, with_shape: bool = True) -> dict:
    rug = rng.lognormal(0.0, 0.8)
    topo = {
        'relief_p95_p05_m': float(np.clip(60 * rug * rng.lognormal(0, 0.15), 1, 3000)),
        'slope_240m_p50_deg': float(np.clip(2 * rug * rng.lognormal(0, 0.15), 0.05, 60)),
        'slope_240m_p90_deg': float(np.clip(6 * rug * rng.lognormal(0, 0.15), 0.1, 80)),
        'roughness_360m_p50_m': float(np.clip(4 * rug * rng.lognormal(0, 0.15), 0.1, 400)),
    }
    if with_shape:
        hi = float(rng.uniform(0.2, 0.8))
        topo.update({
            'hypsometric_integral': hi,
            'elevation_skew_p95_p05': float(np.clip(-1.6 * (hi - 0.5) + rng.normal(0, 0.03), -1, 1)),
            'aspect_240m_resultant_length': float(rng.uniform(0.05, 0.95)),
            'slope_240m_gt15_fraction': float(np.clip(0.02 * rug, 0, 1)),
            'slope_240m_gt25_fraction': float(np.clip(0.005 * rug, 0, 1)),
        })
    return topo


REF = {
    'relief_p95_p05_m': 120.0, 'slope_240m_p50_deg': 3.0, 'slope_240m_p90_deg': 9.0,
    'roughness_360m_p50_m': 7.5, 'hypsometric_integral': 0.61, 'elevation_skew_p95_p05': -0.3,
    'aspect_240m_resultant_length': 0.45, 'slope_240m_gt15_fraction': 0.03, 'slope_240m_gt25_fraction': 0.0,
}


def make_spec() -> dict:
    spec = copy.deepcopy(sim.load_spec())
    spec['fit'].update(min_fit_rows=40, min_body_population=1)
    spec['fit']['covariance'].update(fallback_below_rows=100)
    spec['fit']['gmm'].update(components=[2, 3], max_rows=2000, n_init=1)
    return spec


class TestPatternGrouping(unittest.TestCase):
    def test_matches_np_unique_on_rows(self) -> None:
        rng = np.random.default_rng(3)
        for k in (1, 3, 9):
            avail = rng.random((500, k)) > 0.4
            patterns, inverse = sim._group_patterns(avail)
            self.assertTrue((patterns[inverse] == avail).all())
            ref_patterns, _ = np.unique(avail, axis=0, return_inverse=True)
            self.assertEqual({tuple(r) for r in patterns}, {tuple(r) for r in ref_patterns})

    def test_empty_input(self) -> None:
        patterns, inverse = sim._group_patterns(np.empty((0, 4), dtype=bool))
        self.assertEqual(len(inverse), 0)


class TestPrimitives(unittest.TestCase):
    def test_quantile_normal_is_monotone_and_ties_take_mid_rank(self) -> None:
        values = np.concatenate([np.zeros(500), np.linspace(1, 10, 500)])
        qn = sim.QuantileNormal.fit(values, 1000)
        p = qn.percentile([0.0, 5.0, 10.0, np.nan])
        self.assertAlmostEqual(p[0], 0.25, delta=0.01)  # half the mass sits at 0
        self.assertLess(p[0], p[1])
        self.assertAlmostEqual(p[2], 1.0)
        self.assertTrue(np.isnan(p[3]))
        self.assertTrue(qn.outside(50.0))
        self.assertTrue(np.isfinite(qn.normal(1e9)[0]))  # clipped, not infinite

    def test_collinear_features_do_not_count_twice(self) -> None:
        cov = np.array([[1.0, 0.99], [0.99, 1.0]])
        zc = np.array([[1.0, 1.0]])
        corr, _ = sim.mahalanobis_view(zc, np.zeros(2), cov, 1)
        indep, _ = sim.mahalanobis_view(zc, np.zeros(2), np.eye(2), 1)
        single, _ = sim.mahalanobis_view(np.array([[1.0]]), np.zeros(1), np.eye(1), 1)
        self.assertLess(corr[0], indep[0])
        self.assertLess(corr[0], single[0])  # two redundant agreeing features ~ one feature

    def test_missing_features_use_marginal_covariance(self) -> None:
        cov = np.eye(3)
        zc = np.array([[1.0, np.nan, np.nan], [1.0, 0.0, np.nan], [np.nan, np.nan, np.nan]])
        d, used = sim.mahalanobis_view(zc, np.zeros(3), cov, min_features=2)
        self.assertTrue(np.isnan(d[0]))  # one feature < min_features
        self.assertTrue(np.isfinite(d[1]))
        self.assertTrue(np.isnan(d[2]))
        self.assertEqual(used.tolist(), [1, 2, 0])

    def test_feature_shares_sum_to_one(self) -> None:
        cov = np.array([[1.0, 0.5], [0.5, 2.0]])
        shares = sim.feature_shares(np.array([1.0, -0.5]), cov)
        self.assertAlmostEqual(float(np.nansum(shares)), 1.0)

    def test_calibration_recovers_dominant_view(self) -> None:
        rng = np.random.default_rng(0)
        views = ['a', 'b', 'c']
        diffs = rng.normal(0, 0.3, size=(300, 3))
        # Labellers prefer whoever is closer in view 'a'.
        flip = diffs[:, 0] < 0
        diffs[flip] *= -1
        cal = sim.calibrate_weights(diffs, views, min_pairs=50)
        self.assertEqual(cal['status'], 'calibrated')
        self.assertGreater(cal['weights']['a'], 0.6)
        self.assertTrue(all(w >= 0 for w in cal['weights'].values()))
        self.assertGreater(cal['train_pairwise_accuracy'], 0.9)

    def test_weights_validation(self) -> None:
        spec = sim.load_spec()
        with self.assertRaises(ValueError):
            sim.normalize_weights({'no_existe': 1.0}, spec, 'Mars')
        with self.assertRaises(ValueError):
            sim.normalize_weights({'escabrosidad': -1.0}, spec, 'Mars')
        w = sim.normalize_weights({'radar': 0.5}, spec, 'Mars')
        self.assertEqual(w['radar'], 0.5)
        self.assertEqual(w['escabrosidad'], spec['default_weights']['Mars']['escabrosidad'])


class TestRobustCovarianceDegeneracy(unittest.TestCase):
    """MinCovDet on zero-inflated, tied features must not silently drop a feature."""
    CFG = {'estimator': 'min_cov_det', 'max_rows': 20000, 'fallback_below_rows': 500,
           'fallback_estimator': 'ledoit_wolf', 'shrinkage_to_diagonal': 0.05}

    @staticmethod
    def zero_inflated(n: int, seed: int, zero_mass: float = 0.86) -> np.ndarray:
        r = np.random.default_rng(seed)
        latent = r.multivariate_normal(np.zeros(4), 0.8 * np.ones((4, 4)) + 0.2 * np.eye(4), n)
        base = latent.mean(1) + 0.3 * r.standard_normal(n)
        g15 = np.maximum(0, base - np.quantile(base, zero_mass - 0.05))
        g25 = np.maximum(0, base - np.quantile(base, zero_mass))
        x = np.column_stack([latent, g15, g25])
        return np.column_stack([sim.QuantileNormal.fit(x[:, i], 1000).normal(x[:, i]) for i in range(6)])

    def test_degenerate_min_cov_det_is_replaced_and_keeps_the_dependence(self) -> None:
        fell_back = 0
        for seed in range(8):
            z = self.zero_inflated(10000, seed)
            cov, name = sim.robust_covariance(z, self.CFG, seed)
            d = np.sqrt(np.diag(cov))
            corr = cov / np.outer(d, d)
            eig = np.linalg.eigvalsh(cov)
            with self.subTest(seed=seed, estimator=name):
                self.assertGreater(eig.min() / eig.max(), 1e-3)
                # The two slope-fraction features stay tied to the rest, as in the data.
                self.assertGreater(corr[-1, 0], 0.4)
                self.assertGreater(corr[-1, -2], 0.7)
            fell_back += name == 'ledoit_wolf_after_degenerate_min_cov_det'
        self.assertGreater(fell_back, 0, 'the synthetic data should trigger the degenerate case at least once')

    def test_healthy_min_cov_det_is_kept(self) -> None:
        z = self.zero_inflated(40000, 3)
        self.assertEqual(sim.robust_covariance(z, self.CFG, 3)[1], 'min_cov_det')

    def test_degeneracy_detector(self) -> None:
        good = np.array([[1.0, 0.5], [0.5, 1.0]])
        self.assertIsNone(sim.covariance_degeneracy(good, good))
        self.assertEqual(sim.covariance_degeneracy(np.array([[1.0, 0.0], [0.0, 0.0]]), good), 'singular')
        self.assertEqual(sim.covariance_degeneracy(np.array([[1.0, -0.6], [-0.6, 1.0]]), good), 'correlation_gap')
        self.assertEqual(sim.covariance_degeneracy(np.array([[np.nan, 0.0], [0.0, 1.0]]), good), 'non_finite')


class TestFitSampleReproducibility(unittest.TestCase):
    """The fit sample must be a function of the data and the seed, not of the scan order."""

    @staticmethod
    def sample(ids: list[str], seed: int, size: int = 300, threads: int = 1) -> list[str]:
        import duckdb
        conn = duckdb.connect()
        conn.execute(f'SET threads={threads}')
        conn.execute('CREATE TABLE features_unified (region_id VARCHAR, x DOUBLE)')
        conn.executemany('INSERT INTO features_unified VALUES (?, ?)', [(i, float(n)) for n, i in enumerate(ids)])
        sql = sim.fit_sample_sql('region_id, x', 'x >= 0', size, seed)
        return [r[0] for r in conn.execute(sql).fetchall()]

    def test_same_seed_same_sample_whatever_the_order_and_threads(self) -> None:
        ids = [f'w{i:05d}' for i in range(3000)]
        shuffled = list(np.random.default_rng(1).permutation(ids))
        base = self.sample(ids, 20261114)
        self.assertEqual(len(base), 300)
        self.assertEqual(base, self.sample(list(reversed(ids)), 20261114))
        self.assertEqual(base, self.sample(shuffled, 20261114, threads=4))

    def test_different_seeds_give_different_samples(self) -> None:
        ids = [f'w{i:05d}' for i in range(3000)]
        a, b = set(self.sample(ids, 1)), set(self.sample(ids, 2))
        self.assertLess(len(a & b), 60)  # ~10 % overlap expected by chance

    def test_sample_is_all_rows_when_the_pool_is_smaller(self) -> None:
        ids = [f'w{i:03d}' for i in range(50)]
        self.assertEqual(sorted(self.sample(ids, 5, size=300)), ids)


class TestEngineOnStore(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name) / 'store'
        store = FeatureStore(cls.root, memory_limit='512MB', threads=2)
        rng = np.random.default_rng(7)
        rows = [base_row(f'w{i:04d}', -100 + i * 0.01, 10.0, random_topo(rng)) for i in range(400)]
        rows += [base_row(f'legacy{i:03d}', -90 + i * 0.01, 10.0, random_topo(rng, with_shape=False))
                 for i in range(60)]
        # Rugged twin: matches the reference in ruggedness, far in shape.
        rows.append(base_row('rugged_twin', 0.0, 0.0, {**REF, 'hypsometric_integral': 0.2,
                                                      'elevation_skew_p95_p05': 0.5,
                                                      'aspect_240m_resultant_length': 0.95}))
        # Shape twin: matches in shape, far in ruggedness.
        rows.append(base_row('shape_twin', 0.1, 0.0, {**REF, 'relief_p95_p05_m': 900.0, 'slope_240m_p50_deg': 20.0,
                                                     'slope_240m_p90_deg': 35.0, 'roughness_360m_p50_m': 60.0,
                                                     'slope_240m_gt15_fraction': 0.6,
                                                     'slope_240m_gt25_fraction': 0.3}))
        rows.append(base_row('exact_twin', 0.2, 0.0, dict(REF)))
        # Inside the Mojave holdout basin: never used to fit.
        rows.append(base_row('mojave_holdout', -116.5, 35.0, random_topo(rng)))
        rows.append(base_row('moon-ref', 10.0, -89.0, dict(REF), body='Moon'))
        store.write_base_batch('b', rows)
        radar = []
        for i in range(120):
            cpr = float(rng.uniform(0.1, 1.5))
            radar.append({'region_id': f'w{i:04d}', 'instrument': 'RCM', 'product_id': 'p',
                          'observation_period': None, 'scenes_found': 1, 'n_scenes': 1,
                          'rcm_cpr_p50': cpr, 'rcm_cpr_p90': cpr * 1.5, 'rcm_s1_p50_db': -12.0,
                          'rcm_dop_p50': 0.5, 'rcm_local_incidence_p50_deg': 35.0, 'rcm_valid_fraction': 1.0,
                          'radar_status': 'measured', 'source_manifest_id': 'm', 'updated_at': NOW})
        store.append_enrichment('radar', radar)
        cls.spec = make_spec()
        cls.model = sim.fit_model(cls.root, cls.spec, sample_size=5000, memory_limit='512MB', threads=2)
        cls.engine = sim.SimilarityEngine(cls.model, cls.spec)
        cls.mars = {'id': 'ref', 'body': 'Mars', 'features': REF}

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def search(self, ref=None, **kw):
        return self.engine.search(self.root, ref or self.mars, memory_limit='512MB', threads=2, **kw)

    def test_report_tells_how_many_independent_rows_a_bridge_view_rests_on(self) -> None:
        # `n_complete` of a bridge view counts resampled rows; `fit_population` says how many
        # distinct measured windows they come from.
        radar = sim.model_report(self.model)['views']['radar']
        self.assertTrue(radar['fitted'])
        self.assertEqual(radar['fit_population']['n_measured'], 120)
        self.assertIn(radar['fit_population']['mode'], ('all_enriched', 'biased_enriched_only', 'background_weighted'))

    def test_fit_excludes_holdout_and_learns_views(self) -> None:
        self.assertEqual(self.model['fit_pool']['windows'], 463)  # 464 Earth rows minus the holdout
        views = self.model['views']
        self.assertTrue(views['escabrosidad']['fitted'])
        self.assertTrue(views['forma_hipsometrica']['fitted'])
        self.assertTrue(views['radar']['fitted'])
        self.assertFalse(views['espectral']['fitted'])
        self.assertTrue(views['regimen_morfologico']['fitted'])
        # Ruggedness descriptors are strongly collinear: fewer effective dimensions than features.
        self.assertLess(views['escabrosidad']['effective_dof'], len(views['escabrosidad']['features']) - 1)
        report = sim.model_report(self.model)
        self.assertNotIn('transform', report['features']['relief_p95_p05_m'])

    def test_save_and_load_roundtrip(self) -> None:
        path, report = sim.save_model(self.model, Path(self.tmp.name) / 'm' / 'model.joblib')
        self.assertTrue(report.is_file())
        engine = sim.SimilarityEngine.load(path, self.spec)
        self.assertEqual(engine.model['spec_hash'], self.model['spec_hash'])

    def test_exact_twin_ranks_first(self) -> None:
        res = self.search(limit=3)
        self.assertEqual(res['results'][0]['region_id'], 'exact_twin')
        top = res['results'][0]
        self.assertLess(top['score'], 0.01)
        self.assertIn('relief_p95_p05_m', top['views']['escabrosidad']['features'])
        self.assertEqual(top['coverage'], 1.0)

    def test_weights_change_the_ranking(self) -> None:
        exclude = {'exact_twin'}
        rug = [r['region_id'] for r in self.search(
            limit=5, weights={'escabrosidad': 1, 'forma_hipsometrica': 0, 'organizacion': 0,
                              'regimen_morfologico': 0, 'espectral': 0, 'termica': 0})['results']
               if r['region_id'] not in exclude]
        shape = [r['region_id'] for r in self.search(
            limit=5, weights={'escabrosidad': 0, 'forma_hipsometrica': 1, 'organizacion': 0.2,
                              'regimen_morfologico': 0, 'espectral': 0, 'termica': 0})['results']
                 if r['region_id'] not in exclude]
        self.assertEqual(rug[0], 'rugged_twin')
        self.assertNotIn('rugged_twin', shape[:3])
        self.assertIn('shape_twin', shape[:3])

    def test_missing_policies(self) -> None:
        w = {'escabrosidad': 0.5, 'forma_hipsometrica': 0.5, 'organizacion': 0, 'regimen_morfologico': 0,
             'espectral': 0, 'termica': 0}
        req = self.search(limit=1000, weights=w, missing_policy='require')
        self.assertFalse(any(r['region_id'].startswith('legacy') for r in req['results']))
        neu = self.search(limit=1000, weights=w, missing_policy='neutral')
        legacy = [r for r in neu['results'] if r['region_id'].startswith('legacy')]
        self.assertEqual(len(legacy), 60)
        self.assertTrue(all(r['missing_views'] == ['forma_hipsometrica'] for r in legacy))
        self.assertTrue(all(r['score_low'] <= r['score'] <= r['score_high'] for r in legacy))
        self.assertTrue(all(r['coverage'] == 0.5 for r in legacy))
        ren = self.search(limit=1000, weights=w, missing_policy='renormalize')
        self.assertEqual(len(ren['results']), len(neu['results']))

    def test_rrf_fusion_runs(self) -> None:
        res = self.search(limit=5, fusion='rrf')
        scores = [r['rrf_score'] for r in res['results']]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_unfitted_view_is_reported_not_imputed(self) -> None:
        res = self.search(limit=2, weights={'espectral': 0.5})
        self.assertEqual(res['views']['espectral']['status'], 'not_fitted')
        self.assertNotIn('espectral', res['weights_effective'])
        self.assertTrue(any('espectral' in w for w in res['warnings']))

    def test_moon_reference_from_store_and_radar_bridge(self) -> None:
        res = self.search('moon-ref', limit=3, only_eligible=False)
        self.assertEqual(res['reference']['body'], 'Moon')
        self.assertEqual(res['views']['radar']['status'], 'reference_missing')  # no Mini-RF row
        moon = {'id': 'm', 'body': 'Moon', 'features': REF, 'percentiles': {'cpr_p50': 0.9, 'cpr_p90': 0.9}}
        res = self.search(moon, limit=5, weights={'radar': 1.0, 'escabrosidad': 0, 'forma_hipsometrica': 0,
                                                  'organizacion': 0, 'regimen_morfologico': 0})
        self.assertEqual(res['views']['radar']['status'], 'used')
        self.assertEqual(res['reference']['features']['cpr_p50']['source'], 'explicit_percentile')
        top = res['results'][0]
        self.assertTrue(top['views']['radar']['available'])
        # Windows without radar sit behind every measured one under the neutral policy.
        self.assertEqual(top['coverage'], 1.0)

    def test_region_filter_and_pair_distances(self) -> None:
        d = self.engine.pair_view_distances(self.root, self.mars, ['exact_twin', 'shape_twin'],
                                            memory_limit='512MB', threads=2)
        self.assertEqual(set(d), {'exact_twin', 'shape_twin'})
        self.assertLess(d['exact_twin']['escabrosidad'], d['shape_twin']['escabrosidad'])

    def assert_same_response(self, a: dict, b: dict) -> None:
        self.assertEqual(a['candidates_in_pool'], b['candidates_in_pool'])
        self.assertEqual(a['candidates_ranked'], b['candidates_ranked'])
        self.assertEqual(a['warnings'], b['warnings'])
        self.assertEqual(a['views'], b['views'])
        self.assertEqual(a['weights_effective'], b['weights_effective'])
        self.assertEqual(a['results'], b['results'])

    def test_pool_gives_the_same_answer_as_the_sql_path(self) -> None:
        pool = self.engine.build_pool(self.root, memory_limit='512MB', threads=2)
        self.addCleanup(pool.close)
        moon = {'id': 'm', 'body': 'Moon', 'features': REF, 'percentiles': {'cpr_p50': 0.9, 'cpr_p90': 0.9}}
        cases = [
            dict(),
            dict(only_eligible=False, limit=1000),
            dict(only_eligible=False, limit=1000, missing_policy='require'),
            dict(only_eligible=False, limit=1000, missing_policy='renormalize'),
            dict(only_eligible=False, limit=50, fusion='rrf'),
            dict(only_eligible=False, limit=20, bbox=[-100.5, 9.0, -98.0, 11.0]),
            dict(only_eligible=False, limit=5, region_ids=['exact_twin', 'shape_twin', 'w0003']),
            dict(only_eligible=False, limit=10, weights={'escabrosidad': 0, 'forma_hipsometrica': 1}),
        ]
        for kw in cases:
            with self.subTest(**kw):
                self.assert_same_response(self.search(**kw), self.search(pool=pool, **kw))
        with self.subTest('moon bridge'):
            kw = dict(limit=10, only_eligible=False, weights={'radar': 1.0, 'escabrosidad': 0.5})
            self.assert_same_response(self.search(moon, **kw), self.search(moon, pool=pool, **kw))
        with self.subTest('store reference'):
            self.assert_same_response(self.search('moon-ref', limit=5, only_eligible=False),
                                      self.search('moon-ref', limit=5, only_eligible=False, pool=pool))

    def test_pool_rejects_a_different_profile(self) -> None:
        pool = self.engine.build_pool(self.root, memory_limit='512MB', threads=2)
        self.addCleanup(pool.close)
        with self.assertRaises(ValueError):
            self.search(pool=pool, profile='polar_cold_v1')

    def test_pool_is_safe_across_threads(self) -> None:
        from concurrent.futures import ThreadPoolExecutor
        pool = self.engine.build_pool(self.root, memory_limit='512MB', threads=2)
        self.addCleanup(pool.close)
        expected = self.search(only_eligible=False, limit=30)['results']
        with ThreadPoolExecutor(4) as ex:
            out = list(ex.map(lambda _: self.search(only_eligible=False, limit=30, pool=pool)['results'], range(8)))
        self.assertTrue(all(o == expected for o in out))

    def test_bad_reference_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.search({'body': 'Mars', 'features': {'inventada': 1.0}})
        with self.assertRaises(ValueError):
            self.search('no-existe-en-el-almacen')


if __name__ == '__main__':
    unittest.main()
