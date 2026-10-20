@echo off
setlocal
cd /d "%~dp0"
title Affiliate Auto Studio PC V6
where py >nul 2>&1
if %ERRORLEVEL%==0 (set "PY=py") else (set "PY=python")
if not exist ".venv\Scripts\python.exe" (
    echo [1/3] Creating Python environment...
    %PY% -m venv .venv
    if errorlevel 1 (echo Please install Python 3.11+ and add it to PATH. & pause & exit /b 1)
)
if not exist ".venv\setup_v6.ok" (
    echo [2/3] Installing required packages on first run. Please wait...
    ".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements.txt
    if errorlevel 1 (echo Install failed. Check internet and try again. & pause & exit /b 1)
    type nul > ".venv\setup_v6.ok"
)
echo [3/3] Starting Studio in your web browser...
".venv\Scripts\python.exe" launch_pc.py
if errorlevel 1 (echo Application failed to start. Please screenshot the error. & pause & exit /b 1)
pause
