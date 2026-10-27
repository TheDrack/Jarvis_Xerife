param([switch]$TestNotification)
$ErrorActionPreference = 'Stop'
$repo = 'TheDrack/Jarvis_Xerife'
$api = "https://api.github.com/repos/$repo/actions/runs?per_page=20"
$base = Join-Path $env:LOCALAPPDATA 'Jarvis\GitHubActionsMonitor'
$statePath = Join-Path $base 'state.json'
$logPath = Join-Path $base 'monitor.log'
New-Item -ItemType Directory -Path $base -Force | Out-Null
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$notify = New-Object System.Windows.Forms.NotifyIcon
$notify.Icon = [System.Drawing.SystemIcons]::Information
$notify.Visible = $true
$notify.Text = 'Jarvis - GitHub Actions'
$script:openUrl = "https://github.com/$repo/actions"
$notify.add_BalloonTipClicked({ if ($script:openUrl) { Start-Process $script:openUrl } })
function Write-Log([string]$Message) {
  Add-Content -LiteralPath $logPath -Value ("[{0}] {1}" -f (Get-Date -Format s), $Message) -Encoding UTF8
}
function Show-Notice([string]$Title,[string]$Message,[string]$Url,[bool]$ErrorState=$false) {
  $script:openUrl = $Url
  $notify.BalloonTipTitle = $Title
  $notify.BalloonTipText = $Message
  if ($ErrorState) { $notify.BalloonTipIcon = [System.Windows.Forms.ToolTipIcon]::Error }
  else { $notify.BalloonTipIcon = [System.Windows.Forms.ToolTipIcon]::Info }
  $notify.ShowBalloonTip(10000)
  Write-Log "$Title | $Message | $Url"
}
if ($TestNotification) {
  Show-Notice 'Jarvis — GitHub Actions' 'Teste da notificação do Windows. Clique para abrir o GitHub Actions.' "https://github.com/$repo/actions"
  Start-Sleep -Seconds 3
  $notify.Dispose()
  exit 0
}
$headers = @{ 'User-Agent'='Jarvis-GitHub-Actions-Notifier'; 'Accept'='application/vnd.github+json' }
$seen = @{}
$initialized = $false
if (Test-Path $statePath) {
  try {
    $saved = Get-Content -Raw -LiteralPath $statePath | ConvertFrom-Json
    foreach ($id in $saved.seen_ids) { $seen[[string]$id] = $true }
    $initialized = [bool]$saved.initialized
  } catch { Write-Log "Estado anterior inválido; será reconstruído: $($_.Exception.Message)" }
}
Write-Log 'Monitor iniciado; consulta a cada 120 segundos.'
while ($true) {
  try {
    $response = Invoke-RestMethod -Uri $api -Headers $headers -TimeoutSec 20
    $runs = @($response.workflow_runs)
    if (-not $initialized) {
      foreach ($run in $runs) { if ($run.status -eq 'completed') { $seen[[string]$run.id] = $true } }
      $initialized = $true
      Write-Log "Inicialização: $($runs.Count) execuções existentes registradas sem alertas retroativos."
    } else {
      foreach ($run in ($runs | Sort-Object { [datetime]$_.created_at })) {
        $id = [string]$run.id
        if ($seen.ContainsKey($id)) { continue }
        $seen[$id] = $true
        if ($run.status -ne 'completed') { continue }
        $url = [string]$run.html_url
        $name = [string]$run.name
        $branch = [string]$run.head_branch
        if ($run.conclusion -eq 'success') {
          Show-Notice 'Jarvis — testes aprovados' "$name | Branch: $branch | Execução concluída com sucesso. Clique para abrir." $url
        } elseif ($run.conclusion -in @('failure','timed_out','action_required')) {
          Show-Notice 'Jarvis — testes falharam' "$name | Branch: $branch | Resultado: $($run.conclusion). Clique para ver os logs." $url $true
        } elseif ($run.conclusion -eq 'cancelled') {
          Show-Notice 'Jarvis — execução cancelada' "$name | Branch: $branch | Execução cancelada." $url $true
        }
      }
    }
    $ids = @($seen.Keys | Select-Object -Last 200)
    $state = [ordered]@{ initialized=$initialized; seen_ids=$ids; updated_at=(Get-Date).ToString('o') }
    $state | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $statePath -Encoding UTF8
  } catch {
    Write-Log "Erro consultando GitHub: $($_.Exception.Message)"
  }
  Start-Sleep -Seconds 120
}
