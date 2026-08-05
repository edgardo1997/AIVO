#requires -Version 5.1
<#
.SYNOPSIS
  Build pipeline canónico para Sentinel Alpha.
.DESCRIPTION
  Orquesta frontend, sidecar PyInstaller, validación, Rust/Tauri bundle y
  manifest de artefactos. El script se detiene ante cualquier fallo.
#>
param(
    [string]$Channel = "alpha",
    [string]$OutputDir = "$PSScriptRoot\..\artifacts",
    [switch]$SkipTauri,
    [switch]$SkipTests,
    [switch]$AllowDirty
)

$ErrorActionPreference = "Stop"

function Get-IsDirty {
    $porcelain = git status --porcelain
    return ($null -ne $porcelain)
}

function Get-CanonicalPath($relative) {
    $p = Join-Path (Get-Location).Path $relative
    return [System.IO.Path]::GetFullPath($p)
}

function Remove-Tree($path) {
    if (Test-Path $path) {
        Write-Host "Removing $path" -ForegroundColor Cyan
        Remove-Item -Recurse -Force $path
    }
}

function Step-Exec {
    param(
        [string]$Name,
        [scriptblock]$Command
    )
    Write-Host "`n>>> $Name" -ForegroundColor Cyan
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "$Name failed (exit $LASTEXITCODE)"
    }
    $sw.Stop()
    Write-Host "    completed in $($sw.Elapsed.ToString())" -ForegroundColor Green
}

Set-Location "$PSScriptRoot\.."

$repoRoot = Get-Location
$commit = git rev-parse HEAD
$short = git rev-parse --short HEAD
$branch = git branch --show-current
$dirty = Get-IsDirty
$timestamp = [System.DateTime]::UtcNow.ToString("yyyy-MM-ddTHH:mm:ssZ")

if ($dirty -and -not $AllowDirty) {
    throw "Working tree is dirty. Use -AllowDirty for development builds."
}

$dirtyTag = if ($dirty) { "+dirty.$short" } else { "" }
$buildId = "$Channel-$((Get-Date -Format 'yyyyMMdd'))-$short$dirtyTag"

$packageJson = Get-Content "package.json" | ConvertFrom-Json
$version = $packageJson.version
Write-Host "Building Sentinel $version (channel=$channel, build=$buildId, commit=$commit, dirty=$dirty)" -ForegroundColor Cyan

$env:SENTINEL_ENABLE_ACL = "0"
$env:SENTINEL_ENABLE_FLEET_STARTUP = "0"
$env:SENTINEL_JWT_SECRET = "build-jwt-secret-not-for-production"

# Limpieza controlada
Remove-Tree "$repoRoot\dist"
Remove-Tree "$repoRoot\sidecar\dist"
Remove-Tree "$repoRoot\sidecar\build"
Remove-Tree "$repoRoot\src-tauri\target\release\bundle"
Remove-Tree $OutputDir
New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null

# Frontend
Step-Exec "npm ci" { npm ci }
Step-Exec "frontend build" { npm run build }

if (-not (Test-Path "$repoRoot\dist\index.html")) {
    throw "Frontend build did not produce dist/index.html"
}

# Python + Sidecar
Step-Exec "uv sync" { python -m uv sync --frozen }
Step-Exec "sidecar PyInstaller" { & { Set-Location sidecar; python -m uv run pyinstaller sidecar.spec --noconfirm } }

$sidecarCanonical = Get-CanonicalPath "sidecar\dist\sidecar.exe"
if (-not (Test-Path $sidecarCanonical)) {
    throw "PyInstaller did not produce $sidecarCanonical"
}

$sidecarHash = (Get-FileHash -Path $sidecarCanonical -Algorithm SHA256).Hash
Write-Host "Sidecar canonical: $sidecarCanonical" -ForegroundColor Green
Write-Host "Sidecar SHA-256:   $sidecarHash" -ForegroundColor Green

# Smoke
Step-Exec "sidecar smoke" { & { Set-Location $repoRoot; .\scripts\smoke-sidecar.ps1 -SidecarExe $sidecarCanonical } }

# Rust gates (if not skipped)
if (-not $SkipTests) {
    Step-Exec "Rust tests" { cargo test --locked --manifest-path src-tauri\Cargo.toml }
    Step-Exec "Rust clippy" { cargo clippy --locked --manifest-path src-tauri\Cargo.toml -- -D warnings }
    Step-Exec "Rust fmt check" { cargo fmt --manifest-path src-tauri\Cargo.toml -- --check }
}

# Tauri bundle
if (-not $SkipTauri) {
    Step-Exec "Tauri build" { npm run tauri:build }

    # Extract sidecar from the NSIS installer to verify it is the same binary.
    $installer = Get-ChildItem -Path "$repoRoot\src-tauri\target\release\bundle\nsis" -Filter "Sentinel_*_x64-setup.exe" | Select-Object -First 1
    if (-not $installer) {
        throw "No NSIS installer found under src-tauri/target/release/bundle/nsis"
    }

    $hashMatch = $false
    $inspectDir = Join-Path $env:TEMP "sentinel-build-inspect"
    Remove-Item -Recurse -Force $inspectDir -ErrorAction SilentlyContinue
    New-Item -ItemType Directory -Path $inspectDir | Out-Null
    try {
        $proc = Start-Process -FilePath $installer.FullName -ArgumentList "/S", "/D=$inspectDir" -PassThru -Wait
        if ($proc.ExitCode -ne 0) {
            throw "NSIS silent install failed with exit code $($proc.ExitCode)"
        }
        $bundledSidecar = Join-Path $inspectDir "sidecar\sidecar.exe"
        if (-not (Test-Path $bundledSidecar)) {
            throw "Bundled sidecar.exe not found at $bundledSidecar"
        }
        $bundledHash = (Get-FileHash -Path $bundledSidecar -Algorithm SHA256).Hash
        Write-Host "Bundled sidecar: $bundledSidecar => $bundledHash"
        if ($bundledHash -eq $sidecarHash) {
            $hashMatch = $true
            Write-Host "Bundled sidecar hash matches canonical." -ForegroundColor Green
        }
        else {
            throw "Bundled sidecar hash does not match canonical sidecar."
        }
    }
    finally {
        Remove-Item -Recurse -Force $inspectDir -ErrorAction SilentlyContinue
    }
}
else {
    Write-Warning "Tauri build skipped. Cannot verify bundled sidecar hash."
}

# Artifact manifest
$manifest = @{
    product           = "Sentinel"
    version           = $version
    channel           = $Channel
    build_id          = $buildId
    commit            = $commit
    commit_short      = $short
    branch            = $branch
    dirty             = $dirty
    timestamp_utc     = $timestamp
    platform          = "windows"
    arch              = "x86_64"
    python            = (& python --version).ToString().Replace("Python ", "")
    node              = (node --version).TrimStart("v")
    rust              = (rustc --version).Split(" ")[1]
    sidecar_canonical = $sidecarCanonical
    sidecar_sha256    = $sidecarHash
    frontend_dist     = (Get-CanonicalPath "dist")
    artifacts         = @()
}

# Add known artifacts
if (Test-Path "$repoRoot\src-tauri\target\release\bundle") {
    $bundleFiles = Get-ChildItem -Path "$repoRoot\src-tauri\target\release\bundle" -Recurse -File |
    Where-Object { $_.Extension -in ".exe", ".msi", ".nupkg", ".zip", ".sig" }
    foreach ($f in $bundleFiles) {
        $manifest.artifacts += @{
            name   = $f.Name
            path   = $f.FullName
            sha256 = (Get-FileHash -Path $f.FullName -Algorithm SHA256).Hash
            size   = $f.Length
        }
    }
}

$manifestPath = Join-Path $OutputDir "alpha-manifest.json"
$manifest | ConvertTo-Json -Depth 4 | Set-Content -Path $manifestPath
Write-Host "`nManifest: $manifestPath" -ForegroundColor Green
Write-Host (Get-Content $manifestPath | Out-String)

if (-not $SkipTauri -and -not $hashMatch) {
    throw "Build terminated but bundled sidecar hash verification failed."
}

Write-Host "`nBUILD SUCCESS: $buildId" -ForegroundColor Green
