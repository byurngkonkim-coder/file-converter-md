@echo off
setlocal
cd /d "%~dp0"
start "" pythonw -X utf8 gui.py %*
if %ERRORLEVEL% NEQ 0 (
    python -X utf8 gui.py %*
    pause
)
endlocal
