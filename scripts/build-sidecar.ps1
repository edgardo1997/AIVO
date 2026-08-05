#Requires -Version 7.2
<#
.SYNOPSIS
    Build the Sentinel sidecar from a clean state.
.DESCRIPTION
    Compiles sidecar/main.py with PyInstaller, runs a smoke test,
    writes sidecar hash, and ensures the Tauri build resource exists.
    Must be called before cargo build or Tauri bundle.
#>
param(
    [string]$Channel = "internal-alpha",
    [switch]$SkipTests,
    [switch]$AllowDirty
)

$ErrorActionPreference = 'Stop'
$repoRoot = $PSScriptRoot | Split-Path -Parent
Set-Location $repoRoot

# Pre-check: working tree should be clean unless allowed
if (-not $AllowDirty) {
    $dirty = git status --short
    if ($dirty) {
        Write-Error "Working tree is dirty. Commit or pass -AllowDirty.`n$dirty"
    }
}

$sidecarDir = Join-Path $repoRoot 'sidecar'
$distDir = Join-Path $sidecarDir 'dist'
$buildDir = Join-Path $sidecarDir 'build'
$sidecarExe = Join-Path $distDir 'sidecar.exe'
$hashFile = Join-Path $distDir 'sidecar.sha256'

# Clean previous builds
if (Test-Path $distDir) { Remove-Item -Recurse -Force $distDir }
if (Test-Path $buildDir) { Remove-Item -Recurse -Force $buildDir }
New-Item -ItemType Directory -Path $distDir -Force | Out-Null

# Embed build metadata so the running sidecar can report it
$commit = git rev-parse HEAD
$buildId = "$Channel-$(Get-Date -Format 'yyyyMMdd')-$($commit.Substring(0,7))"
$version = (Get-Content (Join-Path $repoRoot 'package.json') | ConvertFrom-Json).version
$buildInfoPy = Join-Path $sidecarDir '_build_info.py'
@(
    "BUILD_ID = `"$buildId`""
    "VERSION = `"$version`""
    "COMMIT = `"$commit`""
    "CHANNEL = `"$Channel`""
    "TIMESTAMP_UTC = `"$((Get-Date -Format 'o'))`""
) -join "`n" | Out-File -FilePath $buildInfoPy -Encoding utf8

# Build sidecar with uv + PyInstaller
Write-Host "Building sidecar..."
$pyinstaller = (Get-Item (Join-Path $repoRoot '.venv\Scripts\pyinstaller.exe')).FullName
& $pyinstaller (Join-Path $sidecarDir 'sidecar.spec') --workpath $buildDir --distpath $distDir --clean --noconfirm

if (-not (Test-Path $sidecarExe)) {
    Write-Error "sidecar.exe was not produced at $sidecarExe"
}

# Smoke test
Write-Host "Running sidecar smoke..."
& (Join-Path $PSScriptRoot 'smoke-sidecar.ps1') -SidecarExe $sidecarExe

# Hash
$hash = (Get-FileHash $sidecarExe -Algorithm SHA256).Hash.ToLower()
$hash | Out-File -FilePath $hashFile -Encoding ascii
Write-Host "Sidecar hash: $hash"

# Metadata
$commit = git rev-parse HEAD
$buildId = "$Channel-$(Get-Date -Format 'yyyyMMdd')-$($commit.Substring(0,7))"
@{
    version        = (Get-Content (Join-Path $repoRoot 'package.json') | ConvertFrom-Json).version
    build_id       = $buildId
    commit         = $commit
    channel        = $Channel
    timestamp_utc  = (Get-Date -Format 'o')
    sidecar_sha256 = $hash
    platform       = 'windows'
    architecture   = 'x64'
} | ConvertTo-Json -Depth 3 | Out-File -FilePath (Join-Path $distDir 'sidecar-manifest.json') -Encoding utf8

Write-Host "Sidecar build complete: $sidecarExe"
