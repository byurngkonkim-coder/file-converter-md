@echo off
setlocal
cd /d "%~dp0"

set "PY=python"
if exist "venv\Scripts\python.exe" set "PY=venv\Scripts\python.exe"

%PY% -X utf8 cli.py %*
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [Process exited with error code %ERRORLEVEL%]
)
echo.
pause
endlocal
