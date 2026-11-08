import json,unittest
from pathlib import Path
import cv2
import numpy as np
from core import detect,distance
from background import select_target

ROOT=Path(__file__).parent
class RegressionTests(unittest.TestCase):
    def test_real_merged_white_sides_and_close_occluded_platforms(self):
        cfg=json.loads((ROOT/'config.json').read_text('utf-8'))
        cases=[('20261107-211720-background',14,[357,269]),('20261107-211720-background',21,[245,282]),
               ('20261107-211720-background',26,[246,283]),('20261107-210253-background',36,[228,272])]
        for session,seq,point in cases:
            with self.subTest(session=session,seq=seq):
                frame=cv2.imread(str(ROOT/'sessions'/session/f'{seq}-after.png'))
                self.assertIsNotNone(frame,'实机回归帧缺失')
                d=detect(frame,cfg);viable=[c for c in d['candidates'] if c['confidence']>0]
                self.assertTrue(viable,'下一平台漏检')
                closest=min(viable,key=lambda c:distance(c['point'],point))
                self.assertLess(distance(closest['point'],point),6,'顶面中心偏差过大')
                self.assertLess(distance(select_target(d)['point'],point),6,'实际执行选择了错误目标')
    def test_touching_surfaces_across_colors_and_directions(self):
        cfg=json.loads((ROOT/'config.json').read_text('utf-8'))
        for color in [(255,255,255),(242,242,242),(220,220,220),(80,110,70)]:
            for mirror in [False,True]:
                with self.subTest(color=color,mirror=mirror):
                    im=np.full((700,550,3),(210,200,200),np.uint8)
                    def platform(x,y,face):
                        a,b,t=80,46,65
                        side=np.array([[x-a,y],[x,y+b],[x+a,y],[x+a,y+t],[x,y+b+t],[x-a,y+t]],np.int32)
                        cv2.fillPoly(im,[side],tuple(max(0,v-30) for v in face))
                        cv2.fillPoly(im,[np.array([[x,y-b],[x+a,y],[x,y+b],[x-a,y]],np.int32)],face)
                    platform(245,313,color);platform(335,365,(245,245,245))
                    cv2.ellipse(im,(335,335),(15,30),0,0,360,(100,55,55),-1);cv2.circle(im,(335,275),15,(100,55,55),-1)
                    expected=[245,313]
                    if mirror:im=cv2.flip(im,1);expected=[549-245,313]
                    d=detect(im,cfg);target=select_target(d)
                    self.assertIsNotNone(target);self.assertLess(distance(target['point'],expected),5)
    def test_textured_platform_marker_from_new_live_failure(self):
        cfg=json.loads((ROOT/'config.json').read_text('utf-8'))
        frame=cv2.imread(str(ROOT/'sessions/20261107-213737-background/unrecognized-latest.png'))
        self.assertIsNotNone(frame)
        d=detect(frame,cfg);target=select_target(d)
        self.assertIsNotNone(target);self.assertEqual(target['method'],'landing-marker')
        self.assertLess(distance(target['point'],[361,265]),3)
