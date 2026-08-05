#requires -Version 5.1
<#
.SYNOPSIS
  Verify the Sentinel development environment is reproducible and consistent.
.DESCRIPTION
  Reports OK/FAIL for each required component. Never shows secret values.
  Exit code 0 if valid, 1 if not.
#>
param(
    [string]$DataDir = "$PSScriptRoot\..\.local-data\development"
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$global:fail = 0

function Report($name, $ok, $detail = "") {
    $status = if ($ok) { "OK" } else { "FAIL" }
    $color = if ($ok) { "Green" } else { "Red" }
    Write-Host "$name`: $status" -ForegroundColor $color -NoNewline
    if ($detail) { Write-Host " ($detail)" -ForegroundColor Gray }
    else { Write-Host }
    if (-not $ok) { $global:fail++ }
}

Push-Location $repoRoot
try {
    # Python
    $pyOk = (python --version 2>&1) -match "3\.12"
    Report "Python" $pyOk

    $uvOk = [bool](python -m uv --version 2>$null)
    Report "uv" $uvOk

    $lockOk = (Test-Path uv.lock) -and (Test-Path pyproject.toml)
    Report "Python lockfile" $lockOk

    # Node
    $nodeOk = (node --version 2>&1) -match "v(20|2[4-9])"
    Report "Node" $nodeOk (node --version 2>&1)

    $npmCiOk = (Test-Path node_modules) -and (Test-Path package-lock.json)
    Report "npm ci state" $npmCiOk

    # Rust
    $rustOk = (rustc --version 2>&1) -match "1\.96"
    Report "Rust" $rustOk (rustc --version 2>&1)

    $cargoLockOk = Test-Path src-tauri/Cargo.lock
    Report "Cargo.lock" $cargoLockOk

    # Tauri
    $tauriOk = (npx tauri --version 2>&1) -match "2\.11"
    Report "Tauri" $tauriOk

    # WebView2
    $wv2Key = 'HKLM:\SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8B67-6653EC1CCF13}'
    $wv2Ok = Test-Path $wv2Key
    Report "WebView2" $wv2Ok

    # .env
    $envOk = Test-Path .env
    Report ".env" $envOk

    # Secrets (only presence, not values)
    $secretCheck = (Get-ChildItem -Path . -Include 'vault.key','.env' -Recurse -ErrorAction SilentlyContinue | Where-Object { $_.Name -ne '.env.example' }) | Measure-Object
    Report "Secret files present" ($secretCheck.Count -gt 0) "count: $($secretCheck.Count)"

    # Model
    $modelDir = if ($env:SENTINEL_LOCAL_MODEL_DIR) { $env:SENTINEL_LOCAL_MODEL_DIR } else { "$repoRoot\sentinel\local_model" }
    $modelOk = Test-Path $modelDir -PathType Container
    Report "Local model dir" $modelOk

    # Data root
    $dataOk = (Test-Path $DataDir) -or ($env:SENTINEL_DATA_DIR -and (Test-Path $env:SENTINEL_DATA_DIR))
    Report "Data root" $dataOk

    # Build tools
    $msvcOk = [bool](Get-Command cl.exe -ErrorAction SilentlyContinue)
    Report "MSVC" $msvcOk

    if ($global:fail -eq 0) {
        Write-Host "==> Environment is valid." -ForegroundColor Green
    } else {
        Write-Host "==> $global:fail checks failed." -ForegroundColor Red
    }
    exit $global:fail
} finally {
    Pop-Location
}
