@echo off
REM ============================================================
REM  NovoForm — Windows Installation Script
REM  Nova Formworks Pvt. Ltd.
REM  Version: 1.5 — Parser Fixes: L-COL, R-COL, IC Corners (June 2026)
REM  Developed by RLAI (rightleft.ai)
REM
REM  What's new in v1.5:
REM    - Nova Drawing v2 Auto-Detection (KEY FEATURE)
REM      Import DXF with labelled panels (COL:-LxW, FF-COL, R-COL, L-COL)
REM      App reads panel quantities DIRECTLY from drawing — no optimization needed
REM      100% accurate: exactly what engineer drew is what you get
REM    - Casting Height vs Product Height separated
REM      Header: "Height: 2470MM" = pour height
REM      Product: "Panel 600*3200" = physical panel supplied
REM    - HTTP Server mode for central auth (no Windows credentials)
REM      Run start_server.bat on admin machine
REM      Workers connect via http://192.168.1.X:8765
REM    - Server URL config in Admin Panel -> Database Settings
REM
REM  What was new in v1.3:
REM    - Export Formwork Drawing as AutoCAD DXF
REM    - "Add Missing Element" in Review Dialog
REM    - DXF Arrange Dialog: set element order before export
REM    - Shared database setup via Admin Panel
REM
REM  Usage: Double-click this file on any Windows machine.
REM  Requires Python 3.10+ installed and in PATH.
REM  Internet required only during first install (to download packages).
REM  Default login — Username: admin  Password: nova@123
REM ============================================================

setlocal enabledelayedexpansion

REM ── IMPORTANT: Change to script's own directory immediately ─
REM    This ensures requirements.txt and all files are found
REM    regardless of where the user double-clicks from.
set APP_DIR=%~dp0
if "%APP_DIR:~-1%"=="\" set APP_DIR=%APP_DIR:~0,-1%
cd /d "%APP_DIR%"

title NovoForm v1.5 Installer — Nova Formworks

echo.
echo  ====================================================
echo   NovoForm — Formwork Analysis and BOQ Generator
echo   Version 1.5  ^|  Nova Formworks Pvt. Ltd.
echo   Nova Drawing v2 Parser  ^|  June 2026
echo   Developed by RLAI (rightleft.ai)
echo  ====================================================
echo.
echo   What's new in v1.5:
echo     - Nova Drawing v2 Parser (KEY FEATURE)
echo       Import labelled DXF: panel quantities read
echo       directly from drawing — 100% accurate
echo       Supports: Regular, R-COL, L-COL, SF-COL
echo       L-shaped columns with IC inner-corner panels
echo     - Panel count fixes: bounding-box filter
echo       prevents inflated panel counts from frame lines
echo     - HTTP Server mode for central auth
echo       Run start_server.bat on admin machine
echo.
echo   Default login: admin / nova@123
echo   (Change password immediately after first login)
echo.
echo   Installing from: %APP_DIR%
echo.

REM ── 1. Verify requirements.txt is present ────────────────
echo [1/6] Checking installation files...
if not exist "%APP_DIR%\requirements.txt" (
    echo.
    echo  ERROR: requirements.txt not found in:
    echo         %APP_DIR%
    echo.
    echo  Please ensure this BAT file is placed inside the
    echo  NovoForm application folder (same folder as main.py).
    echo.
    pause
    exit /b 1
)
echo  requirements.txt found.

REM ── 2. Check Python ──────────────────────────────────────
echo.
echo [2/6] Checking Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo  ERROR: Python not found in PATH.
    echo  Please install Python 3.10 or higher:
    echo    https://www.python.org/downloads/
    echo.
    echo  IMPORTANT: During installation, check
    echo  "Add Python to PATH" before clicking Install.
    echo.
    pause
    exit /b 1
)
for /f "tokens=2" %%v in ('python --version 2^>^&1') do set PY_VER=%%v
echo  Found Python %PY_VER%

REM ── 3. Remove old venv if upgrading ─────────────────────
echo.
echo [3/6] Checking for existing installation...
if exist "%APP_DIR%\venv" (
    echo  Existing virtual environment found.
    echo  Removing old environment to ensure clean upgrade...
    rmdir /s /q "%APP_DIR%\venv"
    echo  Old environment removed.
) else (
    echo  No existing environment — fresh install.
)

REM ── 4. Create virtual environment ───────────────────────
echo.
echo [4/6] Creating virtual environment...
python -m venv "%APP_DIR%\venv"
if errorlevel 1 (
    echo.
    echo  ERROR: Failed to create virtual environment.
    echo  Try running this script as Administrator.
    echo.
    pause
    exit /b 1
)
echo  Virtual environment created.

REM ── 5. Activate venv and upgrade pip ────────────────────
echo.
echo [5/6] Activating environment and upgrading pip...
call "%APP_DIR%\venv\Scripts\activate.bat"
python -m pip install --upgrade pip --quiet
echo  pip upgraded.

REM ── 6. Install dependencies ─────────────────────────────
echo.
echo [6/6] Installing dependencies (this may take a few minutes)...
echo  Packages: PyQt6, ReportLab, openpyxl, ezdxf, matplotlib, pymupdf...
pip install -r "%APP_DIR%\requirements.txt"
if errorlevel 1 (
    echo.
    echo  ERROR: Dependency installation failed.
    echo  Please check:
    echo    1. Internet connection is active
    echo    2. Firewall / antivirus is not blocking pip
    echo    3. Try running this script as Administrator
    echo.
    pause
    exit /b 1
)
echo  All dependencies installed successfully.

REM ── Create desktop shortcut ──────────────────────────────
echo.
echo  Creating desktop shortcut...

REM Write VBS launcher (hides console window on launch)
set LAUNCHER=%APP_DIR%\launch_novoform.vbs
(
    echo Set WshShell = WScript.CreateObject^("WScript.Shell"^)
    echo WshShell.CurrentDirectory = "%APP_DIR%"
    echo WshShell.Run chr^(34^) ^& "%APP_DIR%\venv\Scripts\pythonw.exe" ^& chr^(34^) ^& " main.py", 0, False
) > "%LAUNCHER%"

REM Create shortcut on Desktop
set SHORTCUT=%USERPROFILE%\Desktop\NovoForm.lnk
powershell -Command "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut('%SHORTCUT%'); $s.TargetPath = 'wscript.exe'; $s.Arguments = '\"%LAUNCHER%\"'; $s.WorkingDirectory = '%APP_DIR%'; $s.Description = 'NovoForm BOQ Generator v1.2'; $s.Save()" >nul 2>&1

if exist "%SHORTCUT%" (
    echo  Desktop shortcut created: NovoForm.lnk
) else (
    echo  Shortcut creation skipped — launch manually via launch_novoform.vbs
)

REM ── Create api_config.json from template if not present ──
if not exist "%APP_DIR%\config\api_config.json" (
    if exist "%APP_DIR%\config\api_config.template.json" (
        copy "%APP_DIR%\config\api_config.template.json" "%APP_DIR%\config\api_config.json" >nul
        echo  Config created from template.
    )
)

REM ── Done ─────────────────────────────────────────────────
echo.
echo  ====================================================
echo   Installation Complete!  ^|  NovoForm v1.5
echo.
echo   To launch NovoForm:
echo     Option 1 : Double-click "NovoForm" on your Desktop
echo     Option 2 : Double-click launch_novoform.vbs
echo     Option 3 : Run manually:
echo                %APP_DIR%\venv\Scripts\pythonw.exe main.py
echo.
echo   App folder : %APP_DIR%
echo   Data folder: %APP_DIR%\data\
echo   Config     : %APP_DIR%\config\panel_config.json
echo.
echo   Support: rightleft.ai  ^|  Nova Formworks Pvt. Ltd.
echo  ====================================================
echo.
pause
endlocal
