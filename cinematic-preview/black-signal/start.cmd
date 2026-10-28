@echo off
cd /d "%~dp0"
where py >nul 2>&1
if not errorlevel 1 (
  py -3 serve.py
) else (
  where python >nul 2>&1
  if errorlevel 1 (
    echo Python 3 is required. Nothing has been installed or modified.
    pause
    exit /b 1
  )
  python serve.py
)
pause
