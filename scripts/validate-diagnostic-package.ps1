#Requires -Version 7.4
<#
.SYNOPSIS
    Valida un paquete de diagnóstico de Sentinel.

.DESCRIPTION
    Comprueba estructura, integridad, hashes, redacción y ausencia de
    datos sensibles o archivos inesperados en un ZIP generado por Sentinel.

.PARAMETER DiagnosticZip
    Ruta al ZIP de diagnóstico.

.PARAMETER ExpectedBuildId
    Build ID que se espera encontrar en el paquete.

.EXAMPLE
    .\scripts\validate-diagnostic-package.ps1 `
        -DiagnosticZip "C:\Temp\Sentinel-Diagnostic-internal-alpha-20260805-000000.zip" `
        -ExpectedBuildId "internal-alpha-20260805-9d5cf43"
#>

param(
    [Parameter(Mandatory = $true)]
    [string]$DiagnosticZip,

    [Parameter(Mandatory = $true)]
    [string]$ExpectedBuildId
)

$ErrorActionPreference = "Stop"

$RequiredFiles = @(
    "summary.json",
    "manifest.json",
    "system.txt",
    "events.jsonl",
    "README.txt",
    "SHA256SUMS.txt",
    "logs/sentinel.log"
)

$ForbiddenValues = @(
    "FAKE_API_KEY_SENTINEL_TEST",
    "FAKE_BEARER_TOKEN_SENTINEL_TEST",
    "FAKE_PASSWORD_SENTINEL_TEST",
    "FAKE_PRIVATE_KEY_SENTINEL_TEST",
    "FAKE_COOKIE_SENTINEL_TEST"
)

$ForbiddenExtensions = @(".key", ".pem", ".pfx", ".p12", ".env")
$ForbiddenPathPatterns = @("/conversations/", "/chat/", "/vault/", "/prompts/")

function Exit-Error([string]$Message) {
    Write-Host "[FAIL] $Message" -ForegroundColor Red
    exit 1
}

Write-Host "Validating: $DiagnosticZip" -ForegroundColor Cyan

if (-not (Test-Path $DiagnosticZip)) {
    Exit-Error "ZIP not found: $DiagnosticZip"
}

$TempDir = Join-Path $env:TEMP ("Sentinel-Diag-Validate-" + [Guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $TempDir -Force | Out-Null

try {
    Expand-Archive -Path $DiagnosticZip -DestinationPath $TempDir -Force

    # 1. Required files
    foreach ($rel in $RequiredFiles) {
        $full = Join-Path $TempDir $rel
        if (-not (Test-Path $full)) {
            Exit-Error "Missing required file: $rel"
        }
    }

    # 2. Manifest JSON validity
    $manifestPath = Join-Path $TempDir "manifest.json"
    $manifest = Get-Content -Path $manifestPath -Raw | ConvertFrom-Json
    if (-not $manifest.files -or $manifest.files.Count -eq 0) {
        Exit-Error "manifest.json does not list any files"
    }

    # 3. SHA-256 hashes
    $shaFile = Join-Path $TempDir "SHA256SUMS.txt"
    $shaLines = Get-Content -Path $shaFile
    foreach ($line in $shaLines) {
        if ([string]::IsNullOrWhiteSpace($line)) { continue }
        $parts = $line -split "  "
        if ($parts.Count -ne 2) {
            Exit-Error "Malformed SHA256SUMS line: $line"
        }
        $expectedHash = $parts[0].Trim().ToLower()
        $relPath = $parts[1].Trim()
        $filePath = Join-Path $TempDir $relPath
        if (-not (Test-Path $filePath)) {
            Exit-Error "SHA256SUMS references missing file: $relPath"
        }
        $actualHash = (Get-FileHash -Path $filePath -Algorithm SHA256).Hash.ToLower()
        if ($expectedHash -ne $actualHash) {
            Exit-Error "Hash mismatch for $relPath (expected $expectedHash, got $actualHash)"
        }
    }

    # 4. Build ID and version consistency
    $summaryPath = Join-Path $TempDir "summary.json"
    $summary = Get-Content -Path $summaryPath -Raw | ConvertFrom-Json
    if ($summary.build_id -ne $ExpectedBuildId) {
        Exit-Error ("Build ID mismatch: expected $ExpectedBuildId, got " + $summary.build_id)
    }
    if ([string]::IsNullOrWhiteSpace($summary.product_version)) {
        Exit-Error "product_version is missing in summary.json"
    }
    if ([string]::IsNullOrWhiteSpace($summary.channel)) {
        Exit-Error "channel is missing in summary.json"
    }
    if ([string]::IsNullOrWhiteSpace($summary.os)) {
        Exit-Error "os is missing in summary.json"
    }

    # 5. README clarity
    $readmePath = Join-Path $TempDir "README.txt"
    $readme = Get-Content -Path $readmePath -Raw
    if ($readme -notmatch "redacted") {
        Write-Warning "README.txt does not mention redaction"
    }

    # 6. No forbidden extensions or paths
    $allFiles = Get-ChildItem -Path $TempDir -Recurse -File
    foreach ($f in $allFiles) {
        $ext = $f.Extension.ToLower()
        if ($ForbiddenExtensions -contains $ext) {
            Exit-Error "Unexpected sensitive extension found: $($f.FullName)"
        }
        $rel = $f.FullName.Substring($TempDir.Length).Replace("\", "/").ToLower()
        foreach ($pat in $ForbiddenPathPatterns) {
            if ($rel -like "*$pat*") {
                Exit-Error "Unexpected personal content path: $rel"
            }
        }
    }

    # 7. No forbidden secret values
    $foundForbidden = @()
    $textContent = $allFiles | ForEach-Object { Get-Content -Path $_.FullName -Raw -ErrorAction SilentlyContinue } | Join-String
    foreach ($secret in $ForbiddenValues) {
        if ($textContent -match [regex]::Escape($secret)) {
            $foundForbidden += $secret
        }
    }
    if ($foundForbidden.Count -gt 0) {
        Exit-Error ("Forbidden fake secrets found in diagnostic package: " + ($foundForbidden -join ", "))
    }

    # 8. Log redaction smoke
    $logFile = Join-Path $TempDir "logs/sentinel.log"
    if (Test-Path $logFile) {
        $logText = Get-Content -Path $logFile -Raw
        if ($logText -match "api_key\s*=\s*[^\s\[\]]{4,}") {
            Write-Warning "Log may contain unredacted api_key value"
        }
        if ($logText -match "bearer\s+[A-Za-z0-9_\-]{8,}", "IgnoreCase") {
            Write-Warning "Log may contain unredacted bearer token"
        }
    }

    Write-Host "[PASS] Diagnostic package is valid and does not contain fake secrets." -ForegroundColor Green
    exit 0
}
finally {
    Remove-Item -Path $TempDir -Recurse -Force -ErrorAction SilentlyContinue
}
