[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [ValidateScript({ Test-Path -LiteralPath $_ -PathType Leaf })]
    [string]$ArtifactSigningMetadata,

    [Parameter(Mandatory)]
    [ValidateScript({ Test-Path -LiteralPath $_ -PathType Leaf })]
    [string]$DlibPath
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$signTool = 'C:\Program Files (x86)\Windows Kits\10\bin\10.0.26100.0\x64\signtool.exe'
$timestampUrl = 'http://timestamp.acs.microsoft.com/'
$artifacts = @(
    @{ Path = Join-Path $root 'src-tauri\target\release\bundle\msi\Sentinel_1.0.0_x64_en-US.msi'; Sha256 = '60D628BB02B939F066D7BC8E6FC0B769E5752E18E0B2C40833651E4E38A8AB1A' },
    @{ Path = Join-Path $root 'src-tauri\target\release\bundle\nsis\Sentinel_1.0.0_x64-setup.exe'; Sha256 = 'E6CB5DC24A0F4820918422FEDE5F2C202ECC6684BBD4F7F634957CEB148805EB' }
)

if (-not (Test-Path -LiteralPath $signTool -PathType Leaf)) {
    throw "SignTool x64 is unavailable: $signTool"
}

foreach ($artifact in $artifacts) {
    if (-not (Test-Path -LiteralPath $artifact.Path -PathType Leaf)) {
        throw "Required release artifact is unavailable: $($artifact.Path)"
    }
    $actualHash = (Get-FileHash -LiteralPath $artifact.Path -Algorithm SHA256).Hash
    if ($actualHash -ne $artifact.Sha256) {
        throw "Refusing to sign an unexpected binary: $($artifact.Path)"
    }
    if ((Get-AuthenticodeSignature -FilePath $artifact.Path).Status -ne 'NotSigned') {
        throw "Refusing to overwrite an existing Authenticode signature: $($artifact.Path)"
    }
}

foreach ($artifact in $artifacts) {
    & $signTool sign /v /debug /fd SHA256 /tr $timestampUrl /td SHA256 /dlib $DlibPath /dmdf $ArtifactSigningMetadata $artifact.Path
    if ($LASTEXITCODE -ne 0) { throw "Authenticode signing failed: $($artifact.Path)" }

    & $signTool verify /pa /v $artifact.Path
    if ($LASTEXITCODE -ne 0) { throw "SignTool verification failed: $($artifact.Path)" }

    $signature = Get-AuthenticodeSignature -FilePath $artifact.Path
    if ($signature.Status -ne 'Valid') {
        throw "PowerShell Authenticode verification failed: $($artifact.Path) :: $($signature.Status)"
    }
}

Write-Output 'Authenticode signatures and timestamps verified. Regenerate Tauri .sig files before publishing.'
