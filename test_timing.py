import unittest
import numpy as np
from timing import wait_stable,wait_until_ns,timer_resolution

class Clock:
    def __init__(self):self.now=0.;self.cancelled=False
    def __call__(self):return self.now
    def wait(self,seconds):self.now+=seconds;return self.cancelled

class TimingTests(unittest.TestCase):
    def test_animation_must_finish_and_settle(self):
        clock=Clock();reference=np.zeros((8,8,3),np.uint8)
        def grab():return np.full_like(reference,min(10,int(clock.now/.06))*10)
        frame=wait_stable(grab,clock,1.2,reference=reference,require_change=True,earliest=.7,clock=clock)
        self.assertGreaterEqual(clock.now,.90)
        self.assertTrue(np.all(frame==100))
    def test_no_response_never_becomes_success(self):
        clock=Clock();frame=np.zeros((8,8,3),np.uint8)
        with self.assertRaisesRegex(ValueError,'响应'):
            wait_stable(lambda:frame,clock,1.2,reference=frame,require_change=True,timeout=1,clock=clock)
    def test_pause_interrupts_wait(self):
        clock=Clock();clock.cancelled=True
        with self.assertRaisesRegex(ValueError,'暂停'):
            wait_stable(lambda:np.zeros((8,8,3),np.uint8),clock,1.2,clock=clock)
    def test_precise_wait_checks_cancel_even_in_tail(self):
        clock=Clock();clock.cancelled=True
        clock.is_set=lambda:clock.cancelled
        with self.assertRaisesRegex(ValueError,'暂停'):
            wait_until_ns(1_000_000,clock,clock=lambda:0)
    def test_precise_wait_checks_focus_in_tail(self):
        import threading
        with self.assertRaisesRegex(ValueError,'失焦'):
            wait_until_ns(1_000_000,threading.Event(),lambda:False,clock=lambda:0)
    def test_timer_resolution_restored_after_exception(self):
        from unittest.mock import patch
        calls=[]
        class WinMM:
            def timeBeginPeriod(self,n):calls.append(('begin',n));return 0
            def timeEndPeriod(self,n):calls.append(('end',n));return 0
        with patch('ctypes.WinDLL',return_value=WinMM()):
            with self.assertRaises(RuntimeError):
                with timer_resolution():raise RuntimeError('test')
        self.assertEqual(calls,[('begin',1),('end',1)])
