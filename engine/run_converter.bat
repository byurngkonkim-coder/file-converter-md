@echo off
setlocal EnableDelayedExpansion
pushd "%~dp0"

set "PY_CMD="

REM 1. Search portable or local virtualenv Python in local or parent folder
if exist "%~dp0venv\Scripts\python.exe" (
    set "PY_CMD=%~dp0venv\Scripts\python.exe"
) else if exist "%~dp0..\venv\Scripts\python.exe" (
    set "PY_CMD=%~dp0..\venv\Scripts\python.exe"
) else if exist "%~dp0.venv\Scripts\python.exe" (
    set "PY_CMD=%~dp0.venv\Scripts\python.exe"
) else if exist "%~dp0..\.venv\Scripts\python.exe" (
    set "PY_CMD=%~dp0..\.venv\Scripts\python.exe"
) else if exist "%~dp0python\python.exe" (
    set "PY_CMD=%~dp0python\python.exe"
) else if exist "%~dp0..\python\python.exe" (
    set "PY_CMD=%~dp0..\python\python.exe"
) else if exist "%~dp0Python311\python.exe" (
    set "PY_CMD=%~dp0Python311\python.exe"
) else if exist "%~dp0Python312\python.exe" (
    set "PY_CMD=%~dp0Python312\python.exe"
) else if exist "%~dp0Python310\python.exe" (
    set "PY_CMD=%~dp0Python310\python.exe"
)

REM 2. Search system PATH python
if not defined PY_CMD (
    where python >nul 2>&1
    if !ERRORLEVEL! EQU 0 set "PY_CMD=python"
)

REM 3. Search Windows Python Launcher
if not defined PY_CMD (
    where py >nul 2>&1
    if !ERRORLEVEL! EQU 0 set "PY_CMD=py -3"
)

REM 4. Search LocalAppData Python installations
if not defined PY_CMD (
    for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python3*") do (
        if exist "%%D\python.exe" set "PY_CMD=%%D\python.exe"
    )
)

REM 5. Fallback if Python is not found
if not defined PY_CMD (
    echo [ERROR] Python environment not found!
    echo To run this application from USB, please either:
    echo  1. Install Python from https://www.python.org/
    echo  2. Copy a portable Python folder into this USB directory [e.g. venv or python]
    echo.
    pause
    popd
    endlocal
    exit /b 1
)

REM Execute CLI with UTF-8 encoding
!PY_CMD! -X utf8 cli.py %*
set "EXIT_CODE=!ERRORLEVEL!"

if !EXIT_CODE! NEQ 0 (
    echo.
    echo [Process finished with exit code !EXIT_CODE!]
)

echo.
pause
popd
endlocal
