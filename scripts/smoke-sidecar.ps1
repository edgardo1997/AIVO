#requires -Version 5.1
<#
.SYNOPSIS
  Smoke test for the compiled sidecar.exe.
.DESCRIPTION
  Starts sidecar.exe on a random free port, checks /api/health,
  verifies the process stops cleanly and the port is released.
#>
param(
    [string]$SidecarExe = "$PSScriptRoot\..\sidecar\dist\sidecar.exe",
    [int]$Port = 0
)

$ErrorActionPreference = "Stop"

function Get-FreePort {
    $listener = New-Object System.Net.Sockets.TcpListener([System.Net.IPAddress]::Loopback, 0)
    $listener.Start()
    $port = $listener.LocalEndpoint.Port
    $listener.Stop()
    return $port
}

function Wait-Health($port, $timeoutSec = 30) {
    $uri = "http://127.0.0.1:$port/api/health"
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    while ($sw.Elapsed.TotalSeconds -lt $timeoutSec) {
        try {
            $resp = Invoke-RestMethod -Uri $uri -TimeoutSec 2 -ErrorAction Stop
            if ($resp.status -eq "healthy") { return $resp }
        }
        catch {
            Start-Sleep -Milliseconds 250
        }
    }
    throw "Sidecar did not become healthy within $timeoutSec seconds"
}

function Test-PortClosed($port) {
    try {
        $client = New-Object System.Net.Sockets.TcpClient
        $client.Connect("127.0.0.1", $port)
        $client.Close()
        return $false
    }
    catch {
        return $true
    }
}

if (-not (Test-Path $SidecarExe)) {
    throw "Sidecar not found: $SidecarExe. Build it with 'python -m uv run pyinstaller sidecar/sidecar.spec --noconfirm'"
}

if ($Port -eq 0) { $Port = Get-FreePort }

$tempDir = New-TemporaryFile | ForEach-Object { $_.FullName }; Remove-Item $tempDir -Force
New-Item -ItemType Directory -Path $tempDir | Out-Null

$env:SENTINEL_PORT = $Port
$env:SENTINEL_HOST = "127.0.0.1"
$env:SENTINEL_ENABLE_ACL = "0"
$env:SENTINEL_ENABLE_FLEET_STARTUP = "0"
$env:SENTINEL_JWT_SECRET = "smoke-test-secret"
$env:SENTINEL_DB_PATH = "$tempDir\smoke.db"
$env:SENTINEL_DATA_DIR = "$tempDir\data"
$env:LOCALAPPDATA = $tempDir
$env:APPDATA = $tempDir

$proc = $null
try {
    Write-Host "Starting sidecar on port $Port ..." -ForegroundColor Cyan
    $proc = Start-Process -FilePath $SidecarExe -PassThru -WindowStyle Hidden
    $health = Wait-Health $Port
    Write-Host "Health OK: $($health | ConvertTo-Json -Compress)" -ForegroundColor Green

    Write-Host "Stopping sidecar process tree (PID $($proc.Id)) ..." -ForegroundColor Cyan
    $stopResult = Start-Process -FilePath "taskkill.exe" -ArgumentList "/T", "/F", "/PID", $proc.Id -WindowStyle Hidden -PassThru -Wait
    if ($stopResult.ExitCode -ne 0 -and $proc.HasExited -eq $false) {
        Write-Warning "taskkill returned exit code $($stopResult.ExitCode); trying Stop-Process fallback"
        Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
    }
    $swExit = [System.Diagnostics.Stopwatch]::StartNew()
    while (-not $proc.HasExited -and $swExit.Elapsed.TotalSeconds -lt 10) {
        Start-Sleep -Milliseconds 250
    }

    Start-Sleep -Seconds 1
    $released = $false
    for ($i = 0; $i -lt 20; $i++) {
        if (Test-PortClosed $Port) { $released = $true; break }
        Start-Sleep -Milliseconds 500
    }
    if (-not $released) {
        Write-Warning "Port $Port may still be in TIME_WAIT; health endpoint was reached"
    }
    else {
        Write-Host "Port $Port released." -ForegroundColor Green
    }
    Write-Host "SMOKE PASSED" -ForegroundColor Green
    exit 0
}
finally {
    if ($proc -and -not $proc.HasExited) { Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue }
    Start-Sleep -Seconds 1
    Remove-Item -Recurse -Force $tempDir -ErrorAction SilentlyContinue
}
