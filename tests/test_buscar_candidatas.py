"""Numerical and acquisition boundaries for bounded screening."""
import copy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import numpy as np
import pyproj
import rasterio
from rasterio.transform import from_origin

SCRIPTS = Path(__file__).resolve().parents[1]/'scripts'
sys.path.insert(0,str(SCRIPTS))
import buscar_candidatas as m


class RegionalScienceTests(unittest.TestCase):
    def test_crc_rejects_truncated_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'good.zip'
            with zipfile.ZipFile(p,'w') as z: z.writestr('a.txt',b'abc')
            self.assertEqual(len(m.check_zip(p)),1)
            p.write_bytes(p.read_bytes()[:-30])
            with self.assertRaises(zipfile.BadZipFile): m.check_zip(p)

    def test_filters_are_inclusive_and_missing_data_not_bad_matches(self):
        p={'slope_distance_max_deg':2,'abs_relief_difference_max_m':60}
        metric={'elevation_coverage':.95,'slope_coverage':.95,'slope_wasserstein_deg':2,'candidate_minus_reference_relief_m':-60}
        self.assertEqual(m.filter_reasons(metric,p,.95),[])
        self.assertEqual(m.filter_reasons({**metric,'candidate_minus_reference_relief_m':60.01},p,.95),['relief_difference_above_threshold'])
        self.assertEqual(m.filter_reasons({**metric,'slope_wasserstein_deg':2.01},p,.95),['slope_distance_above_threshold'])
        reasons=m.filter_reasons({**metric,'slope_coverage':0,'slope_wasserstein_deg':None},p,.95)
        self.assertEqual(reasons,['insufficient_coverage','missing_measurements'])

    def test_grid_is_deterministic_metric_and_inside_aoi(self):
        cfg=m.load_config(); area={'id':'test','name':'test','bbox':[-111,38,-110.5,38.5]}
        a=list(m.grid_sites(area,cfg));b=list(m.grid_sites(area,cfg))
        self.assertEqual(a,b);self.assertGreater(len(a),10)
        geod=pyproj.Geod(ellps='WGS84')
        for site in a:
            ring=m.terrain.geometry(site,cfg)['geometry']['coordinates'][0]
            self.assertTrue(all(-111<=lon<=-110.5 and 38<=lat<=38.5 for lon,lat in ring))
            actual=abs(geod.polygon_area_perimeter(*zip(*ring))[0])
            self.assertAlmostEqual(actual/1e6,9,places=4)

    def test_zero_terrain_kept_and_outside_source_remains_missing(self):
        cfg={**m.load_config(),'window_m':3000,'margin_m':600}
        site={'body':'Earth','latitude':0,'longitude':0}
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'fixture.tif'
            with rasterio.open(p,'w',driver='GTiff',height=61,width=61,count=1,dtype='float64',crs='EPSG:4326',transform=from_origin(-.03,.03,.001,.001),nodata=-32768) as ds:
                ds.write(np.zeros((61,61)),1)
            with rasterio.open(p) as ds:
                stats,_=m.measurements(m.read_local(ds,site,cfg),cfg)
                missing,_=m.measurements(m.read_local(ds,{**site,'longitude':5},cfg),cfg)
            for st in stats:
                self.assertEqual(st['relief_p95_p5_m'],0)
                self.assertEqual(st['slope_quantiles_deg']['p50'],0)
                self.assertEqual(st['slope_coverage'],1)
            for st in missing:
                self.assertEqual(st['slope_coverage'],0)
                self.assertIsNone(st['relief_p95_p5_m'])

    def test_profiles_preserve_order_and_unknown_detail_does_not_download(self):
        cfg=m.load_config()
        for p in ('slope_distance_max_deg','abs_relief_difference_max_m'):
            self.assertLess(cfg['profiles']['strict'][p],cfg['profiles']['baseline'][p])
            self.assertLess(cfg['profiles']['baseline'][p],cfg['profiles']['relaxed'][p])
        with patch('buscar_candidatas.urllib.request.urlopen') as request:
            with self.assertRaisesRegex(ValueError,'Unknown candidate'):m.detail(cfg,'not-a-candidate',False)
            request.assert_not_called()

    def test_missing_detail_is_not_implicitly_downloaded(self):
        with patch('buscar_candidatas.urllib.request.urlopen') as request:
            with self.assertRaises(FileNotFoundError):
                m.acquire_detail_tile({'local_file':'data/raw/srtm/not-existing-phase4.tif'},False)
            request.assert_not_called()


if __name__=='__main__':unittest.main()
