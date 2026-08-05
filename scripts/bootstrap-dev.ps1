#requires -Version 5.1
<#
.SYNOPSIS
  Bootstrap a reproducible Sentinel development environment on Windows.
.DESCRIPTION
  Idempotent script that verifies prerequisites, creates a Python venv,
  installs locked dependencies, installs Node modules, fetches Rust crates,
  creates .env from .env.example and a local data directory, then runs
  smoke checks.
#>
param(
    [switch]$SkipModelDownload,
    [switch]$SkipNode,
    [switch]$SkipRust,
    [string]$DataDir = "$PSScriptRoot\..\.local-data\development"
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
Push-Location $repoRoot

try {
    Write-Host "==> Bootstrapping Sentinel pre-Alpha environment..." -ForegroundColor Cyan

    # --- Python / uv ---
    $pyVersion = (python --version 2>&1) -join " "
    if ($pyVersion -notmatch "3\.12") { throw "Python 3.12 required, found: $pyVersion" }
    Write-Host "Python: $pyVersion" -ForegroundColor Green

    if (-not (python -m uv --version 2>$null)) {
        Write-Host "Installing uv..." -ForegroundColor Yellow
        python -m pip install uv
    }

    python -m uv sync --frozen
    if ($LASTEXITCODE -ne 0) { throw "uv sync failed" }

    # --- Node ---
    if (-not $SkipNode) {
        $nodeVersion = (node --version 2>&1) -join " "
        if ($nodeVersion -notmatch "v(20|2[4-9])") { throw "Node 20+ required, found: $nodeVersion" }
        Write-Host "Node: $nodeVersion" -ForegroundColor Green
        npm ci
        if ($LASTEXITCODE -ne 0) { throw "npm ci failed" }
    }

    # --- Rust ---
    if (-not $SkipRust) {
        $rustVersion = (rustc --version 2>&1) -join " "
        if ($rustVersion -notmatch "1\.96") { throw "Rust 1.96 required, found: $rustVersion" }
        Write-Host "Rust: $rustVersion" -ForegroundColor Green
        cargo fetch --locked --manifest-path src-tauri/Cargo.toml
        if ($LASTEXITCODE -ne 0) { throw "cargo fetch failed" }
    }

    # --- Environment template ---
    if (-not (Test-Path .env)) {
        Copy-Item .env.example .env
        Write-Host "Created .env from .env.example (fill in secrets manually)." -ForegroundColor Yellow
    }

    # --- Data directory ---
    New-Item -ItemType Directory -Force -Path $DataDir | Out-Null
    [System.Environment]::SetEnvironmentVariable("SENTINEL_DATA_DIR", $DataDir, "Process")
    Write-Host "Data directory: $DataDir" -ForegroundColor Green

    # --- Smoke checks ---
    Write-Host "==> Running smoke checks..." -ForegroundColor Cyan
    python -m uv run python -c "import fastapi; import sidecar"
    if (-not $SkipRust) {
        cargo test --locked --manifest-path src-tauri/Cargo.toml
        if ($LASTEXITCODE -ne 0) { throw "cargo test failed" }
    }

    if (-not $SkipNode) {
        npm test
        if ($LASTEXITCODE -ne 0) { throw "npm test failed" }
    }

    if (-not $SkipModelDownload) {
        if (Test-Path scripts\download_local_model.py) {
            Write-Host "Run scripts\download_local_model.py separately to download a model." -ForegroundColor Yellow
        }
    }

    Write-Host "==> Bootstrap complete." -ForegroundColor Green
} finally {
    Pop-Location
}
