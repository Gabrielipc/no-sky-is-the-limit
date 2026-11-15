"""Tests for the single-operator three-body spectral bridge (audit 2026-11-14, priority 6)."""
from __future__ import annotations

from pathlib import Path
import sys
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipelines import spectral_bridge as sb
from pipelines import spectral_params as sp
from pipelines import spectral_readers as sr


def _make_sample(wavelengths: np.ndarray, spectra_2d: np.ndarray, *,
                 instrument: str = 'SYNTH', product_id: str = 'SYNTH_01',
                 footprint_cells: int = 100, kernel_mode: str = 'nm') -> sb.FootprintSample:
    """Build a FootprintSample from (n_bands, n_valid) reflectance."""
    n_valid = spectra_2d.shape[1]
    return sb.FootprintSample(
        instrument=instrument,
        product_id=product_id,
        wavelengths=wavelengths,
        reflectance=spectra_2d[:, None, :],
        footprint_cells=footprint_cells,
        in_coverage_cells=n_valid,
        valid_cells=n_valid,
        pixel_m=60.0,
        kernel_mode=kernel_mode,
        notes=[],
    )


def _emit_like_grid() -> tuple[np.ndarray, np.ndarray]:
    """EMIT L2A-like wavelengths (381-2493 nm, ~7.4 nm) with water-vapour bands masked as NaN."""
    wl = np.linspace(381.0, 2493.0, 285)
    bad = ((wl >= 1327.0) & (wl <= 1432.0)) | ((wl >= 1804.0) & (wl <= 1960.0))
    return wl, bad


def _m3_like_grid() -> np.ndarray:
    """M3 L2-like wavelengths (460-2976 nm, ~20 nm spacing in VNIR/SWIR)."""
    return np.linspace(461.0, 2976.0, 85)


class SyntheticSpectraTest(unittest.TestCase):
    def test_linear_continuum_yields_zero_across_all_parameter_kinds(self):
        wl = np.arange(420.0, 2600.0, sp.CRISM_SAMPLING_NM)
        spectrum = 0.20 + 0.0001 * wl
        data = np.repeat(spectrum[:, None, None], 4, axis=2)
        cube = sp.Cube(data, wl, kernel_mode='channels')
        for name in sp.PARAMS:
            self.assertTrue(sp.covered(cube, name), f'{name} should be covered on CRISM-like grid')
            val = sp.compute(cube, name)
            np.testing.assert_allclose(val, 0.0, atol=1e-12, err_msg=f'Non-zero {name} on linear continuum')

    def test_synthetic_absorption_band_depths_match_analytic_values(self):
        wl = np.arange(420.0, 2600.0, sp.CRISM_SAMPLING_NM)
        n_cells = 40
        # Non-overlapping centre/anchor combinations verified analytically at 10% band depth
        for param, centre in (
            ('BD530_2', 530.0),
            ('BD920_2', 920.0),
            ('BD2210_2', 2210.0),
            ('BD2265', 2265.0),
            ('BD2290', 2290.0),
        ):
            spec = np.full((wl.size, n_cells), 0.30, dtype='float64')
            spec[np.abs(wl - centre) <= 18.0, :] = 0.27
            cube = sp.Cube(spec[:, None, :], wl, kernel_mode='channels')
            vals = sp.compute(cube, param)
            np.testing.assert_allclose(vals, 0.10, atol=1e-12, err_msg=f'Unexpected depth for {param}')

        # Combined non-interfering bands (530, 920, 2210) activate their complexes via summarize_bridge
        combined = np.full((wl.size, n_cells), 0.30, dtype='float64')
        for centre in (530.0, 920.0, 2210.0):
            combined[np.abs(wl - centre) <= 18.0, :] = 0.27
        sample = _make_sample(wl, combined, footprint_cells=n_cells, kernel_mode='channels')
        summary = sb.summarize_bridge(sample)
        self.assertEqual(summary['abs_fe3_oxide_0p53_0p90um']['status'], 'measured')
        self.assertAlmostEqual(summary['abs_fe3_oxide_0p53_0p90um']['active_fraction'], 1.0)
        self.assertEqual(summary['abs_al_oh_2p20um']['by_parameter']['BD2210_2']['status'], 'measured')
        self.assertEqual(summary['abs_mafic_fe2_1p0um']['by_parameter']['BD920_2']['status'], 'measured')

    def test_kernel_mode_channels_matches_nm_at_crism_sampling_and_scales_physically(self):
        wl_crism = np.arange(430.0, 2600.0, sp.CRISM_SAMPLING_NM)
        rng = np.random.default_rng(7)
        data = rng.uniform(0.15, 0.40, size=(wl_crism.size, 2, 3))
        c_chan = sp.Cube(data, wl_crism, kernel_mode='channels')
        c_nm = sp.Cube(data, wl_crism, kernel_mode='nm')
        for name in sp.PARAMS:
            p = sp.PARAMS[name]
            for term in [p.low, p.high, *p.terms, *p.ref_terms, *(t for pair in p.pairs for t in pair)]:
                if term is not None:
                    self.assertEqual(c_chan.window(term), c_nm.window(term))
            np.testing.assert_allclose(sp.compute(c_chan, name), sp.compute(c_nm, name), atol=1e-12)

        # Coarser M3-like grid (~15 nm spacing): k=5 (~+-16.375 nm) selects 3 bands instead of 5 channels
        wl_coarse = np.arange(460.0, 2980.0, 15.0)
        c_coarse_nm = sp.Cube(np.ones((wl_coarse.size, 1, 1)), wl_coarse, kernel_mode='nm')
        lo, hi = c_coarse_nm.window(sp.Term(2210.0, 5))
        self.assertEqual(hi - lo, 3)


class CoverageAndPairingRuleTest(unittest.TestCase):
    def test_emit_atmospheric_windows_and_cutoff_select_fallback_indicators(self):
        wl, bad = _emit_like_grid()
        spec = np.full((wl.size, 50), 0.25, dtype='float64')
        spec[bad, :] = np.nan
        cube = sp.Cube(spec[:, None, :], wl, kernel_mode='nm')

        expected_covered = {'BD530_2', 'BD860_2', 'BD920_2', 'D2200', 'BD2210_2', 'BD2265', 'BD2290'}
        expected_unobserved = {
            'D2300', 'BD1900R2', 'BD1900_2', 'MIN2295_2480', 'BD2500_2',
            'OLINDEX3', 'LCPINDEX2', 'HCPINDEX2',
        }
        for name in expected_covered:
            self.assertTrue(sp.covered(cube, name), f'{name} should be covered on EMIT L2A')
        for name in expected_unobserved:
            self.assertFalse(sp.covered(cube, name), f'{name} should NOT be covered on EMIT L2A')

        # If the 1.8 um water-vapour mask extends below 1790 nm, D2200 also becomes unobserved
        wide_bad = bad | ((wl >= 1790.0) & (wl <= 1804.0))
        spec_wide = np.full((wl.size, 50), 0.25, dtype='float64')
        spec_wide[wide_bad, :] = np.nan
        self.assertFalse(sp.covered(sp.Cube(spec_wide[:, None, :], wl, kernel_mode='nm'), 'D2200'))

    def test_footprint_coverage_threshold_masks_low_support_and_zero_pixels(self):
        wl = np.arange(420.0, 2600.0, sp.CRISM_SAMPLING_NM)

        # 72 valid cells out of 100 (72% < 80% minimum) -> insufficient_coverage
        low_frac = _make_sample(wl, np.full((wl.size, 72), 0.25), footprint_cells=100, kernel_mode='channels')
        sum_low = sb.summarize_bridge(low_frac)
        for cid, rec in sum_low.items():
            self.assertEqual(rec['status'], 'insufficient_coverage', cid)
            self.assertIsNone(rec['p50'])
            self.assertIsNone(rec['p95'])
            self.assertIsNone(rec['active_fraction'])

        # 0 valid cells (permanent shadow) -> insufficient_coverage
        empty = _make_sample(wl, np.empty((wl.size, 0)), footprint_cells=140, kernel_mode='nm')
        sum_empty = sb.summarize_bridge(empty)
        for cid, rec in sum_empty.items():
            self.assertEqual(rec['status'], 'insufficient_coverage', cid)
            self.assertIsNone(rec['p50'])

        # 25 valid cells out of 25 (< 30 MIN_VALID_CELLS) -> insufficient_coverage
        too_few = _make_sample(wl, np.full((wl.size, 25), 0.25), footprint_cells=25, kernel_mode='channels')
        sum_few = sb.summarize_bridge(too_few)
        for cid, rec in sum_few.items():
            self.assertEqual(rec['status'], 'insufficient_coverage', cid)

    def test_pairing_rule_selects_first_shared_indicator_across_three_bodies(self):
        wl_crism = np.arange(420.0, 2600.0, sp.CRISM_SAMPLING_NM)
        crism_spec = np.full((wl_crism.size, 100), 0.30, dtype='float64')
        crism_spec[np.abs(wl_crism - 530.0) <= 15.0, :] = 0.27
        crism_sum = sb.summarize_bridge(_make_sample(
            wl_crism, crism_spec, instrument='CRISM_MTRDR', footprint_cells=100, kernel_mode='channels'
        ))

        wl_emit, bad = _emit_like_grid()
        emit_spec = np.full((wl_emit.size, 100), 0.30, dtype='float64')
        emit_spec[np.abs(wl_emit - 530.0) <= 15.0, :] = 0.25
        emit_spec[bad, :] = np.nan
        emit_sum = sb.summarize_bridge(_make_sample(
            wl_emit, emit_spec, instrument='EMIT_L2A', footprint_cells=100, kernel_mode='nm'
        ))

        mars_earth = sb.pair_comparison(crism_sum, emit_sum)
        self.assertEqual(mars_earth['abs_fe3_oxide_0p53_0p90um']['status'], 'bridged')
        self.assertEqual(mars_earth['abs_fe3_oxide_0p53_0p90um']['parameter'], 'BD530_2')
        self.assertEqual(mars_earth['abs_fe3_oxide_0p53_0p90um']['indicator_rank'], 1)
        self.assertEqual(mars_earth['abs_al_oh_2p20um']['parameter'], 'D2200')
        self.assertEqual(mars_earth['abs_al_oh_2p20um']['indicator_rank'], 1)
        self.assertEqual(mars_earth['abs_fe_mg_oh_2p30um']['parameter'], 'BD2290')
        self.assertEqual(mars_earth['abs_fe_mg_oh_2p30um']['indicator_rank'], 2)
        self.assertEqual(mars_earth['abs_hydrated_sioh_so4_1p9_2p26um']['parameter'], 'BD2265')
        self.assertEqual(mars_earth['abs_hydrated_sioh_so4_1p9_2p26um']['indicator_rank'], 2)
        self.assertEqual(mars_earth['abs_mafic_fe2_1p0um']['parameter'], 'BD920_2')
        self.assertEqual(mars_earth['abs_mafic_fe2_1p0um']['indicator_rank'], 3)
        self.assertEqual(mars_earth['abs_carbonate_2p30_2p50um']['status'], 'unbridged_unobserved')
        self.assertIsNone(mars_earth['abs_carbonate_2p30_2p50um']['parameter'])

        # When 1790-1804 nm is also masked out, Al-OH falls back to rank 2 (BD2210_2)
        emit_wide = np.copy(emit_spec)
        emit_wide[(wl_emit >= 1790.0) & (wl_emit <= 1804.0), :] = np.nan
        emit_wide_sum = sb.summarize_bridge(_make_sample(
            wl_emit, emit_wide, instrument='EMIT_L2A', footprint_cells=100, kernel_mode='nm'
        ))
        mars_earth_wide = sb.pair_comparison(crism_sum, emit_wide_sum)
        self.assertEqual(mars_earth_wide['abs_al_oh_2p20um']['parameter'], 'BD2210_2')
        self.assertEqual(mars_earth_wide['abs_al_oh_2p20um']['indicator_rank'], 2)

        # Illuminated Moon (M3 L2: 461-2976 nm, no water-vapour gaps) pairs at rank 1 for SWIR/mafic complexes
        wl_m3 = _m3_like_grid()
        m3_sum = sb.summarize_bridge(_make_sample(
            wl_m3, np.full((wl_m3.size, 100), 0.25), instrument='M3_L2', footprint_cells=100, kernel_mode='nm'
        ))
        mars_moon = sb.pair_comparison(crism_sum, m3_sum)
        for cid, expected_param in (
            ('abs_al_oh_2p20um', 'D2200'),
            ('abs_fe_mg_oh_2p30um', 'D2300'),
            ('abs_carbonate_2p30_2p50um', 'MIN2295_2480'),
            ('abs_hydrated_sioh_so4_1p9_2p26um', 'BD1900R2'),
            ('abs_mafic_fe2_1p0um', 'OLINDEX3'),
        ):
            self.assertEqual(mars_moon[cid]['status'], 'bridged', cid)
            self.assertEqual(mars_moon[cid]['parameter'], expected_param, cid)
            self.assertEqual(mars_moon[cid]['indicator_rank'], 1, cid)

        # Polar Moon site with 48% valid cells fails coverage -> unbridged_insufficient_coverage
        m3_low = sb.summarize_bridge(_make_sample(
            wl_m3, np.full((wl_m3.size, 48), 0.25), instrument='M3_L2', footprint_cells=100, kernel_mode='nm'
        ))
        mars_polar = sb.pair_comparison(crism_sum, m3_low)
        for cid in ('abs_al_oh_2p20um', 'abs_fe_mg_oh_2p30um', 'abs_carbonate_2p30_2p50um',
                    'abs_hydrated_sioh_so4_1p9_2p26um', 'abs_mafic_fe2_1p0um'):
            self.assertEqual(mars_polar[cid]['status'], 'unbridged_insufficient_coverage', cid)

        # Remote site pending GCP fetch -> pending_remote_fetch for observable indicators,
        # while unobserved indicators stay unbridged_unobserved
        remote_pending = {
            cid: {
                'status': 'on_demand_fetchable',
                'by_parameter': {
                    ind['parameter']: {
                        'parameter': ind['parameter'],
                        'status': (
                            'on_demand_fetchable'
                            if sp.covered(sp.Cube(np.where(bad, np.nan, 0.25)[:, None, None], wl_emit, 'nm'), ind['parameter'])
                            else 'unobserved_by_product'
                        ),
                    }
                    for ind in cdef['indicators']
                },
            }
            for cid, cdef in sb.load_bridge_spec()['complexes'].items()
        }
        mars_pending = sb.pair_comparison(crism_sum, remote_pending)
        self.assertEqual(mars_pending['abs_fe3_oxide_0p53_0p90um']['status'], 'pending_remote_fetch')
        self.assertEqual(mars_pending['abs_mafic_fe2_1p0um']['status'], 'pending_remote_fetch')
        self.assertEqual(mars_pending['abs_carbonate_2p30_2p50um']['status'], 'unbridged_unobserved')


class LocalCacheIntegrationTest(unittest.TestCase):
    def test_crism_jezero_local_cache_1800m_and_3000m(self):
        spec = sb.load_bridge_spec()
        mars_site = next(s for s in spec['sites'] if s['id'] == 'mars-jezero-fan')
        prod = mars_site['product']
        mask_path = ROOT / prod['mask']
        hdr_path = ROOT / prod['header']
        cache_dir = ROOT / prod['cache']
        if not (mask_path.exists() and hdr_path.exists() and cache_dir.exists()):
            self.skipTest('Local CRISM cache not available in this environment')

        src = sr.EnviBsqRemote(prod['url'], hdr_path)
        names = sb.bridge_parameter_names(spec)
        s18 = sr.crism_footprint(src, mask_path, mars_site['longitude'], mars_site['latitude'],
                                 1800, names, cache_dir, prod['product_id'], offline=True)
        self.assertEqual(s18.footprint_cells, 10200)
        self.assertEqual(s18.valid_cells, 8897)
        self.assertGreaterEqual(s18.valid_fraction, 0.80)
        sum18 = sb.summarize_bridge(s18, spec)
        for cid, rec in sum18.items():
            self.assertEqual(rec['status'], 'measured', cid)

        s30 = sr.crism_footprint(src, mask_path, mars_site['longitude'], mars_site['latitude'],
                                 3000, names, cache_dir, prod['product_id'], offline=True)
        self.assertEqual(s30.footprint_cells, 28390)
        self.assertEqual(s30.valid_cells, 20514)
        self.assertLess(s30.valid_fraction, 0.80)
        sum30 = sb.summarize_bridge(s30, spec)
        for cid, rec in sum30.items():
            self.assertEqual(rec['status'], 'insufficient_coverage', cid)

    def test_m3_cached_loc_screening_covers_polar_sites(self):
        spec = sb.load_bridge_spec()
        for sid in ('moon-haworth-fondo', 'moon-de-gerlache-cresta'):
            site = next(s for s in spec['sites'] if s['id'] == sid)
            for strip in site['product']['candidate_strips']:
                loc_path = ROOT / strip['loc_cache']
                if not loc_path.exists():
                    self.skipTest(f'Missing cached M3 LOC {loc_path}')
                screen = sr.m3_cached_loc_screening(loc_path, site['longitude'], site['latitude'])
                self.assertLess(screen['min_distance_m'], 100.0)
                self.assertTrue(screen['footprints']['1800']['covers_footprint'])
                self.assertTrue(screen['footprints']['3000']['covers_footprint'])


if __name__ == '__main__':
    unittest.main()
