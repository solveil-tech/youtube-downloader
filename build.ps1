param(
    [string]$Python = "python"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$BuildPython = Join-Path $ProjectRoot ".buildenv\Scripts\python.exe"

& $Python -m venv (Join-Path $ProjectRoot ".buildenv")
if ($LASTEXITCODE -ne 0) { throw "Failed to prepare the build environment" }
& $BuildPython -m pip install --disable-pip-version-check -r (Join-Path $ProjectRoot "requirements.txt")
if ($LASTEXITCODE -ne 0) { throw "Failed to install build dependencies" }

$SavedPath = $env:PATH
$env:PATH = "$env:SystemRoot\System32;$env:SystemRoot;$env:SystemRoot\System32\Wbem"
try {
    & $BuildPython -m PyInstaller --noconfirm --clean `
        --distpath (Join-Path $ProjectRoot "dist") `
        --workpath (Join-Path $ProjectRoot "build") `
        (Join-Path $ProjectRoot "ytdl.spec")
    if ($LASTEXITCODE -ne 0) { throw "EXE packaging failed" }
} finally {
    $env:PATH = $SavedPath
}

Write-Host "Built: $(Join-Path $ProjectRoot 'dist\ytdl.exe')"
