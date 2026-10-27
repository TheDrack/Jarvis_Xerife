$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $repoRoot ".venv\Scripts\python.exe"
$port = 8765
$stateDir = Join-Path $env:LOCALAPPDATA "Jarvis_Xerife\tailscale"
$logDir = Join-Path $env:LOCALAPPDATA "Jarvis_Xerife\logs"
$pidPath = Join-Path $stateDir "desktop-mcp.pid"

if (-not (Test-Path -LiteralPath $python)) {
    throw "Ambiente Python do Jarvis não encontrado: $python"
}

$tailscale = Get-Command tailscale -ErrorAction SilentlyContinue
if (-not $tailscale) {
    $candidatePaths = @(
        "$env:ProgramFiles\Tailscale IPN\tailscale.exe",
        "$env:ProgramFiles\Tailscale\tailscale.exe"
    )
    $candidate = $candidatePaths | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    if ($candidate) { $tailscale = Get-Item -LiteralPath $candidate }
}
if (-not $tailscale) {
    throw "Tailscale não encontrado. Instale pelo site oficial e entre na sua conta nesta máquina."
}
$tailscaleExe = if ($tailscale.Source) { $tailscale.Source } else { $tailscale.FullName }

$statusText = & $tailscaleExe status --json 2>$null
if ($LASTEXITCODE -ne 0) {
    throw "Tailscale não está conectado. Abra o Tailscale e entre na sua conta primeiro."
}
$status = $statusText | ConvertFrom-Json
$hostName = [string]$status.Self.DNSName
if ($status.BackendState -ne "Running" -or [string]::IsNullOrWhiteSpace($hostName)) {
    throw "Tailscale ainda não concluiu a conexão ao tailnet."
}
$hostName = $hostName.TrimEnd(".").ToLowerInvariant()

# Share a named mutex with the interactive supervisor to prevent concurrent port binds.
$startupMutex = [System.Threading.Mutex]::new($false, 'Global\JarvisDesktopMcpStartup')
$hasStartupLock = $false
try { $hasStartupLock = $startupMutex.WaitOne(20000) }
catch [System.Threading.AbandonedMutexException] { $hasStartupLock = $true }
if (-not $hasStartupLock) {
    $startupMutex.Dispose()
    throw "Outro inicializador está ocupando o lock do MCP; tente novamente."
}

$server = $null
$existingListener = Get-NetTCPConnection -State Listen -LocalAddress "127.0.0.1" -LocalPort $port -ErrorAction SilentlyContinue | Select-Object -First 1
if ($existingListener) {
    # Reuse only a verified Jarvis MCP listener; never kill or adopt an unrelated process.
    $owner = Get-CimInstance Win32_Process -Filter "ProcessId=$($existingListener.OwningProcess)" -ErrorAction SilentlyContinue
    if (-not $owner -or $owner.CommandLine -notmatch 'app\.adapters\.edge\.jarvis_desktop_mcp') {
        throw "A porta 127.0.0.1:$port está ocupada por outro processo (PID $($existingListener.OwningProcess)); ele foi preservado."
    }
    $serverPid = [int]$owner.ProcessId
} else {
    $serverPid = $null
}

$existingServe = (& $tailscaleExe serve status --json 2>$null | Out-String).Trim()
if ($LASTEXITCODE -eq 0 -and $existingServe -and $existingServe -notin @("{}", "null") -and $existingServe -notmatch "No serve config") {
    if ($existingServe -notmatch [regex]::Escape("127.0.0.1:$port")) {
        throw "Tailscale Serve já tem outra configuração; ela foi preservada. Revise 'tailscale serve status' antes de prosseguir."
    }
}

New-Item -ItemType Directory -Path $stateDir, $logDir -Force | Out-Null
$stdout = Join-Path $logDir "desktop-mcp.stdout.log"
$stderr = Join-Path $logDir "desktop-mcp.stderr.log"

$env:JARVIS_DESKTOP_TRANSPORT = "streamable-http"
$env:JARVIS_DESKTOP_HTTP_PORT = [string]$port
$env:JARVIS_DESKTOP_ALLOWED_HOSTS = "127.0.0.1:$port,localhost:$port," + $hostName + "," + $hostName + ":443"
$env:JARVIS_DESKTOP_ALLOWED_ORIGINS = "https://" + $hostName

if (-not $serverPid) {
    $server = Start-Process -FilePath $python `
        -ArgumentList @("-m", "app.adapters.edge.jarvis_desktop_mcp") `
        -WorkingDirectory $repoRoot `
        -WindowStyle Hidden `
        -RedirectStandardOutput $stdout `
        -RedirectStandardError $stderr `
        -PassThru
    $serverPid = [int]$server.Id
}

$ready = $false
for ($attempt = 0; $attempt -lt 40; $attempt++) {
    if ($server -and $server.HasExited) {
        throw "Servidor MCP encerrou durante a inicialização. Consulte: $stderr"
    }
    $client = [System.Net.Sockets.TcpClient]::new()
    try {
        $connect = $client.BeginConnect("127.0.0.1", $port, $null, $null)
        if ($connect.AsyncWaitHandle.WaitOne(250) -and $client.Connected) {
            $ready = $true
            break
        }
    } finally {
        $client.Dispose()
    }
    Start-Sleep -Milliseconds 250
}
if (-not $ready) {
    if ($server) { Stop-Process -Id $server.Id -Force -ErrorAction SilentlyContinue }
    $startupMutex.ReleaseMutex()
    $startupMutex.Dispose()
    throw "O endpoint MCP não abriu em 127.0.0.1:$port. Consulte: $stderr"
}

# The listener is established; release the startup lock before configuring Serve.
$startupMutex.ReleaseMutex()
$startupMutex.Dispose()

# Existing matching Serve routes are already healthy configuration; do not reapply
# them on every logon (Tailscale may return exit code 1 for an unchanged route).
$serveConfigured = $false
if ($existingServe -and $existingServe -notin @("{}", "null") -and $existingServe -match [regex]::Escape("127.0.0.1:$port")) {
    $serveConfigured = $true
}
if (-not $serveConfigured) {
    $serveOutput = & $tailscaleExe serve --yes --bg --https=443 "http://127.0.0.1:$port" 2>&1
    if ($LASTEXITCODE -ne 0) {
        if ($server) { Stop-Process -Id $server.Id -Force -ErrorAction SilentlyContinue }
        throw "Não foi possível configurar Tailscale Serve: $serveOutput"
    }
}
Set-Content -LiteralPath $pidPath -Value $serverPid -Encoding ascii

Write-Output "Jarvis Desktop MCP ativo no tailnet."
Write-Output "URL: https://$hostName/mcp"
Write-Output "PID: $serverPid"
Write-Output "Logs: $logDir"
Write-Output "Acesso público (Funnel): não habilitado."
