"""Tests for the cover backfill over windows already in the store."""
from __future__ import annotations

from contextlib import ExitStack
from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest

import pyarrow as pa
import pyarrow.parquet as pq

from pipelines import etl_contract as contract
from pipelines import etl_cover as cover
from pipelines.etl_store import FeatureStore
from tests.test_etl_eligibility import SCENARIOS, base_row
from tests.test_etl_robustness import FakeRasters, first_site, synthetic_dem

NOW = datetime(2026, 11, 14, 12, 0, tzinfo=timezone.utc)
LEGACY_DROP = ('eligibility_profile', 'cover_status', 'cover_valid_fraction', 'snow_ice_fraction',
               'moss_lichen_fraction', 'water_occurrence_ge50_fraction', 'hypsometric_integral',
               'elevation_skew_p95_p05', 'aspect_240m_resultant_length', 'slope_240m_gt15_fraction',
               'slope_240m_gt25_fraction')


def write_legacy(store_root: Path, rows: list[dict]) -> None:
    """Base partition as written before cover statuses existed (cover never read)."""
    schema = pa.schema([f for f in contract.BASE_WINDOWS_SCHEMA if f.name not in LEGACY_DROP])
    legacy = []
    for r in rows:
        r = {k: v for k, v in r.items() if k in schema.names}
        r.update({'analog_surface_eligibility': 'pending_on_demand_cover_check', 'bare_or_sparse_fraction': None,
                  'trees_fraction': None, 'built_fraction': None, 'permanent_water_fraction': None})
        legacy.append(r)
    part = store_root / 'base' / 'utm_zone_band=N01'
    part.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pylist(legacy, schema=schema).drop(['utm_zone_band']), part / 'part_legacy.parquet')


def cover_row(region_id: str, status: str, eligibility: str, **fractions) -> dict:
    row = {f: None for f in contract.COVER_OVERLAY_FIELDS}
    row.update({'region_id': region_id, 'cover_status': status, 'analog_surface_eligibility': eligibility,
                'eligibility_profile': 'arid_mars_surface_v2', 'source_manifest_id': 'm', 'updated_at': NOW,
                'cover_valid_fraction': 1.0 if status == 'measured' else None, **fractions})
    return row


class TestCoverBackfill(unittest.TestCase):
    def test_overlay_selection_and_ranking(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'store'
            store = FeatureStore(root, memory_limit='512MB', threads=2)
            rows = [base_row(n, SCENARIOS[n]) for n in ('desert', 'forest', 'steppe')]
            for r in rows:
                r['longitude'], r['latitude'] = -110.6, 38.6
            write_legacy(root, rows)

            pending = cover.select_windows(store)
            self.assertEqual({w['region_id'] for w in pending}, {'desert', 'forest', 'steppe'})
            self.assertEqual(store.rank_similar(100.0, 3.0, 9.0), [])

            store.append_enrichment('cover', [
                cover_row('desert', 'measured', 'eligible_arid_exposed', **SCENARIOS['desert']),
                cover_row('forest', 'measured', 'excluded_dense_canopy', **SCENARIOS['forest']),
                cover_row('steppe', 'cover_fetch_failed', 'pending_on_demand_cover_check'),
            ])
            # Failed reads are selected again; measured windows are not.
            self.assertEqual([w['region_id'] for w in cover.select_windows(store)], ['steppe'])
            ranked = store.rank_similar(100.0, 3.0, 9.0)
            self.assertEqual([r['region_id'] for r in ranked], ['desert'])
            self.assertAlmostEqual(ranked[0]['bare_or_sparse_fraction'], SCENARIOS['desert']['bare_or_sparse_fraction'], places=6)
            # Other profiles are re-gated in SQL from the overlaid fractions.
            polar = store.rank_similar(100.0, 3.0, 9.0, profile='polar_cold_v1')
            # The polar profile also needs a cold climate, and this store has no global layers.
            self.assertEqual([r['region_id'] for r in polar], [])
            stats = store.store_stats()
            self.assertEqual(stats['by_eligibility']['eligible_arid_exposed'], 1)

    def test_shortlist_orders_by_topographic_distance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'store'
            store = FeatureStore(root, memory_limit='512MB', threads=2)
            rows = []
            for name, relief in (('far', 600.0), ('near', 121.0), ('mid', 300.0)):
                r = base_row(name, SCENARIOS['desert'])
                r['relief_p95_p05_m'] = relief
                rows.append(r)
            write_legacy(root, rows)
            ref = {'relief_m': 120.27, 'slope_p50_deg': 3.0, 'slope_p90_deg': 9.0}
            got = cover.select_windows(store, limit=2, order_by_reference=ref)
            self.assertEqual([w['region_id'] for w in got], ['near', 'mid'])

    def test_grouping_by_tiles(self) -> None:
        windows = [{'region_id': 'a', 'longitude': -110.6, 'latitude': 38.6},
                   {'region_id': 'b', 'longitude': -112.5, 'latitude': 38.6},
                   {'region_id': 'c', 'longitude': -68.4, 'latitude': -24.5}]
        groups = cover.group_windows(windows)
        self.assertEqual(set(groups), {(30, -120), (-30, -70)})
        self.assertEqual(set(groups[(30, -120)]), {(36, -111), (36, -114)})

    def test_cover_record_uses_stored_land_fraction(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, ExitStack() as stack:
            dem = Path(tmp) / 'dem.tif'
            synthetic_dem(dem)
            site = first_site()
            window = {'region_id': 'w', 'longitude': site['longitude'], 'latitude': site['latitude'],
                      'land_fraction': 1.0}
            from pipelines import atlas_topography as topo
            row, assets = cover.cover_record(window, topo.Land(), FakeRasters(stack, str(dem)), NOW)
            self.assertEqual(row['cover_status'], 'no_cover_tile')
            self.assertEqual(row['analog_surface_eligibility'], 'pending_on_demand_cover_check')
            self.assertEqual(assets, [])


if __name__ == '__main__':
    unittest.main()
