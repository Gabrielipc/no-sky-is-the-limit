"""Tests for the best-framing hypsometric integral of the densified stage."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest

import numpy as np

from pipelines import etl_extractors as ex
from pipelines import etl_framing as framing
from pipelines.etl_store import FeatureStore
from tests.test_etl_eligibility import SCENARIOS, base_row

NOW = datetime(2026, 11, 14, 12, 0, tzinfo=timezone.utc)
CELL = ex.CELL_M
MAX = framing.DEFAULT_MAX_OFFSET_M
SIZE = (ex.WINDOW_M + 2 * ex.HALO_M + 2 * MAX) // CELL
COORDS = (np.arange(SIZE, dtype='float64') - (SIZE - 1) / 2) * CELL
X, Y = np.meshgrid(COORDS, -COORDS)  # row 0 is north
LAND = np.ones((SIZE, SIZE), dtype=bool)


def raised_deposit(east_m: float, north_m: float, regional_slope: float = 0.002) -> np.ndarray:
    """Flat-topped raised deposit (radius 1.3 km, smooth edge) centred off the grid centre.

    Centred in a 3 km footprint it covers more than half of the area, so its framing is
    top-heavy (high integral); shifted framings include more low ground.
    """
    r = np.hypot(X - east_m, Y - north_m)
    deposit = 60.0 / (1.0 + np.exp((r - 1300.0) / 100.0))
    return regional_slope * X + deposit


class TestFraming(unittest.TestCase):
    def test_lattice(self) -> None:
        offsets = framing.lattice(300, 600)
        self.assertEqual(len(offsets), 25)
        self.assertEqual(offsets[0], (0, 0))
        self.assertEqual(len(set(offsets)), 25)
        with self.assertRaises(ValueError):
            framing.lattice(250, 600)

    def test_offset_framing_matches_direct_window(self) -> None:
        z = raised_deposit(600, -300)
        rec = framing.evaluate_framings(z, LAND, reference_hi=0.9)
        size = (ex.WINDOW_M + 2 * ex.HALO_M) // CELL
        m = MAX // CELL
        east, north = rec['best_offset_east_m'], rec['best_offset_north_m']
        direct = ex.compute_topography_features(
            z[m - north // CELL:m - north // CELL + size, m + east // CELL:m + east // CELL + size],
            LAND[:size, :size])
        self.assertAlmostEqual(rec['hi_best'], direct['hypsometric_integral'], places=12)
        self.assertAlmostEqual(rec['best_relief_p95_p05_m'], direct['relief_p95_p05_m'], places=9)

    def test_best_framing_centres_an_off_centre_deposit(self) -> None:
        # On flat ground the most top-heavy framing is the one centred on the deposit.
        z = raised_deposit(600, -300, regional_slope=0.0)
        rec = framing.evaluate_framings(z, LAND, reference_hi=1.0)
        self.assertEqual(rec['framing_status'], 'measured')
        self.assertEqual(rec['framings_evaluated'], 25)
        self.assertEqual((rec['best_offset_east_m'], rec['best_offset_north_m']), (600, -300))
        self.assertTrue(rec['best_at_lattice_edge'])
        inner = framing.evaluate_framings(raised_deposit(300, 0, regional_slope=0.0), LAND, reference_hi=1.0)
        self.assertEqual((inner['best_offset_east_m'], inner['best_offset_north_m']), (300, 0))
        self.assertFalse(inner['best_at_lattice_edge'])
        self.assertGreater(rec['hi_best'], rec['hi_center'])
        self.assertLessEqual(rec['hi_min'], rec['hi_center'])
        self.assertGreaterEqual(rec['hi_max'], rec['hi_best'])

    def test_reference_inside_range_is_matched_closely(self) -> None:
        z = raised_deposit(600, -300)
        probe = framing.evaluate_framings(z, LAND, reference_hi=0.5)
        target = (probe['hi_min'] + probe['hi_max']) / 2
        rec = framing.evaluate_framings(z, LAND, reference_hi=target)
        self.assertLessEqual(abs(rec['hi_best'] - target), abs(rec['hi_center'] - target))

    def test_joint_selection_penalises_relief_drift(self) -> None:
        z = raised_deposit(600, -300)
        other = framing.evaluate_framings(z, LAND, reference_hi=0.75, reference_relief_m=200.0)
        joint = framing.evaluate_framings(z, LAND, reference_hi=0.75, reference_relief_m=40.0)
        self.assertEqual(joint['framing_criterion'], framing.FRAMING_CRITERION)
        self.assertLessEqual(joint['best_distance_score'], joint['center_distance_score'])
        self.assertAlmostEqual(joint['best_distance_score'], framing.densified_distance(
            joint['best_relief_p95_p05_m'], joint['hi_best'], 40.0, 0.75), 5)
        # A framing chosen for another relief can never beat the joint choice under this one.
        self.assertLessEqual(joint['best_distance_score'], framing.densified_distance(
            other['best_relief_p95_p05_m'], other['hi_best'], 40.0, 0.75) + 1e-9)

    def test_missing_dem_is_insufficient_coverage(self) -> None:
        rec = framing.evaluate_framings(np.full((SIZE, SIZE), np.nan), LAND, reference_hi=0.6)
        self.assertEqual(rec['framing_status'], 'insufficient_coverage')
        self.assertEqual(rec['framings_valid'], 0)
        self.assertIsNone(rec['hi_best'])

    def test_wrong_grid_shape_rejected(self) -> None:
        with self.assertRaises(ValueError):
            framing.evaluate_framings(np.zeros((148, 148)), np.ones((148, 148), bool), 0.6)

    def test_store_reports_framing_without_changing_distance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = FeatureStore(Path(tmp) / 'store', memory_limit='512MB', threads=2)
            store.write_base_batch('b', [base_row('desert', SCENARIOS['desert'])])
            before = store.rank_similar(100.0, 3.0, 9.0, ref_hypsometric_integral=0.613)
            self.assertEqual(before[0]['framing_status'], 'on_demand_fetchable')
            self.assertIsNone(before[0]['hi_best_abs_delta'])

            rec = framing.evaluate_framings(raised_deposit(600, -300), LAND, reference_hi=0.613)
            store.append_enrichment('framing', [{
                'region_id': 'desert', 'reference_id': framing.JEZERO_REFERENCE_ID, **rec,
                'source_manifest_id': 'm', 'updated_at': NOW}])
            after = store.rank_similar(100.0, 3.0, 9.0, ref_hypsometric_integral=0.613)
            self.assertEqual(after[0]['framing_status'], 'measured')
            self.assertAlmostEqual(after[0]['hi_best_abs_delta'], abs(rec['hi_best'] - 0.613), places=5)
            self.assertEqual(after[0]['distance_score'], before[0]['distance_score'])
            self.assertIsNotNone(store.compact('framing'))


def framing_row(region_id: str, hi_best: float, relief: float, *, reference_hi: float = 0.613,
                reference_relief: float = 120.0, criterion: str | None = framing.FRAMING_CRITERION,
                step: int = framing.DEFAULT_STEP_M, max_offset: int = MAX) -> dict:
    return {
        'region_id': region_id, 'reference_id': framing.JEZERO_REFERENCE_ID,
        'reference_hypsometric_integral': reference_hi, 'reference_relief_m': reference_relief,
        'framing_criterion': criterion, 'lattice_step_m': step, 'max_offset_m': max_offset,
        'framings_evaluated': 25, 'framings_valid': 25,
        'hi_center': hi_best - 0.05, 'hi_best': hi_best, 'hi_min': hi_best - 0.1, 'hi_max': hi_best,
        'best_offset_east_m': 0, 'best_offset_north_m': 0, 'best_at_lattice_edge': False,
        'best_distance_score': framing.densified_distance(relief, hi_best, reference_relief, reference_hi),
        'center_distance_score': None, 'best_relief_p95_p05_m': relief, 'best_slope_240m_p50_deg': 3.0, 'best_slope_240m_p90_deg': 9.0,
        'best_aspect_240m_resultant_length': 0.4, 'framing_status': 'measured',
        'source_manifest_id': 'm', 'updated_at': NOW,
    }


class DensifiedRankingTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.store = FeatureStore(Path(self._tmp.name) / 'store', memory_limit='512MB', threads=2)
        rows = []
        for rid in ('fan', 'basin', 'other_ref', 'other_relief', 'legacy', 'wide_lattice', 'unframed'):
            row = base_row('desert', SCENARIOS['desert'])
            row['region_id'] = rid
            rows.append(row)
        self.store.write_base_batch('b', rows)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_shape_breaks_ruggedness_ties(self) -> None:
        # Same base topography: the reconnaissance ranking cannot tell them apart.
        recon = self.store.rank_similar(120.0, 3.0, 9.0)
        self.assertEqual(len({round(r['distance_score'], 9) for r in recon}), 1)

        self.store.append_enrichment('framing', [
            framing_row('basin', hi_best=0.42, relief=118.0),
            framing_row('fan', hi_best=0.60, relief=125.0),
            framing_row('other_ref', hi_best=0.61, relief=120.0, reference_hi=0.5),
            framing_row('other_relief', hi_best=0.61, relief=120.0, reference_relief=90.0),
            framing_row('legacy', hi_best=0.61, relief=120.0, criterion=None),
            framing_row('wide_lattice', hi_best=0.61, relief=120.0, max_offset=900),
        ])
        out = self.store.rank_densified(120.0, 0.613)
        # Other reference, lattice or HI-only selection: best framing is not comparable.
        self.assertEqual([r['region_id'] for r in out], ['fan', 'basin'])
        self.assertEqual(out[0]['densified_rank'], 1)
        self.assertEqual(out[0]['candidates_compared'], 2)
        self.assertEqual(out[0]['ranking_vector'], framing.DENSIFIED_VECTOR_ID)
        self.assertEqual(out[0]['ranking_vector_status'], 'pending_blind_validation')
        for r in out:
            # Ranking uses exactly the distance that selected the framing.
            self.assertAlmostEqual(r['distance_score'], framing.densified_distance(
                r['best_relief_p95_p05_m'], r['hi_best'], 120.0, 0.613), 5)
        legacy = [r for r in self.store.rank_similar(120.0, 3.0, 9.0) if r['region_id'] == 'legacy']
        self.assertEqual(legacy[0]['framing_status'], 'measured')

        wide = self.store.rank_densified(120.0, 0.613, max_offset_m=900)
        self.assertEqual([r['region_id'] for r in wide], ['wide_lattice'])

    def test_no_framing_returns_empty(self) -> None:
        self.assertEqual(self.store.rank_densified(120.0, 0.613), [])


if __name__ == '__main__':
    unittest.main()
