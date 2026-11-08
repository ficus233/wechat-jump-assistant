"""Real-frame regression: the yellow band is texture, not a platform boundary."""
import json,unittest
from pathlib import Path
import cv2
from core import detect,distance
from background import select_target

ROOT=Path(__file__).parent
class StripedRoofTests(unittest.TestCase):
    def frame(self,n):
        im=cv2.imread(str(ROOT/'sessions/20261107-221845-background'/f'{n}-after.png'))
        self.assertIsNotNone(im)
        return im
    def test_real_roof_centers_both_directions_and_mirrors(self):
        cfg=json.loads((ROOT/'config.json').read_text('utf-8'))
        # Manual roof outline annotation, not the center of either red fragment.
        for n,center in [(12,[187,249]),(86,[385,253]),(23,[231,274])]:
            for mirror in [False,True]:
                with self.subTest(frame=n,mirror=mirror):
                    im=self.frame(n);expected=list(center)
                    if mirror:im=cv2.flip(im,1);expected[0]=im.shape[1]-1-expected[0]
                    d=detect(im,cfg);target=select_target(d)
                    self.assertIsNotNone(target)
                    self.assertLess(distance(target['point'],expected),5)
                    viable=[c for c in d['candidates'] if c['confidence']>0]
                    self.assertEqual(len(viable),1,'条纹分割出了额外落点')
    def test_current_roof_does_not_offer_its_other_red_half(self):
        cfg=json.loads((ROOT/'config.json').read_text('utf-8'))
        for mirror in [False,True]:
            im=self.frame(25);expected=[157,231.5]
            if mirror:im=cv2.flip(im,1);expected[0]=549-expected[0]
            d=detect(im,cfg);target=select_target(d)
            self.assertIsNotNone(target)
            self.assertLess(distance(target['point'],expected),5)
            self.assertEqual(len([c for c in d['candidates'] if c['confidence']>0]),1)
