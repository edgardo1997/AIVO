@echo off
title Sentinel - Asistente IA
cd /d "%~dp0"

:: ── 1. Check prerequisites ──────────────────────────────────
echo [1/5] Verificando requisitos...

where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python no encontrado. Instalalo desde: https://www.python.org/downloads/
    echo         Marca "Add Python to PATH" durante la instalacion.
    pause
    exit /b 1
)
python --version

where node >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Node.js no encontrado. Instalalo desde: https://nodejs.org/
    pause
    exit /b 1
)
node --version

:: ── 2. Python virtual env ───────────────────────────────────
echo [2/5] Preparando entorno Python...
if not exist "sidecar\.venv\Scripts\python.exe" (
    echo   Creando entorno virtual...
    cd sidecar
    python -m venv .venv
    call .venv\Scripts\activate.bat
    pip install --upgrade pip >nul
    pip install -r requirements.txt
    if errorlevel 1 (
        echo [ERROR] Fallo al instalar dependencias Python.
        pause
        exit /b 1
    )
    cd ..
) else (
    echo   Entorno virtual listo.
)

:: ── 3. Node.js dependencies ────────────────────────────────
echo [3/5] Verificando dependencias Node.js...
if not exist "node_modules" (
    echo   Instalando dependencias...
    call npm install
    if errorlevel 1 (
        echo [ERROR] Fallo al instalar dependencias Node.js.
        pause
        exit /b 1
    )
) else (
    echo   Dependencias listas.
)

:: ── 4. Start sidecar ────────────────────────────────────────
echo [4/5] Iniciando servidor...
cd sidecar
start "Sentinel Sidecar" cmd /c ".venv\Scripts\activate && uvicorn main:app --host 127.0.0.1 --port 8765"
cd ..

:: ── 5. Start frontend and open browser ──────────────────────
echo [5/5] Iniciando interfaz...
start "Sentinel UI" cmd /c "npm run dev"
timeout /t 5 /nobreak >nul
start http://localhost:5173

echo.
echo ============================================
echo   Sentinel esta corriendo
echo ============================================
echo.
echo   Interfaz: http://localhost:5173
echo   API:      http://127.0.0.1:8765
echo.
echo   Para configurar tu proveedor AI:
echo     Ejecuta: configure.bat
echo.
echo   Para cerrar, cierra las ventanas o presiona Ctrl+C aqui.
echo.
pause
