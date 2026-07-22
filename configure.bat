@echo off
title AIVO - Configuration Wizard
setlocal enabledelayedexpansion

echo ============================================
echo    AIVO - Configuration Wizard
echo    Set up your AI provider in 2 minutes
echo ============================================
echo.

:: Find sidecar
set SIDECAR_DIR=%~dp0sidecar
if not exist "%SIDECAR_DIR%\main.py" (
    echo [ERROR] Cannot find sidecar directory.
    pause
    exit /b 1
)

:: Check if running
set SIDECAR_URL=http://127.0.0.1:8765
curl -s -o nul -w "%%{http_code}" "%SIDECAR_URL%/api/health" > "%TEMP%\aivo_health.txt" 2>nul
set /p HEALTH=<"%TEMP%\aivo_health.txt"
del "%TEMP%\aivo_health.txt" 2>nul

if "%HEALTH%"=="200" (
    echo [OK] Sidecar is running on port 8765
) else (
    echo [INFO] Sidecar is not running.
    echo.
    choice /c YN /m "Start sidecar now?"
    if errorlevel 2 exit /b
    
    echo Starting sidecar...
    start "AIVO Sidecar" cmd /c "cd /d "%SIDECAR_DIR%" && .venv\Scripts\activate && uvicorn main:app --host 127.0.0.1 --port 8765"
    echo Waiting for sidecar...
    :wait_loop
    timeout /t 2 /nobreak >nul
    curl -s -o nul -w "%%{http_code}" "%SIDECAR_URL%/api/health" > "%TEMP%\aivo_health.txt" 2>nul
    set /p HEALTH=<"%TEMP%\aivo_health.txt"
    del "%TEMP%\aivo_health.txt" 2>nul
    if not "!HEALTH!"=="200" goto wait_loop
    echo [OK] Sidecar started successfully
)

echo.
echo ============================================
echo  Choose your AI provider:
echo ============================================
echo.
echo  1) OpenRouter (recommended) - Free tier available
echo     Get key: https://openrouter.ai/keys
echo.
echo  2) DeepSeek Direct - Cheap, fast
echo     Get key: https://platform.deepseek.com/api_keys
echo.
echo  3) Ollama (local, offline) - No key needed
echo     Install: https://ollama.com
echo.
echo  4) Skip - I'll configure later via Settings
echo.

:input_loop
set /p CHOICE="Select option (1-4): "
if "%CHOICE%"=="1" set PROVIDER=openrouter& goto :get_key
if "%CHOICE%"=="2" set PROVIDER=deepseek& goto :get_key
if "%CHOICE%"=="3" goto :ollama_setup
if "%CHOICE%"=="4" goto :skip
echo Invalid option. Please enter 1, 2, 3, or 4.
goto input_loop

:get_key
echo.
echo  Step 1: Open this URL in your browser
echo    https://openrouter.ai/keys
echo.
echo  Step 2: Create an account and copy your API key
echo.
set /p API_KEY="Paste your API key here: "
if "%API_KEY%"=="" (
    echo [ERROR] API key cannot be empty.
    goto get_key
)

echo.
echo  Configuring %PROVIDER%...
curl -s -X POST "%SIDECAR_URL%/api/ai/config" ^
  -H "Content-Type: application/json" ^
  -d "{\"provider\":\"%PROVIDER%\",\"api_key\":\"%API_KEY%\"}" ^
  > "%TEMP%\aivo_config.json" 2>nul

type "%TEMP%\aivo_config.json"
del "%TEMP%\aivo_config.json" 2>nul
echo.
echo [OK] Provider configured!
goto :test

:ollama_setup
echo.
echo  Checking if Ollama is running...
curl -s -o nul -w "%%{http_code}" "http://127.0.0.1:11434/api/tags" > "%TEMP%\aivo_ollama.txt" 2>nul
set /p OLLAMA_OK=<"%TEMP%\aivo_ollama.txt"
del "%TEMP%\aivo_ollama.txt" 2>nul

if not "%OLLAMA_OK%"=="200" (
    echo [INFO] Ollama is not running.
    echo  Install from: https://ollama.com
    echo  Then run: ollama run qwen3:1.7b
    echo.
    echo  After installing, re-run this wizard.
    pause
    exit /b
)

echo  Configuring Ollama as local provider...
curl -s -X POST "%SIDECAR_URL%/api/ai/config" ^
  -H "Content-Type: application/json" ^
  -d "{\"provider\":\"ollama\",\"base_url\":\"http://127.0.0.1:11434/v1\",\"model\":\"qwen3:1.7b\"}" ^
  > "%TEMP%\aivo_config.json" 2>nul

type "%TEMP%\aivo_config.json"
del "%TEMP%\aivo_config.json" 2>nul
echo.
echo [OK] Ollama configured!
goto :test

:test
echo.
echo  Testing connection...
curl -s -X POST "%SIDECAR_URL%/api/ai/chat" ^
  -H "Content-Type: application/json" ^
  -d "{\"message\":\"Respond with just the word: OK\"}" ^
  > "%TEMP%\aivo_test.json" 2>nul
if errorlevel 1 (
    echo [WARN] Connection test failed. Check your API key and try again.
    echo  You can always reconfigure later in Settings.
) else (
    type "%TEMP%\aivo_test.json"
    echo.
    echo [OK] Connection successful!
)
del "%TEMP%\aivo_test.json" 2>nul

:skip
echo.
echo ============================================
echo   Setup complete!
echo ============================================
echo.
echo  Open http://localhost:5173 in your browser.
echo  Or run: npm run tauri:dev  (for desktop app)
echo.
echo  Need help? Visit https://github.com/anomalyco/opencode
echo.
pause
