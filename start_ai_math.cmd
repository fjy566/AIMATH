@echo off
setlocal
cd /d "%~dp0"

set "PYTHON="
if exist "%~dp0.venv\Scripts\python.exe" set "PYTHON=%~dp0.venv\Scripts\python.exe"
if not defined PYTHON if exist "E:\ProgramData\anaconda3\python.exe" set "PYTHON=E:\ProgramData\anaconda3\python.exe"
if not defined PYTHON for /f "delims=" %%P in ('where python 2^>nul') do if not defined PYTHON set "PYTHON=%%P"

if not defined PYTHON (
    echo Python was not found. Install Python or create the project .venv first.
    pause
    exit /b 1
)

echo Starting AI Math backend...
"%PYTHON%" "%~dp0scripts\run_server.py" --open
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (
    echo.
    echo The backend stopped with exit code %EXIT_CODE%.
    pause
)

exit /b %EXIT_CODE%
