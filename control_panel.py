"""Small native control surface for the independent background game engine."""
import os,sys,time,subprocess,msvcrt
from pathlib import Path
import tkinter as tk
from tkinter import ttk
from control_channel import read_json,send,alive

ROOT=Path(__file__).resolve().parent
LABELS={'starting':'正在连接游戏','running':'自动游玩中','paused':'已暂停','recognizing':'正在识别下一目标','normalizing_window':'正在恢复标准窗口尺寸','waiting_transition':'等待确认已离开当前平台',
        'waiting_window':'等待游戏窗口','waiting_canvas':'需要重新框选画布','hotkey_error':'快捷键冲突',
        'paused_no_piece':'未识别到棋子，已暂停','stopped':'后台已退出'}

class Panel:
    def __init__(self):
        self.root=tk.Tk();self.root.title('跳一跳控制台');self.root.geometry('540x610+30+40');self.root.minsize(500,590)
        self.root.configure(bg='#f2f6fa');self.started=None;self.pending=None;self.debug_pending=False;self.last_message=None
        style=ttk.Style();style.theme_use('clam')
        style.configure('.',font=('Microsoft YaHei UI',10),background='#f2f6fa',foreground='#17324d')
        style.configure('TButton',padding=(14,10),background='#e2eaf2',borderwidth=0)
        style.map('TButton',background=[('active','#cfdeeb')])
        style.configure('Go.TButton',background='#167e63',foreground='white')
        style.map('Go.TButton',background=[('active','#11684f')])
        outer=ttk.Frame(self.root,padding=24);outer.pack(fill='both',expand=True)
        ttk.Label(outer,text='跳一跳',font=('Microsoft YaHei UI',23,'bold')).pack(anchor='w')
        ttk.Label(outer,text='后台连续游玩 · 自动居中',foreground='#60758a').pack(anchor='w',pady=(3,20))
        self.state=tk.StringVar(value='正在连接后台…');self.detail=tk.StringVar(value='')
        ttk.Label(outer,textvariable=self.state,font=('Microsoft YaHei UI',14,'bold'),wraplength=480).pack(anchor='w')
        ttk.Label(outer,textvariable=self.detail,foreground='#60758a',wraplength=480).pack(anchor='w',pady=(5,18))
        buttons=ttk.Frame(outer);buttons.pack(fill='x')
        for col,(label,command,kind) in enumerate([('开始',self.start,'Go.TButton'),('暂停',lambda:self.command('pause'),'TButton'),('继续',self.start,'TButton'),('退出后台',lambda:self.command('stop'),'TButton')]):
            buttons.columnconfigure(col,weight=1);ttk.Button(buttons,text=label,command=command,style=kind).grid(row=0,column=col,sticky='ew',padx=(0,6 if col<3 else 0))
        self.stats=tk.StringVar(value='本次输入  — 次     方向  —')
        ttk.Label(outer,textvariable=self.stats,font=('Microsoft YaHei UI',11)).pack(anchor='w',pady=(22,8))
        self.timing=tk.StringVar(value='请求 — ms    实际 — ms')
        ttk.Label(outer,textvariable=self.timing,foreground='#60758a').pack(anchor='w')
        ttk.Separator(outer).pack(fill='x',pady=18)
        ttk.Label(outer,text='自动居中',font=('Microsoft YaHei UI',12,'bold')).pack(anchor='w')
        row=ttk.Frame(outer);row.pack(fill='x',pady=(10,0));self.calibration={}
        for col,name in enumerate(['left','right']):
            row.columnconfigure(col,weight=1);cell=ttk.Frame(row,padding=(0,0,16,0));cell.grid(row=0,column=col,sticky='nsew')
            ttk.Label(cell,text='左向' if name=='left' else '右向',foreground='#60758a').pack(anchor='w')
            value=tk.StringVar(value='等待可靠样本');self.calibration[name]=value
            ttk.Label(cell,textvariable=value,justify='left',font=('Microsoft YaHei UI',10)).pack(anchor='w',pady=(5,0))
        tools=ttk.Frame(outer);tools.pack(fill='x',pady=(22,10))
        ttk.Button(tools,text='高级调试 / 框选',command=self.debug).pack(side='left')
        ttk.Button(tools,text='打开日志',command=self.logs).pack(side='left',padx=8)
        self.message=tk.StringVar(value='关闭此窗口后，后台仍可继续运行。')
        ttk.Label(outer,textvariable=self.message,wraplength=480,foreground='#60758a').pack(anchor='w',pady=(4,8))
        ttk.Label(outer,text='F9 继续    F10 暂停    F7 退出后台',foreground='#60758a',font=('Microsoft YaHei UI',9)).pack(anchor='w')
        self.root.after(50,self.poll);self.root.mainloop()
    def command(self,action):
        if not alive(ROOT):self.message.set('后台尚未启动，点击“开始”。');return
        identifier=send(ROOT,action);self.pending=(identifier,time.monotonic(),action)
        self.message.set({'pause':'正在暂停并释放鼠标…','resume':'正在继续…','stop':'正在退出后台…'}[action])
    def start(self):
        if alive(ROOT):self.command('resume');return
        if self.started is not None:return
        exe=Path(sys.executable).with_name('pythonw.exe')
        log=(ROOT/'controller-launch.log').open('a',encoding='utf-8')
        try:subprocess.Popen([str(exe),str(ROOT/'background.py'),'--paused'],cwd=ROOT,stdout=log,stderr=log,creationflags=0x08000000)
        finally:log.close()
        self.started=time.monotonic();self.message.set('正在启动后台引擎…')
    def debug(self):
        self.debug_pending=True
        if alive(ROOT):self.command('stop')
        else:self.open_debug()
    def open_debug(self):
        self.debug_pending=False
        exe=Path(sys.executable).with_name('pythonw.exe')
        subprocess.Popen([str(exe),str(ROOT/'app.py')],cwd=ROOT,creationflags=0x08000000)
        self.message.set('已打开调试画布；关闭调试窗口后可重新开始后台。')
    def logs(self):
        folder=ROOT/'sessions';folder.mkdir(exist_ok=True);os.startfile(folder)
    def poll(self):
        online=alive(ROOT);status=read_json(ROOT/'background-status.json',{})
        self.state.set(LABELS.get(status.get('state'),'后台运行中') if online else '后台未运行')
        self.detail.set(status.get('reason','识别、跳跃与校准在后台独立运行') if online else '点击“开始”即可连接游戏，无需打开截图画布。')
        self.stats.set(f'本次输入  {status.get("attempts",status.get("jumps",0))} 次     方向  '+{'left':'左','right':'右'}.get(status.get('direction'),'—'))
        req=status.get('requested_ms');act=status.get('actual_ms')
        self.timing.set(f'请求 {req:.3f} ms    实际 {act:.3f} ms    偏差 {act-req:+.3f} ms' if isinstance(req,(int,float)) and isinstance(act,(int,float)) else '请求 — ms    实际 — ms')
        model=read_json(ROOT/'auto-center-state.json',{}).get('directions',{})
        for name,text in self.calibration.items():
            value=model.get(name)
            text.set(f'{value["ms_per_px"]:.4f} ms / px\n已修正 {value.get("n",0)} 次' if value else '等待可靠样本')
        if self.started is not None:
            if online:self.started=None;self.command('resume')
            elif time.monotonic()-self.started>8:self.started=None;self.message.set('启动未完成。请关闭旧调试窗口，查看 controller-launch.log。')
        if self.pending:
            ack=read_json(ROOT/'control-result.json',{})
            if ack.get('id')==self.pending[0]:
                self.message.set({'pause':'已收到暂停指令；当前按压会释放。','resume':'已收到继续指令。','stop':'已收到退出指令。'}[self.pending[2]]);self.pending=None
            elif time.monotonic()-self.pending[1]>4:self.message.set('指令尚未确认，请检查后台状态。');self.pending=None
        if self.debug_pending and not online and status.get('state')=='stopped':self.open_debug()
        self.root.after(250,self.poll)

if __name__=='__main__':
    panel_lock=(ROOT/'.control-panel.lock').open('a+b');panel_lock.seek(0,2)
    if not panel_lock.tell():panel_lock.write(b'1');panel_lock.flush()
    panel_lock.seek(0)
    try:msvcrt.locking(panel_lock.fileno(),msvcrt.LK_NBLCK,1)
    except OSError:raise SystemExit('控制台已打开')
    Panel()
