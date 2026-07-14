param(
  [string]$CertificateThumbprint = "",
  [string]$TimestampUrl = "http://timestamp.digicert.com"
)

$ErrorActionPreference = "Stop"
$keyDir = Join-Path $env:LOCALAPPDATA "Sentinel\signing"
$keyPath = Join-Path $keyDir "updater.key"
$passwordPath = Join-Path $keyDir "updater-password.dpapi"
if (-not (Test-Path $keyPath) -or -not (Test-Path $passwordPath)) {
  throw "Protected updater signing material is missing from $keyDir"
}
if (-not $CertificateThumbprint) {
  throw "A trusted Authenticode code-signing certificate thumbprint is required"
}
$certificate = Get-ChildItem Cert:\CurrentUser\My, Cert:\LocalMachine\My -CodeSigningCert |
  Where-Object Thumbprint -eq $CertificateThumbprint | Select-Object -First 1
if (-not $certificate -or -not $certificate.HasPrivateKey -or $certificate.NotAfter -le (Get-Date)) {
  throw "The Authenticode certificate is missing, expired, or lacks its private key"
}

$protected = [IO.File]::ReadAllBytes($passwordPath)
$plain = [Security.Cryptography.ProtectedData]::Unprotect(
  $protected, $null, [Security.Cryptography.DataProtectionScope]::CurrentUser
)
$overlay = Join-Path $env:TEMP "sentinel-signing-$PID.json"
try {
  $env:TAURI_SIGNING_PRIVATE_KEY = $keyPath
  $env:TAURI_SIGNING_PRIVATE_KEY_PASSWORD = [Text.Encoding]::UTF8.GetString($plain)
  @{
    bundle = @{ windows = @{
      certificateThumbprint = $CertificateThumbprint
      digestAlgorithm = "sha256"
      timestampUrl = $TimestampUrl
    }}
  } | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $overlay -Encoding UTF8
  npx tauri build --config $overlay
  if ($LASTEXITCODE -ne 0) { throw "Signed Tauri build failed" }
} finally {
  Remove-Item Env:TAURI_SIGNING_PRIVATE_KEY, Env:TAURI_SIGNING_PRIVATE_KEY_PASSWORD -ErrorAction SilentlyContinue
  Remove-Item -LiteralPath $overlay -Force -ErrorAction SilentlyContinue
  [Array]::Clear($plain, 0, $plain.Length)
}
