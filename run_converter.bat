@echo off
setlocal
cd /d "%~dp0"
python -X utf8 cli.py %*
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [Process exited with error code %ERRORLEVEL%]
)
echo.
pause
endlocal
