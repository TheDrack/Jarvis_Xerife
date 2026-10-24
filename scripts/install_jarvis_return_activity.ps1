$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$runtime = Join-Path $env:LOCALAPPDATA 'Jarvis_Xerife\runtime'
$startup = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\Startup'
$config = Join-Path $env:LOCALAPPDATA 'Jarvis_Xerife\config'
New-Item -ItemType Directory -Path $runtime,$startup,$config -Force | Out-Null
$sourceRoot = Join-Path $repo 'app'
$targetRoot = Join-Path $runtime 'app'
New-Item -ItemType Directory -Path (Join-Path $targetRoot 'application'),(Join-Path $targetRoot 'adapters') -Force | Out-Null
Copy-Item (Join-Path $sourceRoot '__init__.py') (Join-Path $targetRoot '__init__.py') -Force
Copy-Item (Join-Path $sourceRoot 'application\__init__.py') (Join-Path $targetRoot 'application\__init__.py') -Force
Copy-Item (Join-Path $sourceRoot 'application\return_activity_service.py') (Join-Path $targetRoot 'application\return_activity_service.py') -Force
Copy-Item (Join-Path $sourceRoot 'adapters\__init__.py') (Join-Path $targetRoot 'adapters\__init__.py') -Force
Copy-Item (Join-Path $sourceRoot 'adapters\jarvis_return_activity.py') (Join-Path $targetRoot 'adapters\jarvis_return_activity.py') -Force
$python = Join-Path $env:USERPROFILE '.copilot\repos\Jarvis_Xerife\.venv\Scripts\pythonw.exe'
if (-not (Test-Path $python)) { $python = (Get-Command pythonw.exe -ErrorAction Stop).Source }
$shortcutPath = Join-Path $startup 'Jarvis - Retorno de Atividade.lnk'
$ws = New-Object -ComObject WScript.Shell
$shortcut = $ws.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $python
$shortcut.Arguments = '-m app.adapters.jarvis_return_activity'
$shortcut.WorkingDirectory = $runtime
$shortcut.WindowStyle = 7
$shortcut.Description = 'Detecta retorno de atividade após inatividade e cumprimenta o usuário.'
$shortcut.Save()
Write-Output "Installed runtime: $runtime"
Write-Output "Startup shortcut: $shortcutPath"
Write-Output "Python: $python"
