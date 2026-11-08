import unittest
from autocenter import AutoCenter

class AutoCenterTests(unittest.TestCase):
    def test_range_boundary_prediction_is_continuous(self):
        c=self.model();c.directions['right']['precision_model']=dict(k=2.6,b=30,min_d=150,max_d=350)
        for edge in [150,350]:
            a=c.predict([0,0],[edge-.001,0])['requested_ms'];b=c.predict([0,0],[edge+.001,0])['requested_ms']
            self.assertLess(abs(b-a),.1)
    def test_long_run_repeated_refits_stay_finite_and_bounded(self):
        c=self.model()
        for i in range(3200):
            d=100+(i*71)%260;t=2.6*d+30
            c.observe([0,0],[d,0],[d,0],[0,0],t,t,.999)
            plan=c.predict([0,0],[180,0])
            self.assertGreater(plan['requested_ms'],400);self.assertLess(plan['requested_ms'],580)
        self.assertLessEqual(len(c.snapshot()['right']['precision_samples']),60)
        self.assertAlmostEqual(c.predict([0,0],[180,0])['requested_ms'],498,places=4)
    def test_validated_offset_model_improves_short_and_long_predictions(self):
        c=self.model();rows=[]
        for i in range(36):
            d=120+(i*71)%240
            rows.append(dict(direction='right',calibration_eligible=True,projected_displacement_px=d,actual_ms=2.6*d+30))
        c.prime_precision(rows)
        self.assertIn('precision_model',c.snapshot()['right'])
        for d in [150,300]:self.assertAlmostEqual(c.predict([0,0],[d,0])['requested_ms'],2.6*d+30,places=6)
    def test_proportional_data_does_not_gain_spurious_intercept(self):
        c=self.model();c.prime_precision([dict(direction='right',calibration_eligible=True,projected_displacement_px=d,actual_ms=3*d) for d in range(100,350,10)])
        self.assertNotIn('precision_model',c.snapshot()['right'])
    def model(self):
        return AutoCenter({'directions':{'right':{'axis':[1,0],'continuous_proportional_ms_per_px':3},'left':{'axis':[-1,0],'continuous_proportional_ms_per_px':3}}},{'k':3})
    def test_converges_towards_center_without_integer_rounding_error(self):
        c=self.model();errors=[]
        for _ in range(12):
            plan=c.predict([0,0],[203,0]);actual=plan['requested_ms'];land=actual/2.5
            errors.append(abs(land-203));c.observe([0,0],[203,0],[land+30,40],[30,40],actual,actual,.99)
        self.assertLess(errors[-1],1);self.assertLess(errors[-1],errors[0])
    def test_left_and_right_learn_independently(self):
        c=self.model();c.observe([0,0],[200,0],[200,0],[0,0],500,500,.99)
        self.assertLess(c.snapshot()['right']['ms_per_px'],3);self.assertEqual(c.snapshot()['left']['ms_per_px'],3)
    def test_unreliable_camera_match_does_not_change_coefficient(self):
        c=self.model();r=c.observe([0,0],[200,0],[300,0],[0,0],500,500,.5)
        self.assertFalse(r['updated']);self.assertEqual(c.snapshot()['right']['ms_per_px'],3)
    def test_camera_translation_compensated(self):
        c=self.model();r=c.observe([0,0],[200,0],[230,40],[30,40],500,500,.99)
        self.assertAlmostEqual(r['along_error_px'],0);self.assertAlmostEqual(r['cross_error_px'],0)
    def test_drifted_persisted_calibration_is_not_loaded(self):
        model={'directions':{'right':{'axis':[1,0],'continuous_proportional_ms_per_px':2.67}}}
        c=AutoCenter(model,{'k':2.67},{'right':{'ms_per_px':2.19,'n':60}})
        self.assertAlmostEqual(c.snapshot()['right']['ms_per_px'],2.67)
    def test_false_large_parallel_shift_is_not_used_to_calibrate(self):
        c=self.model();r=c.observe([0,0],[200,0],[300,0],[0,0],600,600,.999)
        self.assertFalse(r['updated']);self.assertEqual(c.snapshot()['right']['ms_per_px'],3)
