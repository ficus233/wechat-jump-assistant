"""Bounded real-game experiment. Same capture, detector and press as the panel."""
import argparse,time,json,threading
from pathlib import Path
import cv2,numpy as np
import native
from timing import wait_stable
from policy import landing_result
from core import detect,distance,translation,fit,register_platform
p=argparse.ArgumentParser();p.add_argument('--ms',type=float);p.add_argument('--steps',type=int,default=1);args=p.parse_args()
root=Path(__file__).resolve().parent;out=root/'experiments';out.mkdir(exist_ok=True)
cfg=json.loads((root/'config.json').read_text('utf-8'));roi=[520,250,550,700]
ws=native.windows();assert len(ws)==1;hwnd=ws[0][0];g=native.geometry(hwnd)
sig=[g['width'],g['height'],g['dpi'],roi,cfg['metric']]
samples=json.loads((out/'samples.json').read_text('utf-8')) if (out/'samples.json').exists() else []
cancel=threading.Event()
def log(event,data):
    with (out/'events.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(dict(time=time.time(),event=event,data=data),ensure_ascii=False)+'\n')
    if event!='recognition':print(event,data,flush=True)
def key(k):
    log('key_received',k)
    if k in ['F8','F9','F10'] or k.startswith('error'):cancel.set()
threading.Thread(target=native.hotkeys,args=(key,threading.Event()),daemon=True).start()
def stable():
    return wait_stable(lambda:native.capture(native.geometry(hwnd),roi),cancel,cfg['stable_delta'])
for _ in range(min(args.steps,10)):
    seq=len(samples);before=stable();d=detect(before,cfg);log('recognition',d)
    if d['piece'] is None or d['target'] is None or d['target']['confidence']<.8:raise RuntimeError('识别不可靠')
    piece=d['piece']['point'];target=d['target']['point'];dist=distance(piece,target)
    log('distance',{'px':dist,'piece':piece,'target':target})
    if args.ms is not None:ms=args.ms
    else:
        m=fit(samples,sig)
        if not m['min_d']*.9<=dist<=m['max_d']*1.1:raise RuntimeError('超出校准范围')
        ms=m['k']*dist+m['b'];log('model',m)
    cv2.imwrite(str(out/f'{seq}-before.png'),before)
    actual=native.press(hwnd,roi,ms,cancel,log,point=[300,380])
    after=wait_stable(lambda:native.capture(native.geometry(hwnd),roi),cancel,cfg['stable_delta'],reference=before,require_change=True,earliest=1.20)
    cv2.imwrite(str(out/f'{seq}-after.png'),after)
    post=detect(after,cfg)
    if post['piece'] is None:raise RuntimeError('无可靠落地棋子，停止')
    # Track a top-face corner, away from the piece occluding its center.
    contour=np.array(d['target']['contour']);vertex=contour[np.argmax(contour[:,0])].astype(float);vertex[0]-=14
    shift,quality=register_platform(before,after,d['target'])
    if np.linalg.norm(shift)>max(roi[2:]):raise RuntimeError('镜头对应越界，需人工核实')
    landing=np.array(post['piece']['point']);error=landing-(np.array(target)+shift)
    result=landing_result(float(np.linalg.norm(error)),cfg.get('continue_on_deviation',True))
    rec=dict(signature=sig,piece=piece,target=target,target_distance=dist,displacement=distance(piece,landing-shift),requested_ms=ms,actual_ms=actual,result=result,camera_shift=shift.tolist(),match=quality,landing=landing.tolist(),error=error.tolist(),calibration_eligible=result=='成功')
    samples.append(rec);(out/'samples.json').write_text(json.dumps(samples,ensure_ascii=False,indent=2),'utf-8');log('sample',rec)
    if result not in ['成功','偏差继续']:raise RuntimeError('无可继续的落地状态')
