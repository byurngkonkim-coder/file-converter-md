@echo off
setlocal
cd /d "%~dp0"

set "TARGET=gui.py"
if exist "engine\gui.py" set "TARGET=engine\gui.py"

set "PY=python"
if exist "venv\Scripts\python.exe" set "PY=venv\Scripts\python.exe"
if exist "engine\venv\Scripts\python.exe" set "PY=engine\venv\Scripts\python.exe"

if exist "venv\Scripts\pythonw.exe" (
    start "" "venv\Scripts\pythonw.exe" -X utf8 %TARGET% %*
) else if exist "engine\venv\Scripts\pythonw.exe" (
    start "" "engine\venv\Scripts\pythonw.exe" -X utf8 %TARGET% %*
) else (
    start "" pythonw -X utf8 %TARGET% %*
)
if %ERRORLEVEL% NEQ 0 (
    %PY% -X utf8 %TARGET% %*
    pause
)
endlocal
