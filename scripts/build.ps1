param(
    [ValidateSet("backend", "frontend", "tauri", "all")]
    [string]$Target = "all"
)

$Root = Split-Path -Parent $PSScriptRoot
$Sidecar = Join-Path $Root "sidecar"
$Dist = Join-Path $Sidecar "dist"
$LogFile = Join-Path $Root "build.log"

function Log {
    param([string]$Message)
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "[$ts] $Message" | Tee-Object -FilePath $LogFile -Append
}

function Assert-Exit {
    param([string]$Step)
    if ($LASTEXITCODE -ne 0) {
        Log "FAILED: $Step (exit code $LASTEXITCODE)"
        exit 1
    }
    Log "OK: $Step"
}

# ---------------------------------------------------------------
# 1. Backend — compilar sidecar con PyInstaller
# ---------------------------------------------------------------
if ($Target -in @("backend", "all")) {
    Log "=== Step 1/3: Building backend (PyInstaller) ==="

    # Check prerequisites
    $py = Get-Command python -ErrorAction SilentlyContinue
    if (-not $py) {
        Log "ERROR: Python not found. Install Python 3.12+"
        exit 1
    }

    # Install/upgrade PyInstaller
    python -m pip install --upgrade pyinstaller 2>&1 | Out-File -Append $LogFile
    python -m pip install -r "$Sidecar/requirements.txt" 2>&1 | Out-File -Append $LogFile
    Assert-Exit "pip install"

    # Clean previous build
    if (Test-Path $Dist) {
        Remove-Item -Recurse -Force $Dist
    }
    if (Test-Path (Join-Path $Sidecar "build")) {
        Remove-Item -Recurse -Force (Join-Path $Sidecar "build")
    }

    # Run PyInstaller
    Push-Location $Sidecar
    python -m PyInstaller --clean sidecar.spec 2>&1 | Out-File -Append $LogFile
    Assert-Exit "PyInstaller"
    Pop-Location

    # Verify output
    $exe = Join-Path $Dist "sidecar.exe"
    if (-not (Test-Path $exe)) {
        Log "ERROR: $exe not found after build"
        exit 1
    }
    $size = (Get-Item $exe).Length / 1MB
    Log "Backend built: $exe ({0:n1} MB)" -f $size
}

# ---------------------------------------------------------------
# 2. Frontend — compilar React con Vite
# ---------------------------------------------------------------
if ($Target -in @("frontend", "all")) {
    Log "=== Step 2/3: Building frontend (Vite) ==="

    Push-Location $Root
    npm ci 2>&1 | Out-File -Append $LogFile
    Assert-Exit "npm ci"

    npx --yes tsc -b 2>&1 | Out-File -Append $LogFile
    Assert-Exit "tsc"

    npx vite build 2>&1 | Out-File -Append $LogFile
    Assert-Exit "vite build"
    Pop-Location

    $distDir = Join-Path $Root "dist"
    if (-not (Test-Path $distDir)) {
        Log "ERROR: $distDir not found after build"
        exit 1
    }
    Log "Frontend built: $distDir"
}

# ---------------------------------------------------------------
# 3. Tauri — empaquetar instalador (.msi / .dmg / .deb)
# ---------------------------------------------------------------
if ($Target -in @("tauri", "all")) {
    Log "=== Step 3/3: Building Tauri installer ==="

    # Ensure backend was built first
    $exe = Join-Path $Dist "sidecar.exe"
    if (-not (Test-Path $exe)) {
        Log "ERROR: backend must be built first (run with -Target backend or all)"
        exit 1
    }

    Push-Location $Root
    npx tauri build 2>&1 | Out-File -Append $LogFile
    Assert-Exit "tauri build"
    Pop-Location

    # Locate installer
    $tauriTarget = Join-Path $Root "src-tauri" "target" "release"
    $installer = Get-ChildItem -Path $tauriTarget -Filter "*.msi" -Recurse | Select-Object -First 1
    if ($installer) {
        Log "Installer: $($installer.FullName)"
    } else {
        Log "Tauri build completed. Check $tauriTarget for output."
    }
}

Log "=== BUILD COMPLETE ==="
