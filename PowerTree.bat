@echo off
rem PowerTree launcher.
rem   Double-click / no arguments  -> desktop GUI
rem   With arguments               -> CLI  (e.g. PowerTree info file.ptproj,
rem                                   PowerTree validate x.ptproj, PowerTree --help)
setlocal
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
    echo Virtual environment missing. Run:
    echo    py -3.12 -m venv .venv ^&^& .venv\Scripts\pip install -r requirements.txt
    pause
    exit /b 1
)
set PYTHONPATH=%~dp0src;%PYTHONPATH%
if "%~1"=="" (
    start "" .venv\Scripts\pythonw.exe main.py
    exit /b 0
)
if /i "%~1"=="gui" (
    start "" .venv\Scripts\pythonw.exe main.py %2
    exit /b 0
)
.venv\Scripts\python.exe -m powertree %*
endlocal & exit /b %ERRORLEVEL%
