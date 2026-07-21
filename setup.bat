@echo off
title Sentinel - Entorno de desarrollo
echo ========================================
echo   Sentinel - Entorno de desarrollo
echo ========================================
echo.

:: Find Python
set PYTHON_CMD=
for %%c in (python3 py python) do (
    where %%c > nul 2>&1
    if not errorlevel 1 (
        set PYTHON_CMD=%%c
        goto :found
    )
)
:: Check common paths
for %%p in (
    "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
    "C:\Python312\python.exe"
    "C:\Python313\python.exe"
) do (
    if exist %%p (
        set PYTHON_CMD=%%p
        goto :found
    )
)

echo [ERROR] Python 3.12+ not found.
echo Install it from: https://www.python.org/downloads/
echo Make sure to check "Add Python to PATH" during installation.
pause
exit /b 1

:found
echo [OK] Found Python: %PYTHON_CMD%
%PYTHON_CMD% --version

:: Check Node.js
where node > nul 2>&1
if errorlevel 1 (
    echo [ERROR] Node.js 20+ not found.
    echo Install it from: https://nodejs.org/
    pause
    exit /b 1
)
echo [OK] Found Node.js
node --version

:: Check Rust (optional, for Tauri build)
where cargo > nul 2>&1
if not errorlevel 1 (
    echo [OK] Found Rust
    cargo --version
) else (
    echo [INFO] Rust not found. Only web mode will be available.
    echo Install from: https://rustup.rs/ for desktop app.
)

echo.
echo ---------------------------------------
echo  Installing Python dependencies...
echo ---------------------------------------
cd /d "%~dp0sidecar"
%PYTHON_CMD% -m venv .venv
call .venv\Scripts\activate.bat
pip install --upgrade pip
pip install -r requirements.txt
if errorlevel 1 (
    echo [ERROR] Failed to install Python dependencies.
    pause
    exit /b 1
)
echo [OK] Python dependencies installed.

echo.
echo ---------------------------------------
echo  Installing Node.js dependencies...
echo ---------------------------------------
cd /d "%~dp0"
call npm install
if errorlevel 1 (
    echo [ERROR] Failed to install Node.js dependencies.
    pause
    exit /b 1
)
echo [OK] Node.js dependencies installed.

echo.
echo ========================================
echo   Setup complete!
echo ========================================
echo.
echo To run in browser:
echo   1. Start sidecar:  cd sidecar ^&^& .venv\Scripts\activate ^&^& uvicorn main:app --host 127.0.0.1 --port 8765
echo   2. Start frontend: npm run dev
echo   3. Open:           http://localhost:5173
echo.
echo To run desktop app:
echo   npm run tauri:dev
echo.
pause
