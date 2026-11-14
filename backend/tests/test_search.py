import unittest
from unittest.mock import patch
from app.routers.regions_router import Search, Weights, search
from fastapi import HTTPException

FIXTURE = [
    {'id':'mars-jezero','body':'Mars','metrics':{'slope_deg':5,'relief_m':180}},
    {'id':'earth-atacama','body':'Earth','metrics':{'slope_deg':4.5,'relief_m':330}},
    {'id':'earth-iceland','body':'Earth','metrics':{'slope_deg':9,'relief_m':190}},
    {'id':'earth-utah','body':'Earth','metrics':{'slope_deg':6.5,'relief_m':None}},
]

class SearchTests(unittest.TestCase):
    def setUp(self):
        self.patcher = patch('app.routers.regions_router.regions', return_value=FIXTURE)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def test_weights_change_order(self):
        slope = search(Search(reference_id='mars-jezero', weights=Weights(slope_deg=1, relief_m=0)))
        relief = search(Search(reference_id='mars-jezero', weights=Weights(slope_deg=0, relief_m=1)))
        self.assertEqual(slope['results'][0]['region']['id'], 'earth-atacama')
        self.assertEqual(relief['results'][0]['region']['id'], 'earth-iceland')

    def test_missing_metric_and_breakdown(self):
        result = search(Search(reference_id='mars-jezero', weights=Weights()))['results'][-1]
        self.assertEqual(result['region']['id'], 'earth-utah')
        self.assertIsNone(result['breakdown']['relief_m']['similarity'])
        self.assertEqual(result['available_weight_fraction'], 0.5)
        self.assertAlmostEqual(result['score'], result['breakdown']['slope_deg']['similarity'])

    def test_zero_weights_rejected(self):
        with self.assertRaises(HTTPException):
            search(Search(reference_id='mars-jezero', weights=Weights(slope_deg=0, relief_m=0)))
