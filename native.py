import ctypes as C
from ctypes import wintypes as W
import time, threading, math
import numpy as np
import mss
from timing import wait_until_ns,timer_resolution
u=C.windll.user32
try: u.SetProcessDpiAwarenessContext(C.c_void_p(-4))
except Exception: pass
u.GetForegroundWindow.restype=W.HWND
u.WindowFromPoint.argtypes=[W.POINT]; u.WindowFromPoint.restype=W.HWND
u.GetAncestor.argtypes=[W.HWND,W.UINT];u.GetAncestor.restype=W.HWND
u.GetWindowLongW.argtypes=[W.HWND,C.c_int]
u.IsWindow.argtypes=[W.HWND];u.IsIconic.argtypes=[W.HWND]
u.IsWindowVisible.argtypes=[W.HWND];u.GetClientRect.argtypes=[W.HWND,C.POINTER(W.RECT)]
u.ClientToScreen.argtypes=[W.HWND,C.POINTER(W.POINT)]
u.GetDpiForWindow.argtypes=[W.HWND];u.SetForegroundWindow.argtypes=[W.HWND]
import pyautogui as pg
pg.PAUSE=0
_captures=threading.local()

def windows():
    result=[]
    @C.WINFUNCTYPE(W.BOOL,W.HWND,W.LPARAM)
    def cb(hwnd,_):
        n=u.GetWindowTextLengthW(hwnd); s=C.create_unicode_buffer(n+1); u.GetWindowTextW(hwnd,s,n+1)
        if u.IsWindowVisible(hwnd) and s.value.strip()=='跳一跳': result.append((int(hwnd),s.value))
        return True
    u.EnumWindows(cb,0); return result

def geometry(hwnd):
    if not u.IsWindow(hwnd) or u.IsIconic(hwnd): raise ValueError('窗口不存在或已最小化')
    r=W.RECT(); u.GetClientRect(hwnd,C.byref(r)); p=W.POINT(0,0);u.ClientToScreen(hwnd,C.byref(p))
    return dict(hwnd=hwnd,left=p.x,top=p.y,width=r.right,height=r.bottom,dpi=u.GetDpiForWindow(hwnd),foreground=int(u.GetForegroundWindow() or 0),visible=bool(u.IsWindowVisible(hwnd)),topmost=bool(u.GetWindowLongW(hwnd,-20)&8))

def restore_client_size(hwnd,width,height,dpi):
    """Restore measured physical geometry; never relabel an incompatible model."""
    g=geometry(hwnd)
    if g['dpi']!=dpi:raise ValueError(f'当前DPI {g["dpi"]}，校准DPI {dpi}，请移回原显示器或重新校准')
    rect=W.RECT();u.GetWindowRect.argtypes=[W.HWND,C.POINTER(W.RECT)]
    u.SetWindowPos.argtypes=[W.HWND,W.HWND,C.c_int,C.c_int,C.c_int,C.c_int,W.UINT]
    for _ in range(3):
        g=geometry(hwnd)
        if [g['width'],g['height']]==[width,height]:return g
        u.GetWindowRect(hwnd,C.byref(rect))
        outer_w=rect.right-rect.left+width-g['width'];outer_h=rect.bottom-rect.top+height-g['height']
        if not u.SetWindowPos(hwnd,None,0,0,outer_w,outer_h,0x2|0x4|0x10):raise ValueError('无法恢复校准窗口尺寸')
        time.sleep(.08)
    g=geometry(hwnd)
    if [g['width'],g['height']]!=[width,height]:raise ValueError(f'窗口未接受校准尺寸，实际{g["width"]}×{g["height"]}')
    return g

def capture(g,roi):
    x,y,w,h=roi
    if not hasattr(_captures,'screen'):_captures.screen=mss.mss()
    return np.asarray(_captures.screen.grab(dict(left=g['left']+x,top=g['top']+y,width=w,height=h)))[:,:,:3].copy()

def close_capture():
    if hasattr(_captures,'screen'):
        _captures.screen.close()
        del _captures.screen

def press(hwnd,roi,ms,cancel,log,point=None,unrestricted=False):
    if not math.isfinite(ms) or ms<=0:raise ValueError('时长必须是有限正数')
    if not unrestricted and not 30<=ms<=1500: raise ValueError('按压必须在30至1500ms之间')
    g=geometry(hwnd);x,y,w,h=roi;px=g['left']+x+w//2;py=g['top']+y+int(h*.85)
    if point is not None:
        if not (0<=point[0]<w and 0<=point[1]<h):raise ValueError('输入点不在画布内')
        px=g['left']+x+point[0];py=g['top']+y+point[1]
    if int(u.GetForegroundWindow() or 0)!=hwnd:
        u.SetForegroundWindow(hwnd)
        deadline=time.perf_counter()+.15
        while int(u.GetForegroundWindow() or 0)!=hwnd and time.perf_counter()<deadline:
            if cancel.wait(.01):raise ValueError('操作已暂停')
    if int(u.GetForegroundWindow() or 0)!=hwnd:
        log('focus_check_failed',geometry(hwnd))
        raise ValueError('焦点检查失败，未发送输入')
    pg.moveTo(px,py)
    if int(u.GetAncestor(u.WindowFromPoint(W.POINT(px,py)),2) or 0)!=hwnd: raise ValueError('输入位置被其他窗口遮挡')
    log('focus_check',geometry(hwnd));start_ns=None
    with timer_resolution() as timer_active:
        try:
            if cancel.is_set(): raise ValueError('操作已暂停')
            log('mouseDown',{'requested_ms':ms,'screen':[px,py]})
            down_call_ns=time.perf_counter_ns();pg.mouseDown();start_ns=time.perf_counter_ns()
            wait_until_ns(start_ns+round(ms*1_000_000),cancel,lambda:int(u.GetForegroundWindow() or 0)==hwnd)
        finally:
            # Never let the corner failsafe prevent releasing an already held button.
            saved=pg.FAILSAFE
            release_call_ns=time.perf_counter_ns()
            try:
                pg.FAILSAFE=False
                pg.mouseUp()
            finally:
                pg.FAILSAFE=saved
            end_ns=time.perf_counter_ns()
            actual_ms=None if start_ns is None else (end_ns-start_ns)/1_000_000
            log('mouseUp',{'actual_ms':actual_ms,'requested_ms':ms,
                'timing_error_ms':None if actual_ms is None else actual_ms-ms,
                'hold_to_release_call_ms':None if start_ns is None else (release_call_ns-start_ns)/1_000_000,
                'release_dispatch_ms':(end_ns-release_call_ns)/1_000_000,
                'press_dispatch_ms':None if start_ns is None else (start_ns-down_call_ns)/1_000_000,
                'timer_resolution_1ms':timer_active,'clock':'perf_counter_ns'})
    return actual_ms

def hotkeys(callback,ready,extra_keys=None):
    # OS message queue, independent of capture/inference; registration failure is visible.
    ids={1:(0x77,'F8'),2:(0x78,'F9'),3:(0x79,'F10')}
    if extra_keys:ids.update(extra_keys)
    ok=[]
    for i,(key,name) in ids.items():
        if u.RegisterHotKey(None,i,0x4000,key):ok.append(i)
        else: callback('error:'+name+':RegisterHotKey failed')
    ready.set();msg=W.MSG()
    try:
        while u.GetMessageW(C.byref(msg),None,0,0)>0:
            if msg.message==0x312: callback(ids[int(msg.wParam)][1])
    finally:
        for i in ok:u.UnregisterHotKey(None,i)
