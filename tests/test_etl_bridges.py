"""Tests for the laser (ICESat-2) and radar (RCM) bridges (audit 2026-11-14, priority 7)."""
from __future__ import annotations

from datetime import datetime, timezone
import math
from pathlib import Path
import tempfile
import unittest

import numpy as np
import pyarrow as pa

from pipelines import etl_altimetry as alt
from pipelines import etl_contract as contract
from pipelines import etl_radar as radar
from pipelines.etl_store import FeatureStore

NOW = datetime(2026, 11, 14, 12, 0, tzinfo=timezone.utc)


def profile(h: np.ndarray, step: float = 100.0, azimuth_deg: float = 20.0, h_dem=None) -> alt.Profile:
    s = np.arange(len(h)) * step
    ux, uy = math.sin(math.radians(azimuth_deg)), math.cos(math.radians(azimuth_deg))
    s20 = np.arange(5 * len(h)) * (step / 5)
    h20 = np.interp(s20, s, h)
    return alt.Profile(granule='g', beam='gt1r', beam_type='strong', date='2026-07-30',
                       x=s * ux, y=s * uy, h=h.astype(float), snow=np.zeros(len(h), bool),
                       x20=s20 * ux, y20=s20 * uy, h20=h20, h_dem=h_dem)


class ProfileMetricsTest(unittest.TestCase):
    def test_plane_has_constant_slope_and_zero_differential_slope(self):
        h = 0.05 * np.arange(30) * 100.0  # 5 % grade along track
        m = alt.profile_metrics([profile(h, h_dem=h + 2.0)])
        expected = math.degrees(math.atan(0.05))
        self.assertAlmostEqual(m['laser_slope_100m_p50_deg'], expected, places=6)
        self.assertAlmostEqual(m['laser_slope_20m_p90_deg'], expected, places=6)
        self.assertAlmostEqual(m['laser_diff_slope_200m_p50_deg'], 0.0, places=9)
        self.assertAlmostEqual(m['laser_diff_slope_600m_p50_deg'], 0.0, places=9)
        self.assertAlmostEqual(m['dem_slope_100m_p50_deg'], expected, places=6)
        self.assertAlmostEqual(m['dem_minus_laser_median_m'], 2.0, places=9)
        self.assertAlmostEqual(m['dem_minus_laser_nmad_m'], 0.0, places=9)
        self.assertEqual(m['n_pairs_100m'], 29)
        self.assertEqual(m['n_diff_200m'], 30 - 4)
        self.assertEqual(m['n_diff_600m'], 30 - 12)

    def test_differential_slope_removes_regional_trend_but_keeps_roughness(self):
        rng = np.random.default_rng(0)
        bumps = rng.normal(0, 1.0, 40)
        flat = alt.profile_metrics([profile(bumps)])
        tilted = alt.profile_metrics([profile(bumps + 0.1 * np.arange(40) * 100.0)])
        self.assertGreater(flat['laser_diff_slope_200m_p50_deg'], 0.0)
        self.assertAlmostEqual(flat['laser_diff_slope_200m_p50_deg'], tilted['laser_diff_slope_200m_p50_deg'], places=9)
        self.assertGreater(tilted['laser_slope_100m_p50_deg'], flat['laser_slope_100m_p50_deg'])

    def test_gaps_break_pairs_instead_of_pairing_distant_segments(self):
        p = profile(np.arange(10, dtype=float))
        keep = np.r_[0:4, 6:10]  # a 300 m gap after the fourth segment
        p.x, p.y, p.h, p.snow = p.x[keep], p.y[keep], p.h[keep], p.snow[keep]
        m = alt.profile_metrics([p])
        self.assertEqual(m['n_pairs_100m'], 6)
        i, j = alt.pair_indices(alt.along_track(p.x, p.y), 100.0)
        self.assertTrue(np.all(np.abs(alt.along_track(p.x, p.y)[j] - alt.along_track(p.x, p.y)[i]) < 116))

    def test_unsorted_profile_gives_same_metrics(self):
        h = np.sin(np.arange(25) / 3.0) * 10
        p = profile(h)
        q = profile(h)
        order = np.random.default_rng(1).permutation(len(h))
        q.x, q.y, q.h = q.x[order], q.y[order], q.h[order]
        a, b = alt.profile_metrics([p]), alt.profile_metrics([q])
        for k in ('laser_slope_100m_p50_deg', 'laser_diff_slope_200m_p50_deg', 'laser_diff_slope_600m_p50_deg'):
            self.assertAlmostEqual(a[k], b[k], places=9)

    def test_status(self):
        empty = alt.profile_metrics([])
        self.assertEqual(alt.altimetry_status(empty), 'no_swath_coverage')
        short = alt.profile_metrics([profile(np.zeros(5))])
        self.assertEqual(alt.altimetry_status(short), 'insufficient_coverage')
        long = alt.profile_metrics([profile(np.zeros(30))])
        self.assertEqual(alt.altimetry_status(long), 'measured')

    def test_core_selection_and_search_box(self):
        core = alt.Core.at(-67.91, -25.042)
        w, s, e, n = core.search_bbox()
        self.assertTrue(w < -67.91 < e and s < -25.042 < n)
        lon = np.array([-67.91, -67.91 + 0.02, -67.91])
        lat = np.array([-25.042, -25.042, -25.042 + 0.012])
        self.assertEqual(core.inside(lon, lat).tolist(), [True, False, True])

    def test_range_file_rejects_other_hosts(self):
        with self.assertRaises(ValueError):
            alt.RangeFile('https://example.com/ATL08.h5')


class RadarTest(unittest.TestCase):
    def test_cpr_s1_and_degree_of_polarization(self):
        rr = np.array([0.01, 0.05, 0.0])
        rl = np.array([0.04, 0.05, 0.02])
        np.testing.assert_allclose(radar.cpr(rr, rl)[:2], [0.25, 1.0])
        self.assertAlmostEqual(radar.total_power_db(rr, rl)[0], 10 * math.log10(0.05))
        # Fully polarized single bounce: RR = 0 -> m = 1. Unpolarized: RR = RL, RR.RL* = 0 -> m = 0.
        m = radar.degree_of_polarization(np.array([0.0, 0.03]), np.array([0.04, 0.03]), np.array([0.0, 0.0]))
        np.testing.assert_allclose(m, [1.0, 0.0])

    def test_summary_uses_median_over_scenes_and_shared_cells(self):
        shape = (2, 4, 4)
        rr = np.full(shape, 0.01)
        rl = np.full(shape, 0.04)
        rr[1] = 0.02          # second scene: CPR 0.5 -> per-cell median 0.375
        rr[:, 0, :] = np.nan  # first row never valid
        stack = {'rr': rr, 'rl': rl, 'rrrl_abs': np.zeros(shape), 'inc': np.full(shape, 35.0)}
        out, fraction = radar.summarize_cells(stack)
        self.assertAlmostEqual(fraction, 0.75)
        self.assertAlmostEqual(out['rcm_cpr_p50'], 0.375)
        self.assertAlmostEqual(out['rcm_local_incidence_p50_deg'], 35.0)
        self.assertEqual(radar.radar_status(2, fraction), 'insufficient_coverage')
        self.assertEqual(radar.radar_status(0, 0.0), 'no_swath_coverage')
        self.assertEqual(radar.radar_status(2, 0.9), 'measured')

    def test_asset_host_is_checked(self):
        with self.assertRaises(ValueError):
            radar._check_host('https://example.com/RR.tif')


class ContractTest(unittest.TestCase):
    def _altimetry_row(self, **over):
        row = {'region_id': 'w1', 'instrument': 'ICESat-2/ATLAS ATL08', 'product_id': alt.PRODUCT_ID,
               'observation_period': '2019-01-01/2026-07-30', 'granules_found': 3, 'granules_with_data': 2,
               'n_tracks': 2, 'n_segments': 40, 'n_pairs_20m': 150, 'n_pairs_100m': 38, 'n_diff_200m': 30,
               'n_diff_600m': 20, 'altimetry_status': 'measured', 'source_manifest_id': 'm', 'updated_at': NOW}
        row.update({k: 1.0 for k in alt.ALTIMETRY_METRICS})
        row.update(over)
        return row

    def test_validation_rejects_out_of_range_and_bad_status(self):
        def table(**over):
            return pa.Table.from_pylist([self._altimetry_row(**over)], schema=contract.ENRICHMENT_ALTIMETRY_SCHEMA)
        contract.validate_table(table(), 'enrichment_altimetry')
        with self.assertRaises(ValueError):
            contract.validate_table(table(laser_slope_100m_p50_deg=95.0), 'enrichment_altimetry')
        with self.assertRaises(ValueError):
            contract.validate_table(table(altimetry_status='ok'), 'enrichment_altimetry')

    def test_store_round_trip_and_unified_view(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = FeatureStore(Path(tmp))
            store.append_enrichment('altimetry', [self._altimetry_row()])
            radar_row = {'region_id': 'control-v1:x', 'instrument': 'RCM', 'product_id': radar.PRODUCT_ID,
                         'observation_period': None, 'scenes_found': 0, 'n_scenes': 0,
                         **dict.fromkeys(radar.RADAR_VALUE_KEYS), 'rcm_valid_fraction': 0.0,
                         'radar_status': 'no_swath_coverage', 'source_manifest_id': 'none', 'updated_at': NOW}
            store.append_enrichment('radar', [radar_row])
            with store._connect() as conn:
                n = conn.execute('SELECT count(*) FROM enrichment_altimetry_latest').fetchone()[0]
                status = conn.execute('SELECT radar_status FROM enrichment_radar_latest').fetchone()[0]
                cols = {r[0] for r in conn.execute('DESCRIBE features_unified').fetchall()}
            self.assertEqual(n, 1)
            self.assertEqual(status, 'no_swath_coverage')
            self.assertTrue({'altimetry_status', 'radar_status', 'laser_diff_slope_600m_p50_deg',
                             'rcm_cpr_p50'} <= cols)


class EvidenceSyncTest(unittest.TestCase):
    def test_update_evidence_site_preserves_other_sections_on_disk(self):
        import json
        from scripts import etl_puentes

        with tempfile.TemporaryDirectory() as tmp:
            evidence_path = Path(tmp) / 'resultados.json'
            etl_puentes.update_evidence_site(
                evidence_path,
                'puentes-laser-radar-v1',
                'icesat2',
                {
                    'site': {'kind': 'control', 'region_id': 'control-v1:manicouagan-centro'},
                    'record': {'region_id': 'control-v1:manicouagan-centro', 'altimetry_status': 'measured'},
                    'diagnostics': {'read_seconds': 1.2},
                },
            )
            etl_puentes.update_evidence_site(
                evidence_path,
                'puentes-laser-radar-v1',
                'rcm',
                {
                    'site': {'kind': 'control', 'region_id': 'control-v1:manicouagan-centro'},
                    'record': {'region_id': 'control-v1:manicouagan-centro', 'radar_status': 'measured'},
                    'diagnostics': {'n_scenes': 12},
                },
            )
            data = json.loads(evidence_path.read_text(encoding='utf-8'))
            self.assertEqual(data['spec_id'], 'puentes-laser-radar-v1')
            self.assertEqual(
                [e['site']['region_id'] for e in data['icesat2']],
                ['control-v1:manicouagan-centro'],
            )
            self.assertEqual(
                [e['site']['region_id'] for e in data['rcm']],
                ['control-v1:manicouagan-centro'],
            )

    def test_sync_and_run_summary_reconstruct_from_store_and_preserve_extra_keys(self):
        import argparse
        import json
        from datetime import timedelta
        from scripts import etl_puentes

        alt_row = {
            'region_id': 'control-v1:manicouagan-centro',
            'instrument': 'ICESat-2/ATLAS ATL08',
            'product_id': alt.PRODUCT_ID,
            'observation_period': '2020-03-15/2026-04-02',
            'granules_found': 43,
            'granules_with_data': 7,
            'n_tracks': 13,
            'n_segments': 311,
            'n_pairs_20m': 1519,
            'n_pairs_100m': 291,
            'n_diff_200m': 238,
            'n_diff_600m': 147,
            'altimetry_status': 'measured',
            'source_manifest_id': 'm-alt',
            'updated_at': NOW,
            **{k: 1.0 for k in alt.ALTIMETRY_METRICS},
        }
        radar_measured = {
            'region_id': 'control-v1:manicouagan-centro',
            'instrument': 'RCM',
            'product_id': radar.PRODUCT_ID,
            'observation_period': '2025-07-04/2026-09-01',
            'scenes_found': 60,
            'n_scenes': 12,
            **{k: 0.5 for k in radar.RADAR_VALUE_KEYS},
            'rcm_valid_fraction': 0.98,
            'radar_status': 'measured',
            'source_manifest_id': 'm-rad',
            'updated_at': NOW - timedelta(seconds=10),
        }
        radar_uncovered = {
            'region_id': 'control-v1:mistastin-sur',
            'instrument': 'RCM',
            'product_id': radar.PRODUCT_ID,
            'observation_period': None,
            'scenes_found': 0,
            'n_scenes': 0,
            **dict.fromkeys(radar.RADAR_VALUE_KEYS),
            'rcm_valid_fraction': 0.0,
            'radar_status': 'no_swath_coverage',
            'source_manifest_id': 'none',
            'updated_at': NOW,
        }
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            store = FeatureStore(tmp_path / 'store')
            store.append_enrichment('altimetry', [alt_row])
            store.append_enrichment('radar', [radar_measured, radar_uncovered])

            spec_path = tmp_path / 'spec.json'
            spec_path.write_text(
                json.dumps({
                    'spec_id': 'puentes-laser-radar-v1',
                    'control_sites': [
                        {
                            'id': 'manicouagan-centro',
                            'region_id': 'control-v1:manicouagan-centro',
                            'name': 'Manicouagan',
                            'longitude': -68.7,
                            'latitude': 51.38,
                            'icesat2': True,
                            'rcm': True,
                        },
                        {
                            'id': 'mistastin-sur',
                            'region_id': 'control-v1:mistastin-sur',
                            'name': 'Mistastin',
                            'longitude': -63.3,
                            'latitude': 55.82,
                            'icesat2': True,
                            'rcm': True,
                        },
                    ],
                }),
                encoding='utf-8',
            )
            evidence_path = tmp_path / 'resultados.json'
            evidence_path.write_text(
                json.dumps({
                    'spec_id': 'puentes-laser-radar-v1',
                    'cmr_inventory_and_pilot': {'total_granules': 1263},
                    'rcm': [
                        {
                            'site': {'kind': 'control', 'region_id': 'control-v1:manicouagan-centro'},
                            'record': {
                                'region_id': 'control-v1:manicouagan-centro',
                                'radar_status': 'measured',
                                'updated_at': NOW.isoformat(),
                            },
                            'diagnostics': {'passes_by_direction': {'Descending': 9, 'Ascending': 3}},
                        }
                    ],
                }),
                encoding='utf-8',
            )

            args = argparse.Namespace(
                evidence=evidence_path,
                store_dir=tmp_path / 'store',
                spec=spec_path,
                memory_limit='1GB',
                threads=1,
                arid_limit=8,
                polar_limit=12,
                no_sync_from_store=False,
            )
            etl_puentes.run_summary(args)

            data = json.loads(evidence_path.read_text(encoding='utf-8'))
            self.assertEqual(data['cmr_inventory_and_pilot'], {'total_granules': 1263})
            ice_by_id = {e['site']['region_id']: e for e in data['icesat2']}
            rcm_by_id = {e['site']['region_id']: e for e in data['rcm']}
            self.assertEqual(set(ice_by_id), {'control-v1:manicouagan-centro'})
            self.assertEqual(ice_by_id['control-v1:manicouagan-centro']['record']['n_pairs_100m'], 291)
            self.assertTrue(ice_by_id['control-v1:manicouagan-centro']['diagnostics']['reconstructed_from_store'])
            self.assertEqual(set(rcm_by_id), {'control-v1:manicouagan-centro', 'control-v1:mistastin-sur'})
            self.assertEqual(rcm_by_id['control-v1:mistastin-sur']['record']['radar_status'], 'no_swath_coverage')
            # Existing richer live RCM entry should not be overwritten by older/equal store row.
            self.assertEqual(
                rcm_by_id['control-v1:manicouagan-centro']['diagnostics']['passes_by_direction'],
                {'Descending': 9, 'Ascending': 3},
            )
            self.assertIn('summary', data)


if __name__ == '__main__':
    unittest.main()
