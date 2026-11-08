import unittest
import numpy as np
from directional import fit_directions,predict_direction,infer_unit

class DirectionalTests(unittest.TestCase):
    def test_separate_axes_units_and_proportional_time(self):
        rows=[]
        for sign,scale in [(-1,20),(1,30)]:
            axis=np.array([sign*.8,-.6])
            for n in [3,5,7,9]:
                flight=axis*scale*n;shift=np.array([30,40])
                rows.append(dict(signature='s',piece=[0,0],target=flight.tolist(),landing=(flight+shift).tolist(),camera_shift=shift.tolist(),actual_ms=n*100,result='成功'))
        model=fit_directions(rows,'s')
        for name,scale in [('left',20),('right',30)]:
            m=model['directions'][name];self.assertAlmostEqual(m['unit_px'],scale);self.assertAlmostEqual(m['ms_per_unit'],100)
            out=predict_direction(model,[0,0],(np.array(m['axis'])*scale*6).tolist())
            self.assertEqual(out['integer_units'],6);self.assertAlmostEqual(out['predicted_ms'],600)
    def test_coordinate_translation_invariant(self):
        model={'directions':{'right':dict(axis=[.8,-.6],normal=[.6,.8],unit_px=20,ms_per_unit=100,unit_status='candidate_not_identified')}}
        a=predict_direction(model,[0,0],[80,-60]);b=predict_direction(model,[100,200],[180,140]);self.assertEqual(a['predicted_ms'],b['predicted_ms'])
    def test_rounding_keeps_original_residual(self):
        model={'directions':{'right':dict(axis=[1,0],normal=[0,1],unit_px=20,ms_per_unit=100,unit_status='candidate_not_identified')}}
        out=predict_direction(model,[0,0],[107,4]);self.assertEqual(out['integer_units'],5);self.assertEqual(out['quantization_error_px'],7);self.assertEqual(out['cross_axis_px'],4)
    def test_mismatch_samples_excluded(self):
        with self.assertRaises(ValueError):fit_directions([dict(signature='other')],'s')
