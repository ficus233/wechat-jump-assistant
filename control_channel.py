"""Local, allowlisted command channel; no sockets or keyboard simulation."""
import json,os,time,threading,uuid
from pathlib import Path

COMMANDS={'resume','pause','stop'}

def write_json(path,value,best_effort=False):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_name(path.name+f'.{os.getpid()}.{threading.get_ident()}.tmp')
    temp.write_text(json.dumps(value,ensure_ascii=False,indent=2),'utf-8')
    try:
        attempts=2 if best_effort else 6
        for attempt in range(attempts):
            try:os.replace(temp,path);return True
            except PermissionError:
                if attempt==attempts-1:
                    if best_effort:return False
                    raise
                time.sleep(.002 if best_effort else .002*(2**attempt))
    finally:temp.unlink(missing_ok=True)

def read_json(path,default=None):
    try:return json.loads(Path(path).read_text('utf-8'))
    except (OSError,ValueError):return default

def send(root,action):
    if action not in COMMANDS:raise ValueError('不支持的控制命令')
    identifier=f'{time.time_ns()}-{uuid.uuid4().hex}'
    write_json(Path(root)/'control'/f'{identifier}.json',dict(id=identifier,action=action,time=time.time()))
    return identifier

def collect(root):
    folder=Path(root)/'control';folder.mkdir(exist_ok=True);commands=[]
    for path in sorted(folder.glob('*.json')):
        value=read_json(path,{})
        if value.get('action') in COMMANDS and time.time()-value.get('time',0)<10:commands.append(value)
        path.unlink(missing_ok=True)
    return commands

def alive(root):
    value=read_json(Path(root)/'background-heartbeat.json',{})
    return bool(value.get('alive') and time.time()-value.get('time',0)<3)
