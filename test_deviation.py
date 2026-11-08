import unittest
from policy import landing_result
from core import fit

class DeviationTests(unittest.TestCase):
    def test_arbitrarily_large_error_continues(self):
        for error in [25.01,100,1000,1e100]:self.assertEqual(landing_result(error),'偏差继续')
    def test_unknown_error_continues_without_faking_success(self):
        self.assertEqual(landing_result(None),'偏差继续')
    def test_normal_landing(self):self.assertEqual(landing_result(5),'成功')
    def test_unverified_deviation_does_not_pollute_fit(self):
        samples=[dict(signature='s',displacement=x,actual_ms=2*x+5) for x in [30,60,90]]
        samples.append(dict(signature='s',displacement=500,actual_ms=20,calibration_eligible=False))
        model=fit(samples,'s');self.assertEqual(model['n'],3);self.assertAlmostEqual(model['k'],2)
    def test_panel_does_not_pause_for_huge_error_or_failed_registration(self):
        from unittest.mock import patch
        import numpy as np
        from app import App
        for fail_registration in [False,True]:
            panel=App.__new__(App);panel.cfg={'continue_on_deviation':True}
            panel.det={'piece':{'point':[1000,1000]},'target':{'point':[1100,900]}}
            panel.before=np.zeros((8,8,3),np.uint8);panel.frame=np.full((8,8,3),255,np.uint8)
            panel.before_target={'point':[0,0]};panel.pending={'target':[0,0]};panel.points={}
            panel.log=lambda *a:None;results=[];panel.feedback=results.append
            panel.pause=lambda:self.fail('Must not pause for landing deviation')
            options={'side_effect':ValueError('ambiguous match')} if fail_registration else {'return_value':(np.zeros(2),.99)}
            with patch('app.register_platform',**options):panel.auto_feedback()
            self.assertEqual(results,['偏差继续']);self.assertFalse(panel.pending['calibration_eligible'])
