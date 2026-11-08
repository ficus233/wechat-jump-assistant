import json,time,threading,queue,traceback,sys
from pathlib import Path
import tkinter as tk
from tkinter import ttk,messagebox
import cv2,numpy as np
from PIL import Image,ImageTk
from core import detect,distance,fit,translation,register_platform,validate_model_signature
import native
from timing import wait_stable
from policy import plan_press,landing_result
from directional import fit_directions,predict_direction
from geometry_setup import standardize_window

ROOT=Path(__file__).resolve().parent
class App:
    def __init__(self):
        self.root=tk.Tk();self.root.title('跳一跳 · 校准实验台');self.root.geometry('1000x850+0+0');self.root.attributes('-topmost',True)
        self.cfg=json.loads((ROOT/'config.json').read_text('utf-8')); self.q=queue.Queue();self.cancel=threading.Event();self.busy=False;self.auto=False;self.roi=None;self.hwnd=None;self.frame=None;self.points={};self.pending=None;self.template=None;self.input_verified=False
        self.hotkey_failed=False
        self.session=ROOT/'sessions'/time.strftime('%Y%m%d-%H%M%S');self.session.mkdir(parents=True,exist_ok=True)
        self.samples=json.loads((ROOT/'experiments/samples.json').read_text('utf-8')) if (ROOT/'experiments/samples.json').exists() else []; self.mode=None;self.scale=1.;self.sig=None
        self.status=tk.StringVar(value='首次：定位窗口 → 框选画布 → 标注 → 输入试跳 → 反馈与拟合')
        ttk.Label(self.root,textvariable=self.status,wraplength=1050).pack(fill='x')
        bar=ttk.Frame(self.root);bar.pack(fill='x')
        for label,fn in [('定位窗口',self.locate),('截图/调试',self.refresh),('框选画布',lambda:self.setmode('roi')),('标脚底',lambda:self.setmode('piece')),('标目标顶面',lambda:self.setmode('target')),('标落地点',lambda:self.setmode('landing')),('标同一平台',lambda:self.setmode('anchor')),('棋子模板',lambda:self.setmode('template'))]:ttk.Button(bar,text=label,command=fn).pack(side='left')
        bar2=ttk.Frame(self.root);bar2.pack(fill='x');self.ms=tk.StringVar(value='')
        ttk.Label(bar2,text='试跳ms（实测探索值）').pack(side='left');ttk.Entry(bar2,textvariable=self.ms,width=8).pack(side='left')
        for label,fn in [('一次试跳',lambda:self.launch(True)),('单步 F8',self.launch),('连续 F9',self.continuous),('暂停 F10',self.pause),('拟合模型',self.model),('重新开始/清标注',self.reset)]:ttk.Button(bar2,text=label,command=fn).pack(side='left')
        bar3=ttk.Frame(self.root);bar3.pack(fill='x')
        self.free_mode=tk.BooleanVar(value=self.cfg.get('free_mode',True))
        ttk.Checkbutton(bar3,text='自由试验',variable=self.free_mode).pack(side='left')
        self.direction_units=tk.BooleanVar(value=self.cfg.get('distance_model')=='direction_units')
        ttk.Checkbutton(bar3,text='双向整数单位',variable=self.direction_units).pack(side='left')
        ttk.Button(bar3,text='跳过本次反馈',command=self.skip_feedback).pack(side='left')
        ttk.Button(bar3,text='恢复校准尺寸',command=self.restore_calibration).pack(side='left')
        for result in ['成功','短了','长了','无响应','游戏结束']:
            ttk.Button(bar3,text=result,command=lambda r=result:self.feedback(r)).pack(side='left')
        self.canvas=tk.Canvas(self.root,bg='#202530',height=570);self.canvas.pack(fill='both',expand=True);self.canvas.bind('<ButtonPress-1>',self.down);self.canvas.bind('<ButtonRelease-1>',self.up)
        self.history=tk.Text(self.root,height=8);self.history.pack(fill='x')
        self.root.protocol('WM_DELETE_WINDOW',self.close)
        threading.Thread(target=native.hotkeys,args=(self.key,threading.Event()),daemon=True).start();self.root.after(100,self.pump)
        self.log('startup',{'config':self.cfg})
        if '--continue' in sys.argv:self.root.after(250,self.start_auto)
        self.root.mainloop()
    def log(self,event,data=None):
        record={'time':time.time(),'monotonic':time.perf_counter(),'event':event,'data':data}
        with (self.session/'events.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(record,ensure_ascii=False)+'\n')
        display=data
        if event=='recognition':
            display={k:data[k] for k in ['piece','target','ambiguous']}
            display={k:({kk:vv for kk,vv in v.items() if kk!='contour'} if isinstance(v,dict) else v) for k,v in display.items()}
        self.q.put(('log',event+' '+json.dumps(display,ensure_ascii=False)))
    def key(self,key):
        self.log('key_received',key)
        if key.startswith('error:'):self.hotkey_failed=True;self.cancel.set()
        if key=='F10': self.cancel.set();self.auto=False
        self.q.put(('key',key))
    def pump(self):
        try:
            while True:
                kind,value=self.q.get_nowait()
                if kind=='log':self.history.insert('end',value+'\n');self.history.see('end')
                elif kind=='key':
                    if value=='F8':self.launch()
                    elif value=='F9':self.continuous()
                    elif value=='F10':self.pause()
                    else:self.status.set(value)
                elif kind=='done':
                    self.busy=False;self.pending=value;self.frame=value.pop('_after');self.points={};self.draw()
                    self.status.set(f'请求 {value["requested_ms"]:.3f}ms / 实际 {value["actual_ms"]:.3f}ms / 偏差 {value["actual_ms"]-value["requested_ms"]:+.3f}ms；落稳帧已保存，可反馈或跳过')
                    if self.auto:self.auto_feedback()
                elif kind=='error':self.busy=False;self.pause();self.status.set(value.strip().splitlines()[-1])
                elif kind=='reobserve':
                    self.busy=False;self.frame=value;self.points={};self.draw()
                    self.status.set('画面变化，已自动重新识别，继续下一跳')
                    self.root.after(30,self.next_auto)
        except queue.Empty:pass
        self.root.after(30,self.pump)
    def locate(self):
        ws=native.windows()
        if len(ws)!=1:self.status.set('窗口候选不唯一：'+str(ws));return
        try:
            _,report=standardize_window(ws[0][0],self.cfg);self.log('standard_geometry',report)
        except Exception as e:self.status.set(str(e));return
        self.hwnd=ws[0][0];self.roi=self.cfg.get('calibrated_roi');self.sig=None;self.points={};self.input_verified=bool(self.cfg.get('model'));self.refresh()
    def restore_calibration(self):
        if self.busy:self.status.set('请先暂停并等待鼠标释放');return
        try:
            if self.pending:raise ValueError('请先处理上一跳反馈，恢复尺寸会改变画面')
            saved=json.loads((ROOT/'config.json').read_text('utf-8'))
            model=saved.get('model')
            if not model:raise ValueError('没有已保存校准模型，请先采样拟合')
            signature=model['signature']
            if not self.hwnd:
                ws=native.windows()
                if len(ws)!=1:raise ValueError('请先定位唯一游戏窗口')
                self.hwnd=ws[0][0]
            self.pause();g=native.restore_client_size(self.hwnd,*signature[:3])
            self.cfg['model']=model;self.cfg['metric']=signature[4];self.roi=list(signature[3]);self.sig=None;self.points={};self.input_verified=True
            self.log('restored_calibration',g);self.refresh()
            self.status.set(f'已恢复校准尺寸{g["width"]}×{g["height"]}、DPI{g["dpi"]}及原画布，请检查截图后单步')
        except Exception as e:self.status.set(str(e));self.log('restore_failed',str(e))
    def geo(self):
        if not self.hwnd:raise ValueError('先定位窗口')
        g=native.geometry(self.hwnd);sig=[g['width'],g['height'],g['dpi'],self.roi,self.cfg['metric']]
        if self.sig and self.sig!=sig and (self.busy or not self.free_mode.get()):raise ValueError('尺寸/DPI/画布改变，重新定位框选与校准')
        return g,sig
    def refresh(self):
        if self.busy:return
        try:
            g,sig=self.geo();self.frame=native.capture(g,self.roi or [0,0,g['width'],g['height']]);self.points={};self.draw();self.log('geometry',g);self.status.set(str(g))
        except Exception as e:self.status.set(str(e))
    def setmode(self,m):
        if self.busy:return
        if m=='roi' and self.roi:self.roi=None;self.sig=None;self.refresh()
        self.mode=m;self.status.set('拖动框选' if m in ['roi','template'] else '点击'+m+'；脚底为接触面中心，目标为顶面中心，白点须检查')
    def down(self,e):self.start=(int(e.x/self.scale),int(e.y/self.scale))
    def up(self,e):
        if self.frame is None or not self.mode:return
        p=(int(e.x/self.scale),int(e.y/self.scale));h,w=self.frame.shape[:2]
        if not(0<=p[0]<w and 0<=p[1]<h):return
        if self.mode in ['roi','template']:
            x,y=min(self.start[0],p[0]),min(self.start[1],p[1]);bw,bh=abs(p[0]-self.start[0]),abs(p[1]-self.start[1])
            if min(bw,bh)<10:return
            if self.mode=='roi':self.roi=[x,y,bw,bh];self.sig=None;self.input_verified=False;self.refresh()
            else:self.template=self.frame[y:y+bh,x:x+bw].copy();cv2.imwrite(str(self.session/'piece-template.png'),self.template)
        else:
            self.points[self.mode]=list(p);g,_=self.geo();offset=np.array([g['left']+(self.roi or [0,0])[0],g['top']+(self.roi or [0,0])[1]])
            auto=(self.det.get('piece') if self.mode=='piece' else self.det.get('target'))
            self.log('annotation',dict(kind=self.mode,local=p,screen=(np.array(p)+offset).tolist(),error_px=None if auto is None else distance(p,auto['point'])));self.draw(redetect=False)
        self.mode=None
    def draw(self,redetect=True):
        if self.frame is None:return
        if redetect:
            started=time.perf_counter();self.det=detect(self.frame,self.cfg,self.template)
            if self.free_mode.get() and self.det['target'] is None:
                candidates=[c for c in self.det['candidates'] if c['confidence']>0]
                if candidates:
                    self.det['target']=max(candidates,key=lambda c:(c['confidence'],c['point'][1]))
                    self.log('experiment_warning','多个候选，按置信度和前方距离选择；全部候选保留在日志')
            self.log('detection_ms',(time.perf_counter()-started)*1000)
        im=self.frame.copy()
        for c in self.det['candidates']:cv2.polylines(im,[np.array(c['contour'],np.int32)],True,(0,160,255),1)
        for name,color in [('piece',(60,255,60)),('target',(0,0,255))]:
            item=self.det[name];p=self.points.get(name,item['point'] if item else None)
            if p is not None:cv2.drawMarker(im,tuple(map(int,p)),color,cv2.MARKER_CROSS,20,2)
        for name,p in self.points.items():cv2.circle(im,tuple(p),5,(255,0,255),2)
        if self.direction_units.get() and self.det['piece'] and self.cfg.get('directional_model'):
            origin=np.array(self.points.get('piece',self.det['piece']['point']),float)
            for name,axis_model in self.cfg['directional_model']['directions'].items():
                axis=np.array(axis_model['axis']);normal=np.array(axis_model['normal']);unit=axis_model['unit_px']
                color=(255,190,30) if name=='left' else (30,210,255)
                end=origin+axis*unit*6
                cv2.arrowedLine(im,tuple(origin.astype(int)),tuple(end.astype(int)),color,1,tipLength=.12)
                normal_end=origin+normal*unit*2
                cv2.arrowedLine(im,tuple(origin.astype(int)),tuple(normal_end.astype(int)),color,1,tipLength=.15)
                cv2.putText(im,'O',tuple((origin+[4,12]).astype(int)),cv2.FONT_HERSHEY_SIMPLEX,.35,color,1)
                for n in range(1,7):
                    tick=origin+axis*unit*n
                    cv2.line(im,tuple((tick-normal*3).astype(int)),tuple((tick+normal*3).astype(int)),color,1)
                cv2.putText(im,f'{name[0].upper()}: 1u={unit:.2f}px',tuple((end+[0,-6]).astype(int)),cv2.FONT_HERSHEY_SIMPLEX,.35,color,1,cv2.LINE_AA)
        self.scale=min(1000/im.shape[1],550/im.shape[0],1.);im=cv2.resize(im,None,fx=self.scale,fy=self.scale)
        self.photo=ImageTk.PhotoImage(Image.fromarray(cv2.cvtColor(im,cv2.COLOR_BGR2RGB)));self.canvas.delete('all');self.canvas.create_image(0,0,anchor='nw',image=self.photo)
        if redetect:self.log('recognition',self.det)
    def pause(self):self.cancel.set();self.auto=False;self.status.set('已暂停；进行中的按压将释放鼠标')
    def reset(self):
        self.pause();self.pending=None;self.points={};self.refresh();self.status.set('请在游戏中正常点击再来一局，然后截图；保留校准历史')
    def continuous(self):
        self.auto=True;self.launch()
    def start_auto(self):
        self.locate();self.continuous()
    def retry_recognition(self):
        if self.auto and not self.cancel.is_set() and not self.busy and not self.pending:
            self.refresh();self.root.after(30,self.next_auto)
    def skip_feedback(self):
        if self.busy:return
        self.pause()
        if self.pending:
            rec=dict(self.pending);rec['result']='skipped';rec['displacement']=None
            self.samples.append(rec);self.log('feedback_skipped',rec)
            (self.session/'samples.json').write_text(json.dumps(self.samples,ensure_ascii=False,indent=2),'utf-8')
        self.pending=None;self.refresh();self.status.set('已跳过本次反馈，可重新单步或连续；该记录不参与拟合')
    def launch(self,trial=False):
        if self.busy:return
        try:
            if self.hotkey_failed:raise ValueError('全局热键注册失败，关闭重复实例或解决冲突后重启')
            if self.pending:raise ValueError('上一跳未收到反馈，禁止继续')
            if not self.roi:raise ValueError('先框选游戏画布，排除侧栏和分数')
            g,sig=self.geo()
            if self.sig and sig!=self.sig:
                self.frame=native.capture(g,self.roi);self.points={};self.draw()
            self.sig=sig
            p=self.points.get('piece',(self.det['piece'] or {}).get('point'));t=self.points.get('target',(self.det['target'] or {}).get('point'))
            if not trial and (p is None or t is None):
                if self.auto:
                    self.status.set('等待棋子/下一目标出现，自动重新识别；F10停止')
                    self.root.after(200,self.retry_recognition);return
                raise ValueError('请标出脚底和目标，或填写ms使用一次试跳')
            d=distance(p,t,self.cfg['metric']) if p is not None and t is not None else None
            trial_ms=None
            if trial:
                text=self.ms.get().strip()
                if text:
                    try:trial_ms=float(text)
                    except ValueError:raise ValueError('按压时长请填写毫秒数，支持小数，例如500.5')
                elif d is None:raise ValueError('请填写按压时长（毫秒），或先标出脚底和目标让模型预测')
            ms,warnings=plan_press(self.cfg['model'],sig,d,free=self.free_mode.get(),trial_ms=trial_ms,max_ms=self.cfg['max_ms'],input_verified=self.input_verified,confidence=(self.det['target'] or {}).get('confidence',0),automatic=self.auto)
            directional_measurement=None
            if trial_ms is None and self.direction_units.get() and p is not None and t is not None:
                try:
                    directional_model=self.cfg.get('directional_model')
                    if not directional_model:raise ValueError('双向单位模型未拟合，沿用原模型')
                    if directional_model['signature']!=sig:
                        if not self.free_mode.get():raise ValueError('双向单位模型尺度不同，请拟合或启用自由试验')
                        warnings.append('双向单位模型跨尺度试验')
                    directional_measurement=predict_direction(directional_model,p,t)
                    ms=directional_measurement['predicted_ms'];self.log('direction_units',directional_measurement)
                except ValueError as e:warnings.append(str(e))
            if trial:self.auto=False
            for warning in warnings:self.log('experiment_warning',warning)
            self.status.set(f'{d} {self.cfg["metric"]} → {ms:.2f}ms；'+('；'.join(warnings) if warnings else '检查焦点后执行'))
            if directional_measurement:
                v=directional_measurement
                self.status.set(f'{v["direction"]}方向：{v["raw_units"]:.3f} → {v["integer_units"]}单位；每单位{v["unit_px"]:.3f}px；取整残差{v["quantization_error_px"]:+.2f}px → {ms:.3f}ms')
            unrestricted=self.free_mode.get()
            landing_earliest=0. if unrestricted else 1.20
            self.cancel.clear();self.busy=True;before=self.frame.copy();self.before_target=self.det['target'];seq=len(self.samples)
            def work():
                try:
                    started=time.perf_counter()
                    # Verify the annotated frame is still current and settled before input.
                    last=native.capture(g,self.roi)
                    if np.mean(cv2.absdiff(last,before))>self.cfg['stable_delta']:
                        if self.auto:
                            fresh=wait_stable(lambda:native.capture(self.geo()[0],self.roi),self.cancel,self.cfg['stable_delta'])
                            self.log('auto_reobserve','起跳前画面变化，重新识别而不使用旧坐标')
                            self.q.put(('reobserve',fresh));return
                        raise ValueError('画面已变化，请重新截图标注')
                    wait_stable(lambda:native.capture(self.geo()[0],self.roi),self.cancel,self.cfg['stable_delta'])
                    cv2.imwrite(str(self.session/f'{seq}-before.png'),before)
                    actual=native.press(self.hwnd,self.roi,ms,self.cancel,self.log,unrestricted=unrestricted)
                    last=wait_stable(lambda:native.capture(self.geo()[0],self.roi),self.cancel,self.cfg['stable_delta'],reference=before,require_change=True,earliest=landing_earliest)
                    self.log('jump_cycle_ms',(time.perf_counter()-started)*1000)
                    cv2.imwrite(str(self.session/f'{seq}-after.png'),last)
                    rec=dict(signature=sig,piece=p,target=t,target_distance=d,directional_measurement=directional_measurement,requested_ms=ms,actual_ms=actual,geometry=g,result='unconfirmed',displacement=None,seq=seq,_after=last)
                    self.before=before;self.q.put(('done',rec))
                except Exception:self.log('exception',traceback.format_exc());self.q.put(('error',traceback.format_exc()))
                finally:native.close_capture()
            threading.Thread(target=work,daemon=True).start()
        except Exception as e:self.auto=False;self.status.set(str(e));self.log('blocked',str(e))
    def auto_feedback(self):
        try:
            if not self.det['piece']:raise ValueError('未识别到落稳棋子，不能确定是否游戏结束')
            if np.mean(cv2.absdiff(self.before,self.frame))<.1:raise ValueError('无响应，禁止继续')
            keep_going=self.cfg.get('continue_on_deviation',True)
            error_px=None;landing=np.array(self.det['piece']['point'])
            try:
                if not self.before_target:raise ValueError('原平台未标识')
                shift,q=register_platform(self.before,self.frame,self.before_target)
                expected=np.array(self.pending['target'])+shift
                error_px=float(np.linalg.norm(landing-expected))
                self.points['landing']=landing.tolist();self.points['anchor']=expected.tolist();self.pending['registration_confidence']=q
            except ValueError as e:
                if not keep_going:raise
                self.log('landing_registration_warning',str(e))
            result=landing_result(error_px,keep_going)
            self.pending['landing_error_px']=error_px
            self.pending['calibration_eligible']=result=='成功'
            if result=='偏差继续':
                self.log('deviation_continue',{'error_px':error_px,'next_target_detected':self.det['target'] is not None})
            self.feedback(result)
        except Exception as e:self.pause();self.status.set(str(e));self.log('auto_paused',str(e))
    def feedback(self,result):
        if not self.pending:return
        rec=self.pending;rec['result']=result
        if result not in ['无响应','游戏结束']:self.input_verified=True
        if 'landing' in self.points and rec.get('piece') is not None:
            try:
                if 'anchor' in self.points:shift=np.array(self.points['anchor'])-rec['target'];quality='manual_same_platform'
                else:shift,quality=translation(self.before,self.frame,rec['target'])
                corrected=np.array(self.points['landing'])-shift
                rec['landing']=self.points['landing'];rec['landing_corrected']=corrected.tolist()
                rec['displacement']=distance(rec['piece'],corrected,self.cfg['metric']);rec['camera_shift']=shift.tolist();rec['registration']=quality
            except ValueError as e:self.status.set(str(e));return
        # Direction-only feedback is an inequality, never a fabricated displacement.
        if result in ['短了','长了']:rec['constraint']='T(target_distance) '+('>' if result=='短了' else '<')+' actual_ms'
        self.samples.append(rec);self.log('sample',rec);(self.session/'samples.json').write_text(json.dumps(self.samples,ensure_ascii=False,indent=2),'utf-8');self.pending=None
        if self.auto and result in ['成功','偏差继续']:
            self.points={};self.draw(redetect=False);self.status.set(f'{result}，准备下一跳');self.root.after(30,self.next_auto)
        elif self.auto:self.pause()
        else:self.status.set('反馈已保存；可继续采样或拟合')
    def next_auto(self):
        if self.auto and not self.cancel.is_set():self.launch()
    def model(self):
        try:
            self.cfg['model']=fit(self.samples,self.sig)
            try:self.cfg['directional_model']=fit_directions(self.samples,self.sig)
            except ValueError as e:self.log('directional_fit_warning',str(e))
            self.cfg['distance_model']='direction_units' if self.direction_units.get() else 'euclidean_px'
            (ROOT/'config.json').write_text(json.dumps(self.cfg,ensure_ascii=False,indent=2),'utf-8');self.status.set(str(self.cfg['model']))
        except Exception as e:self.status.set(str(e))
    def close(self):
        self.cancel.set()
        if self.busy:self.root.after(100,self.close)
        else:native.close_capture();self.root.destroy()

if __name__=='__main__':
    import msvcrt
    instance_lock=(ROOT/'.instance.lock').open('a+b');instance_lock.seek(0,2)
    if instance_lock.tell()==0:instance_lock.write(b'1');instance_lock.flush()
    instance_lock.seek(0)
    try:msvcrt.locking(instance_lock.fileno(),msvcrt.LK_NBLCK,1)
    except OSError:
        print('已有控制面板运行，请关闭旧面板后再启动。',flush=True)
        raise SystemExit(1)
    App()
