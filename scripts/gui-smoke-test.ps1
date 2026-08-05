#requires -Version 5.1
<#
.SYNOPSIS
  GUI smoke test for the compiled Sentinel Alpha.
.DESCRIPTION
  Installs the NSIS bundle to a temporary location, starts sentinel.exe,
  waits for the sidecar to become healthy, collects logs and exits.
  This does not validate visual UX; it only verifies startup, sidecar
  launch and process lifecycle.
#>
param(
    [string]$Installer = "$PSScriptRoot\..\src-tauri\target\release\bundle\nsis\Sentinel_0.1.0-alpha.1_x64-setup.exe"
)

$ErrorActionPreference = "Stop"

function Wait-Health($port, $timeoutSec = 90) {
    $uri = "http://127.0.0.1:$port/api/health"
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    while ($sw.Elapsed.TotalSeconds -lt $timeoutSec) {
        try {
            $resp = Invoke-RestMethod -Uri $uri -TimeoutSec 2 -ErrorAction Stop
            if ($resp.status -eq "healthy") { return $resp }
        }
        catch { Start-Sleep -Milliseconds 250 }
    }
    throw "Sidecar did not become healthy"
}

$installDir = Join-Path $env:TEMP "sentinel-gui-smoke"
Remove-Item -Recurse -Force $installDir -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Path $installDir | Out-Null

$proc = Start-Process -FilePath $Installer -ArgumentList "/S", "/D=$installDir" -PassThru -Wait
if ($proc.ExitCode -ne 0) { throw "Installer exited $($proc.ExitCode)" }

$exe = Join-Path $installDir "sentinel.exe"
if (-not (Test-Path $exe)) { throw "sentinel.exe not found at $exe" }

# Collect Sentinel logs after run
$logDir = Join-Path $env:LOCALAPPDATA "com.aivo.desktop"

Write-Host "Starting sentinel.exe ..." -ForegroundColor Cyan
$app = Start-Process -FilePath $exe -WorkingDirectory $installDir -PassThru

try {
    Start-Sleep -Seconds 10
    $sentinelProcess = Get-Process -Id $app.Id -ErrorAction SilentlyContinue
    $sidecarProcesses = Get-Process sidecar -ErrorAction SilentlyContinue

    Write-Host "Sentinel PID: $($app.Id)" -ForegroundColor Cyan
    if ($sidecarProcesses) {
        $sidecarPids = $sidecarProcesses | ForEach-Object { $_.Id }
        Write-Host "Sidecar PIDs: $($sidecarPids -join ', ')" -ForegroundColor Cyan
    }
    else {
        Write-Warning "No sidecar process found."
    }

    $health = Wait-Health 8765
    Write-Host "Health OK: $($health | ConvertTo-Json -Compress)" -ForegroundColor Green
    $smokePassed = $true
}
catch {
    Write-Warning $_.Exception.Message
    $smokePassed = $false
}
finally {
    Stop-Process -Id $app.Id -Force -ErrorAction SilentlyContinue
    Get-Process sidecar -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
    Remove-Item -Recurse -Force $installDir -ErrorAction SilentlyContinue
}

# Show last lines of log if present
if (Test-Path $logDir) {
    $logFiles = Get-ChildItem -Path $logDir -Filter "*.log" -Recurse -ErrorAction SilentlyContinue | Select-Object -First 5
    foreach ($lf in $logFiles) {
        Write-Host "`nLog: $($lf.FullName)" -ForegroundColor Cyan
        Get-Content $lf.FullName -Tail 30 | ForEach-Object { Write-Host $_ }
    }
}

if ($smokePassed) {
    Write-Host "`nGUI SMOKE PASSED" -ForegroundColor Green
    exit 0
}
else {
    Write-Host "`nGUI SMOKE FAILED" -ForegroundColor Red
    exit 1
}
