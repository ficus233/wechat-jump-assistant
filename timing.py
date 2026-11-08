"""Wait for observed stability instead of stacking fixed sleeps."""
import time
import cv2
import numpy as np
from contextlib import contextmanager

@contextmanager
def timer_resolution():
    """Request process timer precision only while holding; always restore it."""
    import ctypes
    winmm=ctypes.WinDLL('winmm')
    active=winmm.timeBeginPeriod(1)==0
    try:yield active
    finally:
        if active:winmm.timeEndPeriod(1)

def wait_until_ns(deadline,cancel,check_focus=None,*,clock=time.perf_counter_ns):
    """Coarse cancellable waits then a <=2ms fine tail; no file IO in the tail."""
    while True:
        now=clock();remaining=deadline-now
        if cancel.is_set():raise ValueError('按压被暂停')
        if remaining<=0:return
        if check_focus is not None and not check_focus():raise ValueError('按压期间失焦')
        if remaining>2_000_000:
            if cancel.wait(min((remaining-2_000_000)/1e9,.004)):raise ValueError('按压被暂停')

def wait_stable(grab,cancel,delta,*,reference=None,require_change=False,
                earliest=.0,stable_for=.30,timeout=6.,clock=time.perf_counter,poll_interval=.06):
    start=clock();last=grab();stable_start=start;count=0
    changed=reference is not None and float(np.mean(cv2.absdiff(last,reference)))>delta
    while clock()-start<timeout:
        if cancel.wait(poll_interval):raise ValueError('已暂停')
        frame=grab();now=clock()
        if reference is not None and np.mean(cv2.absdiff(frame,reference))>delta:changed=True
        if np.mean(cv2.absdiff(frame,last))<delta:count+=1
        else:stable_start=now;count=0
        last=frame
        if now-start>=earliest and now-stable_start>=stable_for and count>=4:
            if changed or not require_change:return frame
    raise ValueError('未获得可靠画面响应/落稳反馈，停止继续输入')
