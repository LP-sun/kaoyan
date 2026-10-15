@echo off
setlocal
title PhysicsPrep
cd /d "%~dp0PhysicsPrep"
if errorlevel 1 (
    echo ERROR: PhysicsPrep folder was not found beside this launcher.
    pause
    exit /b 1
)
if not exist ".venv\Scripts\python.exe" (
    echo ERROR: Python environment not found: .venv\Scripts\python.exe
    pause
    exit /b 1
)
set "GRADIO_ANALYTICS_ENABLED=False"
set "PHYSICSPREP_PORT=7860"
set "PHYSICSPREP_OPEN_BROWSER=true"
echo Starting PhysicsPrep at http://127.0.0.1:7860
echo Keep this window open while studying. Press Ctrl+C to stop.
echo.
".venv\Scripts\python.exe" app.py
set "PHYSICSPREP_EXIT_CODE=%ERRORLEVEL%"
echo.
if not "%PHYSICSPREP_EXIT_CODE%"=="0" (
    echo PhysicsPrep stopped with error code %PHYSICSPREP_EXIT_CODE%.
    echo If port 7860 is already in use, check your existing PhysicsPrep window.
)
pause
exit /b %PHYSICSPREP_EXIT_CODE%
