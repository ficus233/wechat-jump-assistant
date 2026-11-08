import unittest,json
from unittest.mock import patch
from pathlib import Path
import cv2
from core import detect,distance
from background import select_target
from platforms import current_surface,remained_on_platform

ROOT=Path(__file__).parent
class PlatformTests(unittest.TestCase):
    def test_close_edge_landing_on_next_platform_overrides_radius(self):
        source={'contour':[[0,0],[40,0],[40,40],[0,40]]}
        target={'contour':[[42,0],[82,0],[82,40],[42,40]],'confidence':.88}
        a={'point':[30,20],'box':[15,0,30,100]};b={'point':[45,20],'box':[30,0,30,100]}
        with patch('platforms.static_board_score',return_value=.98):
            self.assertFalse(remained_on_platform(None,None,source,a,b,target)[0])
            b['point']=[35,20]
            self.assertTrue(remained_on_platform(None,None,source,a,b,target)[0])
    def test_real_edge_occluded_textured_target_is_recovered(self):
        im=cv2.imread(str(ROOT/'sessions/20261108-110645-background/unrecognized-latest.png'))
        self.assertIsNotNone(im)
        for mirror in [False,True]:
            frame=cv2.flip(im,1) if mirror else im
            target=select_target(detect(frame,self.cfg(),include_fallback=True))
            self.assertIsNotNone(target)
            self.assertLess(distance(target['point'],[226 if mirror else 323,290]),7)
    def frame(self,n):return cv2.imread(str(ROOT/'sessions/20261107-214634-background'/f'{n}-after.png'))
    def cfg(self):return json.loads((ROOT/'config.json').read_text('utf-8'))
    def test_cube_is_one_target_not_nine_tiles(self):
        d=detect(self.frame(24),self.cfg());target=select_target(d)
        self.assertEqual(target['method'],'grid-platform');self.assertLess(distance(target['point'],[431,227]),6)
    def test_standing_cube_targets_real_next_platform(self):
        for n in [25,26]:
            with self.subTest(n=n):
                d=detect(self.frame(n),self.cfg());target=select_target(d);source=current_surface(d)
                self.assertEqual(source['method'],'grid-platform');self.assertTrue(source['current_platform'])
                self.assertLess(distance(target['point'],[355,271]),6)
    def test_same_cube_repeat_is_detected(self):
        a=self.frame(25);b=self.frame(26);da=detect(a,self.cfg());db=detect(b,self.cfg())
        same,score=remained_on_platform(a,b,current_surface(da),da['piece'],db['piece'])
        self.assertTrue(same);self.assertGreater(score,.86)
    def test_departure_to_new_platform_not_blocked(self):
        a=self.frame(26);b=self.frame(27);da=detect(a,self.cfg());db=detect(b,self.cfg())
        same,score=remained_on_platform(a,b,current_surface(da),da['piece'],db['piece'])
        self.assertFalse(same)
    def test_tile_repeat_still_blocked_without_reconstructed_source(self):
        a=self.frame(25);b=self.frame(26);da=detect(a,self.cfg());db=detect(b,self.cfg())
        same,score=remained_on_platform(a,b,None,da['piece'],db['piece']);self.assertTrue(same)
    def test_small_tile_source_cannot_bypass_repeat_check(self):
        a=self.frame(25);b=self.frame(26);da=detect(a,self.cfg());db=detect(b,self.cfg());x,y=da['piece']['point']
        tiny={'contour':[[x-5,y-5],[x+5,y-5],[x+5,y+5],[x-5,y+5]]}
        same,score=remained_on_platform(a,b,tiny,da['piece'],db['piece']);self.assertTrue(same)
