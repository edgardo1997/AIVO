#requires -Version 5.1
<#
.SYNOPSIS
  Lifecycle smoke tests for the compiled Sentinel Alpha.
.DESCRIPTION
  Installs the NSIS bundle to a temp location, starts sentinel.exe, captures
  the process tree (sentinel, sidecar, WebView2), verifies health, kills the
  sidecar by PID, and verifies that a normal close leaves no owned processes
  or WebView2 orphans behind.
#>
param(
    [string]$Installer = "$PSScriptRoot\..\src-tauri\target\release\bundle\nsis\Sentinel_0.1.0-alpha.1_x64-setup.exe"
)

$ErrorActionPreference = "Stop"

function Get-ProcessTreeInfo {
    $procs = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
    Select-Object ProcessId, ParentProcessId, Name, ExecutablePath, CommandLine, CreationDate
    return $procs
}

function Find-SentinelChildren($sentinelPid) {
    $procs = Get-ProcessTreeInfo
    $children = @($procs | Where-Object { $_.ParentProcessId -eq $sentinelPid })
    # Recursively gather descendants up to 3 levels.
    $level = $children
    for ($i = 0; $i -lt 2; $i++) {
        $pids = $level | ForEach-Object { $_.ProcessId }
        $next = @($procs | Where-Object { $_.ParentProcessId -in $pids })
        $children += $next
        $level = $next
    }
    return $children | Sort-Object ProcessId -Unique
}

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
    throw "Sidecar did not become healthy in $timeoutSec seconds"
}

$report = [ordered]@{
    started   = [System.DateTime]::UtcNow.ToString("o")
    installer = $Installer
    steps     = @()
}

$installDir = Join-Path $env:TEMP "sentinel-lifecycle"
Remove-Item -Recurse -Force $installDir -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Path $installDir | Out-Null

$report.steps += @{ name = "install"; status = "running" }
$proc = Start-Process -FilePath $Installer -ArgumentList "/S", "/D=$installDir" -PassThru -Wait
if ($proc.ExitCode -ne 0) { throw "Installer failed" }
$report.steps[-1].status = "ok"

$exe = Join-Path $installDir "sentinel.exe"
if (-not (Test-Path $exe)) { throw "sentinel.exe not found" }

# Baseline WebView2 PIDs
$report.steps += @{ name = "baseline_webview2"; status = "running" }
$baselineWebview2 = (Get-ProcessTreeInfo | Where-Object { $_.Name -eq "msedgewebview2.exe" }).ProcessId
$report.steps[-1].status = "ok"; $report.steps[-1].count = $baselineWebview2.Count

$report.steps += @{ name = "start_sentinel"; status = "running" }
$app = Start-Process -FilePath $exe -WorkingDirectory $installDir -PassThru
Start-Sleep -Seconds 10
$report.steps[-1].sentinel_pid = $app.Id; $report.steps[-1].status = "ok"

$report.steps += @{ name = "wait_sidecar"; status = "running" }
$children = Find-SentinelChildren $app.Id
$sidecar = $children | Where-Object { $_.Name -ieq "sidecar.exe" } | Select-Object -First 1
if (-not $sidecar) {
    # sidecar may run without a PPID link because of Windows intermediate process; fall back to port owner
    Start-Sleep -Seconds 5
    $conn = Get-NetTCPConnection -LocalPort 8765 -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($conn) { $sidecar = Get-Process -Id $conn.OwningProcess -ErrorAction SilentlyContinue | Select-Object @{N = "ProcessId"; E = { $_.Id } }, @{N = "Name"; E = { $_.Name } }, @{N = "ExecutablePath"; E = { $_.Path } } }
}
if (-not $sidecar) { throw "Sidecar process not found" }
$report.steps[-1].sidecar_pid = $sidecar.ProcessId; $report.steps[-1].status = "ok"

$report.steps += @{ name = "health"; status = "running" }
$health = Wait-Health 8765 90
$report.steps[-1].health = $health | ConvertTo-Json -Compress; $report.steps[-1].status = "ok"

# WebView2 after start
$report.steps += @{ name = "webview2_after_start"; status = "running" }
$afterWebview2 = (Get-ProcessTreeInfo | Where-Object { $_.Name -eq "msedgewebview2.exe" }).ProcessId
$ourWebview2 = $afterWebview2 | Where-Object { $_ -notin $baselineWebview2 }
$report.steps[-1].count = $ourWebview2.Count; $report.steps[-1].pids = @($ourWebview2); $report.steps[-1].status = "ok"

# Crash sidecar
$report.steps += @{ name = "kill_sidecar"; status = "running" }
$sidecarProc = Get-Process -Id $sidecar.ProcessId -ErrorAction SilentlyContinue
if ($sidecarProc) {
    $sidecarProc.Kill()
    $sidecarProc.WaitForExit(5000) | Out-Null
}
Start-Sleep -Seconds 3
$report.steps[-1].status = "ok"

$report.steps += @{ name = "sentinel_alive_after_sidecar_death"; status = "running" }
$alive = Get-Process -Id $app.Id -ErrorAction SilentlyContinue
if (-not $alive) { throw "Sentinel died after sidecar crash" }
$report.steps[-1].alive = $true; $report.steps[-1].status = "ok"

$report.steps += @{ name = "health_after_sidecar_death"; status = "running" }
try {
    Invoke-RestMethod -Uri "http://127.0.0.1:8765/api/health" -TimeoutSec 3 | Out-Null
    $report.steps[-1].reachable = $true
}
catch {
    $report.steps[-1].reachable = $false
}
$report.steps[-1].status = "ok"

# Normal close (request WM_CLOSE, then Kill if the process does not exit)
$report.steps += @{ name = "close_sentinel"; status = "running" }
$closed = $app.CloseMainWindow()
if (-not $closed) {
    $report.steps[-1].close_main_window = $false
}
$app.WaitForExit(8000) | Out-Null
if (-not $app.HasExited) {
    $report.steps[-1].kill_fallback = $true
    $app.Kill()
    $app.WaitForExit(5000) | Out-Null
}
Start-Sleep -Seconds 3
$report.steps[-1].status = "ok"

# Track owned PIDs for cleanup verification
$ownedSidecarPids = @($sidecar.ProcessId)

# Verify cleanup
$report.steps += @{ name = "verify_cleanup"; status = "running" }
$leftoverSentinel = Get-Process -Id $app.Id -ErrorAction SilentlyContinue
$leftoverSidecars = Get-Process -Name sidecar -ErrorAction SilentlyContinue | Where-Object { $_.Id -in $ownedSidecarPids }
$finalWebview2 = (Get-ProcessTreeInfo | Where-Object { $_.Name -eq "msedgewebview2.exe" }).ProcessId
$orphanWebview2 = $ourWebview2 | Where-Object { $_ -in $finalWebview2 }
$report.steps[-1].sentinel_leftover = @($leftoverSentinel | ForEach-Object { $_.Id })
$report.steps[-1].sidecar_leftover = @($leftoverSidecars | ForEach-Object { $_.Id })
$report.steps[-1].webview2_orphans = @($orphanWebview2)
$report.steps[-1].status = "ok"

# Cleanup install dir
Remove-Item -Recurse -Force $installDir -ErrorAction SilentlyContinue

$report.ended = [System.DateTime]::UtcNow.ToString("o")
$reportPath = Join-Path $env:TEMP "sentinel-lifecycle-report.json"
$report | ConvertTo-Json -Depth 5 | Set-Content -Path $reportPath

Write-Host "`nLifecycle smoke report: $reportPath" -ForegroundColor Cyan
Write-Host ($report | ConvertTo-Json -Depth 3) -ForegroundColor Cyan

$hasOrphans = ($report.steps[-1].sentinel_leftover.Count -gt 0) -or ($report.steps[-1].sidecar_leftover.Count -gt 0) -or ($report.steps[-1].webview2_orphans.Count -gt 0)
if ($hasOrphans) {
    Write-Host "LIFECYCLE SMOKE FOUND ORPHANS" -ForegroundColor Red
    exit 1
}
Write-Host "LIFECYCLE SMOKE PASSED" -ForegroundColor Green
exit 0
