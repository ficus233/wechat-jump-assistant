import unittest,tempfile,csv,json
from pathlib import Path
from unittest.mock import patch
from measurements import Measurements
from autocenter import AutoCenter
from geometry_setup import standardize_window

class MeasurementTests(unittest.TestCase):
    def test_unknown_displacement_is_blank_and_each_press_is_recorded(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);session=root/'session';session.mkdir();ledger=Measurements(root,session)
            ledger.append(dict(record_id='one',signature=[1077,1040,120,[520,250,550,700],'euclidean_px'],requested_ms=500,actual_ms=501,measurement_status='camera_registration_failed'))
            rows=list(csv.DictReader((root/'jump-measurements.csv').open(encoding='utf-8-sig',newline='')))
            self.assertEqual(len(rows),1);self.assertEqual(rows[0]['actual_ms'],'501');self.assertEqual(rows[0]['displacement_px'],'')
            self.assertEqual(rows[0]['client_width'],'1077')
    def test_cross_run_learning_only_uses_matching_reliable_geometry(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);session=root/'session';session.mkdir();ledger=Measurements(root,session);sig=[1077,1040,120,[],'euclidean_px']
            for i in range(4):ledger.append(dict(record_id=str(i),signature=sig,direction='right',actual_ms=500,projected_displacement_px=200,calibration_eligible=True,same_platform=False))
            ledger.append(dict(record_id='bad',signature=sig,direction='right',actual_ms=10,projected_displacement_px=500,calibration_eligible=False))
            c=AutoCenter(None,{'k':2.6});self.assertEqual(ledger.prime(c,sig),4);self.assertAlmostEqual(c.snapshot()['right']['ms_per_px'],2.5)
            self.assertEqual(ledger.prime(c,[800,600,120,[],'euclidean_px']),0)
    def test_standard_size_is_restored_automatically(self):
        cfg={'model':{'signature':[1077,1040,120,[],'euclidean_px']}}
        before=dict(width=900,height=900,dpi=120);after=dict(width=1077,height=1040,dpi=120)
        with patch('geometry_setup.native.geometry',return_value=before),patch('geometry_setup.native.restore_client_size',return_value=after) as restore:
            result,report=standardize_window(123,cfg)
        restore.assert_called_once_with(123,1077,1040,120);self.assertEqual(result,after)
