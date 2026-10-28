# Resolve machine-specific locations once, so the supervisors contain no hard-coded user path.
# Precedence: environment variable -> machine.paths.json next to this file -> auto-detection.
# machine.paths.json is written by `jarvis_magic.ps1 -Action install` and stays machine-local.
$script:JarvisMachineScriptRoot = $PSScriptRoot
$script:JarvisMachinePaths = @{}

$machineConfigPath = Join-Path $script:JarvisMachineScriptRoot 'machine.paths.json'
if (Test-Path -LiteralPath $machineConfigPath) {
    try {
        $loaded = Get-Content -LiteralPath $machineConfigPath -Raw -ErrorAction Stop | ConvertFrom-Json
        foreach ($property in $loaded.PSObject.Properties) {
            if ($property.Value) { $script:JarvisMachinePaths[$property.Name] = [string]$property.Value }
        }
    } catch {
        Write-Warning "machine.paths.json inválido em ${machineConfigPath}: $_"
    }
}

function Get-JarvisConfiguredPath {
    param([string]$Name, [string]$EnvironmentVariable)
    if ($EnvironmentVariable) {
        $value = [Environment]::GetEnvironmentVariable($EnvironmentVariable)
        if ($value) { return $value }
    }
    if ($script:JarvisMachinePaths.ContainsKey($Name)) { return $script:JarvisMachinePaths[$Name] }
    return $null
}

function Get-JarvisUserHome {
    $configured = Get-JarvisConfiguredPath -Name 'userHome' -EnvironmentVariable 'JARVIS_USER_HOME'
    if ($configured) { return $configured }

    # SYSTEM has USERPROFILE under system32; only trust a real user profile.
    if ($env:USERPROFILE -and $env:USERPROFILE -notmatch '\\systemprofile$') { return $env:USERPROFILE }

    $interactive = (Get-CimInstance Win32_ComputerSystem -ErrorAction SilentlyContinue).UserName
    if ($interactive) {
        $name = ($interactive -split '\\')[-1]
        $detected = Join-Path $env:SystemDrive ('Users\' + $name)
        if (Test-Path -LiteralPath $detected) { return $detected }
    }
    throw 'Perfil do usuário não detectado. Defina JARVIS_USER_HOME ou rode jarvis_magic.ps1 -Action install.'
}

function Get-JarvisRepoRoot {
    $configured = Get-JarvisConfiguredPath -Name 'repoRoot' -EnvironmentVariable 'JARVIS_REPO_ROOT'
    if ($configured) { return $configured }

    $candidate = $script:JarvisMachineScriptRoot
    while ($candidate) {
        if (Test-Path -LiteralPath (Join-Path $candidate 'app\adapters\edge\jarvis_desktop_mcp.py')) {
            return $candidate
        }
        $parent = Split-Path -Parent $candidate
        if (-not $parent -or $parent -eq $candidate) { break }
        $candidate = $parent
    }
    throw 'Raiz do repositório não detectada. Defina JARVIS_REPO_ROOT ou rode jarvis_magic.ps1 -Action install.'
}

function Get-JarvisInstallDir {
    $configured = Get-JarvisConfiguredPath -Name 'installDir' -EnvironmentVariable 'JARVIS_INSTALL_DIR'
    if ($configured) { return $configured }
    return (Join-Path $env:ProgramData 'Jarvis_Xerife')
}

function Get-JarvisNodeRoot {
    $configured = Get-JarvisConfiguredPath -Name 'nodeRoot' -EnvironmentVariable 'JARVIS_NODE_ROOT'
    if ($configured) { return $configured }
    return (Join-Path $env:ProgramFiles 'nodejs')
}

function Save-JarvisMachinePaths {
    param(
        [Parameter(Mandatory)][System.Collections.IDictionary]$Paths,
        [Parameter(Mandatory)][string]$Directory
    )
    New-Item -ItemType Directory -Path $Directory -Force | Out-Null
    $target = Join-Path $Directory 'machine.paths.json'
    ($Paths | ConvertTo-Json) | Set-Content -LiteralPath $target -Encoding UTF8
    return $target
}
