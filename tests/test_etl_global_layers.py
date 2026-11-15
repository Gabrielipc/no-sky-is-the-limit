"""Offline tests of the global coarse surface layer (build with fake products, sample, store)."""
from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
import tempfile
import unittest

import numpy as np
from pyproj import CRS
import rasterio
from rasterio.transform import from_origin

from pipelines import etl_global_layers as gl
from pipelines.etl_global_schema import GLOBAL_COLUMNS, GLOBAL_LAYERS
from pipelines.etl_store import FeatureStore


class FakeDataset:
    def __init__(self, data, attrs=None):
        self.data = np.asarray(data)
        self.attrs = attrs or {}
        self.ndim = self.data.ndim
        self.shape = self.data.shape

    def __getitem__(self, key):
        return self.data[key]


class FakeH5(dict):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def granule(gid: str, day: date, url: str | None = None) -> dict:
    return {'id': gid, 'url': url or f'https://example.test/{gid}.hdf', 'time_start': f'{day.isoformat()}T00:00:00Z'}


def months(year: int) -> list[date]:
    return [date(year, m, 1) for m in range(1, 13)]


class BuildTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.layers = root / 'layers'
        self.cache = root / 'cache'
        self.cache.mkdir()
        self.spec = gl.load_spec()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def ctx(self, **kw) -> gl.BuildContext:
        return gl.BuildContext(out_dir=self.layers, cache_dir=self.cache, workers=1, **kw)

    def test_imerg_annual_total_and_dry_months(self) -> None:
        # 36 lon x 18 lat (10° cells); rate 1 mm/h everywhere except a dry pixel (0 mm/h).
        def opener(url):
            rate = np.ones((1, 36, 18), dtype='float32')
            rate[0, 0, 0] = 0.0          # lon -175, lat -85 (south-west corner)
            rate[0, 1, 0] = -9999.9      # missing pixel
            return FakeH5({'Grid/precipitation': rate})

        grans = [granule(f'imerg-{d:%Y%m}', d) for d in months(2021)]
        cfg = self.spec['layers']['imerg'] | {'period': {'start': '2021-01-01', 'end': '2021-12-31'}}
        meta = gl.build_imerg(cfg, self.ctx(search=lambda *a, **k: grans, opener=opener))
        self.assertEqual(len(meta['granules']), 12)
        with rasterio.open(self.layers / 'imerg' / 'precip_annual_mm.tif') as src:
            annual = src.read(1)
            self.assertEqual(annual.shape, (18, 36))
            self.assertAlmostEqual(src.transform.a, 10.0)
        self.assertAlmostEqual(float(annual[0, 5]), 8760.0, places=1)    # 365 days * 24 h * 1 mm/h
        self.assertAlmostEqual(float(annual[-1, 0]), 0.0)                 # south-west dry pixel, north-up
        self.assertTrue(np.isnan(annual[-1, 1]))
        with rasterio.open(self.layers / 'imerg' / 'dry_months_fraction.tif') as src:
            dry = src.read(1)
        self.assertEqual(float(dry[-1, 0]), 1.0)
        self.assertEqual(float(dry[0, 5]), 0.0)

    def test_snow_ignores_mask_codes(self) -> None:
        values = {'2021-01': 80, '2021-02': 20, '2021-03': 250}  # 250 = cloud, not a cover value

        def reader(path, layers):
            month = path.stem.split('_')[1]
            return {'Snow_Cover_Monthly_CMG': np.full((18, 36), values[month], dtype='uint8')}, None

        grans = [granule(f'snow_{d:%Y-%m}', d) for d in (date(2021, 1, 1), date(2021, 2, 1), date(2021, 3, 1))]
        downloaded = []
        cfg = self.spec['layers']['snow'] | {'period': {'start': '2021-01-01', 'end': '2021-03-31'}}
        gl.build_snow(cfg, self.ctx(search=lambda *a, **k: grans, reader=reader,
                                    downloader=lambda url, target: downloaded.append(target) or target.touch()))
        with rasterio.open(self.layers / 'snow' / 'snow_cover_mean_pct.tif') as src:
            self.assertAlmostEqual(float(src.read(1)[3, 3]), 50.0)
        with rasterio.open(self.layers / 'snow' / 'snow_months_fraction.tif') as src:
            self.assertAlmostEqual(float(src.read(1)[3, 3]), 0.5)
        self.assertTrue(downloaded and not any(p.exists() for p in downloaded))  # granules erased

    def test_ati_from_monthly_requires_valid_months(self) -> None:
        day = np.full((12, 1, 2), 310.0)
        night = np.full((12, 1, 2), 290.0)
        albedo = np.full((12, 1, 2), 0.2)
        night[3:, 0, 1] = np.nan  # only 3 valid months in the second pixel
        delta, alb, ati = gl.ati_from_monthly(day, night, albedo, min_delta_k=1.0, min_valid_months=4)
        self.assertAlmostEqual(float(ati[0, 0]), 0.8 / 20.0)
        self.assertAlmostEqual(float(delta[0, 0]), 20.0)
        self.assertAlmostEqual(float(alb[0, 0]), 0.2, places=6)
        self.assertTrue(np.isnan(ati[0, 1]))

    def test_build_ati_end_to_end(self) -> None:
        shape = (18, 36)

        def reader(path, layers):
            if 'LST_Day_CMG' in layers:
                raw_day = np.full(shape, int(305 / 0.02), dtype='uint16')
                raw_night = np.full(shape, int(285 / 0.02), dtype='uint16')
                qc = np.zeros(shape, dtype='uint8')
                return {'LST_Day_CMG': raw_day, 'LST_Night_CMG': raw_night, 'QC_Day': qc, 'QC_Night': qc}, None
            return {'Albedo_WSA_shortwave': np.full(shape, 250, dtype='int16'),
                    'BRDF_Quality': np.zeros(shape, dtype='uint8')}, None

        def search(collection, *a, **k):
            if collection['short_name'] == 'MYD11C3':
                return [granule(f'MYD11C3.{d:%Y%m}', d) for d in months(2023)]
            return [granule(f'MCD43C3.{d:%Y%m%d}', d) for d in (date(2023, m, 1) for m in range(1, 13))]

        cfg = self.spec['layers']['ati'] | {'albedo_step_days': 1}
        gl.build_ati(cfg, self.ctx(search=search, reader=reader, downloader=lambda u, t: t.touch()))
        with rasterio.open(self.layers / 'ati' / 'ati.tif') as src:
            self.assertAlmostEqual(float(src.read(1)[5, 5]), 0.75 / 20.0, places=5)

    def test_emissivity_mosaic_places_tiles_by_name(self) -> None:
        # ppd = 2 -> each 1° tile is 2x2 cells of 0.5°.
        tiles = {'AG1km.v003.39.-111.0010': 900, 'AG1km.v003.-03.105.0010': 950}

        def opener(url):
            gid = url.rsplit('/', 1)[1][:-3]
            return FakeH5({'Emissivity/Mean': np.full((5, 2, 2), tiles[gid], dtype='int16')})

        grans = [granule(g, date(2000, 1, 1), f'https://example.test/{g}.h5') for g in tiles]
        cfg = self.spec['layers']['emissivity'] | {'pixels_per_degree': 2}
        meta = gl.build_emissivity(cfg, self.ctx(search=lambda *a, **k: grans, opener=opener))
        self.assertEqual(meta['granules_count'], 2)
        with rasterio.open(self.layers / 'emissivity' / 'emissivity_b10_b14.tif') as src:
            self.assertEqual(src.count, 5)
            row, col = src.index(-110.5, 38.5)
            self.assertEqual(int(src.read(1)[row, col]), 900)
            row, col = src.index(105.5, -3.5)
            self.assertEqual(int(src.read(3)[row, col]), 950)
            row, col = src.index(0.25, 0.25)
            self.assertEqual(int(src.read(1)[row, col]), gl.AG1KM_NODATA)

    def test_emissivity_indices(self) -> None:
        bands = np.array([[0.90, 0.90], [0.95, 0.95], [0.90, 0.30], [0.96, 0.96], [0.97, 0.97]])
        idx = gl.emissivity_indices(bands)
        self.assertAlmostEqual(float(idx['emis_quartz_index_cmg'][0]), 0.95 ** 2 / (0.90 * 0.90))
        self.assertAlmostEqual(float(idx['emis_mafic_index_cmg'][0]), (0.90 + 0.95) / (0.90 + 0.96))
        self.assertAlmostEqual(float(idx['emis_carbonate_index_cmg'][0]), 0.96 / 0.97)
        self.assertTrue(np.isnan(idx['emis_mean_b10_b14_cmg'][1]))  # band out of the valid range

    def test_soil_moisture_quality_and_fill(self) -> None:
        def opener(url):
            sm = np.full((4, 6), 0.2, dtype='float32')
            qa = np.zeros((4, 6), dtype='uint16')
            sm[0, 0] = -9999.0
            qa[1, 1] = 1  # not recommended
            if url.endswith('2.h5'):
                sm[2, 2] = 0.4
            return FakeH5({'Soil_Moisture_Retrieval_Data_AM/soil_moisture': sm,
                           'Soil_Moisture_Retrieval_Data_AM/retrieval_qual_flag': qa})

        grans = [granule('smap1', date(2021, 1, 1), 'https://example.test/1.h5'),
                 granule('smap2', date(2021, 1, 9), 'https://example.test/2.h5')]
        cfg = self.spec['layers']['soil_moisture'] | {'period': {'start': '2021-01-01', 'end': '2021-01-31'}}
        gl.build_soil_moisture(cfg, self.ctx(search=lambda *a, **k: grans, opener=opener))
        with rasterio.open(self.layers / 'soil_moisture' / 'soil_moisture_mean.tif') as src:
            mean = src.read(1)
            self.assertEqual(CRS.from_user_input(src.crs).to_epsg(), 6933)
        self.assertTrue(np.isnan(mean[0, 0]) and np.isnan(mean[1, 1]))
        self.assertAlmostEqual(float(mean[2, 2]), 0.3, places=6)
        with rasterio.open(self.layers / 'soil_moisture' / 'soil_moisture_obs_fraction.tif') as src:
            self.assertEqual(float(src.read(1)[3, 3]), 1.0)

    def test_permafrost_grid_from_cf_coordinates(self) -> None:
        wkt = CRS.from_epsg(3995).to_wkt()

        def opener(url):
            x = np.array([0.0, 1000.0, 2000.0])
            y = np.array([-1000.0, 0.0, 1000.0])  # south to north: must be flipped
            pfr = np.array([[[10, 20, 30], [40, 50, 60], [70, 80, 90]]], dtype='int8')
            return FakeH5({'x': x, 'y': y, 'crs': FakeDataset([0], {'crs_wkt': wkt}),
                           'PFR': FakeDataset(pfr, {'grid_mapping': 'crs'})})

        gl.build_permafrost(self.spec['layers']['permafrost'], self.ctx(opener=opener))
        with rasterio.open(self.layers / 'permafrost' / 'permafrost_fraction_northern_hemisphere.tif') as src:
            data = src.read(1)
            self.assertAlmostEqual(float(data[0, 0]), 0.7)   # north row first
            self.assertAlmostEqual(src.transform.c, -500.0)

    def test_build_layers_skips_existing_and_reports_failures(self) -> None:
        def opener(url):
            return FakeH5({'Grid/precipitation': np.ones((1, 36, 18), dtype='float32')})

        grans = [granule(f'imerg-{d:%Y%m}', d) for d in months(2021)]
        spec = self.spec
        spec['layers']['imerg']['period'] = {'start': '2021-01-01', 'end': '2021-12-31'}
        ctx = self.ctx(search=lambda *a, **k: grans, opener=opener)
        first = gl.build_layers(['imerg'], ctx, spec)
        self.assertEqual(first['imerg']['status'], 'built')
        meta = gl.read_layer_meta(self.layers / 'imerg')
        self.assertEqual(len(meta['outputs']['precip_annual_mm']['sha256']), 64)
        self.assertEqual(gl.build_layers(['imerg'], ctx, spec)['imerg']['status'], 'skipped_existing')
        failed = gl.build_layers(['snow'], self.ctx(search=lambda *a, **k: []), spec)
        self.assertEqual(failed['snow']['status'], 'failed')


class SampleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_nearest_cell_and_outside(self) -> None:
        data = np.arange(18 * 36, dtype='float32').reshape(18, 36)
        path = gl.write_raster(self.root / 'r.tif', data, gl.WGS84, gl.geo_transform(data.shape))
        vals, inside = gl.sample_raster(path, np.array([-175.0, 5.0, 0.0]), np.array([85.0, -5.0, 95.0]))
        self.assertEqual(float(vals[0, 0]), 0.0)
        self.assertEqual(float(vals[0, 1]), data[9, 18])
        self.assertFalse(inside[2])

    def test_footprint_mean_ignores_nodata(self) -> None:
        # 0.01° grid around (10, 10): footprint of 3 km covers ~3 cells per axis.
        data = np.full((200, 200), 1.0, dtype='float32')
        data[100, 100] = np.nan
        data[99, 99] = 4.0
        transform = from_origin(9.0, 11.0, 0.01, 0.01)
        path = gl.write_raster(self.root / 'f.tif', data, gl.WGS84, transform)
        vals, inside = gl.sample_raster(path, np.array([10.0]), np.array([10.0]), half_m=1500.0, strip_rows=37)
        self.assertTrue(inside[0])
        self.assertGreater(float(vals[0, 0]), 1.0)
        self.assertLess(float(vals[0, 0]), 4.0)
        vals_n, _ = gl.sample_raster(path, np.array([10.0]), np.array([10.0]))
        self.assertTrue(np.isnan(vals_n[0, 0]))  # nearest cell is the nodata one

    def test_projected_raster(self) -> None:
        data = np.full((10, 10), 0.25, dtype='float32')
        path = gl.write_raster(self.root / 'e.tif', data, gl.EASE2_CRS, gl.SMAP_TRANSFORM)
        vals, inside = gl.sample_raster(path, np.array([-179.9, 0.0]), np.array([84.0, 0.0]))
        self.assertTrue(inside[0])
        self.assertAlmostEqual(float(vals[0, 0]), 0.25)
        self.assertFalse(inside[1])  # far from the 10x10 corner raster

    def _imerg_layer(self, layers: Path) -> None:
        d = layers / 'imerg'
        annual = np.full((18, 36), 200.0, dtype='float32')
        annual[0, 0] = 20000.0  # out of contract range -> discarded
        gl.write_raster(d / 'precip_annual_mm.tif', annual, gl.WGS84, gl.geo_transform(annual.shape))
        gl.write_raster(d / 'dry_months_fraction.tif', np.full((18, 36), 0.5, dtype='float32'), gl.WGS84,
                        gl.geo_transform(annual.shape))
        gl.write_layer_meta(d, {'layer': 'imerg', 'products': ['GPM_3IMERGM.07'], 'granules': ['a'],
                                'period': '2021-01/2021-12', 'params': {},
                                'outputs': {'precip_annual_mm': 'precip_annual_mm.tif',
                                            'dry_months_fraction': 'dry_months_fraction.tif'}})

    def test_sample_columns_statuses_and_store_round_trip(self) -> None:
        layers = self.root / 'layers'
        self._imerg_layer(layers)
        lons, lats = np.array([5.0, -175.0]), np.array([5.0, 85.0])
        cols, sts = gl.sample_columns(lons, lats, layers, gl.built_layers(layers))
        self.assertEqual(float(cols['precip_annual_mm_cmg'][0]), 200.0)
        self.assertTrue(np.isnan(cols['precip_annual_mm_cmg'][1]))
        self.assertEqual(list(sts['imerg_cmg_status']), ['measured', 'insufficient_coverage'])
        self.assertTrue(all(s == 'on_demand_fetchable' for s in sts['snow_cmg_status']))

        now = datetime(2026, 11, 14, tzinfo=timezone.utc)
        manifest_id, manifests = gl.manifests_for(layers, now)
        self.assertEqual({m['product_id'] for m in manifests}, {'GPM_3IMERGM.07'})
        rows = gl.rows_from_columns(np.array(['w1', 'w2'], dtype=object), cols, sts, manifest_id, now)
        self.assertEqual(set(rows[0]) - {'region_id', 'global_layers_version', 'source_manifest_id', 'updated_at'},
                         set(GLOBAL_COLUMNS) | {f'{k}_cmg_status' for k in GLOBAL_LAYERS})
        store = FeatureStore(self.root / 'store')
        store.append_enrichment('global', rows, manifests)
        with store._connect() as conn:
            got = conn.execute('SELECT region_id, precip_annual_mm_cmg, imerg_cmg_status FROM enrichment_global_latest '
                               'ORDER BY region_id').fetchall()
        self.assertEqual(got[0][0], 'w1')
        self.assertAlmostEqual(got[0][1], 200.0)
        self.assertEqual(got[1][2], 'insufficient_coverage')


if __name__ == '__main__':
    unittest.main()


class CliSampleTest(unittest.TestCase):
    def test_sample_writes_every_earth_window_and_summary(self) -> None:
        from scripts import etl_capa_global as cli
        from tests.test_similarity_ml import base_row, REF
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = FeatureStore(root / 'store', memory_limit='512MB', threads=2)
            store.write_base_batch('b', [base_row('e1', 5.0, 5.0, dict(REF)), base_row('e2', -175.0, 85.0, dict(REF)),
                                         base_row('m1', 10.0, -89.0, dict(REF), body='Moon')])
            SampleTests._imerg_layer(None, root / 'layers')
            evidence = root / 'resumen.json'
            cli.main(['--layers-dir', str(root / 'layers'), 'sample', '--store-dir', str(root / 'store'),
                      '--memory-limit', '512MB', '--threads', '2', '--block-rows', '1', '--evidence', str(evidence)])
            with store._connect() as conn:
                rows = conn.execute('SELECT region_id, imerg_cmg_status, snow_cmg_status FROM features_unified '
                                    'ORDER BY region_id').fetchall()
            self.assertEqual(rows, [('e1', 'measured', 'on_demand_fetchable'),
                                    ('e2', 'insufficient_coverage', 'on_demand_fetchable'),
                                    ('m1', 'unobserved_by_product', 'unobserved_by_product')])
            summary = __import__('json').loads(evidence.read_text())
            self.assertEqual(summary['windows'], 2)
            self.assertEqual(summary['layers']['imerg']['status'], {'insufficient_coverage': 1, 'measured': 1})
            self.assertEqual(len(list((root / 'store' / 'enrichment' / 'global').glob('*.parquet'))), 1)  # compacted
