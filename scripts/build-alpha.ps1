#requires -Version 5.1
<#
.SYNOPSIS
  Build pipeline canónico para Sentinel con canales firmes.
.DESCRIPTION
  Orquesta frontend, sidecar PyInstaller, validación, Rust/Tauri bundle,
  firma según canal y manifest de artefactos. El script se detiene ante
  cualquier fallo. Un build que no cumple la política de su canal falla
  antes de compilar.
#>
param(
    [ValidateSet("development", "internal-alpha", "external-alpha", "stable")]
    [string]$Channel = "internal-alpha",
    [string]$OutputDir = "$PSScriptRoot\..\artifacts\$Channel",
    [switch]$SkipTests,
    [switch]$AllowDirty
)

$ErrorActionPreference = "Stop"

# ---------------------------------------------------------------------------
# Channel policy matrix
# ---------------------------------------------------------------------------
$ChannelPolicy = @{
    "development"    = @{ dirty = $true; updater = $false; tauriSign = $false; authenticode = $false; tag = $false; requireClean = $false }
    "internal-alpha" = @{ dirty = $false; updater = $false; tauriSign = $false; authenticode = $false; tag = $false; requireClean = $true }
    "external-alpha" = @{ dirty = $false; updater = $true; tauriSign = $true; authenticode = $true; tag = $false; requireClean = $true }
    "stable"         = @{ dirty = $false; updater = $true; tauriSign = $true; authenticode = $true; tag = $true; requireClean = $true }
}

$policy = $ChannelPolicy[$Channel]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
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

function Test-Command($cmd) {
    return [bool](Get-Command $cmd -ErrorAction SilentlyContinue)
}

function Invoke-TauriBuild {
    param([string]$BuildChannel)
    if ($BuildChannel -eq "internal-alpha" -or $BuildChannel -eq "development") {
        Step-Exec "Tauri build (internal, no updater)" { npm run tauri:build }
    }
    else {
        $releaseConfig = Get-CanonicalPath "src-tauri\tauri.release.conf.json"
        if (-not (Test-Path $releaseConfig)) {
            throw "Release Tauri config not found at $releaseConfig"
        }
        if (-not $env:TAURI_SIGNING_PRIVATE_KEY) {
            throw "TAURI_SIGNING_PRIVATE_KEY is required for channel '$BuildChannel'"
        }
        Step-Exec "Tauri build ($BuildChannel, updater signed)" { npm exec -- tauri build --config "$releaseConfig" }
    }
}

function Test-SignToolAvailable {
    return (Test-Command signtool) -or (Test-Path "C:\Program Files (x86)\Windows Kits\10\bin\10.0.22621.0\x64\signtool.exe")
}

# ---------------------------------------------------------------------------
# Source truth
# ---------------------------------------------------------------------------
Set-Location "$PSScriptRoot\.."
$repoRoot = Get-Location

$commit = git rev-parse HEAD
$short = git rev-parse --short HEAD
$branch = git branch --show-current
$dirty = Get-IsDirty
$hasTag = $null -ne (git tag --points-at HEAD)
$timestamp = [System.DateTime]::UtcNow.ToString("yyyy-MM-ddTHH:mm:ssZ")
$packageJson = Get-Content "package.json" | ConvertFrom-Json
$version = $packageJson.version

Write-Host "Building Sentinel $version (channel=$Channel, commit=$commit, branch=$branch, dirty=$dirty, tag=$hasTag)" -ForegroundColor Cyan

# ---------------------------------------------------------------------------
# Prechecks
# ---------------------------------------------------------------------------
if ($dirty) {
    if ($policy.requireClean -and -not $AllowDirty) {
        throw "Working tree is dirty and channel '$Channel' requires a clean tree. Commit or use -AllowDirty for development."
    }
    if (-not $policy.dirty -and $AllowDirty) {
        Write-Warning "Working tree is dirty but -AllowDirty was used. This build is for development only."
    }
}

if ($policy.tag -and -not $hasTag) {
    throw "Channel '$Channel' requires a git tag on HEAD."
}

if ($policy.updater -and [string]::IsNullOrWhiteSpace($env:TAURI_SIGNING_PRIVATE_KEY)) {
    throw "Channel '$Channel' requires TAURI_SIGNING_PRIVATE_KEY."
}

if ($policy.authenticode -and -not (Test-SignToolAvailable)) {
    throw "Channel '$Channel' requires Authenticode. signtool.exe was not found."
}

Write-Host "Prechecks passed for channel '$Channel'." -ForegroundColor Green

# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------
$env:SENTINEL_ENABLE_ACL = "0"
$env:SENTINEL_ENABLE_FLEET_STARTUP = "0"
$env:SENTINEL_JWT_SECRET = "build-jwt-secret-not-for-production"

$dirtyTag = if ($dirty) { "+dirty.$short" } else { "" }
$buildId = "$Channel-$((Get-Date -Format 'yyyyMMdd'))-$short$dirtyTag"

# ---------------------------------------------------------------------------
# Clean
# ---------------------------------------------------------------------------
Remove-Tree "$repoRoot\dist"
Remove-Tree "$repoRoot\sidecar\dist"
Remove-Tree "$repoRoot\sidecar\build"
Remove-Tree "$repoRoot\src-tauri\target\release\bundle"
Remove-Tree $OutputDir
New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null

# ---------------------------------------------------------------------------
# Frontend
# ---------------------------------------------------------------------------
Step-Exec "npm ci" { npm ci }
Step-Exec "frontend build" { npm run build }

if (-not (Test-Path "$repoRoot\dist\index.html")) {
    throw "Frontend build did not produce dist/index.html"
}

# ---------------------------------------------------------------------------
# Sidecar
# ---------------------------------------------------------------------------
Step-Exec "uv sync" { python -m uv sync --frozen }
Step-Exec "sidecar PyInstaller" { & { Set-Location sidecar; python -m uv run pyinstaller sidecar.spec --noconfirm } }

$sidecarCanonical = Get-CanonicalPath "sidecar\dist\sidecar.exe"
if (-not (Test-Path $sidecarCanonical)) {
    throw "PyInstaller did not produce $sidecarCanonical"
}

$sidecarHash = (Get-FileHash -Path $sidecarCanonical -Algorithm SHA256).Hash
Write-Host "Sidecar canonical: $sidecarCanonical" -ForegroundColor Green
Write-Host "Sidecar SHA-256:   $sidecarHash" -ForegroundColor Green

Step-Exec "sidecar smoke" { & { Set-Location $repoRoot; .\scripts\smoke-sidecar.ps1 -SidecarExe $sidecarCanonical } }

# ---------------------------------------------------------------------------
# Rust gates
# ---------------------------------------------------------------------------
if (-not $SkipTests) {
    Step-Exec "Rust tests" { cargo test --locked --manifest-path src-tauri\Cargo.toml }
    Step-Exec "Rust clippy" { cargo clippy --locked --manifest-path src-tauri\Cargo.toml -- -D warnings }
    Step-Exec "Rust fmt check" { cargo fmt --manifest-path src-tauri\Cargo.toml -- --check }
}

# ---------------------------------------------------------------------------
# Authenticode sidecar (external-alpha / stable)
# ---------------------------------------------------------------------------
if ($policy.authenticode) {
    $certThumb = $env:SENTINEL_AUTHENTICODE_THUMBPRINT
    $timestampUrl = $env:SENTINEL_TIMESTAMP_URL
    if (-not $certThumb) { throw "SENTINEL_AUTHENTICODE_THUMBPRINT is required for Authenticode." }
    if (-not $timestampUrl) { throw "SENTINEL_TIMESTAMP_URL is required for Authenticode." }
    Step-Exec "Authenticode sidecar" {
        signtool sign /sha1 $certThumb /tr $timestampUrl /td sha256 /fd sha256 /a $sidecarCanonical
    }
    $sig = Get-AuthenticodeSignature $sidecarCanonical
    if ($sig.Status -ne "Valid") {
        throw "sidecar.exe Authenticode status is $($sig.Status)"
    }
}

# ---------------------------------------------------------------------------
# Tauri bundle
# ---------------------------------------------------------------------------
Invoke-TauriBuild -BuildChannel $Channel

# ---------------------------------------------------------------------------
# Extract and verify bundled sidecar hash
# ---------------------------------------------------------------------------
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

# ---------------------------------------------------------------------------
# Authenticode sentinel (external-alpha / stable)
# ---------------------------------------------------------------------------
$sentinelExe = "$repoRoot\src-tauri\target\release\sentinel.exe"
if ($policy.authenticode) {
    if (Test-Path $sentinelExe) {
        Step-Exec "Authenticode sentinel" {
            signtool sign /sha1 $env:SENTINEL_AUTHENTICODE_THUMBPRINT /tr $env:SENTINEL_TIMESTAMP_URL /td sha256 /fd sha256 /a $sentinelExe
        }
        $sig = Get-AuthenticodeSignature $sentinelExe
        if ($sig.Status -ne "Valid") { throw "sentinel.exe Authenticode status is $($sig.Status)" }
    }
    $bundleFiles = Get-ChildItem -Path "$repoRoot\src-tauri\target\release\bundle" -Recurse -File |
    Where-Object { $_.Extension -in ".exe", ".msi" }
    foreach ($f in $bundleFiles) {
        Step-Exec "Authenticode installer $($f.Name)" {
            signtool sign /sha1 $env:SENTINEL_AUTHENTICODE_THUMBPRINT /tr $env:SENTINEL_TIMESTAMP_URL /td sha256 /fd sha256 /a $f.FullName
        }
        $sig = Get-AuthenticodeSignature $f.FullName
        if ($sig.Status -ne "Valid") { throw "$($f.Name) Authenticode status is $($sig.Status)" }
    }
}

# ---------------------------------------------------------------------------
# Collect artifact hashes
# ---------------------------------------------------------------------------
$manifest = @{
    product           = "Sentinel"
    version           = $version
    channel           = $Channel
    build_id          = $buildId
    commit            = $commit
    commit_short      = $short
    branch            = $branch
    dirty             = $dirty
    tag               = $hasTag
    timestamp_utc     = $timestamp
    platform          = "windows"
    arch              = "x86_64"
    python            = (& python --version).ToString().Replace("Python ", "")
    node              = (node --version).TrimStart("v")
    rust              = (rustc --version).Split(" ")[1]
    sidecar_canonical = $sidecarCanonical
    sidecar_sha256    = $sidecarHash
    updater_enabled   = $policy.updater
    tauri_signed      = $policy.tauriSign
    authenticode      = $policy.authenticode
    frontend_dist     = (Get-CanonicalPath "dist")
    artifacts         = @()
}

$bundleFiles = Get-ChildItem -Path "$repoRoot\src-tauri\target\release\bundle" -Recurse -File -ErrorAction SilentlyContinue |
Where-Object { $_.Extension -in ".exe", ".msi" }
foreach ($f in $bundleFiles) {
    $manifest.artifacts += @{
        name   = $f.Name
        path   = $f.FullName
        sha256 = (Get-FileHash -Path $f.FullName -Algorithm SHA256).Hash
        size   = $f.Length
    }
}

$manifestPath = Join-Path $OutputDir "manifest.json"
$manifest | ConvertTo-Json -Depth 4 | Set-Content -Path $manifestPath
Write-Host "`nManifest: $manifestPath" -ForegroundColor Green

# Copy artifacts to channel output directory
$bundleFiles | ForEach-Object {
    Copy-Item -Path $_.FullName -Destination (Join-Path $OutputDir $_.Name)
}

# SHA256SUMS.txt
$sums = $manifest.artifacts | ForEach-Object { "$($_.sha256)  $($_.name)" }
$sums | Set-Content -Path (Join-Path $OutputDir "SHA256SUMS.txt")

# ---------------------------------------------------------------------------
# Postchecks
# ---------------------------------------------------------------------------
if (-not $hashMatch) {
    throw "Postcheck failed: bundled sidecar hash does not match canonical."
}

foreach ($a in $manifest.artifacts) {
    if (-not (Test-Path $a.path)) {
        throw "Postcheck failed: artifact $($a.name) missing at $($a.path)"
    }
}

if ($policy.authenticode) {
    foreach ($a in $manifest.artifacts) {
        $sig = Get-AuthenticodeSignature $a.path
        if ($sig.Status -ne "Valid") {
            throw "Postcheck failed: $($a.name) Authenticode status is $($sig.Status)"
        }
    }
}

Write-Host "`nBUILD SUCCESS: $buildId" -ForegroundColor Green
Write-Host "Artifacts: $OutputDir" -ForegroundColor Green
