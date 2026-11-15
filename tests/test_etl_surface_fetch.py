"""Offline tests of the surface acquisition layer and MODIS apparent thermal inertia.

Every reader is driven with fake CMR searches, fake HDF5 files and fake HDF4 rasters built on
the real grids (IMERG 0.1°, EASE2 9 km, AG100 tiles, MODIS sinusoidal), so no request leaves
the machine.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
import tempfile
import unittest

from affine import Affine
import numpy as np
from pyproj import CRS

from pipelines import etl_surface_dimensions as surf
from pipelines import etl_surface_fetch as fetch
from pipelines.etl_store import FeatureStore
from scripts import etl_superficie as cli

NOW = datetime(2026, 11, 14, 12, 0, tzinfo=timezone.utc)
UTAH = fetch.Site('earth-utah-1', -110.5, 38.5)


class FakeDataset:
    def __init__(self, data, attrs=None):
        self.data = np.asarray(data)
        self.attrs = attrs or {}
        self.shape = self.data.shape
        self.ndim = self.data.ndim

    def __getitem__(self, key):
        return self.data[key]


class FakeH5(dict):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def granule(gid: str, day: date, url: str | None = None) -> dict:
    url = url or f'https://data.example/{gid}'
    return {'id': gid, 'url': url, 'time_start': f'{day.isoformat()}T00:00:00Z', 'links': [url]}


class TestApparentThermalInertia(unittest.TestCase):
    def _season_stack(self, n_pix=9, seasons=('2023-DJF', '2023-MAM', '2023-JJA'), n_obs=25):
        rng = np.random.default_rng(0)
        day, night, alb, ds, ns, als = [], [], [], [], [], []
        for k, season in enumerate(seasons):
            day.append(300.0 + k + rng.normal(0, 0.5, (n_obs, n_pix)))
            night.append(280.0 + k + rng.normal(0, 0.5, (n_obs, n_pix)))
            alb.append(np.full((3, n_pix), 0.2))
            ds += [season] * n_obs
            ns += [season] * n_obs
            als += [season] * 3
        return np.vstack(day), np.vstack(night), np.vstack(alb), np.array(ds), np.array(ns), np.array(als)

    def test_ati_value_and_status(self) -> None:
        out, frac, status = surf.compute_modis_ati_metrics(*self._season_stack())
        self.assertEqual(status, 'measured')
        self.assertAlmostEqual(frac, 1.0)
        self.assertAlmostEqual(out['modis_ati_p50_per_k'], 0.8 / 20.0, places=2)
        self.assertLess(out['modis_ati_iqr_per_k'], 0.01)

    def test_ati_needs_clear_observations_and_seasons(self) -> None:
        day, night, alb, ds, ns, als = self._season_stack()
        day[:, :3] = np.nan  # three of nine pixels never clear by day -> 6/9 < 80 %
        out, frac, status = surf.compute_modis_ati_metrics(day, night, alb, ds, ns, als)
        self.assertEqual(status, 'insufficient_coverage')
        self.assertAlmostEqual(frac, 6 / 9)
        self.assertIsNone(out['modis_ati_p50_per_k'])

        one_season = self._season_stack(seasons=('2023-JJA',))
        _, frac1, status1 = surf.compute_modis_ati_metrics(*one_season)
        self.assertEqual((status1, frac1), ('no_swath_coverage', 0.0))

    def test_ati_rejects_small_day_night_contrast(self) -> None:
        day, night, alb, ds, ns, als = self._season_stack()
        _, _, status = surf.compute_modis_ati_metrics(night + 0.5, night, alb, ds, ns, als)
        self.assertEqual(status, 'no_swath_coverage')

    def test_extract_window_includes_ati(self) -> None:
        day, night, alb, ds, ns, als = self._season_stack()
        row = surf.extract_surface_dimensions_window('r', updated_at=NOW, raw_inputs={'apparent_thermal_inertia': {
            'lst_day_k': day, 'lst_night_k': night, 'albedo': alb,
            'day_season': ds, 'night_season': ns, 'albedo_season': als}})
        self.assertEqual(row['apparent_thermal_inertia_status'], 'measured')
        self.assertEqual(row['aridity_status'], 'on_demand_fetchable')


class TestGrids(unittest.TestCase):
    def test_grid_indices_match_cmr_granules(self) -> None:
        # The CMR granules of this bbox are MOD11A1 ...h09v05... and AG100.v003.39.-111.0001.
        self.assertEqual(fetch.modis_tile(-110.5, 38.5), (9, 5))
        self.assertEqual(fetch.ag100_tile(-110.5, 38.5), (39, -111))
        self.assertEqual(fetch.imerg_index(-179.99, -89.99), (0, 0))
        self.assertEqual(fetch.imerg_index(179.99, 89.99), (3599, 1799))
        row, col = fetch.ease2_index(0.05, 0.05)
        self.assertEqual((row, col), (811, 1928))  # first cell north-east of (0, 0)

    def test_lst_quality_bits(self) -> None:
        raw = np.array([15000, 15000, 15000, 15000, 0])
        qc = np.array([0b00000000, 0b01000001, 0b10000001, 0b00000010, 0])
        np.testing.assert_allclose(fetch.lst_kelvin(raw, qc), [300.0, 300.0, np.nan, np.nan, np.nan])

    def test_modis_pixels_in_footprint(self) -> None:
        x0 = fetch.MODIS_X0 + 9 * fetch.MODIS_TILE_M
        y0 = fetch.MODIS_Y0 - 5 * fetch.MODIS_TILE_M
        t1km = Affine(fetch.MODIS_TILE_M / 1200, 0, x0, 0, -fetch.MODIS_TILE_M / 1200, y0)
        rr, cc = fetch.modis_pixels(UTAH, t1km, (1200, 1200))
        self.assertTrue(6 <= rr.size <= 16)
        t500 = Affine(t1km.a / 2, 0, x0, 0, t1km.e / 2, y0)
        self.assertEqual(fetch.modis_pixels(UTAH, t500 * Affine.scale(2), (1200, 1200))[0].size, rr.size)


class TestReaders(unittest.TestCase):
    def test_aridity_monthly_totals(self) -> None:
        months = [date(2023, m, 1) for m in range(1, 13)]
        i, j = fetch.imerg_index(UTAH.longitude, UTAH.latitude)

        def opener(url):
            rate = np.zeros((1, 3600, 1800), dtype=np.float32)
            month = int(url.rsplit('-', 1)[1])
            rate[0, i, j] = 0.01 if month <= 6 else -9999.9
            return FakeH5({'Grid/precipitation': FakeDataset(rate)})

        search = lambda coll, bbox, start, end: [granule(f'imerg-{d:%m}', d, f'https://x/imerg-{d.month}') for d in months]
        result = fetch.fetch_aridity([UTAH], date(2023, 1, 1), date(2023, 12, 31), workers=1,
                                     search=search, opener=opener)
        series = result.inputs[UTAH.region_id]['monthly_precip_mm']
        self.assertEqual(series.shape, (12,))
        self.assertAlmostEqual(series[0], 0.01 * 31 * 24, places=4)
        self.assertTrue(np.isnan(series[6:]).all())
        self.assertEqual(len(result.granules), 12)

    def test_soil_moisture_series(self) -> None:
        r, c = fetch.ease2_index(UTAH.longitude, UTAH.latitude)
        days = [date(2023, 6, d) for d in range(1, 17)]

        def opener(url):
            sm = np.full((1624, 3856), -9999.0, dtype=np.float32)
            qa = np.full((1624, 3856), 65534, dtype=np.uint16)
            sm[r, c], qa[r, c] = 0.12, 0
            g = 'Soil_Moisture_Retrieval_Data_AM/'
            return FakeH5({g + 'soil_moisture': FakeDataset(sm), g + 'retrieval_qual_flag': FakeDataset(qa)})

        search = lambda coll, bbox, start, end: [granule(f'smap-{d.day}', d) for d in days]
        result = fetch.fetch_soil_moisture([UTAH], days[0], days[-1], step_days=8, workers=1,
                                           search=search, opener=opener)
        raw = result.inputs[UTAH.region_id]
        self.assertEqual(raw['sm_m3m3'].tolist(), [np.float32(0.12).item()] * 2)
        out, _, status = surf.compute_smap_moisture_metrics(raw['sm_m3m3'], raw['qa_flag'])
        self.assertEqual(status, 'measured')

    def test_emissivity_tile(self) -> None:
        n = 1000
        lat = np.repeat(np.linspace(39.0, 38.0, n)[:, None], n, axis=1).astype(np.float32)
        lon = np.repeat(np.linspace(-111.0, -110.0, n)[None, :], n, axis=0).astype(np.float32)
        emis = np.empty((5, n, n), dtype=np.int16)
        for b, v in enumerate((940, 945, 950, 960, 965)):
            emis[b] = v
        h5 = FakeH5({'Geolocation/Latitude': FakeDataset(lat), 'Geolocation/Longitude': FakeDataset(lon),
                     'Emissivity/Mean': FakeDataset(emis)})
        search = lambda coll, bbox, *a: [granule('AG100.v003.39.-111.0001', date(2000, 1, 1))]
        result = fetch.fetch_emissivity([UTAH], workers=1, search=search, opener=lambda url: h5)
        bands = result.inputs[UTAH.region_id]['emissivity_b10_b14']
        self.assertEqual(bands.shape[0], 5)
        self.assertTrue(700 <= bands.shape[1] <= 1100)  # ~30 x 30 cells of 100 m in 3 km
        self.assertAlmostEqual(bands[0, 0], 0.94, places=6)
        _, _, status = surf.compute_aster_ged_emissivity_metrics(bands)
        self.assertEqual(status, 'measured')

    def test_permafrost_polar_stereographic(self) -> None:
        site = fetch.Site('earth-devon-1', -89.8, 75.4)
        crs = CRS.from_epsg(3995)
        from pyproj import Transformer
        cx, cy = Transformer.from_crs('EPSG:4326', crs, always_xy=True).transform(site.longitude, site.latitude)
        x = np.arange(cx - 10_000, cx + 10_001, 1000.0)
        y = np.arange(cy + 10_000, cy - 10_001, -1000.0)

        def make(var, value):
            grid = np.full((1, y.size, x.size), value, dtype=np.float32)
            return FakeH5({'x': FakeDataset(x), 'y': FakeDataset(y),
                           'polar_stereographic': FakeDataset(0, {'crs_wkt': crs.to_wkt()}),
                           var: FakeDataset(grid, {'grid_mapping': b'polar_stereographic', '_FillValue': -9999.0})})

        opener = lambda url: make('PFR', 90.0) if '-PFR-' in url else make('ALT', 0.6)
        result = fetch.fetch_permafrost([site], 2023, opener=opener)
        raw = result.inputs[site.region_id]
        self.assertEqual(raw['pfr_pct'].size, 9)  # 3 x 3 cells of 1 km
        out, _, status = surf.compute_permafrost_metrics(raw['pfr_pct'], raw['alt_m'])
        self.assertEqual(status, 'measured')
        self.assertAlmostEqual(out['cci_permafrost_probability'], 0.9, places=5)
        self.assertAlmostEqual(out['cci_active_layer_thickness_m'], 0.6, places=5)
        self.assertTrue(all(g.startswith('northern_hemisphere/') for g in result.granules))

    def _modis_reader(self, values: dict):
        x0 = fetch.MODIS_X0 + 9 * fetch.MODIS_TILE_M
        y0 = fetch.MODIS_Y0 - 5 * fetch.MODIS_TILE_M

        def reader(path, layers):
            size = 2400 if any('500m' in l or 'Albedo' in l or 'NDSI' in l for l in layers) else 1200
            t = Affine(fetch.MODIS_TILE_M / size, 0, x0, 0, -fetch.MODIS_TILE_M / size, y0)
            return {l: np.full((size, size), values[l]) for l in layers}, t
        return reader

    def test_snow_downloads_reads_and_erases(self) -> None:
        days = [date(2023, 1, d) for d in range(1, 9)]
        seen = []

        def downloader(url, target):
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b'hdf4')
            seen.append(target)
            return target

        search = lambda coll, bbox, s, e: [granule(f'MOD10A1.A{d:%Y%j}.h09v05.061', d) for d in days]
        reader = self._modis_reader({'NDSI_Snow_Cover': 60, 'NDSI_Snow_Cover_Basic_QA': 0})
        with tempfile.TemporaryDirectory() as tmp:
            result = fetch.fetch_snow([UTAH], days[0], days[-1], Path(tmp), step_days=1, workers=1,
                                      search=search, downloader=downloader, reader=reader)
            self.assertFalse(any(p.exists() for p in seen))
        raw = result.inputs[UTAH.region_id]
        self.assertEqual(raw['ndsi_snow_cover'].shape[0], 8)
        out, _, status = surf.compute_mod10a1_snow_metrics(raw['ndsi_snow_cover'], raw['qa_flag'])
        self.assertEqual(status, 'measured')
        self.assertAlmostEqual(out['mod10a1_snow_days_fraction'], 1.0)

    def test_apparent_thermal_inertia_pipeline(self) -> None:
        start, end = fetch.season_range(2023)
        all_days = [date.fromordinal(o) for o in range(start.toordinal(), end.toordinal() + 1)]

        def search(coll, bbox, s, e):
            name = coll['short_name']
            step = 8 if name == 'MCD43A3' else 1
            return [granule(f'{name}.A{d:%Y%j}.h09v05.061', d) for d in all_days[::step]]

        reader = self._modis_reader({'LST_Day_1km': 15000, 'QC_Day': 0, 'LST_Night_1km': 14000, 'QC_Night': 0,
                                     'Albedo_WSA_shortwave': 200,
                                     'BRDF_Albedo_Band_Mandatory_Quality_shortwave': 0})
        downloader = lambda url, target: target
        with tempfile.TemporaryDirectory() as tmp:
            result = fetch.fetch_apparent_thermal_inertia([UTAH], start, end, Path(tmp), lst_step_days=3,
                                                          albedo_step_days=1, workers=1, search=search,
                                                          downloader=downloader, reader=reader)
        raw = result.inputs[UTAH.region_id]
        self.assertEqual(raw['lst_day_k'].shape[1], raw['albedo'].shape[1])
        self.assertEqual(set(raw['day_season']), {'2023-DJF', '2023-MAM', '2023-JJA', '2023-SON'})
        out, frac, status = surf.compute_modis_ati_metrics(**{
            k: raw[k] for k in ('lst_day_k', 'lst_night_k', 'albedo')},
            day_season=raw['day_season'], night_season=raw['night_season'], albedo_season=raw['albedo_season'])
        self.assertEqual(status, 'measured')
        self.assertAlmostEqual(out['modis_ati_p50_per_k'], 0.8 / 20.0, places=6)

    def test_sar_temporal_median_with_mask(self) -> None:
        def scene(vv, mask_value):
            mask = np.zeros((100, 100), dtype=np.uint8)
            mask[:10] = mask_value
            return {'VV': np.full((100, 100), vv, dtype=np.float32),
                    'VH': np.full((100, 100), vv / 10, dtype=np.float32), 'mask': mask}

        scenes = iter([scene(0.1, 2), scene(0.2, 0), scene(0.3, 0)])
        search = lambda coll, bbox, s, e: [granule(f'opera-{k}_VV.tif', date(2023, 1, k + 1),
                                                   f'https://x/opera-{k}_VV.tif') for k in range(3)]
        result = fetch.fetch_sar([UTAH], date(2023, 1, 1), date(2023, 2, 1), workers=1, search=search,
                                 scene_reader=lambda urls, site: next(scenes))
        raw = result.inputs[UTAH.region_id]
        self.assertAlmostEqual(float(raw['sigma0_vv_linear'][0, 0]), 0.25, places=6)
        self.assertAlmostEqual(float(raw['sigma0_vv_linear'][50, 50]), 0.2, places=6)
        out, _, status = surf.compute_sentinel1_rtc_metrics(raw['sigma0_vv_linear'], raw['sigma0_vh_linear'])
        self.assertEqual(status, 'measured')
        self.assertAlmostEqual(out['s1_rtc_vh_vv_ratio_db'], -10.0, places=4)


class TestStoreIntegration(unittest.TestCase):
    def test_rows_manifests_and_merge(self) -> None:
        aridity = fetch.FetchResult('aridity', inputs={UTAH.region_id: {
            'monthly_precip_mm': np.array([2.0] * 12)}}, granules=['g1'], period='2023-01/2023-12',
            support='nearest_native_pixel_0.1deg')
        manifest_id, manifests = fetch.build_manifests([aridity], NOW)
        rows = fetch.build_rows([UTAH], [aridity], manifest_id, NOW)
        self.assertEqual(rows[0]['aridity_status'], 'measured')
        self.assertEqual({m['product_id'] for m in manifests}, {'GPM_3IMERGM.07'})
        with tempfile.TemporaryDirectory() as tmp:
            store = FeatureStore(Path(tmp))
            store.append_enrichment('surface', rows, manifests)

            snow = fetch.FetchResult('snow_persistence', inputs={UTAH.region_id: {
                'ndsi_snow_cover': np.zeros((10, 4)), 'qa_flag': np.zeros((10, 4), dtype=int)}})
            later = fetch.build_rows([UTAH], [snow], 'm2', NOW.replace(hour=13))
            stored = cli.stored_rows(store, [UTAH.region_id])
            merged = cli.merge_with_stored(later[0], stored[UTAH.region_id], {'snow_persistence'})
            self.assertEqual(merged['aridity_status'], 'measured')
            self.assertEqual(merged['snow_persistence_status'], 'measured')
            store.append_enrichment('surface', [merged])
            self.assertEqual(cli.pending([UTAH], cli.stored_rows(store, [UTAH.region_id]),
                                         ['aridity', 'snow_persistence']), [])
            self.assertEqual(len(cli.pending([UTAH], cli.stored_rows(store, [UTAH.region_id]),
                                             ['permafrost'])), 1)


if __name__ == '__main__':
    unittest.main()


class RetryTest(unittest.TestCase):
    def test_transient_errors_are_retried_and_permanent_ones_are_not(self) -> None:
        import urllib.error
        from pipelines import etl_surface_fetch as f
        calls, sleeps = [], []

        def flaky():
            calls.append(1)
            if len(calls) < 3:
                raise urllib.error.URLError('[Errno -3] Temporary failure in name resolution')
            return 'ok'

        self.assertEqual(f.with_retries(flaky, sleep=sleeps.append), 'ok')
        self.assertEqual(sleeps, [5.0, 10.0])

        def forbidden():
            raise urllib.error.HTTPError('u', 403, 'Forbidden', {}, None)

        with self.assertRaises(urllib.error.HTTPError):
            f.with_retries(forbidden, sleep=sleeps.append)
        self.assertEqual(len(sleeps), 2)  # 403 is not retried
