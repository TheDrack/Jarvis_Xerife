#requires -Version 5.1
[CmdletBinding()]
param(
    [ValidateSet('install','start','stop','status','doctor','uninstall')]
    [string]$Action = 'status',
    [switch]$IncludeRdc
)
$ErrorActionPreference = 'Stop'
$RepoRoot = Split-Path -Parent $PSScriptRoot
$TaskName = 'Jarvis-RDC-Boot-Connect'
$InteractiveTaskName = 'Jarvis-Desktop-MCP-Interactive'
$BootScript = 'C:\ProgramData\Jarvis_Xerife\start-jarvis-boot.ps1'
$InteractiveBootScript = 'C:\ProgramData\Jarvis_Xerife\start-jarvis-mcp-interactive.ps1'
$Tailscale = @("$env:ProgramFiles\Tailscale\tailscale.exe", "$env:ProgramFiles\Tailscale IPN\tailscale.exe") | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
function Need-Admin {
    $p = [Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
    if (-not $p.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw 'Esta ação exige PowerShell como Administrador. Reabra o terminal com Executar como administrador.'
    }
}
function Log([string]$Message) { Write-Host ("[{0}] {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Message) }
function Check-Task { Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue }
function Check-InteractiveTask { Get-ScheduledTask -TaskName $InteractiveTaskName -ErrorAction SilentlyContinue }
function Stop-LegacySystemMcp {
    $legacy = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object { $_.SessionId -eq 0 -and $_.CommandLine -match 'app\.adapters\.edge\.jarvis_desktop_mcp' }
    foreach ($process in $legacy) {
        try {
            Stop-Process -Id $process.ProcessId -Force -ErrorAction Stop
            Log "MCP legado encerrado em Session 0 (PID=$($process.ProcessId)); será reiniciado na sessão interativa."
        } catch {
            Log "AVISO: não foi possível encerrar o MCP legado PID=$($process.ProcessId): $_"
        }
    }
}
switch ($Action) {
    'status' {
        Log "Repo: $RepoRoot"
        if ($Tailscale) { & $Tailscale status } else { Write-Warning 'Tailscale CLI não encontrado.' }
        foreach ($name in @($TaskName, $InteractiveTaskName)) {
            $task = Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
            if ($task) {
                $task | Select-Object TaskName, State, @{N='RunAs';E={$_.Principal.UserId}}, @{N='Trigger';E={($_.Triggers | ForEach-Object {$_.CimClass.CimClassName}) -join ','}} | Format-List
                Get-ScheduledTaskInfo -TaskName $name -ErrorAction SilentlyContinue | Select-Object LastRunTime, LastTaskResult | Format-List
            } else { Write-Warning "Tarefa $name não instalada." }
        }
        Get-NetTCPConnection -State Listen -LocalPort 8765 -ErrorAction SilentlyContinue | Select-Object LocalAddress, LocalPort, OwningProcess | Format-Table -AutoSize
        if (Test-Path 'C:\ProgramData\Jarvis_Xerife\logs\supervisor.log') { Get-Content 'C:\ProgramData\Jarvis_Xerife\logs\supervisor.log' -Tail 8 }
    }
    'doctor' {
        $checks = [ordered]@{}
        $checks['Repo'] = Test-Path (Join-Path $RepoRoot 'README.md')
        $checks['PythonVenv'] = Test-Path (Join-Path $RepoRoot '.venv\Scripts\python.exe')
        $checks['TailscaleCLI'] = [bool]$Tailscale
        $checks['NodeJS'] = [bool](Get-Command node.exe -ErrorAction SilentlyContinue)
        $checks['BootScript'] = Test-Path $BootScript
        $checks['InteractiveScript'] = Test-Path $InteractiveBootScript
        $checks['BootTask'] = [bool](Check-Task)
        $checks['InteractiveTask'] = [bool](Check-InteractiveTask)
        $currentSessionId = (Get-Process -Id $PID).SessionId
        $listener = Get-NetTCPConnection -State Listen -LocalPort 8765 -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($listener) {
            $ownerProcess = Get-CimInstance Win32_Process -Filter "ProcessId = $($listener.OwningProcess)" -ErrorAction SilentlyContinue
            $checks['McpInteractiveSession'] = [bool]($ownerProcess -and $ownerProcess.SessionId -eq $currentSessionId)
            if ($ownerProcess) { Log "MCP listener PID=$($ownerProcess.ProcessId) SessionId=$($ownerProcess.SessionId); current session=$currentSessionId" }
        } else { $checks['McpInteractiveSession'] = $false }
        foreach ($key in $checks.Keys) { '{0,-24} {1}' -f $key, $(if ($checks[$key]) {'OK'} else {'MISSING/FAIL'}) }
        if ($Tailscale) { & $Tailscale status; & $Tailscale serve status }
        try {
            $client = [Net.Sockets.TcpClient]::new()
            $async = $client.BeginConnect('127.0.0.1', 8765, $null, $null)
            $ok = $async.AsyncWaitHandle.WaitOne(1500) -and $client.Connected
            $client.Dispose()
            Log "Jarvis localhost:8765 listener: $ok"
        } catch { Log "Jarvis listener check failed: $_" }
        if ($checks.Values -contains $false) { exit 2 }
    }
    'install' {
        Need-Admin
        if (-not $Tailscale) { throw 'Instale o Tailscale oficial antes de continuar.' }
        if (-not (Test-Path (Join-Path $RepoRoot '.venv\Scripts\python.exe'))) { throw 'Venv do projeto ausente. Siga docs/INSTALACAO_WINDOWS.md.' }
        $sourceBoot = Join-Path $PSScriptRoot 'start-jarvis-boot.ps1'
        $sourceInteractive = Join-Path $PSScriptRoot 'start-jarvis-mcp-interactive.ps1'
        if (-not (Test-Path -LiteralPath $sourceBoot)) { throw "Script fonte de boot não encontrado: $sourceBoot" }
        if (-not (Test-Path -LiteralPath $sourceInteractive)) { throw "Script fonte interativo não encontrado: $sourceInteractive" }
        $up = & $Tailscale up --unattended=true 2>&1
        if ($LASTEXITCODE -ne 0) { throw "Falha ao ativar Tailscale unattended: $up" }
        Log 'Tailscale configurado para executar sem login.'
        $serve = (& $Tailscale serve status --json 2>$null | Out-String).Trim()
        if ($serve -and $serve -notin @('{}','null') -and $serve -notmatch '127\.0\.0\.1:8765') {
            throw 'Tailscale Serve já possui configuração diferente; preservada. Inspecione tailscale serve status antes de alterar.'
        }
        New-Item -ItemType Directory -Path (Split-Path -Parent $BootScript) -Force | Out-Null
        Copy-Item -LiteralPath $sourceBoot -Destination $BootScript -Force
        Copy-Item -LiteralPath $sourceInteractive -Destination $InteractiveBootScript -Force
        Log "Supervisor SYSTEM sincronizado: $sourceBoot -> $BootScript"
        Log "Supervisor interativo sincronizado: $sourceInteractive -> $InteractiveBootScript"
        $existingSystemTask = Check-Task
        if ($existingSystemTask -and $existingSystemTask.State -eq 'Running') {
            Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
            Start-Sleep -Milliseconds 500
        }
        $systemTaskAction = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$BootScript`""
        $systemTrigger = New-ScheduledTaskTrigger -AtStartup
        $systemPrincipal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
        $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew
        Register-ScheduledTask -TaskName $TaskName -Action $systemTaskAction -Trigger $systemTrigger -Principal $systemPrincipal -Settings $settings -Description 'JARVIS boot supervisor: RDC under SYSTEM; desktop MCP in the interactive user session.' -Force | Out-Null
        $userId = [Security.Principal.WindowsIdentity]::GetCurrent().Name
        $interactiveAction = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$InteractiveBootScript`""
        $interactiveTrigger = New-ScheduledTaskTrigger -AtLogOn -User $userId
        $interactivePrincipal = New-ScheduledTaskPrincipal -UserId $userId -LogonType Interactive -RunLevel Limited
        Register-ScheduledTask -TaskName $InteractiveTaskName -Action $interactiveAction -Trigger $interactiveTrigger -Principal $interactivePrincipal -Settings $settings -Description 'JARVIS Desktop MCP: screen capture and input in the logged-on user session.' -Force | Out-Null
        Stop-LegacySystemMcp
        Start-ScheduledTask -TaskName $TaskName
        Start-ScheduledTask -TaskName $InteractiveTaskName
        Log "Tarefas instaladas e iniciadas. Usuário interativo: $userId."
        if ($IncludeRdc) { Log 'RDC incluído; o teste de desktop deve ocorrer na sessão interativa do usuário.' }
    }
    'start' {
        Need-Admin
        $task = Check-Task
        if ($task) { Start-ScheduledTask -TaskName $TaskName; Log 'Supervisor SYSTEM iniciado.' }
        else { & (Join-Path $PSScriptRoot 'start_jarvis_tailscale.ps1') }
        if (Check-InteractiveTask) { Start-ScheduledTask -TaskName $InteractiveTaskName; Log 'Supervisor MCP interativo iniciado.' }
    }
    'stop' {
        Need-Admin
        foreach ($name in @($TaskName, $InteractiveTaskName)) {
            if (Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue) {
                Stop-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
                Log "Tarefa $name parada; processos filhos existentes não são encerrados automaticamente."
            }
        }
    }
    'uninstall' {
        Need-Admin
        foreach ($name in @($InteractiveTaskName, $TaskName)) {
            if (Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue) {
                Stop-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
                Unregister-ScheduledTask -TaskName $name -Confirm:$false
                Log "Tarefa $name removida."
            }
        }
        Log 'Não removi Tailscale, a configuração Serve, scripts, dados ou credenciais.'
    }
}
