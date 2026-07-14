param([string]$Executable = "$PSScriptRoot\..\sidecar\dist\sidecar.exe")

$ErrorActionPreference = "Stop"
$resolved = (Resolve-Path -LiteralPath $Executable).Path
$token = -join ((1..64) | ForEach-Object { "0123456789abcdef"[(Get-Random -Maximum 16)] })
$env:SENTINEL_SESSION_TOKEN = $token
$dbPath = Join-Path $env:TEMP "sentinel-release-smoke-$PID.db"
$env:SENTINEL_DB_PATH = $dbPath
$pluginRoot = Join-Path $env:TEMP "sentinel-release-plugins-$PID"
$env:SENTINEL_PLUGIN_DIR = $pluginRoot
$stdout = Join-Path $env:TEMP "sentinel-release-smoke-$PID.out.log"
$stderr = Join-Path $env:TEMP "sentinel-release-smoke-$PID.err.log"
$process = Start-Process -FilePath $resolved -PassThru -WindowStyle Hidden `
  -RedirectStandardOutput $stdout -RedirectStandardError $stderr

function Stop-ProcessTree([int]$ProcessId) {
  $children = Get-CimInstance Win32_Process -Filter "ParentProcessId = $ProcessId" -ErrorAction SilentlyContinue
  foreach ($child in $children) { Stop-ProcessTree -ProcessId $child.ProcessId }
  Stop-Process -Id $ProcessId -Force -ErrorAction SilentlyContinue
}

try {
  $ready = $false
  for ($attempt = 0; $attempt -lt 120; $attempt++) {
    Start-Sleep -Milliseconds 250
    try {
      $headers = @{ Authorization = "Bearer $token" }
      $health = Invoke-RestMethod -Uri "http://127.0.0.1:8765/api/health" -Headers $headers -TimeoutSec 1
      $info = Invoke-RestMethod -Uri "http://127.0.0.1:8765/api/info" -Headers $headers -TimeoutSec 1
      if ($health.status -eq "ok" -and $info.version -eq "1.0.0") { $ready = $true; break }
    } catch {}
  }
  if (-not $ready) {
    $details = @()
    if (Test-Path $stdout) { $details += Get-Content $stdout -Tail 40 }
    if (Test-Path $stderr) { $details += Get-Content $stderr -Tail 40 }
    throw "Packaged sidecar did not pass authenticated health and version checks.`n$($details -join "`n")"
  }
  $pluginId = "release_smoke_$PID"
  $executeUri = "http://127.0.0.1:8765/v1/execute"
  $createBody = @{ tool_id = "plugins.create"; params = @{ name = $pluginId; template = "minimal" } } | ConvertTo-Json -Depth 4
  $loadBody = @{ tool_id = "plugins.load"; params = @{ plugin_id = $pluginId } } | ConvertTo-Json -Depth 4
  $unloadBody = @{ tool_id = "plugins.unload"; params = @{ plugin_id = $pluginId } } | ConvertTo-Json -Depth 4
  $created = Invoke-RestMethod -Uri $executeUri -Method Post -Headers $headers -ContentType "application/json" -Body $createBody
  $loaded = Invoke-RestMethod -Uri $executeUri -Method Post -Headers $headers -ContentType "application/json" -Body $loadBody
  if (-not $created.success -or -not $loaded.success -or -not $loaded.data.isolated) {
    throw "Packaged external plugin did not load in an isolated process"
  }
  Invoke-RestMethod -Uri $executeUri -Method Post -Headers $headers -ContentType "application/json" -Body $unloadBody | Out-Null
  Write-Output "Release smoke test passed: Sentinel $($info.version)"
} finally {
  Stop-ProcessTree -ProcessId $process.Id
  Remove-Item -LiteralPath $stdout, $stderr -Force -ErrorAction SilentlyContinue
  Remove-Item -LiteralPath $pluginRoot -Recurse -Force -ErrorAction SilentlyContinue
  Remove-Item -LiteralPath $dbPath, "$dbPath-wal", "$dbPath-shm" -Force -ErrorAction SilentlyContinue
}
