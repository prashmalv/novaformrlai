@echo off
REM ============================================================
REM  NovoForm — Windows Installation Script
REM  Nova Formworks Pvt. Ltd.
REM  Developed by RLAI (rightleft.ai)
REM
REM  Usage: Double-click this file on any Windows machine.
REM  Requires Python 3.10+ installed and in PATH.
REM  Internet required only during first install (to download packages).
REM ============================================================

setlocal enabledelayedexpansion
title NovoForm Installer

echo.
echo  ====================================================
echo   NovoForm — Formwork Analysis and BOQ Generator
echo   Installation Script  (Nova Formworks Pvt. Ltd.)
echo  ====================================================
echo.

REM ── 1. Check Python ──────────────────────────────────────
echo [1/5] Checking Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo  ERROR: Python not found.
    echo  Please install Python 3.10 or higher from https://www.python.org/downloads/
    echo  Make sure to check "Add Python to PATH" during installation.
    echo.
    pause
    exit /b 1
)
for /f "tokens=2" %%v in ('python --version 2^>^&1') do set PY_VER=%%v
echo  Found Python %PY_VER%

REM ── 2. Create virtual environment ───────────────────────
echo.
echo [2/5] Creating virtual environment in .\venv ...
if exist venv (
    echo  Virtual environment already exists — skipping creation.
) else (
    python -m venv venv
    if errorlevel 1 (
        echo  ERROR: Failed to create virtual environment.
        pause
        exit /b 1
    )
    echo  Virtual environment created.
)

REM ── 3. Activate venv and upgrade pip ────────────────────
echo.
echo [3/5] Activating environment and upgrading pip...
call venv\Scripts\activate.bat
python -m pip install --upgrade pip --quiet
echo  pip upgraded.

REM ── 4. Install dependencies ─────────────────────────────
echo.
echo [4/5] Installing dependencies (this may take a few minutes)...
pip install -r requirements.txt --quiet
if errorlevel 1 (
    echo.
    echo  ERROR: Dependency installation failed.
    echo  Check your internet connection and try again.
    pause
    exit /b 1
)
echo  Dependencies installed successfully.

REM ── 5. Create desktop shortcut ──────────────────────────
echo.
echo [5/5] Creating desktop shortcut...

REM Get current directory
set APP_DIR=%~dp0
REM Remove trailing backslash
if "%APP_DIR:~-1%"=="\" set APP_DIR=%APP_DIR:~0,-1%

REM Write VBS launcher to avoid console window flash
set LAUNCHER=%APP_DIR%\launch_novoform.vbs
echo Set WshShell = WScript.CreateObject("WScript.Shell") > "%LAUNCHER%"
echo WshShell.CurrentDirectory = "%APP_DIR%" >> "%LAUNCHER%"
echo WshShell.Run chr(34) ^& "%APP_DIR%\venv\Scripts\pythonw.exe" ^& chr(34) ^& " main.py", 0, False >> "%LAUNCHER%"

REM Create shortcut on Desktop
set SHORTCUT=%USERPROFILE%\Desktop\NovoForm.lnk
powershell -Command ^
  "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut('%SHORTCUT%'); $s.TargetPath = 'wscript.exe'; $s.Arguments = '\"%LAUNCHER%\"'; $s.WorkingDirectory = '%APP_DIR%'; $s.Description = 'NovoForm BOQ Generator'; $s.Save()" >nul 2>&1

if exist "%SHORTCUT%" (
    echo  Desktop shortcut created: NovoForm.lnk
) else (
    echo  Could not create shortcut — run launch_novoform.vbs manually.
)

REM ── Done ─────────────────────────────────────────────────
echo.
echo  ====================================================
echo   Installation Complete!
echo.
echo   To launch NovoForm:
echo     Option 1: Double-click "NovoForm" on your Desktop
echo     Option 2: Double-click launch_novoform.vbs
echo     Option 3: Run:  venv\Scripts\pythonw.exe main.py
echo.
echo   Data folder: %APP_DIR%\data\
echo   Config:      %APP_DIR%\config\panel_config.json
echo  ====================================================
echo.
pause
endlocal
