#requires -Version 5.1
<#
.SYNOPSIS
  Smoke test for Sentinel single instance behavior.
.DESCRIPTION
  Installs, starts Sentinel, then attempts to start a second instance.
  Records whether one or two processes exist and whether sidecar port 8765
  is shared or duplicated.
#>
param(
    [string]$Installer = "$PSScriptRoot\..\src-tauri\target\release\bundle\nsis\Sentinel_0.1.0-alpha.1_x64-setup.exe"
)

$ErrorActionPreference = "Stop"

$installDir = Join-Path $env:TEMP "sentinel-two-instance"
Remove-Item -Recurse -Force $installDir -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Path $installDir | Out-Null

$proc = Start-Process -FilePath $Installer -ArgumentList "/S", "/D=$installDir" -PassThru -Wait
if ($proc.ExitCode -ne 0) { throw "Installer failed" }

$exe = Join-Path $installDir "sentinel.exe"

$first = Start-Process -FilePath $exe -WorkingDirectory $installDir -PassThru
Start-Sleep -Seconds 12

$before = Get-Process -Name sentinel -ErrorAction SilentlyContinue | Where-Object { $_.Path -like "*$installDir*" }
$portOwnerBefore = Get-NetTCPConnection -LocalPort 8765 -ErrorAction SilentlyContinue | Select-Object -First 1

$second = Start-Process -FilePath $exe -WorkingDirectory $installDir -PassThru
Start-Sleep -Seconds 5

$after = Get-Process -Name sentinel -ErrorAction SilentlyContinue | Where-Object { $_.Path -like "*$installDir*" }
$portOwnerAfter = Get-NetTCPConnection -LocalPort 8765 -ErrorAction SilentlyContinue | Select-Object -First 1

$first | Stop-Process -Force
Start-Sleep -Seconds 2
$second | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2

Remove-Item -Recurse -Force $installDir -ErrorAction SilentlyContinue

$report = [ordered]@{
    first_pid = $first.Id
    second_pid = $second.Id
    sentinel_count_before_second = $before.Count
    sentinel_count_after_second = $after.Count
    port_owner_before = if ($portOwnerBefore) { $portOwnerBefore.OwningProcess } else { $null }
    port_owner_after = if ($portOwnerAfter) { $portOwnerAfter.OwningProcess } else { $null }
    single_instance = $after.Count -le $before.Count
}

$reportPath = Join-Path $env:TEMP "sentinel-two-instance-report.json"
$report | ConvertTo-Json | Set-Content -Path $reportPath

Write-Host ($report | ConvertTo-Json) -ForegroundColor Cyan

if ($report.single_instance) {
    Write-Host "TWO-INSTANCE SMOKE PASSED" -ForegroundColor Green
    exit 0
}
Write-Host "TWO-INSTANCE SMOKE FAILED: second instance was allowed" -ForegroundColor Red
exit 1
