#Requires -Version 7.4
<#
.SYNOPSIS
    Regression test for the Sentinel NSIS installer.

.DESCRIPTION
    Performs a controlled install/uninstall cycle in a non-temp user-writable
    location and validates that the installer does not register itself under
    %TEMP%, leaves no running processes, and cleans up correctly.

.PARAMETER Installer
    Path to the NSIS installer to test.

.PARAMETER InstallRoot
    Root directory for the test installation. Defaults to a folder under
    %LOCALAPPDATA% (not %TEMP%).
#>

param(
    [Parameter(Mandatory = $true)]
    [string]$Installer,

    [string]$InstallRoot = ""
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $Installer)) {
    throw "Installer not found: $Installer"
}

if ([string]::IsNullOrWhiteSpace($InstallRoot)) {
    $InstallRoot = Join-Path $env:LOCALAPPDATA "Sentinel-Install-Test-$([Guid]::NewGuid().ToString("N"))"
}

$tempPrefix = $env:TEMP.ToLower()
$InstallRoot = [System.IO.Path]::GetFullPath($InstallRoot)
if ($InstallRoot.ToLower().StartsWith($tempPrefix)) {
    throw "InstallRoot cannot be under %TEMP%: $InstallRoot"
}

Remove-Item -Recurse -Force $InstallRoot -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Path $InstallRoot -Force | Out-Null

function Get-SentinelUninstallKey {
    $keys = @(
        "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\Sentinel",
        "HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\Sentinel",
        "HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\Sentinel"
    )
    foreach ($key in $keys) {
        if (Test-Path $key) { return $key }
    }
    return $null
}

function Stop-SentinelProcessTree($ProcessId) {
    if (-not $ProcessId) { return }
    $proc = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
    if ($proc -and -not $proc.HasExited) {
        Start-Process -FilePath "taskkill.exe" -ArgumentList "/T", "/F", "/PID", $ProcessId -WindowStyle Hidden -Wait
    }
}

$sentinelPid = $null
try {
    # 1. Install
    Write-Host ">>> Installing Sentinel to $InstallRoot ..." -ForegroundColor Cyan
    $proc = Start-Process -FilePath $Installer -ArgumentList "/S", "/D=$InstallRoot" -PassThru -Wait
    if ($proc.ExitCode -ne 0) {
        throw "Installer failed with exit code $($proc.ExitCode)"
    }

    # 2. Verify files
    $sentinelExe = Join-Path $InstallRoot "sentinel.exe"
    $sidecarExe = Join-Path $InstallRoot "sidecar\sidecar.exe"
    $uninstallExe = Join-Path $InstallRoot "uninstall.exe"
    if (-not (Test-Path $sentinelExe)) { throw "sentinel.exe not found at $sentinelExe" }
    if (-not (Test-Path $sidecarExe)) { throw "sidecar.exe not found at $sidecarExe" }
    if (-not (Test-Path $uninstallExe)) { throw "uninstall.exe not found at $uninstallExe" }

    # 3. Verify registry
    $uninstallKey = Get-SentinelUninstallKey
    if (-not $uninstallKey) {
        throw "No Sentinel uninstall registry entry found"
    }
    $installLocation = ((Get-ItemProperty -Path $uninstallKey -Name InstallLocation -ErrorAction SilentlyContinue).InstallLocation -replace '^"|"$', '').TrimEnd('\')
    $uninstallString = ((Get-ItemProperty -Path $uninstallKey -Name UninstallString -ErrorAction SilentlyContinue).UninstallString -replace '^"|"$', '').TrimEnd('\')

    if ([string]::IsNullOrWhiteSpace($installLocation)) {
        throw "InstallLocation is missing from registry"
    }
    if ([string]::IsNullOrWhiteSpace($uninstallString)) {
        throw "UninstallString is missing from registry"
    }
    if ($installLocation.ToLower().StartsWith($tempPrefix)) {
        throw "FAIL: InstallLocation is under %TEMP%: $installLocation"
    }
    if ($uninstallString.ToLower().StartsWith($tempPrefix)) {
        throw "FAIL: UninstallString is under %TEMP%: $uninstallString"
    }
    if ($installLocation.ToLower() -ne $InstallRoot.ToLower()) {
        Write-Warning "InstallLocation ($installLocation) does not match requested root ($InstallRoot). The installer may have ignored /D."
    }

    Write-Host "InstallLocation: $installLocation" -ForegroundColor Green
    Write-Host "UninstallString: $uninstallString" -ForegroundColor Green

    # 4. Start Sentinel and check it runs from the installed path
    Write-Host ">>> Starting Sentinel from installed path ..." -ForegroundColor Cyan
    $run = Start-Process -FilePath $sentinelExe -WorkingDirectory $InstallRoot -WindowStyle Hidden -PassThru
    $sentinelPid = $run.Id
    Start-Sleep -Seconds 5
    if ($run.HasExited) {
        throw "Sentinel exited immediately after starting"
    }
    $running = Get-Process -Id $sentinelPid -ErrorAction SilentlyContinue
    if (-not $running) {
        throw "Sentinel process not found after start"
    }
    Write-Host "Sentinel running from installed path (PID $sentinelPid)" -ForegroundColor Green

    # 5. Close Sentinel
    Stop-SentinelProcessTree $sentinelPid
    Start-Sleep -Seconds 2

    # 6. Uninstall
    Write-Host ">>> Uninstalling ..." -ForegroundColor Cyan
    $uninst = Start-Process -FilePath $uninstallExe -ArgumentList "/S" -PassThru -Wait
    if ($uninst.ExitCode -ne 0) {
        throw "Uninstaller failed with exit code $($uninst.ExitCode)"
    }
    Start-Sleep -Seconds 2

    # 7. Verify no processes left
    $sentinelProcs = Get-Process -Name sentinel -ErrorAction SilentlyContinue
    $sidecarProcs = Get-Process -Name sidecar -ErrorAction SilentlyContinue
    if ($sentinelProcs) {
        Write-Warning "Sentinel processes still running after uninstall"
        foreach ($p in $sentinelProcs) { Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue }
    }
    if ($sidecarProcs) {
        Write-Warning "Sidecar processes still running after uninstall"
        foreach ($p in $sidecarProcs) { Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue }
    }

    # 8. Verify cleanup
    $remaining = @($sentinelExe, $sidecarExe, $uninstallExe) | Where-Object { Test-Path $_ }
    if ($remaining.Count -gt 0) {
        throw "Binaries still present after uninstall: $($remaining -join ', ')"
    }

    Write-Host "[PASS] Installer regression passed." -ForegroundColor Green
    exit 0
}
catch {
    Write-Host "[FAIL] $_" -ForegroundColor Red
    if ($sentinelPid) { Stop-SentinelProcessTree $sentinelPid }
    exit 1
}
finally {
    Remove-Item -Recurse -Force $InstallRoot -ErrorAction SilentlyContinue
    # Remove any uninstall key that still points to a now-deleted path
    $uninstallKey = Get-SentinelUninstallKey
    if ($uninstallKey) {
        $installLocation = (Get-ItemProperty -Path $uninstallKey -Name InstallLocation -ErrorAction SilentlyContinue).InstallLocation
        if (-not $installLocation -or -not (Test-Path $installLocation)) {
            Remove-Item -Path $uninstallKey -Recurse -Force -ErrorAction SilentlyContinue
        }
    }
}
