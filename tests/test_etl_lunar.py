"""Tests for the Moon in the feature store contract (audit 2026-11-14, section 2.1)."""
from __future__ import annotations

from datetime import datetime, timezone
import json
import math
from pathlib import Path
import tempfile
import unittest

import numpy as np
import pyarrow as pa
import rasterio
from pyproj import Transformer
from rasterio.transform import from_origin

from pipelines import etl_contract as contract
from pipelines import etl_lunar as lunar
from pipelines.etl_store import FeatureStore

NOW = datetime(2026, 11, 14, 12, 0, tzinfo=timezone.utc)
SITE = {'id': 'sintetico', 'name': 'Sitio sintético', 'longitude': -5.0, 'latitude': -87.45,
        'dem_source': 'dem'}
GRADIENT = 0.1  # m/m along stereographic x -> about 5.71 deg


def write_polar_raster(path: Path, fn, crs=lunar.SOUTH_POLAR_STEREO, half=7000, cell=20.0) -> None:
    """GeoTIFF in lunar south polar stereographic around SITE; values = fn(x, y) in that CRS."""
    x0, y0 = Transformer.from_crs(crs.geodetic_crs, crs, always_xy=True).transform(SITE['longitude'], SITE['latitude'])
    n = int(2 * half / cell)
    xs = x0 - half + (np.arange(n) + 0.5) * cell
    ys = y0 + half - (np.arange(n) + 0.5) * cell
    xx, yy = np.meshgrid(xs, ys)
    data = fn(xx - x0, yy - y0).astype('float32')
    with rasterio.open(path, 'w', driver='GTiff', height=n, width=n, count=1, dtype='float32', nodata=np.nan,
                       crs=crs, transform=from_origin(x0 - half, y0 + half, cell, cell)) as dst:
        dst.write(data, 1)


def spec_with(sources: dict) -> dict:
    spec = json.loads(lunar.SPEC_PATH.read_text(encoding='utf-8'))
    for sid, src in sources.items():
        spec['sources'][sid] = src
    return spec


class TestLunarGeometry(unittest.TestCase):
    def test_partition_is_polar_stereographic_by_hemisphere(self) -> None:
        self.assertEqual(lunar.polar_partition(-87.45), 'MOON_SPS')
        self.assertEqual(lunar.polar_partition(85.0), 'MOON_NPS')
        with self.assertRaises(ValueError):
            lunar.polar_partition(10.0)

    def test_rejects_rasters_not_on_the_lunar_sphere(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'tierra.tif'
            with rasterio.open(path, 'w', driver='GTiff', height=4, width=4, count=1, dtype='float32',
                               crs='EPSG:4326', transform=from_origin(0, 4, 1, 1)) as dst:
                dst.write(np.zeros((4, 4), 'float32'), 1)
            with self.assertRaisesRegex(ValueError, 'lunar'):
                lunar.read_footprint(str(path), lunar.core_footprint(-5.0, -87.45))


class TestLunarTopography(unittest.TestCase):
    def test_plane_gives_expected_slope_with_the_earth_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'dem.tif'
            write_polar_raster(path, lambda x, y: 1000.0 + GRADIENT * x)
            dem = {'path': str(path), 'product_id': 'synthetic-lola', 'asset_id': 'dem.tif'}
            row, manifests, diag = lunar.extract_lunar_window(SITE, dem, NOW)
        # Polar stereographic scale at 87.45 deg S is (1 + sin 87.45)/2; slope in true metres.
        k = (1 + math.sin(math.radians(87.45))) / 2
        expected = math.degrees(math.atan(GRADIENT / k))
        self.assertEqual(row['body'], 'Moon')
        self.assertEqual(row['utm_zone_band'], 'MOON_SPS')
        self.assertEqual(row['qa_status'], 'rankable')
        self.assertEqual(row['analog_surface_eligibility'], 'moon_reference_surface')
        self.assertEqual((row['window_m'], row['cell_m'], row['slope_base_m'], row['roughness_radius_m']),
                         (3000, 30, 240, 360))
        self.assertAlmostEqual(row['slope_240m_p50_deg'], expected, delta=0.02)
        self.assertAlmostEqual(row['slope_240m_p90_deg'], expected, delta=0.02)
        self.assertAlmostEqual(row['hypsometric_integral'], 0.5, delta=0.02)
        self.assertGreater(row['aspect_240m_resultant_length'], 0.99)
        self.assertEqual(row['slope_240m_gt15_fraction'], 0.0)
        self.assertAlmostEqual(diag['support_mean'], 1.0)
        self.assertEqual(manifests[0]['planetary_frame'], 'MOON_ME_DE421')
        self.assertIn('1737400', manifests[0]['crs_wkt'])
        self.assertEqual(manifests[0]['access_mode'], 'cache')
        contract.validate_table(pa.Table.from_pylist([row], schema=contract.BASE_WINDOWS_SCHEMA), 'base_windows')

    def test_window_outside_the_dem_is_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'dem.tif'
            write_polar_raster(path, lambda x, y: np.full(x.shape, np.nan))
            row, manifests, _ = lunar.extract_lunar_window(
                SITE, {'path': str(path), 'product_id': 'p', 'asset_id': 'a'}, NOW)
        self.assertEqual(row['qa_status'], 'dem_unavailable')
        self.assertIsNone(row['relief_p95_p05_m'])
        self.assertEqual(manifests, [])


class TestLunarDimensions(unittest.TestCase):
    def setUp(self) -> None:
        self.base = {'slope_240m_p90_deg': 8.0}
        self.thresholds = lunar.load_spec()['site_gate'][lunar.LUNAR_SITE_PROFILE]

    def test_psr_fraction_and_unconfirmed_products(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'psr.tif'
            write_polar_raster(path, lambda x, y: (x < 500).astype('float32'))
            spec = spec_with({'lola_lpsr_80s_20mpp': {
                'status': 'confirmed', 'path': str(path), 'product_id': 'psr', 'asset_id': 'psr.tif',
                'valid_range': [0, 1]}})
            row, manifests, _ = lunar.extract_lunar_dimensions(SITE, self.base, spec, NOW)
        self.assertEqual(row['psr_status'], 'measured')
        self.assertAlmostEqual(row['psr_fraction'], 2 / 3, delta=0.03)
        self.assertEqual(row['psr_valid_fraction'], 1.0)
        for dim in ('illumination', 'diviner_temperature', 'diviner_regolith', 'minirf'):
            self.assertEqual(row[f'{dim}_status'], 'on_demand_fetchable')
            self.assertIsNone(row[f'{dim}_valid_fraction'])
        self.assertEqual(row['lunar_site_status'], 'volatile_target_psr')
        self.assertEqual(len(manifests), 1)
        contract.validate_table(pa.Table.from_pylist([row], schema=contract.ENRICHMENT_LUNAR_SCHEMA),
                                'enrichment_lunar')

    def test_diviner_amplitude_is_per_cell(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmax, tmin = Path(tmp) / 'tmax.tif', Path(tmp) / 'tmin.tif'
            write_polar_raster(tmax, lambda x, y: 100.0 + 0.01 * (x + 7000))
            write_polar_raster(tmin, lambda x, y: 30.0 + 0.01 * (x + 7000))
            spec = spec_with({
                'diviner_tmax_south': {'status': 'confirmed', 'path': str(tmax), 'product_id': 'd', 'asset_id': 'tmax'},
                'diviner_tmin_south': {'status': 'confirmed', 'path': str(tmin), 'product_id': 'd', 'asset_id': 'tmin'},
            })
            row, _, _ = lunar.extract_lunar_dimensions(SITE, self.base, spec, NOW)
        self.assertEqual(row['diviner_temperature_status'], 'measured')
        self.assertAlmostEqual(row['diviner_tamp_p50_k'], 70.0, places=3)
        self.assertAlmostEqual(row['diviner_tmax_p50_k'] - row['diviner_tmin_p50_k'], 70.0, delta=0.5)

    def test_site_gate_order(self) -> None:
        gate = lunar.classify_lunar_site
        t = self.thresholds
        self.assertEqual(gate({'slope_240m_p90_deg': 30.0}, {'psr_fraction': 0.9}, t), 'volatile_target_psr')
        self.assertEqual(gate({'slope_240m_p90_deg': 30.0}, {'psr_fraction': 0.1}, t), 'excluded_steep')
        self.assertEqual(gate({'slope_240m_p90_deg': None}, {}, t), 'pending_topography')
        self.assertEqual(gate(self.base, {'psr_fraction': 0.0}, t), 'pending_illumination')
        self.assertEqual(gate(self.base, {'illumination_mean_fraction': 0.1}, t), 'excluded_low_illumination')
        self.assertEqual(gate(self.base, {'illumination_mean_fraction': 0.6}, t), 'base_candidate_illuminated')


class TestSitePosition(unittest.TestCase):
    def test_peak_at_centre_and_offset_peak(self) -> None:
        n = 100  # 3 km core at 30 m
        yy, xx = np.mgrid[0:n, 0:n] - (n / 2 - 0.5)
        cone = 1000.0 - 10.0 * np.hypot(xx, yy)
        psr = np.zeros((n, n))
        centred = lunar.site_position_check(cone, psr)
        self.assertGreater(centred['centre_elevation_percentile_in_core'], 0.99)
        self.assertLess(centred['distance_to_local_max_m'], 30.0)
        self.assertEqual((centred['psr_at_centre'], centred['psr_core_fraction']), (0.0, 0.0))
        shifted = lunar.site_position_check(1000.0 - 10.0 * np.hypot(xx - 6, yy), None)
        self.assertAlmostEqual(shifted['distance_to_local_max_m'], 180.0, delta=30.0)
        self.assertIsNone(shifted['psr_at_centre'])


class TestLunarStore(unittest.TestCase):
    def test_moon_rows_in_unified_view_and_out_of_earth_ranking(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dem, psr = Path(tmp) / 'dem.tif', Path(tmp) / 'psr.tif'
            write_polar_raster(dem, lambda x, y: 1000.0 + GRADIENT * x)
            write_polar_raster(psr, lambda x, y: np.zeros(x.shape))
            spec = spec_with({'lola_lpsr_80s_20mpp': {
                'status': 'confirmed', 'path': str(psr), 'product_id': 'psr', 'asset_id': 'psr.tif'}})
            base, manifests, _ = lunar.extract_lunar_window(
                SITE, {'path': str(dem), 'product_id': 'dem', 'asset_id': 'dem.tif'}, NOW)
            dims, dim_manifests, _ = lunar.extract_lunar_dimensions(SITE, base, spec, NOW)
            earth = {**base, 'region_id': 'earth-1', 'body': 'Earth', 'grid_version': 'utm-ups-v1',
                     'utm_zone_band': 'N05', 'batch_id': 'b', 'analog_surface_eligibility': 'eligible_polar_cold_exposed',
                     'eligibility_profile': 'polar_cold_v1', 'cover_status': 'measured', 'cover_valid_fraction': 1.0,
                     'bare_or_sparse_fraction': 0.9, 'trees_fraction': 0.0, 'built_fraction': 0.0,
                     'permanent_water_fraction': 0.0, 'snow_ice_fraction': 0.05, 'moss_lichen_fraction': 0.05,
                     'water_occurrence_ge50_fraction': 0.0}
            store = FeatureStore(Path(tmp) / 'store')
            store.write_base_batch(base['batch_id'], [base], manifests)
            store.write_base_batch('b', [earth], [{
                'source_manifest_id': 'm', 'product_id': 'copernicus-glo30', 'asset_id': 'tile',
                'access_mode': 'cache', 'sha256_or_etag': None, 'native_resolution_m': 30.0,
                'effective_resolution_m': 30.0, 'observation_period': 'static', 'created_at': NOW}])
            store.append_enrichment('lunar', [dims], dim_manifests)
            self.assertTrue((Path(tmp) / 'store/base/utm_zone_band=MOON_SPS').is_dir())
            with store._connect() as conn:
                cur = conn.execute(
                    'SELECT region_id, body, psr_status, psr_fraction, illumination_status, lunar_site_status, '
                    'abs_al_oh_2p20um_status, hls_status, thermal_status FROM features_unified ORDER BY body')
                rows = {r[1]: r for r in cur.fetchall()}
                frames = dict(conn.execute(
                    "SELECT asset_id, planetary_frame FROM read_parquet(?)",
                    [str(Path(tmp) / 'store/manifests/*.parquet')]).fetchall())
            ranked = store.rank_similar(1.0, 5.0, 5.0, profile='polar_cold_v1', only_eligible=False)
        moon, earth_row = rows['Moon'], rows['Earth']
        self.assertEqual(moon[2:6], ('measured_absent', 0.0, 'on_demand_fetchable', 'pending_illumination'))
        self.assertEqual(moon[6:], ('unobserved_by_product',) * 3)
        self.assertEqual(earth_row[2], 'unobserved_by_product')
        self.assertIsNone(earth_row[5])
        self.assertEqual(frames, {'dem.tif': 'MOON_ME_DE421', 'psr.tif': 'MOON_ME_DE421', 'tile': 'EARTH_WGS84'})
        self.assertEqual([r['region_id'] for r in ranked], ['earth-1'])


class TestLunarSpec(unittest.TestCase):
    def test_store_spec_and_lunar_spec_align_with_contract(self) -> None:
        store_spec = contract.load_store_spec()
        self.assertEqual(store_spec['enums']['body'], list(contract.BODY_ENUM))
        self.assertEqual(store_spec['enums']['planetary_frame'], list(contract.PLANETARY_FRAME_ENUM))
        self.assertEqual(store_spec['enums']['lunar_site_status'], list(lunar.LUNAR_SITE_STATUS_ENUM))
        self.assertIn('enrichment_lunar', store_spec['tables'])
        spec = lunar.load_spec()
        self.assertEqual(set(spec['dimensions']), set(lunar.LUNAR_DIMENSIONS))
        for dim, dim_spec in spec['dimensions'].items():
            self.assertEqual(set(dim_spec['layers']), set(lunar.LUNAR_DIMENSIONS[dim]))
            for layer in dim_spec['layers'].values():
                self.assertIn(layer['source'], spec['sources'])
        for site in spec['sites']:
            self.assertEqual(spec['sources'][site['dem_source']]['status'], 'confirmed')
            lunar.polar_partition(site['latitude'])



class MirrorLookupTests(unittest.TestCase):
    """`source_path` prefers a complete mirrored copy over a remote range read."""
    SOURCE = {'asset_id': 'LDEM_80S_20MPP_ADJ.TIF', 'url': 'https://example.org/LDEM.TIF'}

    def test_without_a_complete_copy_it_reads_the_url(self) -> None:
        from unittest import mock
        from pipelines import etl_mirror
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict('os.environ', {'ANALOGOS_MIRROR_DIR': tmp}):
            self.assertEqual(lunar.source_path(self.SOURCE), '/vsicurl/https://example.org/LDEM.TIF')
            item = next(p for p in etl_mirror.load_manifest()['products'] if p['asset_id'] == self.SOURCE['asset_id'])
            copy = Path(tmp) / item['path']
            copy.parent.mkdir(parents=True)
            copy.write_bytes(b'incompleto')  # wrong size: ignored
            self.assertTrue(lunar.source_path(self.SOURCE).startswith('/vsicurl/'))

    def test_a_complete_copy_overrides_the_url(self) -> None:
        from unittest import mock
        from pipelines import etl_mirror
        manifest = {'products': [{'id': 'x', 'asset_id': 'LDEM_80S_20MPP_ADJ.TIF', 'bytes': 4, 'path': 'a/b.tif'}]}
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict('os.environ', {'ANALOGOS_MIRROR_DIR': tmp}):
            (Path(tmp) / 'a').mkdir()
            (Path(tmp) / 'a/b.tif').write_bytes(b'1234')
            with mock.patch.object(etl_mirror, 'load_manifest', return_value=manifest):
                self.assertEqual(lunar.source_path(self.SOURCE), str(Path(tmp) / 'a/b.tif'))


if __name__ == '__main__':
    unittest.main()


class TestLunarImport(unittest.TestCase):
    def test_import_writes_the_measured_evidence_to_the_store(self) -> None:
        import argparse
        import importlib.util
        root = Path(__file__).resolve().parents[1]
        loader = importlib.util.spec_from_file_location('etl_luna_script', root / 'scripts/etl_luna.py')
        script = importlib.util.module_from_spec(loader)
        loader.loader.exec_module(script)
        evidence = json.loads((root / 'docs/evidencia-luna-polar/resultados.json').read_text(encoding='utf-8'))
        expected = {e['base_window']['region_id']: e['base_window'] for e in evidence['sites']}
        with tempfile.TemporaryDirectory() as tmp:
            args = argparse.Namespace(evidence=str(root / 'docs/evidencia-luna-polar/resultados.json'),
                                      site=None, store_dir=str(Path(tmp) / 'store'), memory_limit='1GB', threads=1)
            script.run_import(args)
            script.run_import(args)  # idempotent: the latest lunar row wins, the base batch is replaced
            with FeatureStore(Path(tmp) / 'store')._connect() as conn:
                rows = conn.execute("SELECT region_id, relief_p95_p05_m, lunar_site_status FROM features_unified "
                                    "WHERE body = 'Moon' ORDER BY region_id").fetchall()
        self.assertEqual([r[0] for r in rows], sorted(expected))
        for region_id, relief, status in rows:
            self.assertAlmostEqual(relief, expected[region_id]['relief_p95_p05_m'], places=3)
            self.assertIsNotNone(status)
