import unittest
import numpy as np
import cv2
from core import fit,distance,translation,detect,register_platform
class Tests(unittest.TestCase):
    def test_metric(self):
        self.assertEqual(distance([0,0],[3,4]),5)
        self.assertEqual(distance([0,0],[3,4],'horizontal_px'),3)
    def test_fit_and_scale_isolation(self):
        samples=[dict(signature=[1],displacement=d,actual_ms=2*d+10) for d in [30,60,100]]
        m=fit(samples,[1]);self.assertAlmostEqual(m['k'],2);self.assertAlmostEqual(m['b'],10)
        with self.assertRaises(ValueError):fit(samples,[2])
    def test_camera_translation(self):
        a=np.random.default_rng(4).integers(0,255,(200,200,3),dtype=np.uint8)
        import cv2
        b=cv2.warpAffine(a,np.float32([[1,0,12],[0,1,-9]]),(200,200))
        shift,q=translation(a,b,[90,90]);np.testing.assert_allclose(shift,[12,-9]);self.assertGreater(q,.99)
    def test_blank_is_not_target(self):
        cfg=dict(piece_bgr_low=[65,25,25],piece_bgr_high=[150,95,100],base_correction_px=3)
        d=detect(np.full((400,300,3),220,np.uint8),cfg)
        self.assertIsNone(d['piece']);self.assertIsNone(d['target'])
    def test_real_camera_registration_and_cup_foot(self):
        from pathlib import Path
        import json
        p=Path(__file__).parent;cfg=json.loads((p/'config.json').read_text('utf-8'))
        a=cv2.imread(str(p/'experiments/7-before.png'));b=cv2.imread(str(p/'experiments/7-after.png'))
        if a is None:self.skipTest('Real-frame evidence unavailable')
        shift,q=register_platform(a,b,detect(a,cfg)['target']);np.testing.assert_allclose(shift,[10,95],atol=3)
        cup=detect(cv2.imread(str(p/'experiments/4-after.png')),cfg)['piece']['point']
        self.assertLess(distance(cup,[206,366]),5)
if __name__=='__main__':unittest.main()
