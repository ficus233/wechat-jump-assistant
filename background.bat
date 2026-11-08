@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "PY="
if exist "..\..\work\python\python.exe" set "PY=..\..\work\python\python.exe"
if not defined PY (
  py -3 -c "import sys;assert sys.version_info >= (3,11)" >nul 2>&1
  if not errorlevel 1 set "PY=py -3"
)
if not defined PY (
  python -c "import sys;assert sys.version_info >= (3,11)" >nul 2>&1
  if not errorlevel 1 set "PY=python"
)
if not defined PY (
  echo [失败] 没有可运行的 Python 3.11+。请从 python.org 安装，包含 Tcl/Tk 和 pip。
  echo WindowsApps 中的 python 占位入口不是 Python。安装后重新双击。
  pause
  exit /b 1
)
echo [1/3] 检查独立环境...
if not exist .venv\Scripts\python.exe %PY% -m venv .venv
if errorlevel 1 goto fail
echo [2/3] 检查依赖缓存...
.venv\Scripts\python.exe bootstrap.py --check >dependency-check.log 2>&1
if not errorlevel 1 goto ready
echo 首次安装或依赖变化，正在安装，详情见 install.log...
.venv\Scripts\python.exe -m pip install -r requirements.txt >install.log 2>&1
if errorlevel 1 goto fail
.venv\Scripts\python.exe bootstrap.py --stamp >>install.log 2>&1
if errorlevel 1 goto fail
:ready
echo [3/3] 后台自动运行：F10暂停 / F9继续 / F7退出。
start "" /b ".venv\Scripts\pythonw.exe" background.py
if errorlevel 1 goto fail
exit /b 0
:fail
echo [失败] 请查看 install.log / startup.log，日志已保留。
pause
exit /b 1
