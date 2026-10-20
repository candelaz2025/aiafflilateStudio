@echo off
cd /d "%~dp0"
echo Affiliate Auto Studio - Windows Update Manager
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" updater.py apply %*
) else (
  py -3 updater.py apply %*
)
if errorlevel 1 (
  echo.
  echo Update was not applied. See error message above.
)
echo.
pause
