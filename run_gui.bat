@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"

set "TARGET=gui.py"
if exist "engine\gui.py" set "TARGET=engine\gui.py"

set "PY_CMD="
set "PYW_CMD="

REM 1. Search local or engine virtualenv Python
if exist "%~dp0engine\venv\Scripts\pythonw.exe" set "PYW_CMD=%~dp0engine\venv\Scripts\pythonw.exe"
if exist "%~dp0engine\venv\Scripts\python.exe" set "PY_CMD=%~dp0engine\venv\Scripts\python.exe"
if exist "%~dp0venv\Scripts\pythonw.exe" set "PYW_CMD=%~dp0venv\Scripts\pythonw.exe"
if exist "%~dp0venv\Scripts\python.exe" set "PY_CMD=%~dp0venv\Scripts\python.exe"

if not defined PY_CMD if exist "%~dp0.venv\Scripts\python.exe" (
    if exist "%~dp0.venv\Scripts\pythonw.exe" set "PYW_CMD=%~dp0.venv\Scripts\pythonw.exe"
    set "PY_CMD=%~dp0.venv\Scripts\python.exe"
)
if not defined PY_CMD if exist "%~dp0python\python.exe" (
    if exist "%~dp0python\pythonw.exe" set "PYW_CMD=%~dp0python\pythonw.exe"
    set "PY_CMD=%~dp0python\python.exe"
)
if not defined PY_CMD if exist "%~dp0Python311\python.exe" (
    if exist "%~dp0Python311\pythonw.exe" set "PYW_CMD=%~dp0Python311\pythonw.exe"
    set "PY_CMD=%~dp0Python311\python.exe"
)
if not defined PY_CMD if exist "%~dp0Python312\python.exe" (
    if exist "%~dp0Python312\pythonw.exe" set "PYW_CMD=%~dp0Python312\pythonw.exe"
    set "PY_CMD=%~dp0Python312\python.exe"
)
if not defined PY_CMD if exist "%~dp0Python310\python.exe" (
    if exist "%~dp0Python310\pythonw.exe" set "PYW_CMD=%~dp0Python310\pythonw.exe"
    set "PY_CMD=%~dp0Python310\python.exe"
)

REM 2. Search adjacent folder (MyOCR) virtualenv
if not defined PY_CMD if exist "%~dp0..\MyOCR\venv\Scripts\python.exe" (
    if exist "%~dp0..\MyOCR\venv\Scripts\pythonw.exe" set "PYW_CMD=%~dp0..\MyOCR\venv\Scripts\pythonw.exe"
    set "PY_CMD=%~dp0..\MyOCR\venv\Scripts\python.exe"
)

REM 3. Search system PATH pythonw / python
if not defined PYW_CMD (
    where pythonw >nul 2>&1
    if !ERRORLEVEL! EQU 0 set "PYW_CMD=pythonw"
)
if not defined PY_CMD (
    where python >nul 2>&1
    if !ERRORLEVEL! EQU 0 set "PY_CMD=python"
)

REM 4. Search Windows Python Launcher
if not defined PY_CMD (
    where py >nul 2>&1
    if !ERRORLEVEL! EQU 0 (
        set "PY_CMD=py -3"
        where pyw >nul 2>&1
        if !ERRORLEVEL! EQU 0 set "PYW_CMD=pyw -3"
    )
)

REM 5. Search LocalAppData Python installations
if not defined PY_CMD (
    for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python3*") do (
        if exist "%%D\pythonw.exe" set "PYW_CMD=%%D\pythonw.exe"
        if exist "%%D\python.exe" set "PY_CMD=%%D\python.exe"
    )
)

REM 6. Fallback if Python is not found
if not defined PY_CMD (
    echo [ERROR] Python environment not found!
    echo To run this application, please install Python from https://www.python.org/
    echo.
    pause
    endlocal
    exit /b 1
)

REM Launch GUI application
if defined PYW_CMD (
    start "" !PYW_CMD! -X utf8 %TARGET% %*
    if !ERRORLEVEL! NEQ 0 (
        !PY_CMD! -X utf8 %TARGET% %*
        if !ERRORLEVEL! NEQ 0 pause
    )
) else (
    !PY_CMD! -X utf8 %TARGET% %*
    if !ERRORLEVEL! NEQ 0 pause
)

endlocal
