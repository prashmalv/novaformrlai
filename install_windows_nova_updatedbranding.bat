@echo off
REM ============================================================
REM  NovoForm — Windows Installer
REM  Nova Formworks Pvt. Ltd.
REM  Version: 1.28 — July 2026
REM  Developed by RLAI (rightleft.ai)
REM
REM  INSTALL STRATEGY (v1.21+):
REM    Installs into the current user's AppData\Local folder.
REM    No Administrator rights required.
REM    Each Windows user gets their own independent installation.
REM    Desktop shortcut is created on the current user's Desktop.
REM
REM  Install location : %LOCALAPPDATA%\NovoForm
REM  Shortcut         : %USERPROFILE%\Desktop\NovoForm.lnk
REM
REM  Usage: Double-click this file on any Windows machine.
REM  Requires Python 3.10+ installed and added to PATH.
REM  Internet required only during first install (packages).
REM  Default login — Username: admin  Password: nova@123
REM ============================================================

setlocal enabledelayedexpansion

REM ── Source directory = folder where this BAT file lives ──────
set SRC_DIR=%~dp0
if "%SRC_DIR:~-1%"=="\" set SRC_DIR=%SRC_DIR:~0,-1%

REM ── Install directory = current user's local AppData ─────────
set INSTALL_DIR=%LOCALAPPDATA%\NovoForm

title NovoForm v1.28 Installer

echo.
echo  ====================================================
echo   NovoForm — Formwork Analysis and BOQ Generator
echo   Version 1.28  ^|  Nova Formworks Pvt. Ltd.
echo   July 2026  ^|  Developed by RLAI (rightleft.ai)
echo  ====================================================
echo.
echo   Installing for user : %USERNAME%
echo   Install location    : %INSTALL_DIR%
echo   Desktop shortcut    : %USERPROFILE%\Desktop\NovoForm.lnk
echo.
echo   What's new in v1.28:
echo     - SW label-to-polygon matching fixed for multi-floor DXF drawings
echo     - Same-floor Y-band priority prevents cross-floor label swaps
echo   What was new in v1.27:
echo     - Complex SW shapes (L, T, E, U, comb) now get full polygon BOQ
echo     - All faces including IC inner corners calculated automatically
echo   What was new in v1.26:
echo     - Rectangular SW BOQ fixed: all 4 faces covered (same as column)
echo     - Face-panel top-down diagram in BOQ PDF per element
echo   What was new in v1.25:
echo     - SW10 (and similar elements) now read correctly from DXF
echo     - Red highlight for unreadable elements, orange for L-shaped
echo   What was new in v1.23:
echo     - All 31 elements listed separately in BOQ PDF and Excel
echo     - Natural alphabetical sort: C1,C2...C9,C10 (not C1,C10,C2)
echo   What was new in v1.21:
echo     - No Administrator rights required for installation
echo     - BOQ panel sums now match edge dimensions exactly
echo     - DXF element count fixes (duplicate polygon removal)
echo     - Input field character limits to prevent layout breaks
echo.
echo   Default login: admin / nova@123
echo   (Change password immediately after first login)
echo.

REM ── 1. Verify source files are present ───────────────────────
echo [1/6] Checking source files...
if not exist "%SRC_DIR%\main.py" (
    echo.
    echo  ERROR: main.py not found in: %SRC_DIR%
    echo.
    echo  Please extract the full NovoForm ZIP to a folder
    echo  before running this installer. All files must be
    echo  in the same folder as install_windows*.bat.
    echo.
    pause
    exit /b 1
)
if not exist "%SRC_DIR%\requirements.txt" (
    echo.
    echo  ERROR: requirements.txt not found in: %SRC_DIR%
    echo.
    pause
    exit /b 1
)
echo  Source files OK.

REM ── 2. Check Python ──────────────────────────────────────────
echo.
echo [2/6] Checking Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo  ERROR: Python not found in PATH.
    echo.
    echo  Please install Python 3.10 or higher from:
    echo    https://www.python.org/downloads/
    echo.
    echo  IMPORTANT: During Python setup, check the box:
    echo    "Add Python to PATH"   (on the first screen)
    echo  Then run this installer again.
    echo.
    pause
    exit /b 1
)
for /f "tokens=2" %%v in ('python --version 2^>^&1') do set PY_VER=%%v
echo  Found Python %PY_VER%

REM ── 3. Copy application files to install directory ───────────
echo.
echo [3/6] Installing application files to user profile...
echo  Destination: %INSTALL_DIR%

if not exist "%INSTALL_DIR%"         mkdir "%INSTALL_DIR%"
if not exist "%INSTALL_DIR%\src"     mkdir "%INSTALL_DIR%\src"
if not exist "%INSTALL_DIR%\config"  mkdir "%INSTALL_DIR%\config"
if not exist "%INSTALL_DIR%\assets"  mkdir "%INSTALL_DIR%\assets"

REM Copy core Python files
copy /Y "%SRC_DIR%\main.py"          "%INSTALL_DIR%\main.py"          >nul 2>&1
copy /Y "%SRC_DIR%\requirements.txt" "%INSTALL_DIR%\requirements.txt" >nul 2>&1

REM Copy source tree, config, assets
xcopy "%SRC_DIR%\src"    "%INSTALL_DIR%\src\"    /E /I /Y /Q >nul 2>&1
xcopy "%SRC_DIR%\config" "%INSTALL_DIR%\config\" /E /I /Y /Q >nul 2>&1
xcopy "%SRC_DIR%\assets" "%INSTALL_DIR%\assets\" /E /I /Y /Q >nul 2>&1

REM Create data directory only on fresh install (never overwrite on upgrade)
REM This preserves the user's login database (novoform_auth.db).
if not exist "%INSTALL_DIR%\data" mkdir "%INSTALL_DIR%\data"

if not exist "%INSTALL_DIR%\main.py" (
    echo.
    echo  ERROR: File copy failed. Check that the source folder
    echo  is accessible and your user account can write to:
    echo  %INSTALL_DIR%
    echo.
    pause
    exit /b 1
)
echo  Files installed successfully.

REM ── 4. Remove old virtual environment (clean upgrade) ────────
echo.
echo [4/6] Setting up Python environment...
if exist "%INSTALL_DIR%\venv" (
    echo  Removing previous environment for a clean upgrade...
    rmdir /s /q "%INSTALL_DIR%\venv"
)

python -m venv "%INSTALL_DIR%\venv"
if errorlevel 1 (
    echo.
    echo  ERROR: Could not create Python virtual environment.
    echo  Please check that Python is installed correctly
    echo  with the 'venv' module included.
    echo.
    pause
    exit /b 1
)
echo  Python environment ready.

REM ── 5. Upgrade pip ───────────────────────────────────────────
REM    Full venv path avoids the pip self-replacement restart bug.
echo.
echo [5/6] Upgrading pip...
"%INSTALL_DIR%\venv\Scripts\python.exe" -m pip install --upgrade pip --quiet
if errorlevel 1 (
    echo  Note: pip upgrade skipped — using bundled version.
)
echo  pip ready.

REM ── 6. Install dependencies ──────────────────────────────────
echo.
echo [6/6] Installing packages (3-5 minutes on first install)...
echo  PyQt6, ReportLab, openpyxl, ezdxf, matplotlib, pymupdf...
echo  Note: pip may reuse cached packages — this is normal.
echo  Please wait and do NOT close this window.
echo.
"%INSTALL_DIR%\venv\Scripts\python.exe" -m pip install -r "%INSTALL_DIR%\requirements.txt" --timeout 120
if errorlevel 1 (
    echo.
    echo  ERROR: Package installation failed. Please check:
    echo    1. Internet connection is active
    echo    2. Firewall / antivirus is not blocking pip
    echo    3. If behind a proxy, set the HTTP_PROXY variable
    echo.
    pause
    exit /b 1
)
echo  All packages installed successfully.

REM ── Create VBS launcher (hides the console window on launch) ─
set LAUNCHER=%INSTALL_DIR%\launch_novoform.vbs
(
    echo Set WshShell = WScript.CreateObject^("WScript.Shell"^)
    echo WshShell.CurrentDirectory = "%INSTALL_DIR%"
    echo WshShell.Run chr^(34^) ^& "%INSTALL_DIR%\venv\Scripts\pythonw.exe" ^& chr^(34^) ^& " main.py", 0, False
) > "%LAUNCHER%"

REM ── Create desktop shortcut on the current user's Desktop ────
echo.
echo  Creating desktop shortcut for %USERNAME%...
set SHORTCUT=%USERPROFILE%\Desktop\NovoForm.lnk
powershell -NoProfile -Command ^
    "$ws = New-Object -ComObject WScript.Shell; ^
     $s  = $ws.CreateShortcut('%SHORTCUT%'); ^
     $s.TargetPath      = 'wscript.exe'; ^
     $s.Arguments       = '\"%LAUNCHER%\"'; ^
     $s.WorkingDirectory= '%INSTALL_DIR%'; ^
     $s.Description     = 'NovoForm BOQ Generator — Nova Formworks v1.28'; ^
     $s.Save()" >nul 2>&1

if exist "%SHORTCUT%" (
    echo  Desktop shortcut created: %SHORTCUT%
) else (
    echo  Shortcut could not be created automatically.
    echo  To launch, double-click: %LAUNCHER%
)

REM ── Create api_config.json from template (first run only) ────
if not exist "%INSTALL_DIR%\config\api_config.json" (
    if exist "%INSTALL_DIR%\config\api_config.template.json" (
        copy "%INSTALL_DIR%\config\api_config.template.json" ^
             "%INSTALL_DIR%\config\api_config.json" >nul
        echo  Config file created from template.
    )
)

REM ── Done ─────────────────────────────────────────────────────
echo.
echo  ====================================================
echo   Installation Complete!  ^|  NovoForm v1.28
echo.
echo   To launch NovoForm:
echo     Option 1 : Double-click "NovoForm" on your Desktop
echo     Option 2 : Double-click:
echo                %LAUNCHER%
echo     Option 3 : Run manually in a terminal:
echo                "%INSTALL_DIR%\venv\Scripts\pythonw.exe" main.py
echo.
echo   App folder  : %INSTALL_DIR%
echo   Data folder : %INSTALL_DIR%\data\
echo   Config      : %INSTALL_DIR%\config\panel_config.json
echo.
echo   To upgrade later: run this installer again.
echo   User data (login database) is preserved on upgrade.
echo.
echo   Support: rightleft.ai  ^|  Nova Formworks Pvt. Ltd.
echo  ====================================================
echo.
pause
endlocal
