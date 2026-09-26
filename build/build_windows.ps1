<#
.SYNOPSIS
    Production build of MUSTACOM BUSINESS MANAGER for Windows.
.DESCRIPTION
    1. installs the runtime dependencies (requirements.txt),
    2. freezes the application with PyInstaller into dist\mustacom,
    3. compiles the Inno Setup installer installer\mustacom.iss into
       installer\Output\MUSTACOM-Business-Manager-Setup.exe.

    Requires: Python 3.10+, and Inno Setup 6 (iscc.exe) either on PATH or in
    the default install location.  Run from the repository root:
        powershell -ExecutionPolicy Bypass -File build\build_windows.ps1
#>
param(
    [string]$Version = "1.0.0",
    [switch]$SkipInstaller,
    [switch]$SkipFreeze
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Push-Location $Root

Write-Host "==> MUSTACOM BUSINESS MANAGER $Version - production build"

# 1. dependencies -------------------------------------------------------------
Write-Host "==> Installing dependencies"
python -m pip install --upgrade pip | Out-Null
python -m pip install -r requirements.txt pyinstaller

# 2. freeze -------------------------------------------------------------------
if (-not $SkipFreeze) {
    Write-Host "==> Freezing with PyInstaller"
    python -m PyInstaller --noconfirm --clean build\mustacom.spec
    $exe = "dist\mustacom\MUSTACOM-Business-Manager.exe"
    if (-not (Test-Path $exe)) { throw "PyInstaller did not produce $exe" }
    Write-Host "==> Frozen OK: $exe"
}

# 3. installer ----------------------------------------------------------------
if (-not $SkipInstaller) {
    $iscc = Get-Command iscc -ErrorAction SilentlyContinue
    if (-not $iscc) {
        $candidate = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
        if (Test-Path $candidate) { $iscc = Get-Command $candidate }
    }
    if (-not $iscc) { throw "Inno Setup (ISCC.exe) not found - install Inno Setup 6" }

    Write-Host "==> Compiling Inno Setup installer"
    & $iscc.Source /DAppVersion=$Version installer\mustacom.iss
    if ($LASTEXITCODE -ne 0) { throw "ISCC failed" }
    $setup = "installer\Output\MUSTACOM-Business-Manager-Setup.exe"
    Write-Host "==> DONE: $setup"
}

Pop-Location
