@echo off
REM ======================================================================
REM  start.bat - ONE-CLICK LAUNCHER FOR AQUA SHIELD
REM
REM  Just double-click this file. It will:
REM    1. find Python on this computer
REM    2. create a private Python environment in the "venv" folder (first run only)
REM    3. install all required packages from requirements.txt
REM       (first run only, or again if requirements.txt changes)
REM    4. load settings / API keys from the .env file, if you have one
REM    5. check that the AI model file was downloaded (Git LFS)
REM    6. start the web server and open http://localhost:8000 in your browser
REM
REM  To stop the server: close this window, or press Ctrl+C in it.
REM  Running it again automatically stops an old server still using port 8000.
REM  NOTE: the first run can take 10+ minutes - PyTorch is a large download (~1 GB).
REM ======================================================================

title AQUA SHIELD - Launcher

REM Always work from the folder this file is in (so double-clicking works from anywhere)
cd /d "%~dp0"

echo =================================================================
echo   AQUA SHIELD - Ocean Intelligence System - One-Click Launcher
echo =================================================================
echo.

REM ----------------------------------------------------------------------
REM  STEP 1: Find Python ("py" launcher first, then "python")
REM ----------------------------------------------------------------------
set "PYTHON_CMD="
py -3 --version >nul 2>&1 && set "PYTHON_CMD=py -3"
if not defined PYTHON_CMD (
    python --version >nul 2>&1 && set "PYTHON_CMD=python"
)
if not defined PYTHON_CMD goto :no_python
echo [1/6] Python found:
%PYTHON_CMD% --version
echo.

REM ----------------------------------------------------------------------
REM  STEP 2: Create the virtual environment (only if it doesn't exist yet)
REM  A virtual environment keeps this project's packages separate from
REM  the rest of the computer.
REM ----------------------------------------------------------------------
if exist "venv\Scripts\python.exe" goto :venv_ready
echo [2/6] Creating virtual environment in "venv" (first run only)...
%PYTHON_CMD% -m venv venv
if errorlevel 1 goto :venv_failed
:venv_ready
echo [2/6] Virtual environment ready.
echo.

REM From here on, use the Python inside venv
set "VENV_PY=venv\Scripts\python.exe"

REM ----------------------------------------------------------------------
REM  STEP 3: Install packages - skipped if requirements.txt is unchanged
REM  since the last successful install (a copy is kept inside venv)
REM ----------------------------------------------------------------------
fc /b "requirements.txt" "venv\requirements.installed" >nul 2>&1
if not errorlevel 1 goto :deps_ready
echo [3/6] Installing required packages (this can take a while the first time)...
"%VENV_PY%" -m pip install --upgrade pip
"%VENV_PY%" -m pip install -r requirements.txt
if errorlevel 1 goto :deps_failed
copy /y "requirements.txt" "venv\requirements.installed" >nul
:deps_ready
echo [3/6] Packages installed.
echo.

REM ----------------------------------------------------------------------
REM  STEP 4: Load .env settings (e.g. PELYR_API_KEY=...) into this window.
REM  The Python code reads these with os.getenv(); lines starting with # are skipped.
REM  If there is no .env file, copy .env.example to .env and fill in your keys.
REM ----------------------------------------------------------------------
if not exist ".env" goto :no_env
for /f "usebackq eol=# tokens=1,* delims==" %%A in (".env") do (
    if not "%%B"=="" set "%%A=%%B"
)
echo [4/6] Loaded settings from .env
goto :env_done
:no_env
echo [4/6] No .env file found - live AIS vessel data (Pelyr) will be disabled.
echo       Tip: copy .env.example to .env and add your PELYR_API_KEY.
:env_done
echo.

REM ----------------------------------------------------------------------
REM  STEP 5: Check the U-Net model file. If it is only a few bytes, it is a
REM  Git LFS "pointer" and the real ~160 MB model was never downloaded.
REM ----------------------------------------------------------------------
set "MODEL_FILE=backend\models\checkpoints\best_model.pth"
set "MODEL_SIZE=0"
if exist "%MODEL_FILE%" for %%F in ("%MODEL_FILE%") do set "MODEL_SIZE=%%~zF"
if %MODEL_SIZE% GTR 1000000 goto :model_ok
echo [5/6] Model weights not downloaded - trying "git lfs pull"...
git lfs pull >nul 2>&1
if exist "%MODEL_FILE%" for %%F in ("%MODEL_FILE%") do set "MODEL_SIZE=%%~zF"
if %MODEL_SIZE% GTR 1000000 goto :model_ok
echo       WARNING: real model file is missing. The app will still start, but
echo       spill detection will use placeholder values. To fix: clone the repo
echo       with Git, then run "git lfs install" and "git lfs pull".
goto :model_done
:model_ok
echo [5/6] Model weights found.
:model_done
echo.

REM ----------------------------------------------------------------------
REM  STOP ANY OLD SERVER: if something is already listening on port 8000
REM  (e.g. AQUA SHIELD started earlier and never closed), stop it first so
REM  the new server can use the port. netstat lists open ports; the 5th
REM  column is the process ID (PID). /T also stops its child processes.
REM ----------------------------------------------------------------------
echo Checking for a server already running on port 8000...
set "KILLED_OLD="
for /f "tokens=5" %%P in ('netstat -ano ^| findstr /R /C:":8000 .*LISTENING"') do (
    if not "%%P"=="0" (
        taskkill /F /T /PID %%P >nul 2>&1
        echo   Stopped old server process [PID %%P]
        set "KILLED_OLD=1"
    )
)
REM Give Windows ~2 seconds to release the port before starting again
REM (ping is used as a delay because it works in any console window)
if defined KILLED_OLD ping -n 3 127.0.0.1 >nul
if not defined KILLED_OLD echo   Port 8000 is free.
echo.

REM ----------------------------------------------------------------------
REM  STEP 6: Start the server. run.py opens the browser automatically
REM  after ~1.5 seconds at http://localhost:8000
REM ----------------------------------------------------------------------
echo [6/6] Starting AQUA SHIELD at http://localhost:8000
echo       Keep this window open while using the app. Close it to stop.
echo =================================================================
echo.
"%VENV_PY%" run.py

echo.
echo Server stopped.
pause
exit /b 0

REM ---------------------------- ERROR MESSAGES ----------------------------
:no_python
echo ERROR: Python was not found on this computer.
echo Install Python 3.9 or newer from https://www.python.org/downloads/
echo and tick "Add Python to PATH" during installation. Then run this file again.
pause
exit /b 1

:venv_failed
echo ERROR: Could not create the virtual environment.
pause
exit /b 1

:deps_failed
echo ERROR: Package installation failed. Check your internet connection and
echo the messages above, then run this file again (it will retry the install).
pause
exit /b 1
