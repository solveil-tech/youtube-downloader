param(
    [string]$Python = "python"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$BuildPython = Join-Path $ProjectRoot ".buildenv\Scripts\python.exe"

& $Python -m venv (Join-Path $ProjectRoot ".buildenv")
& $BuildPython -m pip install --disable-pip-version-check -r (Join-Path $ProjectRoot "requirements.txt")

$SavedPath = $env:PATH
$env:PATH = "$env:SystemRoot\System32;$env:SystemRoot;$env:SystemRoot\System32\Wbem"
try {
    & $BuildPython -m PyInstaller --noconfirm --clean `
        --distpath (Join-Path $ProjectRoot "dist") `
        --workpath (Join-Path $ProjectRoot "build") `
        (Join-Path $ProjectRoot "ytdl.spec")
} finally {
    $env:PATH = $SavedPath
}

Write-Host "Built: $(Join-Path $ProjectRoot 'dist\ytdl.exe')"
