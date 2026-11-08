"""Headless continuous screen/input loop. No canvas, Tk window, browser or port."""
import argparse,json,time,threading,traceback,sys,msvcrt
import os
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import cv2,numpy as np
import native
from core import detect,register_platform
from timing import wait_stable
from autocenter import AutoCenter
from control_channel import write_json,collect
from platforms import current_surface,remained_on_platform
from measurements import Measurements
from geometry_setup import standardize_window

ROOT=Path(__file__).resolve().parent

def select_target(d):
    source=current_surface(d)
    def valid(c):
        return c['confidence']>0 and (source is None or cv2.pointPolygonTest(np.array(source['contour'],np.float32),tuple(map(float,c['point'])),False)<0)
    if d['target'] and valid(d['target']):return d['target']
    candidates=[c for c in d['candidates'] if valid(c)]
    if not candidates:candidates=[c for c in d.get('fallback_candidates',[]) if valid(c)]
    return max(candidates,key=lambda c:(c['confidence'],c['point'][1])) if candidates else None

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--steps',type=int,default=0);parser.add_argument('--paused',action='store_true');args=parser.parse_args()
    lock=(ROOT/'.instance.lock').open('a+b');lock.seek(0,2)
    if not lock.tell():lock.write(b'1');lock.flush()
    lock.seek(0)
    try:msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
    except OSError:print('已有实例运行');return
    cfg=json.loads((ROOT/'config.json').read_text('utf-8'))
    session=ROOT/'sessions'/time.strftime('%Y%m%d-%H%M%S-background');session.mkdir(parents=True,exist_ok=True)
    cancel=threading.Event();stop=threading.Event();log_lock=threading.Lock();last_status={}
    if args.paused:cancel.set()
    def log(event,data=None):
        record=dict(time=time.time(),monotonic=time.perf_counter(),event=event,data=data)
        with log_lock:
            with (session/'events.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(record,ensure_ascii=False)+'\n')
    def status(state,**data):
        nonlocal last_status
        value={**last_status,'state':state,'reason':'',**data}
        if value==last_status:return
        last_status=value
        write_json(ROOT/'background-status.json',dict(time=time.time(),**value),best_effort=True)
    def key(value):
        log('key_received',value)
        if value=='F10':cancel.set();status('paused')
        elif value=='F9':cancel.clear();status('running')
        elif value=='F7':cancel.set();stop.set()
        elif value.startswith('error:'):cancel.set();status('hotkey_error',reason=value)
    ready=threading.Event();threading.Thread(target=native.hotkeys,args=(key,ready,{4:(0x76,'F7')}),daemon=True).start();ready.wait(2)
    def controls():
        next_heartbeat=0.
        while not stop.is_set():
            try:
                for command in collect(ROOT):
                    key({'resume':'F9','pause':'F10','stop':'F7'}[command['action']])
                    write_json(ROOT/'control-result.json',dict(id=command['id'],action=command['action'],ok=True,time=time.time()))
                if time.monotonic()>=next_heartbeat:
                    write_json(ROOT/'background-heartbeat.json',dict(alive=True,pid=os.getpid(),time=time.time(),session=session.name),best_effort=True)
                    next_heartbeat=time.monotonic()+.5
            except Exception:log('control_issue',traceback.format_exc())
            stop.wait(.025)
    control_thread=threading.Thread(target=controls,daemon=True);control_thread.start()
    status('paused' if cancel.is_set() else 'starting',jumps=0)
    pool=ThreadPoolExecutor(max_workers=1,thread_name_prefix='landing-calibration')
    controller=None;signature=None;frame=None;cached_detection=None;jumps=0;origin_time=time.perf_counter();jobs=[];last_missed=0.
    normalized_hwnd=None;blocked=None;platform_id=0;ledger=Measurements(ROOT,session);attempts=0
    log('startup',dict(mode='background',auto_center=True,config=cfg))
    def calibrate(before,after,target,piece,post_piece,actual,requested,seq,control,sig,same,source_id):
        row=dict(record_id=f'{session.name}/{seq}',time=time.time(),signature=sig,direction='right' if target['point'][0]>=piece[0] else 'left',
            source_platform_id=source_id,target_platform_id=source_id+1,actual_platform_id=(source_id if same else source_id+1) if post_piece else None,target_method=target.get('method'),target_distance_px=float(np.linalg.norm(np.array(target['point'])-piece)),
            requested_ms=requested,actual_ms=actual,piece_x=piece[0],piece_y=piece[1],same_platform=same,calibration_eligible=False,measurement_status='unconfirmed',
            before_frame=f'{seq}-before.png',after_frame=f'{seq}-after.png')
        if post_piece:row.update(landing_x=post_piece['point'][0],landing_y=post_piece['point'][1])
        try:
            # Evidence and expensive registration run outside the next-jump path.
            cv2.imwrite(str(session/f'{seq}-before.png'),before,[cv2.IMWRITE_PNG_COMPRESSION,1])
            cv2.imwrite(str(session/f'{seq}-after.png'),after,[cv2.IMWRITE_PNG_COMPRESSION,1])
            if not post_piece:row['measurement_status']='no_landing_piece';return
            if same:row['measurement_status']='same_platform_no_repeat';return
            if target['confidence']<.8:
                row['measurement_status']='uncertain_target_geometry'
                log('auto_center_skipped',dict(seq=seq,reason='备用轮廓顶面中心未确认，不修改系数'));return
            shift,quality=register_platform(before,after,target)
            report=control.observe(piece,target['point'],post_piece['point'],shift,actual,requested,quality)
            corrected=np.array(post_piece['point'])-shift;delta=corrected-piece
            axis=np.array(control.snapshot()[row['direction']]['axis'])
            row.update(camera_dx=float(shift[0]),camera_dy=float(shift[1]),displacement_dx=float(delta[0]),displacement_dy=float(delta[1]),
                displacement_px=float(np.linalg.norm(delta)),projected_displacement_px=float(delta@axis),landing_error_px=float(np.linalg.norm(corrected-target['point'])),
                registration_confidence=quality,calibration_eligible=report['updated'],measurement_status='registered' if report['updated'] else 'registered_untrusted')
            report.update(seq=seq,camera_shift=shift.tolist(),piece=piece,target=target['point'],landing=post_piece['point'],actual_ms=actual,requested_ms=requested)
            log('auto_center_update',report)
            state=dict(signature=sig,directions=control.snapshot(),calibration_version=2)
            write_json(ROOT/'auto-center-state.json',state)
        except Exception:
            row['measurement_status']='camera_registration_failed';log('calibration_unavailable',dict(seq=seq,reason=traceback.format_exc()))
        finally:ledger.append(row)
    try:
        while not stop.is_set():
            if cancel.is_set():stop.wait(.10);frame=None;continue
            windows=native.windows()
            if len(windows)!=1:status('waiting_window',candidates=len(windows));stop.wait(.20);continue
            hwnd=windows[0][0];g=native.geometry(hwnd);roi=list(cfg['calibrated_roi'])
            expected=cfg.get('standard_client_size',cfg['model']['signature'][:2])
            if normalized_hwnd!=hwnd or [g['width'],g['height']]!=list(expected):
                try:
                    status('normalizing_window',jumps=jumps);g,details=standardize_window(hwnd,cfg);log('standard_geometry',details)
                    normalized_hwnd=hwnd;signature=None;frame=None;cached_detection=None;blocked=None
                    if cancel.wait(.12):continue
                except Exception as e:status('waiting_canvas',reason=str(e));stop.wait(.2);continue
            if roi[0]+roi[2]>g['width'] or roi[1]+roi[3]>g['height']:
                status('waiting_canvas',reason='窗口布局变化，请用debug.bat重新框选');stop.wait(.2);continue
            sig=[g['width'],g['height'],g['dpi'],roi,cfg['metric']]
            if sig!=signature:
                state=None
                try:
                    saved=json.loads((ROOT/'auto-center-state.json').read_text('utf-8'))
                    if saved.get('signature')==sig and saved.get('calibration_version')==2:state=saved['directions']
                except (FileNotFoundError,ValueError,KeyError):pass
                controller=AutoCenter(cfg.get('directional_model'),cfg['model'],state)
                if state is None:log('historical_calibration_samples',ledger.prime(controller,sig))
                try:
                    history=[json.loads(line) for line in (ROOT/'jump-measurements.jsonl').read_text('utf-8').splitlines()[-5000:]]
                    controller.prime_precision([row for row in history if row.get('signature')==sig])
                    log('precision_models',controller.snapshot())
                except (FileNotFoundError,ValueError,KeyError):pass
                signature=sig;frame=None
            def grab():
                current=native.geometry(hwnd)
                if [current['width'],current['height'],current['dpi']]!=sig[:3]:raise ValueError('窗口尺寸改变，重新定位')
                return native.capture(current,roi)
            sent=False;input_result={};plan=None
            try:
                if frame is None:
                    cached_detection=None;frame=wait_stable(grab,cancel,cfg['stable_delta'],stable_for=.20,poll_interval=.04)
                d=cached_detection if cached_detection is not None else detect(frame,cfg)
                cached_detection=None;target=select_target(d);piece=d['piece']
                if blocked:
                    still_same,score=remained_on_platform(blocked['frame'],frame,blocked['source'],blocked['piece'],piece,blocked['target'])
                    if still_same or piece is None:
                        status('waiting_transition',jumps=jumps,reason='仍在已起跳的平台，不重复按压；等待离台或重新开始')
                        frame=None;stop.wait(.10);continue
                    blocked=None;platform_id+=1;log('platform_transition_recovered',dict(platform_id=platform_id,static_score=score))
                if target is None:
                    d=detect(frame,cfg,include_fallback=True);target=select_target(d);piece=d['piece']
                if piece is None or target is None:
                    status('recognizing',jumps=jumps,reason='正在按顶面结构重识别，不依赖平台之间的地面')
                    if time.monotonic()-last_missed>3:
                        cv2.imwrite(str(session/'unrecognized-latest.png'),frame)
                        log('unrecognized',dict(piece=piece,candidates=d['candidates'],fallback=d.get('fallback_candidates',[])))
                        last_missed=time.monotonic()
                    frame=None;stop.wait(.08);continue
                # Revalidate once, but do not wait for stability a second time.
                current=grab()
                if np.mean(cv2.absdiff(current,frame))>cfg['stable_delta']:frame=None;continue
                plan=controller.predict(piece['point'],target['point']);before=frame;cycle=time.perf_counter()
                log('jump_plan',dict(seq=jumps,attempt=attempts+1,**plan,target=target['point'],piece=piece['point'],target_method=target.get('method','original-top'),target_confidence=target['confidence'],target_source=target.get('source')))
                source=current_surface(d);sent=False
                def input_log(event,data):
                    nonlocal sent,blocked,attempts
                    if event=='mouseDown':
                        sent=True;attempts+=1;blocked=dict(frame=before,source=source,piece=piece,target=target)
                    if event=='mouseUp':input_result.update(data)
                    log(event,data)
                actual=native.press(hwnd,roi,plan['requested_ms'],cancel,input_log,unrestricted=True)
                after=wait_stable(grab,cancel,cfg['stable_delta'],reference=before,require_change=True,stable_for=.20,poll_interval=.04)
                post=detect(after,cfg);jumps+=1
                same,static_score=remained_on_platform(before,after,source,piece,post['piece'],target)
                source_id=platform_id
                if not same and post['piece'] is not None:blocked=None;platform_id+=1
                log('platform_transition',dict(seq=jumps,source_id=source_id,destination_id=platform_id,same_platform=same,static_score=static_score))
                log('jump_landed',dict(seq=jumps,actual_ms=actual,cycle_ms=(time.perf_counter()-cycle)*1000,piece_detected=post['piece'] is not None))
                jobs=[j for j in jobs if not j.done()]
                if len(jobs)<3:jobs.append(pool.submit(calibrate,before,after,target,piece['point'],post['piece'],actual,plan['requested_ms'],attempts,controller,list(sig),same,source_id))
                else:
                    ledger.append(dict(record_id=f'{session.name}/{attempts}',time=time.time(),signature=list(sig),direction=plan['direction'],requested_ms=plan['requested_ms'],actual_ms=actual,source_platform_id=source_id,target_platform_id=source_id+1,calibration_eligible=False,measurement_status='calibration_queue_busy'))
                    log('calibration_skipped','后台队列忙，继续下一跳')
                status('running',jumps=jumps,attempts=attempts,requested_ms=round(plan['requested_ms'],3),actual_ms=round(actual,3),direction=plan['direction'])
                frame=after;cached_detection=post
                if post['piece'] is None:cancel.set();status('paused_no_piece',jumps=jumps)
                if args.steps and jumps>=args.steps:break
            except Exception as e:
                if sent and plan:
                    ledger.append(dict(record_id=f'{session.name}/{attempts}',time=time.time(),signature=list(sig),direction=plan['direction'],
                        requested_ms=plan['requested_ms'],actual_ms=input_result.get('actual_ms'),source_platform_id=platform_id,target_platform_id=platform_id+1,
                        calibration_eligible=False,measurement_status='input_interrupted',reason=str(e),piece_x=piece['point'][0],piece_y=piece['point'][1]))
                log('loop_issue',traceback.format_exc());frame=None
                if '焦点' in str(e) or '失焦' in str(e) or '响应' in str(e):cancel.set();status('paused',reason=str(e),jumps=jumps)
                elif not cancel.is_set():status('recognizing',reason=str(e));stop.wait(.10)
    finally:
        cancel.set();stop.set();control_thread.join(timeout=1);pool.shutdown(wait=True);native.close_capture()
        status('stopped',jumps=jumps,elapsed_s=round(time.perf_counter()-origin_time,3));log('stopped',dict(jumps=jumps))
        write_json(ROOT/'background-heartbeat.json',dict(alive=False,pid=os.getpid(),time=time.time()))
        lock.close()

if __name__=='__main__':main()
