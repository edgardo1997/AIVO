#requires -Version 5.1
<#
.SYNOPSIS
  Prepara un entorno limpio para pruebas E2E de Sentinel.
.DESCRIPTION
  Crea un perfil temporal bajo %TEMP%\SentinelE2E con Downloads, Documents
  y PDFs de prueba con fechas controladas. Registra metadatos y hashes.
#>
param(
    [string]$Root = "$env:TEMP\SentinelE2E",
    [switch]$Clean
)

$ErrorActionPreference = "Stop"

if ($Clean -and (Test-Path $Root)) {
    Remove-Item -Recurse -Force $Root
}

$folders = @(
    "$Root\Downloads",
    "$Root\Documents",
    "$Root\Reviewed",
    "$Root\SentinelData"
)
$folders | ForEach-Object { New-Item -ItemType Directory -Path $_ -Force | Out-Null }

# Create PDF-like files (minimal headers so file command recognizes them as PDF)
$pdfs = @(
    @{ Name = "invoice_old.pdf"; DaysAgo = 7; Size = 12KB }
    @{ Name = "report_middle.pdf"; DaysAgo = 2; Size = 24KB }
    @{ Name = "report_latest.pdf"; DaysAgo = 0; Size = 36KB }
)

function New-PdfLikeFile($path, $size) {
    $header = "%PDF-1.4`n1 0 obj`n<< /Type /Catalog /Pages 2 0 R >>`nendobj`n2 0 obj`n<< /Type /Pages /Kids [] /Count 0 >>`nendobj`nxref`n0 3`n0000000000 65535 f `n0000000009 00000 n `n0000000058 00000 n `ntrailer`n<< /Size 3 /Root 1 0 R >>`nstartxref`n109`n%%EOF`n"
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($header)
    $fs = [System.IO.File]::Create($path)
    try {
        $fs.Write($bytes, 0, $bytes.Length)
        $remaining = $size - $bytes.Length
        if ($remaining -gt 0) {
            $padding = New-Object byte[] $remaining
            (New-Object System.Random).NextBytes($padding)
            $fs.Write($padding, 0, $padding.Length)
        }
    }
    finally {
        $fs.Close()
    }
}

$manifest = @{
    root    = $Root
    created = [System.DateTime]::UtcNow.ToString("o")
    files   = @()
}

foreach ($pdf in $pdfs) {
    $path = Join-Path "$Root\Downloads" $pdf.Name
    New-PdfLikeFile -path $path -size $pdf.Size
    $item = Get-Item $path
    $item.LastWriteTime = [System.DateTime]::Now.AddDays(-$pdf.DaysAgo)
    $hash = (Get-FileHash -Path $path -Algorithm SHA256).Hash
    $manifest.files += @{
        name            = $pdf.Name
        path            = $path
        size            = $item.Length
        mtime           = $item.LastWriteTime.ToString("o")
        sha256          = $hash
        expected_latest = $pdf.Name -eq "report_latest.pdf"
    }
}

$manifestPath = Join-Path $Root "manifest.json"
$manifest | ConvertTo-Json -Depth 4 | Set-Content -Path $manifestPath

Write-Host "E2E environment ready at $Root" -ForegroundColor Green
Write-Host "Manifest: $manifestPath" -ForegroundColor Green
