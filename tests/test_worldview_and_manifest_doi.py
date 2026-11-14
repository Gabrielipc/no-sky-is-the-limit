"""Tests for NASA Worldview blind-review links and Open Science Catalog DOIs in manifests (audit §4)."""
from __future__ import annotations

from datetime import datetime, timezone
import json
import math
from pathlib import Path
import tempfile
import unittest
from urllib.parse import parse_qs, urlparse

import pyarrow as pa
import pyarrow.parquet as pq

from pipelines import atlas_sources as sources
from pipelines import etl_contract as contract
from pipelines import etl_publish as publish
from pipelines import etl_surface_dimensions as surf
from pipelines import worldview_blind as wv
from pipelines.etl_store import FeatureStore
from tests.test_etl_eligibility import SCENARIOS, base_row

NOW = datetime(2026, 11, 14, 12, 0, tzinfo=timezone.utc)


class TestWorldviewBlindLinks(unittest.TestCase):
    def test_equal_metric_scale_fixed_date_and_blind_strips_labels(self) -> None:
        equator = wv.build_worldview_url(0.0, 0.0, half_span_km=6.0, date='2024-06-15', blind_mode=True)
        arctic = wv.build_worldview_url(
            -89.683,
            75.367,
            half_span_km=6.0,
            date='2024-06-15',
            layers=('VIIRS_SNPP_CorrectedReflectance_TrueColor', 'Reference_Labels_15m', 'Reference_Features_15m'),
            blind_mode=True,
        )
        self.assertEqual(equator['span_km'], 12.0)
        self.assertEqual(arctic['span_km'], 12.0)
        self.assertEqual(equator['date'], arctic['date'])

        # Metric lat span matches across latitudes; Arctic lon span widens by 1/cos(lat).
        eq_w, eq_s, eq_e, eq_n = equator['bbox_wgs84']
        ar_w, ar_s, ar_e, ar_n = arctic['bbox_wgs84']
        self.assertAlmostEqual(eq_n - eq_s, ar_n - ar_s, places=4)
        self.assertGreater(ar_e - ar_w, (eq_e - eq_w) * 3.5)
        self.assertAlmostEqual(
            (ar_e - ar_w) * math.cos(math.radians(75.367)),
            eq_e - eq_w,
            delta=0.005,
        )

        # Label and feature overlays must never appear in blind mode.
        self.assertNotIn('Reference_Labels_15m', arctic['layers'])
        self.assertNotIn('Reference_Features_15m', arctic['layers'])
        self.assertNotIn('Reference_Labels_15m', arctic['worldview_url'])
        self.assertIn('worldview.earthdata.nasa.gov', arctic['worldview_url'])
        self.assertIn('wvs.earthdata.nasa.gov/api/v1/snapshot', arctic['gibs_snapshot_url'])

        parsed_wv = parse_qs(urlparse(arctic['worldview_url']).query)
        self.assertIn('2024-06-15', parsed_wv['t'][0])

    def test_blind_review_package_hides_rank_distance_and_identity(self) -> None:
        cands = [
            {
                'region_id': 'utm-1', 'area_id': 'utah', 'rank': 1, 'distance_score': 0.12,
                'split': 'development', 'longitude': -110.6, 'latitude': 38.6,
                'relief_p95_p05_m': 45.0, 'slope_240m_p50_deg': 2.1, 'hypsometric_integral': 0.55,
            },
            {
                'region_id': 'utm-2', 'area_id': 'atacama', 'rank': 2, 'distance_score': 0.25,
                'split': 'development', 'longitude': -67.9, 'latitude': -25.0,
                'relief_p95_p05_m': 82.0, 'slope_240m_p50_deg': 3.4, 'hypsometric_integral': 0.61,
            },
            {
                'region_id': 'utm-3', 'area_id': 'devon', 'rank': 3, 'distance_score': 0.41,
                'split': 'control', 'longitude': -89.683, 'latitude': 75.367,
                'relief_p95_p05_m': 110.0, 'slope_240m_p50_deg': 4.0, 'hypsometric_integral': 0.49,
            },
        ]
        pkg_a = wv.build_blind_review_package(cands)
        pkg_b = wv.build_blind_review_package(list(reversed(cands)))

        # Shuffled order depends strictly on region_id HMAC, never on rank/input order.
        self.assertEqual([r['bbox_wgs84'] for r in pkg_a['blind_sheet']], [r['bbox_wgs84'] for r in pkg_b['blind_sheet']])
        self.assertEqual([r['blind_id'] for r in pkg_a['blind_sheet']], ['BLIND-001', 'BLIND-002', 'BLIND-003'])

        serialized_sheet = json.dumps(pkg_a['blind_sheet'])
        for forbidden in ('utm-1', 'utm-2', 'utm-3', 'utah', 'atacama', 'devon', '0.12', '0.25', '0.41', 'distance_score'):
            self.assertNotIn(forbidden, serialized_sheet)
        for item in pkg_a['blind_sheet']:
            self.assertTrue(set(item.keys()).isdisjoint(wv.FORBIDDEN_BLIND_KEYS))
            self.assertTrue(set(item['review_fields'].keys()).isdisjoint(wv.FORBIDDEN_BLIND_KEYS))

        recovered = {v['region_id']: v['rank'] for v in pkg_a['unblinding_key'].values()}
        self.assertEqual(recovered, {'utm-1': 1, 'utm-2': 2, 'utm-3': 3})


class TestManifestDOIsAndPublish(unittest.TestCase):
    def test_source_manifests_preserve_osc_doi_and_publish_exports_it(self) -> None:
        self.assertEqual(sources.CATALOG['esa_cci_permafrost']['doi'], '10.5285/6ef1a60b678f4048a20b5c8d94d665c9')
        self.assertEqual(sources.CATALOG['esa_cci_permafrost']['product_version'], '5.0')

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = FeatureStore(root / 'store', memory_limit='512MB', threads=2)
            base_rows = [
                {
                    **base_row('utm-ups-v1-10000-32612-420-50-a', SCENARIOS['desert']),
                    'relief_p95_p05_m': 121.0,
                    'slope_240m_p50_deg': 3.1,
                    'slope_240m_p90_deg': 9.3,
                    'roughness_360m_p50_m': 7.0,
                    'qa_status': 'rankable',
                    'source_manifest_id': 'm1',
                }
            ]
            # Write GLO-30/WorldCover manifests (auto-enriched from catalog) + ESA CCI Permafrost OSC manifest.
            manifests = [
                {
                    'source_manifest_id': 'm1', 'product_id': pid, 'asset_id': aid, 'access_mode': 'cache',
                    'sha256_or_etag': 'abc', 'native_resolution_m': 30.0, 'effective_resolution_m': 30.0,
                    'observation_period': 'static', 'created_at': NOW,
                }
                for pid, aid in (('copernicus-glo30', 'dem.tif'), ('esa-worldcover-2021', 'wc.tif'), ('jrc-gsw-v1_5', 'jrc.tif'))
            ] + surf.build_surface_source_manifests(fetched_at=NOW)
            store.write_base_batch('b1', base_rows, manifests)
            store.mark_batch_completed('b1', {'status': 'complete'})

            releases = root / 'releases'
            releases.mkdir()
            manifest = publish.publish_release(store, 'doi-test-r1', root=releases, set_current=True)
            self.assertIn('esa_cci_permafrost', manifest['source_catalog'])

            published_sources = json.loads((releases / 'doi-test-r1' / 'sources.json').read_text(encoding='utf-8'))
            self.assertEqual(published_sources['dem.tif']['doi'], '10.5270/ESA-c5d3d65')
            self.assertEqual(published_sources['wc.tif']['doi'], '10.5281/zenodo.7254221')
            self.assertEqual(published_sources['wc.tif']['product_version'], 'v200')
            pf = published_sources['permafrost:primary:ESA_CCI_PERMAFROST_v5.0']
            self.assertEqual(pf['doi'], '10.5285/6ef1a60b678f4048a20b5c8d94d665c9')
            self.assertEqual(pf['product_version'], '5.0')

    def test_publish_handles_legacy_manifest_parquet_without_doi(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = FeatureStore(root / 'store', memory_limit='512MB', threads=2)
            row = {
                **base_row('utm-ups-v1-10000-32612-420-50-leg', SCENARIOS['desert']),
                'relief_p95_p05_m': 121.0,
                'slope_240m_p50_deg': 3.1,
                'slope_240m_p90_deg': 9.3,
                'roughness_360m_p50_m': 7.0,
                'qa_status': 'rankable',
                'source_manifest_id': 'm-leg',
            }
            store.write_base_batch('b1', [row], manifests=None)
            store.mark_batch_completed('b1', {'status': 'complete'})

            # Write a legacy Parquet manifest without `doi` or `product_version` columns.
            legacy_schema = pa.schema([
                f for f in contract.SOURCE_MANIFESTS_SCHEMA if f.name not in ('doi', 'product_version')
            ])
            legacy_rows = [
                {
                    'source_manifest_id': 'm-leg', 'product_id': pid, 'asset_id': aid, 'access_mode': 'cache',
                    'sha256_or_etag': 'x', 'native_resolution_m': 30.0, 'effective_resolution_m': 30.0,
                    'observation_period': 'static', 'created_at': NOW, 'crs_wkt': None, 'planetary_frame': 'EARTH_WGS84',
                }
                for pid, aid in (('copernicus-glo30', 'dem.tif'), ('esa-worldcover-2021', 'wc.tif'), ('jrc-gsw-v1_5', 'jrc.tif'))
            ]
            pq.write_table(pa.Table.from_pylist(legacy_rows, schema=legacy_schema),
                           store.root / 'manifests' / 'sources_legacy.parquet', compression='zstd')

            releases = root / 'releases'
            releases.mkdir()
            publish.publish_release(store, 'legacy-r1', root=releases)
            published_sources = json.loads((releases / 'legacy-r1' / 'sources.json').read_text(encoding='utf-8'))
            self.assertIsNone(published_sources['dem.tif']['doi'])
            self.assertIsNone(published_sources['dem.tif']['product_version'])


if __name__ == '__main__':
    unittest.main()
