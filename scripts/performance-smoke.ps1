#requires -Version 5.1
<#
.SYNOPSIS
  Performance and stability smoke test for Sentinel.
.DESCRIPTION
  Installs the NSIS bundle to a temp location, measures startup, readiness,
  idle RAM/CPU, and performs 3 open/close cycles.
#>
param(
    [string]$Installer = "$PSScriptRoot\..\src-tauri\target\release\bundle\nsis\Sentinel_0.1.0-alpha.1_x64-setup.exe"
)

$ErrorActionPreference = "Stop"

$installDir = "$env:LOCALAPPDATA\SentinelPerf"
$uninstaller = Join-Path $installDir "uninstall.exe"

$report = [ordered]@{
    started = [System.DateTime]::UtcNow.ToString("o")
    install_dir = $installDir
    installer = $Installer
    installed_size_mb = 0
    baseline = @()
    cycles = @()
    idle_samples = @()
}

function Wait-Health($port, $timeoutSec = 90) {
    $uri = "http://127.0.0.1:$port/api/health"
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    while ($sw.Elapsed.TotalSeconds -lt $timeoutSec) {
        try {
            return Invoke-RestMethod -Uri $uri -TimeoutSec 2 -ErrorAction Stop
        } catch { Start-Sleep -Milliseconds 250 }
    }
    throw "Sidecar did not become healthy in $timeoutSec seconds"
}

function Get-SentinelChildren($sentinelPid) {
    $procs = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Select-Object ProcessId, ParentProcessId, Name, ExecutablePath, CommandLine
    $children = @($procs | Where-Object { $_.ParentProcessId -eq $sentinelPid })
    $level = $children
    for ($i = 0; $i -lt 2; $i++) {
        $pids = $level | ForEach-Object { $_.ProcessId }
        $next = @($procs | Where-Object { $_.ParentProcessId -in $pids })
        $children += $next
        $level = $next
    }
    return $children | Sort-Object ProcessId -Unique
}

function Measure-Idle($pids, $seconds, $sampleIntervalSec = 5) {
    $samples = @()
    $cores = (Get-CimInstance Win32_ComputerSystem).NumberOfLogicalProcessors
    $startCpu = @{}
    for ($t = 0; $t -lt $seconds; $t += $sampleIntervalSec) {
        $procs = Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.Id -in $pids }
        $totalWs = ($procs | Measure-Object WorkingSet -Sum).Sum
        $totalPriv = ($procs | Measure-Object PrivateMemorySize -Sum).Sum
        $cpuPct = 0
        $now = [System.DateTime]::UtcNow
        foreach ($p in $procs) {
            $key = $p.Id
            $cpuNow = $p.TotalProcessorTime.TotalSeconds
            if ($startCpu.ContainsKey($key)) {
                $delta = $cpuNow - $startCpu[$key]
                $cpuPct += [math]::Round(($delta / ($sampleIntervalSec * $cores)) * 100, 2)
            }
            $startCpu[$key] = $cpuNow
        }
        $samples += [ordered]@{
            t = $t
            timestamp = $now.ToString("o")
            pids_count = $procs.Count
            working_set_mb = [math]::Round($totalWs / 1MB, 2)
            private_mb = [math]::Round($totalPriv / 1MB, 2)
            cpu_pct = [math]::Round($cpuPct, 2)
        }
        Start-Sleep -Seconds $sampleIntervalSec
    }
    return $samples
}

# Clean and install
Remove-Item -Recurse -Force $installDir -ErrorAction SilentlyContinue
$proc = Start-Process -FilePath $Installer -ArgumentList "/S", "/D=$installDir" -PassThru -Wait
if ($proc.ExitCode -ne 0) { throw "Install failed" }

$report.installed_size_mb = [math]::Round((Get-ChildItem -Recurse $installDir | Measure-Object -Property Length -Sum).Sum / 1MB, 2)

# 3 open/close cycles
for ($i = 1; $i -le 3; $i++) {
    $startAt = [System.DateTime]::UtcNow
    $app = Start-Process -FilePath (Join-Path $installDir "sentinel.exe") -WorkingDirectory $installDir -PassThru
    $processAt = [System.DateTime]::UtcNow
    # Wait for health
    $health = $null
    $readyAt = $null
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    while ($sw.Elapsed.TotalSeconds -lt 90 -and -not $health) {
        try { $health = Wait-Health 8765 2 } catch { }
        if ($health) { $readyAt = [System.DateTime]::UtcNow; break }
        Start-Sleep -Milliseconds 250
    }
    if (-not $health) { throw "Cycle $i did not become healthy" }

    $pids = @($app.Id) + (Get-SentinelChildren $app.Id | ForEach-Object { $_.ProcessId }) | Select-Object -Unique
    if ($i -eq 1) {
        # sample idle for 60s on first cycle
        $report.idle_samples = Measure-Idle $pids 60 5
    }

    $closeStart = [System.DateTime]::UtcNow
    $app.CloseMainWindow() | Out-Null
    Start-Sleep -Seconds 8
    if (-not $app.HasExited) { $app.Kill(); $app.WaitForExit(5000) | Out-Null }
    Get-Process -Name sidecar -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 4
    $closeEnd = [System.DateTime]::UtcNow

    $report.cycles += [ordered]@{
        cycle = $i
        time_to_process_ms = [math]::Round(($processAt - $startAt).TotalMilliseconds)
        time_to_ready_ms = [math]::Round(($readyAt - $startAt).TotalMilliseconds)
        close_ms = [math]::Round(($closeEnd - $closeStart).TotalMilliseconds)
        pids = $pids
    }
}

# Uninstall
try {
    $u = Start-Process -FilePath $uninstaller -ArgumentList "/S" -PassThru -Wait -ErrorAction SilentlyContinue
    if ($u -and $u.ExitCode -ne 0) { throw "Uninstall exit code $($u.ExitCode)" }
} catch { Write-Warning "Uninstall failed: $_" }
Start-Sleep -Seconds 5
Remove-Item -Recurse -Force $installDir -ErrorAction SilentlyContinue
Get-Process -Name sentinel, sidecar -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue

$report.ended = [System.DateTime]::UtcNow.ToString("o")
$reportPath = Join-Path $env:TEMP "sentinel-performance-smoke.json"
$report | ConvertTo-Json -Depth 4 | Set-Content -Path $reportPath

Write-Host "Performance smoke report: $reportPath" -ForegroundColor Cyan
Write-Host ($report | ConvertTo-Json -Depth 3) -ForegroundColor Cyan

$maxReady = ($report.cycles | Measure-Object time_to_ready_ms -Maximum).Maximum
if ($maxReady -gt 120000) {
    Write-Host "PERF SMOKE WARNING: time-to-ready exceeded 120s" -ForegroundColor Yellow
    exit 1
}
Write-Host "PERF SMOKE PASSED" -ForegroundColor Green
exit 0
