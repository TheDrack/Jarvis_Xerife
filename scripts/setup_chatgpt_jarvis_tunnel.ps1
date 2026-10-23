#requires -Version 5.1
[CmdletBinding()]
param(
    [ValidateSet('configure','run','start','status','stop','uninstall')]
    [string]$Action = 'status'
)
$ErrorActionPreference = 'Stop'
$ProfileName = 'jarvis-direct-chatgpt'
$TaskName = 'Jarvis-OpenAI-Secure-MCP-Tunnel'
$Client = Join-Path $env:LOCALAPPDATA 'Programs\tunnel-client\tunnel-client.exe'
$ProfileDir = Join-Path $env:USERPROFILE '.config\tunnel-client'
$SecretDir = Join-Path $env:LOCALAPPDATA 'Jarvis_Xerife\secrets'
$SecretFile = Join-Path $SecretDir 'openai-tunnel-runtime-key.dpapi'
$LogDir = Join-Path $env:LOCALAPPDATA 'Jarvis_Xerife\logs'
$LogFile = Join-Path $LogDir 'openai-tunnel-client.log'
$HealthUrl = 'http://127.0.0.1:8767'
$ProfileFile = Join-Path $ProfileDir ($ProfileName + '.yaml')

function Write-Log([string]$Message) {
    New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
    Add-Content -LiteralPath $LogFile -Value ('[{0}] {1}' -f (Get-Date -Format s), $Message)
}
function Set-RuntimeKey {
    if (-not (Test-Path -LiteralPath $SecretFile)) {
        throw "Chave runtime não cadastrada. Execute -Action configure."
    }
    $raw = (Get-Content -LiteralPath $SecretFile -Raw).Trim()
    $secure = $raw | ConvertTo-SecureString
    $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    try {
        $env:CONTROL_PLANE_API_KEY = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
    } finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)
        $secure.Dispose()
    }
}
function Test-JarvisLocal {
    $tcp = [Net.Sockets.TcpClient]::new()
    try {
        $a = $tcp.BeginConnect('127.0.0.1',8765,$null,$null)
        if (-not $a.AsyncWaitHandle.WaitOne(1500) -or -not $tcp.Connected) {
            throw 'Jarvis MCP não está escutando em 127.0.0.1:8765. Inicie o MCP interativo primeiro.'
        }
    } finally { $tcp.Dispose() }
}
function Invoke-TunnelDoctor {
    Set-RuntimeKey
    # An ephemeral port avoids colliding with a healthy tunnel-client already on 8767.
    & $Client doctor --profile $ProfileName --profile-dir $ProfileDir --health-listen-addr '127.0.0.1:0' --explain
    if ($LASTEXITCODE -ne 0) { throw "tunnel-client doctor falhou (exit=$LASTEXITCODE)." }
}
switch ($Action) {
    'configure' {
        if (-not (Test-Path -LiteralPath $Client)) { throw "tunnel-client não encontrado: $Client. Instale-o pela página oficial Platform → Tunnels." }
        Test-JarvisLocal
        $tunnelId = Read-Host 'Cole o tunnel_id criado em https://platform.openai.com/settings/organization/tunnels'
        if ($tunnelId -notmatch '^tunnel_[A-Za-z0-9_-]{8,}$') { throw 'Formato de tunnel_id inválido.' }
        $key = Read-Host 'Informe a runtime API key com permissão Tunnels Read + Use (entrada oculta)' -AsSecureString
        if ($key.Length -lt 20) { $key.Dispose(); throw 'A chave parece curta demais; nenhuma configuração foi aplicada.' }
        New-Item -ItemType Directory -Path $SecretDir -Force | Out-Null
        $key | ConvertFrom-SecureString | Set-Content -LiteralPath $SecretFile -Encoding ascii
        $key.Dispose()
        New-Item -ItemType Directory -Path $ProfileDir -Force | Out-Null
        & $Client init --sample sample_mcp_remote_no_auth --profile $ProfileName --profile-dir $ProfileDir --tunnel-id $tunnelId --mcp-server-url 'http://127.0.0.1:8765/mcp' --control-plane-api-key-ref 'env:CONTROL_PLANE_API_KEY' --health-listen-addr '127.0.0.1:8767' --force
        if ($LASTEXITCODE -ne 0) { throw "Falha ao criar perfil tunnel-client (exit=$LASTEXITCODE)." }
        Invoke-TunnelDoctor
        $userId = [Security.Principal.WindowsIdentity]::GetCurrent().Name
        $scriptPath = $PSCommandPath
        $taskAction = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument ('-NoProfile -ExecutionPolicy Bypass -File "' + $scriptPath + '" -Action run')
        $trigger = New-ScheduledTaskTrigger -AtLogOn -User $userId
        $principal = New-ScheduledTaskPrincipal -UserId $userId -LogonType Interactive -RunLevel Limited
        $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew
        Register-ScheduledTask -TaskName $TaskName -Action $taskAction -Trigger $trigger -Principal $principal -Settings $settings -Description 'Private OpenAI Secure MCP Tunnel to Jarvis Desktop MCP; runs as the interactive user.' -Force | Out-Null
        Write-Log "Configured profile=$ProfileName endpoint=http://127.0.0.1:8765/mcp task=$TaskName"
        Write-Output "Perfil configurado. Tarefa instalada para o usuário $userId."
        Write-Output 'A conexão no ChatGPT ainda precisa ser criada em Plugins/Apps com Connection=Tunnel.'
        Start-ScheduledTask -TaskName $TaskName
    }
    'run' {
        if (-not (Test-Path -LiteralPath $Client)) { throw "tunnel-client não encontrado: $Client" }
        Set-RuntimeKey
        Test-JarvisLocal
        Write-Log "Starting tunnel-client profile=$ProfileName"
        try {
            & $Client run --profile $ProfileName --profile-dir $ProfileDir 2>&1 | ForEach-Object {
                Add-Content -LiteralPath $LogFile -Value ([string]$_)
            }
            $code = $LASTEXITCODE
            Write-Log "tunnel-client exited code=$code"
            exit $code
        } catch {
            Write-Log "ERROR: $_"
            throw
        } finally {
            Remove-Item Env:CONTROL_PLANE_API_KEY -ErrorAction SilentlyContinue
        }
    }
    'start' {
        $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
        if (-not $task) { throw "Tarefa ausente. Execute -Action configure após criar tunnel_id e runtime key." }
        Start-ScheduledTask -TaskName $TaskName
        Write-Output "Tarefa $TaskName iniciada."
    }
    'status' {
        Write-Output "Client installed: $(Test-Path -LiteralPath $Client)"
        Write-Output "Profile configured: $(Test-Path -LiteralPath $ProfileFile)"
        Write-Output "Encrypted runtime key exists: $(Test-Path -LiteralPath $SecretFile)"
        $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
        if ($task) {
            $task | Select-Object TaskName,State,@{N='RunAs';E={$_.Principal.UserId}} | Format-List
            Get-ScheduledTaskInfo -TaskName $TaskName -ErrorAction SilentlyContinue | Select-Object LastRunTime,LastTaskResult | Format-List
        } else { Write-Output "Task installed: False" }
        try {
            $ready = Invoke-RestMethod -Uri ($HealthUrl + '/readyz') -TimeoutSec 2
            Write-Output 'Tunnel readiness endpoint responded.'
            $ready | ConvertTo-Json -Depth 6
        } catch { Write-Output 'Tunnel readiness endpoint not responding; tunnel is not yet verified.' }
        if (Test-Path -LiteralPath $LogFile) { Get-Content -LiteralPath $LogFile -Tail 12 }
    }
    'stop' {
        Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
        Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
            Where-Object { $_.CommandLine -match 'tunnel-client\.exe run --profile jarvis-direct-chatgpt' } |
            ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
        Write-Output 'Tarefa parada.'
    }
    'uninstall' {
        Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath $ProfileFile -Force -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath $SecretFile -Force -ErrorAction SilentlyContinue
        Write-Output 'Tarefa, perfil Jarvis dedicado e segredo DPAPI removidos. Nenhum outro túnel foi alterado.'
    }
}
