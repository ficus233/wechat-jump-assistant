import unittest
from policy import plan_press
class PolicyTests(unittest.TestCase):
    def setUp(self):
        self.sig=[1077,1040,120,[520,250,550,700],'euclidean_px']
        self.model=dict(signature=self.sig,k=2.6,b=23,min_d=150,max_d=340)
    def test_free_mode_warns_and_executes_outside_scale_and_range(self):
        sig=[1080,1045,120,[0,0,550,700],'euclidean_px']
        ms,warnings=plan_press(self.model,sig,400,free=True,input_verified=False,confidence=.45,automatic=True)
        self.assertAlmostEqual(ms,1063);self.assertEqual(len(warnings),4)
    def test_strict_mode_preserves_validation(self):
        with self.assertRaises(ValueError):plan_press(self.model,self.sig,400)
    def test_trial_needs_no_detection_or_calibration(self):
        ms,warnings=plan_press(None,self.sig,None,free=True,trial_ms=2000)
        self.assertEqual(ms,2000);self.assertTrue(warnings)
    def test_invalid_duration_still_rejected(self):
        for value in [0,-1,float('inf'),float('nan')]:
            with self.assertRaises(ValueError):plan_press(None,self.sig,None,free=True,trial_ms=value)
