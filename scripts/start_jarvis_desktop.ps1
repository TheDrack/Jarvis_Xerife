[CmdletBinding()]
param(
    [int]$Port = 8766,
    [ValidateSet("home", "intelligence", "network")]
    [string]$Page = "home",
    [string]$BaseUrl = $env:JARVIS_CLOUD_BASE_URL,
    [switch]$LoopbackOnly,
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
$python = [string](@($pythonCandidates)[0])
& $python -c "import webview, fastapi, uvicorn, httpx, psutil" 2>$null
if ($LASTEXITCODE -ne 0) {
    throw "Dependências desktop ausentes. Execute: python -m pip install -r requirements/desktop.txt"
}

Push-Location $repoRoot
try {
    $arguments = @("-m", "app.adapters.edge.jarvis_desktop_shell", "--port", "$Port")
    if ($BaseUrl) {
        $arguments += @("--base-url", $BaseUrl, "--page", $Page)
    }
    if ($LoopbackOnly) { $arguments += "--loopback-only" }
    if ($DebugWebView) { $arguments += "--debug" }
    & $python @arguments
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}