#Requires -Version 7.4
<#
.SYNOPSIS
    Prepara datos de prueba seguros para la validación manual de Fase 14.

.DESCRIPTION
    Crea un perfil de datos temporal bajo %TEMP%\Sentinel-Fase14-Validation
    con secretos falsos y una configuración corrupta controlada.
    No toca %USERPROFILE%\.sentinel ni inicia/ciera procesos.
    Si Sentinel compilado no soporta data root temporal, se debe probar con
    un usuario Windows temporal y copiar los archivos generados a su perfil.
#>

$ErrorActionPreference = "Stop"

$TestRoot = Join-Path $env:TEMP "Sentinel-Fase14-Validation"
$TestData = Join-Path $TestRoot "data"
$TestLogs = Join-Path $TestData "logs"
$TestBackups = Join-Path $TestData "backups"
$TestConfig = Join-Path $TestData "config"

Remove-Item -Path $TestRoot -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Path $TestLogs -Force | Out-Null
New-Item -ItemType Directory -Path $TestBackups -Force | Out-Null
New-Item -ItemType Directory -Path $TestConfig -Force | Out-Null

# Secretos falsos para probar redacción
$FakeSecrets = @(
    "FAKE_API_KEY_SENTINEL_TEST",
    "FAKE_BEARER_TOKEN_SENTINEL_TEST",
    "FAKE_PASSWORD_SENTINEL_TEST",
    "FAKE_PRIVATE_KEY_SENTINEL_TEST",
    "FAKE_COOKIE_SENTINEL_TEST"
)

$LogLines = @(
    '2026-08-05T00:00:00Z INFO sentinel.test: starting Fase 14 validation',
    '2026-08-05T00:00:01Z INFO sentinel.test: api_key=FAKE_API_KEY_SENTINEL_TEST',
    '2026-08-05T00:00:02Z INFO sentinel.test: Authorization: Bearer FAKE_BEARER_TOKEN_SENTINEL_TEST',
    '2026-08-05T00:00:03Z WARN sentinel.test: password=FAKE_PASSWORD_SENTINEL_TEST',
    '2026-08-05T00:00:04Z INFO sentinel.test: private_key=FAKE_PRIVATE_KEY_SENTINEL_TEST',
    '2026-08-05T00:00:05Z INFO sentinel.test: cookie=FAKE_COOKIE_SENTINEL_TEST',
    '2026-08-05T00:00:06Z INFO sentinel.test: C:\Users\SomeUser\Documents\file.pdf changed',
    '2026-08-05T00:00:07Z INFO sentinel.test: validation complete'
)

$LogLines | Set-Content -Path (Join-Path $TestLogs "sentinel.log") -Encoding UTF8

# Configuración corrupta para probar reparación
$CorruptConfig = @{
    schema = "sentinel-config"
    version = "0.1.0-alpha.1"
    providers = @(
        @{ id = "openrouter"; api_key = "FAKE_API_KEY_SENTINEL_TEST"; name = "OpenRouter" }
    )
    permissions = @(
        @{ level = "view"; paths = @("C:\\Users\\SomeUser\\Documents") }
    )
}

$CorruptConfig | ConvertTo-Json -Depth 5 | Set-Content -Path (Join-Path $TestConfig "settings.json") -Encoding UTF8

# Backup válido para probar reparación
$ValidConfig = @{
    schema = "sentinel-config"
    version = "0.1.0-alpha.1"
    providers = @()
    permissions = @()
    validated = $true
}

$ValidConfig | ConvertTo-Json -Depth 5 | Set-Content -Path (Join-Path $TestBackups "settings-20260801-000000.json") -Encoding UTF8

# Archivo de referencia con los secretos a buscar
$FakeSecrets | Set-Content -Path (Join-Path $TestRoot "FAKE_SECRETS.txt") -Encoding UTF8

Write-Host "=============================================="
Write-Host "  Fase 14 — datos de validación preparados"
Write-Host "=============================================="
Write-Host ""
Write-Host "Directorio de prueba: $TestRoot"
Write-Host ""
Write-Host "Archivos generados:"
Write-Host "  - logs\sentinel.log            (con secretos falsos)"
Write-Host "  - config\settings.json         (configuración corrupta)"
Write-Host "  - backups\settings-*.json      (backup válido)"
Write-Host "  - FAKE_SECRETS.txt            (lista de secretos a buscar)"
Write-Host ""
Write-Host "Secretos falsos insertados:"
$FakeSecrets | ForEach-Object { Write-Host "  - $_" }
Write-Host ""
Write-Host "Instrucciones:"
Write-Host ""
Write-Host "1. Si la build compilada soporta SENTINEL_DATA_DIR, inyectar:"
Write-Host "   `$env:SENTINEL_DATA_DIR = '$($TestData)'`"
Write-Host "   .​\artifacts\internal-alpha\Sentinel_0.1.0-alpha.1_x64-setup.exe"
Write-Host ""
Write-Host "2. Si no lo soporta, ejecutar la prueba en un usuario Windows temporal:"
Write-Host "   a. Crear usuario local `SentinelTest` (admin no requerido)."
Write-Host "   b. Iniciar sesión como `SentinelTest`."
Write-Host "   c. Copiar todo el contenido de:"
Write-Host "      $TestData"
Write-Host "   d. Pegar en:"
Write-Host "      %USERPROFILE%\.sentinel"
Write-Host "   e. Instalar y ejecutar Sentinel desde la build de validación."
Write-Host ""
Write-Host "3. No ejecutar la build con el usuario principal sin aislamiento,"
Write-Host "   para evitar modificar configuración real."
Write-Host ""
Write-Host "Validación ZIP posterior:"
Write-Host "   .\scripts\validate-diagnostic-package.ps1 -DiagnosticZip <ruta-zip> -ExpectedBuildId <build-id>"
