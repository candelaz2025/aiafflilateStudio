@echo off
cd /d "%~dp0"
title Affiliate Auto Studio V7.10 Shopee Scan & Import
if not exist ".venv\Scripts\python.exe" (
  py -3 -m venv .venv
  if errorlevel 1 (echo Please install Python 3.11+ and enable PATH. && pause && exit /b 1)
)
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (echo Dependency installation failed. && pause && exit /b 1)
echo.
echo Affiliate Auto Studio V7.10 Shopee Scan & Import (local)
echo http://127.0.0.1:8010
echo WARNING: LOCAL mode is not a public website. Do not use port forwarding.
echo.
start "" "http://127.0.0.1:8010"
".venv\Scripts\python.exe" -m uvicorn community_app:app --host 127.0.0.1 --port 8010
pause
