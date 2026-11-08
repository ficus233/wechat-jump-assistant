"""Read-only desktop diagnostic. Use --press-ms only for an explicit test jump."""
import argparse,json,time,threading
from pathlib import Path
import cv2
import native
from core import detect
p=argparse.ArgumentParser();p.add_argument('--roi',nargs=4,type=int);p.add_argument('--press-ms',type=float);p.add_argument('--point',nargs=2,type=int);args=p.parse_args()
root=Path(__file__).resolve().parent;out=root/'evidence';out.mkdir(exist_ok=True)
def log(event,data):
    line=json.dumps(dict(time=time.time(),event=event,data=data),ensure_ascii=False)
    print(line,flush=True)
    with (out/'probe.jsonl').open('a',encoding='utf-8') as f:f.write(line+'\n')
ws=native.windows();log('windows',ws)
if len(ws)!=1:raise RuntimeError('Expected unique game window')
hwnd=ws[0][0];g=native.geometry(hwnd);log('geometry',g);roi=args.roi or [0,0,g['width'],g['height']]
before=native.capture(g,roi);cv2.imwrite(str(out/'before.png'),before)
cfg=json.loads((root/'config.json').read_text('utf-8'));log('recognition',detect(before,cfg))
if args.press_ms is not None:
    running=threading.Event();running.set()
    def during():
        i=0
        while running.wait(.001) and running.is_set() and i<30:
            cv2.imwrite(str(out/f'during-{i:02}.png'),native.capture(native.geometry(hwnd),roi));i+=1;time.sleep(.04)
    t=threading.Thread(target=during);t.start()
    try:
        actual=native.press(hwnd,roi,args.press_ms,threading.Event(),log,point=args.point);log('actual_ms',actual)
    finally:running.clear();t.join()
    for i in range(12):
        time.sleep(.25);cv2.imwrite(str(out/f'after-{i:02}.png'),native.capture(native.geometry(hwnd),roi))
