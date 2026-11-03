[CmdletBinding()]
param(
    [string]$PythonPath = ""
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot

if ([string]::IsNullOrWhiteSpace($PythonPath)) {
    $venvPython = Join-Path $repoRoot ".venv\Scripts\python.exe"
    if (Test-Path $venvPython) {
        $PythonPath = $venvPython
    }
    else {
        $pythonCommand = Get-Command python -ErrorAction Stop
        $PythonPath = $pythonCommand.Source
    }
}
elseif (-not (Test-Path $PythonPath)) {
    $pythonCommand = Get-Command $PythonPath -ErrorAction SilentlyContinue
    if ($null -eq $pythonCommand) {
        throw "Python executable not found: $PythonPath"
    }
    $PythonPath = $pythonCommand.Source
}

$specPath = Join-Path $repoRoot "JarvisDesktop.spec"
$distPath = Join-Path $repoRoot "dist"
$workPath = Join-Path $repoRoot "build"

if (-not (Test-Path $specPath)) {
    throw "PyInstaller spec not found: $specPath"
}

Push-Location $repoRoot
try {
    & $PythonPath -m PyInstaller --version
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller is unavailable in the selected Python environment."
    }

    $pyinstallerArgs = @(
        "--noconfirm",
        "--clean",
        "--distpath", $distPath,
        "--workpath", $workPath,
        $specPath
    )
    & $PythonPath -m PyInstaller @pyinstallerArgs

    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller failed with exit code $LASTEXITCODE."
    }

    $bundlePath = Join-Path $distPath "JarvisDesktop"
    $exePath = Join-Path $bundlePath "JarvisDesktop.exe"
    $iconPath = Join-Path $bundlePath "_internal\desktop\jarvis.ico"

    if (-not (Test-Path $exePath)) {
        throw "Build finished without the expected executable: $exePath"
    }
    if (-not (Test-Path $iconPath)) {
        throw "Build finished without the bundled Windows icon: $iconPath"
    }

    $sizeMb = [math]::Round((Get-Item $exePath).Length / 1MB, 2)
    Write-Output "Jarvis Desktop bundle created: $bundlePath"
    Write-Output "Executable: $exePath ($sizeMb MB)"
    Write-Output "Embedded icon asset: $iconPath"
}
finally {
    Pop-Location
}
