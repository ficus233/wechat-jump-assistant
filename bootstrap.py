"""Cache successful dependency setup; never contact pip on an unchanged launch."""
import hashlib,json,sys,importlib
from pathlib import Path
root=Path(__file__).resolve().parent
marker=root/'.venv'/'dependency-state.json'
digest=hashlib.sha256((root/'requirements.txt').read_bytes()).hexdigest()
try:
    if '--check' in sys.argv:
        if json.loads(marker.read_text('utf-8'))['requirements_sha256']!=digest:raise ValueError('requirements changed')
    for name in ['numpy','cv2','mss','pyautogui','PIL']:importlib.import_module(name)
    if '--stamp' in sys.argv:marker.write_text(json.dumps({'requirements_sha256':digest}),'utf-8')
except Exception as exc:
    print('Dependency setup required:',exc)
    raise SystemExit(1)
