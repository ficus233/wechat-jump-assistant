"""Safety-path tests with mocked OS and mouse, never sends desktop input."""
import unittest,threading
from unittest.mock import patch
import native
class FakeOS:
    def SetForegroundWindow(self,*a):pass
    def GetForegroundWindow(self):return 123
    def WindowFromPoint(self,*a):return 123
    def GetAncestor(self,*a):return 123
class FakeMouse:
    FAILSAFE=True
    def __init__(self,cancel):self.cancel=cancel;self.events=[]
    def moveTo(self,*a):pass
    def mouseDown(self):self.events.append('down');self.cancel.set()
    def mouseUp(self):self.events.append('up');assert not self.FAILSAFE
class Safety(unittest.TestCase):
    def test_cancel_releases(self):
        cancel=threading.Event();mouse=FakeMouse(cancel)
        g={'left':0,'top':0}
        with patch.object(native,'u',FakeOS()),patch.object(native,'pg',mouse),patch.object(native,'geometry',return_value=g):
            with self.assertRaisesRegex(ValueError,'暂停'):native.press(123,[0,0,100,100],100,cancel,lambda *a:None)
        self.assertEqual(mouse.events,['down','up']);self.assertTrue(mouse.FAILSAFE)
    def test_focus_denies_input(self):
        cancel=threading.Event();mouse=FakeMouse(cancel);os=FakeOS();os.GetForegroundWindow=lambda:999
        with patch.object(native,'u',os),patch.object(native,'pg',mouse),patch.object(native,'geometry',return_value={'left':0,'top':0}):
            with self.assertRaisesRegex(ValueError,'焦点'):native.press(123,[0,0,100,100],100,cancel,lambda *a:None)
        self.assertEqual(mouse.events,[])
if __name__=='__main__':unittest.main()
