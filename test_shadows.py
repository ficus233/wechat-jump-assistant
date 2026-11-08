import json,unittest
from pathlib import Path
import cv2,numpy as np
from core import detect,distance
from background import select_target
from shadows import ground_shadow_mask
ROOT=Path(__file__).parent
class ShadowTests(unittest.TestCase):
    def test_late_game_shadow_touching_cone_and_neighbor(self):
        cfg=json.loads((ROOT/'config.json').read_text('utf-8'))
        im=cv2.imread(str(ROOT/'sessions/20261108-103748-background/402-before.png'))
        self.assertIsNotNone(im)
        for mirror in [False,True]:
            frame=cv2.flip(im,1) if mirror else im
            target=select_target(detect(frame,cfg,include_fallback=True))
            self.assertIsNotNone(target)
            self.assertLess(distance(target['point'],[195.5 if mirror else 353.5,271.5]),4)
    def test_real_small_round_platform_not_its_shadow_both_directions(self):
        cfg=json.loads((ROOT/'config.json').read_text('utf-8'))
        im=cv2.imread(str(ROOT/'sessions/20261107-223222-background/477-after.png'))
        self.assertIsNotNone(im)
        for mirror in [False,True]:
            frame=cv2.flip(im,1) if mirror else im
            expected=[150 if mirror else 399,245.5]
            d=detect(frame,cfg,include_fallback=True);target=select_target(d)
            self.assertIsNotNone(target);self.assertLess(distance(target['point'],expected),4)
            self.assertFalse(any(c['confidence']>0 and distance(c['point'],[193 if mirror else 356,294])<15 for c in d['candidates']))
    def test_shadow_mask_keeps_neutral_cap_supported_by_wall(self):
        for bg in [(220,200,190),(220,220,220)]:
            im=np.full((300,400,3),bg,np.uint8);shade=tuple(round(v*.7) for v in bg)
            cv2.ellipse(im,(90,180),(38,20),0,0,360,shade,-1)
            cv2.rectangle(im,(225,140),(275,220),(100,100,100),-1)
            cv2.ellipse(im,(250,140),(25,14),0,0,360,shade,-1)
            mask=ground_shadow_mask(im)
            self.assertEqual(mask[180,90],255);self.assertEqual(mask[140,250],0)
