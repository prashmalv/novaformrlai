@echo off
REM ============================================================
REM  NovoForm — Windows Installation Script
REM  Nova Formworks Pvt. Ltd.
REM  Version: 1.20 — Floor-plan diagrams, shape images, dual DXF import (July 2026)
REM  Developed by RLAI (rightleft.ai)
REM
REM  What's new in v1.20:
REM    - Floor-Plan Diagrams: last column of BOQ PDF and Excel now shows a
REM      shape diagram for every element with overall dimensions + panel summary.
REM    - Pre-defined Shape Images: SW5/6/7/8/10/11/12/14 show actual Nova
REM      formwork drawings; other shear walls show auto-detected L/T/E shape.
REM    - Dual DXF Import: two separate browse sections —
REM      "Client Drawing (DXF)" and "Nova Formwork Drawing (DXF)" — no more
REM      confusion about which file to upload where.
REM    - Labels cleaned: "DWG/DXF" changed to "DXF" throughout the UI.
REM    - No-gap panel preference: optimizer tries gap=0 first (more accurate).
REM
REM  What was new in v1.19:
REM    - PDF Import: Nova box-culvert PDFs now import elements + panel BOQ
REM      automatically (BOX CULVERT / UPPER PIPE / BOTTOM PIPE / BOTTOM PANEL).
REM    - "Import Elements" button replaces "Open & Review" in PDF section.
REM    - Same Replace/Add/Cancel flow as Nova DXF import.
REM
REM  What was new in v1.18:
REM    - Edit Panels button in BOQ Results: select element row, edit/add/delete panels.
REM    - Double-click Per-Element Breakdown row to open panel editor.
REM    - Delete element now removes its BOQ entry (lists stay in sync).
REM
REM  What was new in v1.14:
REM    - CRITICAL FIX: First-import mismatch on Col.dxf (24-element drawings)
REM      Root cause: Windows Defender scans file CONCURRENTLY with ezdxf read,
REM      causing partial entity load (10/24 correct on first import).
REM      Fix: entire file read into RAM first, ezdxf parses from BytesIO —
REM      file is never opened a second time, Defender cannot interfere.
REM      All imports (first, second, any) now produce identical correct results.
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

title NovoForm v1.20 Installer — Nova Formworks

REM ── Check: must be run as Administrator ──────────────────
net session >nul 2>&1
if errorlevel 1 (
    echo.
    echo  ====================================================
    echo   ERROR: Administrator privileges required!
    echo.
    echo   Please right-click this file and select:
    echo     "Run as administrator"
    echo.
    echo   Without admin rights, Python packages may fail
    echo   to install due to file permission errors.
    echo  ====================================================
    echo.
    pause
    exit /b 1
)

echo.
echo  ====================================================
echo   NovoForm — Formwork Analysis and BOQ Generator
echo   Version 1.20  ^|  Nova Formworks Pvt. Ltd.
echo   Nova Drawing v2 Parser  ^|  July 2026
echo   Developed by RLAI (rightleft.ai)
echo  ====================================================
echo.
echo   What's new in v1.20:
echo     - Floor-Plan Diagrams in BOQ PDF and Excel
echo       (shape image + dimensions + panel summary)
echo     - Pre-defined SW shape images (SW5-SW14)
echo     - Dual DXF Import: Client + Nova Drawing sections
echo     - v1.19: PDF Import for Nova box-culvert drawings
echo     - v1.18: Edit/Delete panels in BOQ Results tab
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

REM ── 5. Upgrade pip ──────────────────────────────────────
REM    Use full venv python path — avoids pip self-replacement restart issue.
echo.
echo [5/6] Upgrading pip (please wait)...
"%APP_DIR%\venv\Scripts\python.exe" -m pip install --upgrade pip --quiet
if errorlevel 1 (
    echo  Warning: pip upgrade skipped — using bundled version.
)
echo  pip ready.

REM ── 6. Install dependencies ─────────────────────────────
echo.
echo [6/6] Installing dependencies (this may take 3-5 minutes)...
echo  Packages: PyQt6, ReportLab, openpyxl, ezdxf, matplotlib, pymupdf...
echo  Please wait — do NOT close this window.
echo.
"%APP_DIR%\venv\Scripts\python.exe" -m pip install -r "%APP_DIR%\requirements.txt" --timeout 120
if errorlevel 1 (
    echo.
    echo  ERROR: Dependency installation failed.
    echo  Please check:
    echo    1. Internet connection is active
    echo    2. Firewall / antivirus is not blocking pip
    echo    3. Try running this script as Administrator
    echo    4. If behind a proxy, set HTTP_PROXY environment variable
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
echo   Installation Complete!  ^|  NovoForm v1.20
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
