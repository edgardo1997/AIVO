#Requires -Version 7.4
<#
.SYNOPSIS
    Verifies that repeated sidecar smoke tests do not leave orphan sidecar processes.
#>

param(
    [string]$SidecarExe = "$PSScriptRoot\..\sidecar\dist\sidecar.exe",
    [int]$Runs = 3
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $SidecarExe)) {
    throw "Sidecar not found: $SidecarExe"
}

function Get-SidecarProcessCount {
    return (Get-Process -Name sidecar -ErrorAction SilentlyContinue | Measure-Object).Count
}

$before = Get-SidecarProcessCount
Write-Host "Sidecar processes before test: $before" -ForegroundColor Cyan

for ($i = 1; $i -le $Runs; $i++) {
    Write-Host ">>> Smoke run $i / $Runs" -ForegroundColor Cyan
    & (Join-Path $PSScriptRoot 'smoke-sidecar.ps1') -SidecarExe $SidecarExe
    if ($LASTEXITCODE -ne 0) { throw "Smoke run $i failed" }
    $mid = Get-SidecarProcessCount
    Write-Host "Sidecar processes after run $i : $mid" -ForegroundColor Cyan
    if ($mid -gt $before) {
        throw "Orphan sidecar processes detected after smoke run $i : $mid (expected $before)"
    }
}

$after = Get-SidecarProcessCount
if ($after -ne $before) {
    throw "Sidecar process count changed: $before -> $after"
}

Write-Host "[PASS] No orphan sidecar processes after $Runs smoke runs." -ForegroundColor Green
exit 0
