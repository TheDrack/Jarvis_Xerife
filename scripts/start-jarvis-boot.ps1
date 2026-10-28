# SYSTEM-level supervisor: maintain the RDC bridge only.
# Jarvis Desktop MCP must run in the interactive user's session for screen capture/input.
# Machine paths come from jarvis-machine.ps1 (env vars or machine.paths.json), never literals.
param(
    [string]$UserHome,
    [string]$InstallDir,
    [string]$NodeRoot
)
$ErrorActionPreference = 'Continue'
. (Join-Path $PSScriptRoot 'jarvis-machine.ps1')
if (-not $UserHome) { $UserHome = Get-JarvisUserHome }
if (-not $InstallDir) { $InstallDir = Get-JarvisInstallDir }
if (-not $NodeRoot) { $NodeRoot = Get-JarvisNodeRoot }

$logs = Join-Path $InstallDir 'logs'
New-Item -ItemType Directory -Path $logs -Force | Out-Null
$env:USERPROFILE = $UserHome
$env:HOME = $UserHome
$env:APPDATA = Join-Path $UserHome 'AppData\Roaming'
$env:LOCALAPPDATA = Join-Path $UserHome 'AppData\Local'
$env:NPM_CONFIG_CACHE = Join-Path $UserHome 'AppData\Local\npm-cache'
$pathEntries = @(
    $NodeRoot,
    (Join-Path $env:APPDATA 'npm'),
    (Join-Path $env:ProgramFiles 'Tailscale')
)
$env:PATH = ($pathEntries -join ';') + ';' + $env:PATH
$node = Join-Path $NodeRoot 'node.exe'
$npxCli = Join-Path $NodeRoot 'node_modules\npm\bin\npx-cli.js'
$rdcOut = Join-Path $logs 'rdc.stdout.log'
$rdcErr = Join-Path $logs 'rdc.stderr.log'
$supervisorLog = Join-Path $logs 'supervisor.log'
function Log([string]$message) {
    Add-Content -LiteralPath $supervisorLog -Value ('[{0}] {1}' -f (Get-Date -Format s), $message)
}
function Find-RDC {
    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -match 'desktop-commander.*remote|npx-cli\.js.*desktop-commander.*remote' } |
        Select-Object -First 1
}
function Ensure-RDC {
    if (Find-RDC) { return }
    if (-not (Test-Path -LiteralPath $node) -or -not (Test-Path -LiteralPath $npxCli)) {
        Log "ERRO: Node/npx ausente em $NodeRoot; RDC não iniciado"
        return
    }
    try {
        $process = Start-Process -FilePath $node -ArgumentList @(('"' + $npxCli + '"'), '--yes', '@wonderwhy-er/desktop-commander@latest', 'remote') -WorkingDirectory $UserHome -WindowStyle Hidden -RedirectStandardOutput $rdcOut -RedirectStandardError $rdcErr -PassThru
        Start-Sleep -Seconds 3
        $process.Refresh()
        if ($process.HasExited) {
            Log "ERRO: RDC encerrou código=$($process.ExitCode); ver rdc.stderr.log"
        } else {
            Log "RDC iniciado PID=$($process.Id)"
        }
    } catch {
        Log "ERRO iniciando RDC: $_"
    }
}
Log "Supervisor de boot iniciado: RDC em SYSTEM; Jarvis Desktop MCP será iniciado no logon interativo. userHome=$UserHome"
while ($true) {
    try { Ensure-RDC } catch { Log "ERRO RDC supervisor: $_" }
    Start-Sleep -Seconds 30
}
