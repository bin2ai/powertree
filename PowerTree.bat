@echo off
rem PowerTree launcher — double-click to start (uses the project venv).
cd /d "%~dp0"
if not exist .venv\Scripts\pythonw.exe (
    echo Virtual environment missing. Run:  py -3.12 -m venv .venv ^&^& .venv\Scripts\pip install -r requirements.txt
    pause
    exit /b 1
)
start "" .venv\Scripts\pythonw.exe main.py %*
