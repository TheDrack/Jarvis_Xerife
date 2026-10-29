[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateLength(1, 1000)]
    [string]$Text,
    [ValidateSet("notification", "speak")]
    [string]$Mode = "notification",
    [ValidateLength(1, 80)]
    [string]$Title = "Jarvis",
    [string]$DeviceId,
    [string]$UserId,
    [int]$AckWaitSeconds = 10
)

$ErrorActionPreference = "Stop"
$baseUrl = $env:JARVIS_API_BASE_URL
if ([string]::IsNullOrWhiteSpace($baseUrl)) { $baseUrl = "https://jarvis-api-c47i.onrender.com" }
$baseUrl = $baseUrl.TrimEnd("/")
$key = $env:JARVIS_MOBILE_NOTIFY_KEY
if ([string]::IsNullOrWhiteSpace($key)) {
    $keyPath = Join-Path $env:LOCALAPPDATA "Jarvis_Xerife\config\mobile_notify\mobile_notify.key"
    if (Test-Path -LiteralPath $keyPath) {
        $key = (Get-Content -LiteralPath $keyPath -Raw).Trim()
    }
}
if ([string]::IsNullOrWhiteSpace($key) -or $key.Length -lt 32) {
    throw "JARVIS_MOBILE_NOTIFY_KEY is not configured. Configure the dedicated service credential first."
}
$headers = @{ "X-Jarvis-Mobile-Notify-Key" = $key }

if ([string]::IsNullOrWhiteSpace($DeviceId)) {
    $inventory = Invoke-RestMethod -Method Get -Uri "$baseUrl/v1/mobile/push/agent/devices" -Headers $headers -TimeoutSec 10
    if ($inventory.count -eq 0) {
        throw "No registered or connected mobile device is available."
    }
    if ($inventory.count -ne 1) {
        throw "Multiple mobile devices are available; specify -DeviceId and -UserId."
    }
    $DeviceId = [string]$inventory.devices[0].device_id
    $UserId = [string]$inventory.devices[0].user_id
}
$payload = @{
    text = $Text.Trim()
    title = $Title.Trim()
    mode = $Mode
    device_id = $DeviceId
}
if (-not [string]::IsNullOrWhiteSpace($UserId)) { $payload.user_id = $UserId }
$result = Invoke-RestMethod -Method Post -Uri "$baseUrl/v1/mobile/push/notify" -Headers $headers -ContentType "application/json" -Body ($payload | ConvertTo-Json -Compress) -TimeoutSec 40

if ($result.status -eq "queued" -and $result.event_id -and $AckWaitSeconds -gt 0) {
    $deadline = [DateTime]::UtcNow.AddSeconds([Math]::Min($AckWaitSeconds, 30))
    do {
        Start-Sleep -Seconds 2
        try {
            $delivery = Invoke-RestMethod -Method Get -Uri "$baseUrl/v1/mobile/push/agent/events/$($result.event_id)" -Headers $headers -TimeoutSec 10
            if ($delivery.status -eq "acknowledged" -or $delivery.status -eq "expired") {
                $result | Add-Member -NotePropertyName "delivery_status" -NotePropertyValue $delivery.status -Force
                break
            }
        } catch {
            # Keep the original queue response; do not leak credentials or event text.
        }
    } while ([DateTime]::UtcNow -lt $deadline)
    if (-not $result.PSObject.Properties["delivery_status"]) {
        $result | Add-Member -NotePropertyName "delivery_status" -NotePropertyValue "pending_ack" -Force
    }
}
[pscustomobject]@{
    status = $result.status
    transport = $result.transport
    mode = $result.mode
    device_id = $result.device_id
    event_id = $result.event_id
    delivery_status = $result.delivery_status
} | ConvertTo-Json -Compress
