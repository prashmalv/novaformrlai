@echo off
REM ============================================================
REM  NovoForm — Application Launcher
REM  Nova Formworks Pvt. Ltd.
REM  Version: 1.18
REM
REM  Double-click this file to start NovoForm.
REM  Run install_windows_nova_updatedbranding.bat first
REM  if you have not installed NovoForm yet.
REM ============================================================

setlocal

REM Change to the folder where this bat file lives
set APP_DIR=%~dp0
if "%APP_DIR:~-1%"=="\" set APP_DIR=%APP_DIR:~0,-1%
cd /d "%APP_DIR%"

title NovoForm v1.19 — Nova Formworks

REM ── Check venv is present ────────────────────────────────
if not exist "%APP_DIR%\venv\Scripts\pythonw.exe" (
    echo.
    echo  ====================================================
    echo   NovoForm is not installed yet.
    echo.
    echo   Please run:
    echo     install_windows_nova_updatedbranding.bat
    echo   to install NovoForm first.
    echo  ====================================================
    echo.
    pause
    exit /b 1
)

REM ── Check main.py is present ────────────────────────────
if not exist "%APP_DIR%\main.py" (
    echo.
    echo  ERROR: main.py not found in %APP_DIR%
    echo  Please ensure this file is inside the NovoForm folder.
    echo.
    pause
    exit /b 1
)

REM ── Launch NovoForm (no console window) ─────────────────
start "" "%APP_DIR%\venv\Scripts\pythonw.exe" "%APP_DIR%\main.py"

endlocal
