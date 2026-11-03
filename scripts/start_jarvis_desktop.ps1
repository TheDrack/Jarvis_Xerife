[CmdletBinding()]
param(
    [ValidateSet("home", "intelligence", "network")]
    [string]$Page = "home",
    [string]$BaseUrl = $env:JARVIS_CLOUD_BASE_URL,
    [switch]$DebugWebView
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$pythonCandidates = @(
    (Join-Path $repoRoot ".venv\Scripts\python.exe"),
    (Get-Command python -ErrorAction SilentlyContinue).Source,
    (Get-Command py -ErrorAction SilentlyContinue).Source
) | Where-Object { $_ -and (Test-Path $_) }

if (-not $pythonCandidates) {
    throw "Python 3.10+ não encontrado. Instale Python e repita."
}

$python = $pythonCandidates[0]
& $python -c "import webview" 2>$null
if ($LASTEXITCODE -ne 0) {
    throw "pywebview não está instalado. Instale com: python -m pip install -r requirements/desktop.txt"
}

Push-Location $repoRoot
try {
    $arguments = @("-m", "app.adapters.edge.jarvis_desktop_shell", "--page", $Page)
    if ($BaseUrl) {
        $arguments += @("--base-url", $BaseUrl)
    }
    if ($DebugWebView) {
        $arguments += "--debug"
    }
    & $python @arguments
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
