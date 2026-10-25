@echo off
cd /d "%~dp0"
python -m venv .venv && .venv\Scripts\python -m pip install -r requirements.txt
pause
