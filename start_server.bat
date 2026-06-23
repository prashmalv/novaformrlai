@echo off
REM ============================================================
REM  NovoForm Auth Server — Start Script
REM  Run this on the ADMIN machine only.
REM  Worker machines connect via: http://<THIS-IP>:8765
REM
REM  Keep this window open while team is working.
REM  Close it to stop the server.
REM ============================================================

setlocal
set APP_DIR=%~dp0
if "%APP_DIR:~-1%"=="\" set APP_DIR=%APP_DIR:~0,-1%
cd /d "%APP_DIR%"

title NovoForm Auth Server — Running

echo.
echo  Checking virtual environment...
if not exist "%APP_DIR%\venv\Scripts\python.exe" (
    echo.
    echo  ERROR: Virtual environment not found.
    echo  Please run install_windows_nova_updatedbranding.bat first.
    echo.
    pause
    exit /b 1
)

echo  Starting NovoForm Auth Server...
echo  (Keep this window open while team is using the app)
echo.

"%APP_DIR%\venv\Scripts\python.exe" server.py

echo.
echo  Server stopped.
pause
endlocal
