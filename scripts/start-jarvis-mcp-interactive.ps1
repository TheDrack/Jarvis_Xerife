# JARVIS Desktop MCP supervisor for the interactive user session.
# Desktop capture/input must run in the logged-on user's session, not Session 0.
$ErrorActionPreference = 'Continue'
$repo = 'C:\Users\USER\.copilot\repos\Jarvis_Xerife'
$userHome = 'C:\Users\USER'
$logs = Join-Path $env:LOCALAPPDATA 'Jarvis_Xerife\logs'
New-Item -ItemType Directory -Path $logs -Force | Out-Null
$python = Join-Path $repo '.venv\Scripts\python.exe'
$jarvisOut = Join-Path $logs 'jarvis-mcp.stdout.log'
$jarvisErr = Join-Path $logs 'jarvis-mcp.stderr.log'
$supervisorLog = Join-Path $logs 'jarvis-mcp-supervisor.log'
$sessionId = (Get-Process -Id $PID).SessionId
$env:USERPROFILE = $userHome
$env:HOME = $userHome
$env:APPDATA = Join-Path $userHome 'AppData\Roaming'
$env:LOCALAPPDATA = Join-Path $userHome 'AppData\Local'
function Log([string]$message) {
    Add-Content -LiteralPath $supervisorLog -Value ('[{0}] {1}' -f (Get-Date -Format s), $message)
}
function Find-Jarvis {
    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object { $_.SessionId -eq $sessionId -and $_.CommandLine -match 'app\.adapters\.edge\.jarvis_desktop_mcp' } |
        Select-Object -First 1
}
function Ensure-Jarvis {
    if (Find-Jarvis) { return }
    if (-not (Test-Path -LiteralPath $python)) {
        Log "ERRO: Python do venv ausente: $python"
        return
    }

    # Serialize both boot paths so they cannot race to bind port 8765.
    $startupMutex = [System.Threading.Mutex]::new($false, 'Global\JarvisDesktopMcpStartup')
    $hasStartupLock = $false
    try {
        try { $hasStartupLock = $startupMutex.WaitOne(15000) }
        catch [System.Threading.AbandonedMutexException] { $hasStartupLock = $true }
        if (-not $hasStartupLock) {
            Log 'AVISO: outro inicializador mantém o lock MCP; nova tentativa no próximo ciclo.'
            return
        }

        if (Find-Jarvis) { return }
        $listener = Get-NetTCPConnection -State Listen -LocalPort 8765 -ErrorAction SilentlyContinue |
            Select-Object -First 1
        if ($listener) {
            Log "AVISO: porta 8765 já está ocupada pelo PID $($listener.OwningProcess); preservando o processo existente."
            return
        }
        $env:JARVIS_DESKTOP_TRANSPORT = 'streamable-http'
        $env:JARVIS_DESKTOP_HTTP_PORT = '8765'
        $env:JARVIS_DESKTOP_ALLOWED_HOSTS = '127.0.0.1:8765,localhost:8765,multimetal.tail350144.ts.net,multimetal.tail350144.ts.net:443,desktop-hpj82ua.tail350144.ts.net,desktop-hpj82ua.tail350144.ts.net:443'
        $env:JARVIS_DESKTOP_ALLOWED_ORIGINS = 'https://multimetal.tail350144.ts.net,https://desktop-hpj82ua.tail350144.ts.net'
        try {
            $process = Start-Process -FilePath $python -ArgumentList @('-m','app.adapters.edge.jarvis_desktop_mcp') -WorkingDirectory $repo -WindowStyle Hidden -RedirectStandardOutput $jarvisOut -RedirectStandardError $jarvisErr -PassThru
            Start-Sleep -Seconds 3
            $process.Refresh()
            if ($process.HasExited) {
                Log "ERRO: Jarvis MCP encerrou código=$($process.ExitCode); ver $jarvisErr"
            } else {
                Log "Jarvis MCP interativo iniciado PID=$($process.Id), SessionId=$sessionId"
            }
        } catch {
            Log "ERRO iniciando Jarvis MCP interativo: $_"
        }
    } finally {
        if ($hasStartupLock) { $startupMutex.ReleaseMutex() }
        $startupMutex.Dispose()
    }
}
Log "Supervisor interativo iniciado SessionId=$sessionId User=$env:USERNAME"
while ($true) {
    try { Ensure-Jarvis } catch { Log "ERRO supervisor: $_" }
    Start-Sleep -Seconds 15
}
