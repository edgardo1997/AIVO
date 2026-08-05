#requires -Version 5.1
<#
.SYNOPSIS
  Validates the NSIS installer end-to-end: install, start, verify, uninstall.
.DESCRIPTION
  Installs the official NSIS bundle to a temp location, starts Sentinel,
  verifies sidecar hash, checks health, runs uninstaller and inspects residuals.
#>
param(
    [string]$Installer = "$PSScriptRoot\..\src-tauri\target\release\bundle\nsis\Sentinel_0.1.0-alpha.1_x64-setup.exe",
    [string]$CanonicalSidecar = "$PSScriptRoot\..\sidecar\dist\sidecar.exe"
)

$ErrorActionPreference = "Stop"

$installDir = "C:\Users\$env:USERNAME\AppData\Local\SentinelSmoke"
$uninstaller = Join-Path $installDir "uninstall.exe"
$manifestPath = Join-Path $env:TEMP "installer-smoke-report.json"

$report = [ordered]@{
    installer         = $Installer
    canonical_sidecar = $CanonicalSidecar
    install_dir       = $installDir
    started           = [System.DateTime]::UtcNow.ToString("o")
    steps             = @()
}

function Step($name, $action) {
    $report.steps += @{ name = $name; status = "running" }
    try {
        & $action
        $report.steps[-1].status = "ok"
    }
    catch {
        $report.steps[-1].status = "fail"
        $report.steps[-1].error = $_.Exception.Message
        throw
    }
}

function Wait-Health($port, $timeoutSec = 90) {
    $uri = "http://127.0.0.1:$port/api/health"
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    while ($sw.Elapsed.TotalSeconds -lt $timeoutSec) {
        try {
            return Invoke-RestMethod -Uri $uri -TimeoutSec 2 -ErrorAction Stop
        }
        catch { Start-Sleep -Milliseconds 250 }
    }
    throw "Sidecar did not become healthy in $timeoutSec seconds"
}

# Clean any previous attempt
Remove-Item -Recurse -Force $installDir -ErrorAction SilentlyContinue

Step "install" {
    $proc = Start-Process -FilePath $Installer -ArgumentList "/S", "/D=$installDir" -PassThru -Wait
    if ($proc.ExitCode -ne 0) { throw "Installer exit code $($proc.ExitCode)" }
    if (-not (Test-Path (Join-Path $installDir "sentinel.exe"))) { throw "sentinel.exe not installed" }
    if (-not (Test-Path (Join-Path $installDir "sidecar\sidecar.exe"))) { throw "sidecar.exe not installed" }
}

Step "hash_sidecar" {
    $installedSidecar = Join-Path $installDir "sidecar\sidecar.exe"
    $canonical = (Get-FileHash -Path $CanonicalSidecar -Algorithm SHA256).Hash
    $installed = (Get-FileHash -Path $installedSidecar -Algorithm SHA256).Hash
    if ($canonical -ne $installed) { throw "Sidecar hash mismatch: canonical=$canonical installed=$installed" }
    $report.steps[-1].canonical = $canonical
    $report.steps[-1].installed = $installed
}

Step "start" {
    $app = Start-Process -FilePath (Join-Path $installDir "sentinel.exe") -WorkingDirectory $installDir -PassThru
    Start-Sleep -Seconds 10
    $report.steps[-1].sentinel_pid = $app.Id
    # wait for port to appear
    for ($i = 0; $i -lt 30; $i++) {
        try {
            $conn = Get-NetTCPConnection -LocalPort 8765 -ErrorAction Stop | Select-Object -First 1
            if ($conn) { break }
        }
        catch { Start-Sleep -Seconds 1 }
    }
}

Step "health" {
    $health = Wait-Health 8765 90
    $report.steps[-1].health = $health | ConvertTo-Json -Compress
}

Step "close" {
    Get-Process -Name sentinel -ErrorAction SilentlyContinue | Where-Object { $_.Path -like "*$installDir*" } | ForEach-Object { $_.CloseMainWindow() | Out-Null }
    Start-Sleep -Seconds 8
    Get-Process -Name sentinel -ErrorAction SilentlyContinue | Where-Object { $_.Path -like "*$installDir*" } | Stop-Process -Force -ErrorAction SilentlyContinue
    Get-Process -Name sidecar -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 5
}

Step "uninstall" {
    if (-not (Test-Path $uninstaller)) { throw "uninstall.exe not found" }
    $proc = Start-Process -FilePath $uninstaller -ArgumentList "/S" -PassThru -Wait
    if ($proc.ExitCode -ne 0) { throw "Uninstaller exit code $($proc.ExitCode)" }
    # NSIS uninstaller may spawn a child; wait for the install dir to disappear or timeout
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    while ((Test-Path $installDir) -and $sw.Elapsed.TotalSeconds -lt 30) {
        Start-Sleep -Milliseconds 250
    }
    $report.steps[-1].uninstall_waited = $sw.Elapsed.TotalSeconds
}

Step "residuals" {
    $leftover = Test-Path $installDir
    $residualProcesses = @(
        @(Get-Process -Name sentinel -ErrorAction SilentlyContinue | Where-Object { $_.Path -like "*$installDir*" } | ForEach-Object { $_.Id })
        @(Get-Process -Name sidecar -ErrorAction SilentlyContinue | Where-Object { $_.Path -like "*$installDir*" } | ForEach-Object { $_.Id })
    ) | ForEach-Object { $_ } | Where-Object { $_ }
    $report.steps[-1].install_dir_leftover = $leftover
    $report.steps[-1].process_residuals = @($residualProcesses)
    $report.steps[-1].manual_cleanup = $leftover
    if ($leftover -and (-not (Remove-Item -Recurse -Force $installDir -ErrorAction SilentlyContinue))) {
        # do not throw; report the failure
    }
}

$report.ended = [System.DateTime]::UtcNow.ToString("o")
$report | ConvertTo-Json -Depth 4 | Set-Content -Path $manifestPath

$hasResiduals = $report.steps | Where-Object { $_.name -eq "residuals" -and $_.install_dir_leftover }

Write-Host "Installer smoke report: $manifestPath" -ForegroundColor Cyan
Write-Host ($report | ConvertTo-Json -Depth 3) -ForegroundColor Cyan

if ($hasResiduals) {
    Write-Host "INSTALLER SMOKE: UNINSTALLER LEFT RESIDUALS" -ForegroundColor Yellow
    exit 1
}
Write-Host "INSTALLER SMOKE PASSED" -ForegroundColor Green
exit 0
