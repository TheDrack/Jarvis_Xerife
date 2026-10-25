# Interactive administrator password reset for the hosted Jarvis API.
# Run: powershell -ExecutionPolicy Bypass -File .\scripts\reset_admin_password.ps1
# The reset token must be configured as JARVIS_ADMIN_RESET_TOKEN in Render.
$ErrorActionPreference = "Stop"
$endpoint = "https://jarvis-api-c47i.onrender.com/internal/admin/password-reset"

Write-Host "Jarvis - redefinir senha do administrador" -ForegroundColor Cyan
Write-Host "O token sera solicitado sem ser exibido; a nova senha tambem nao sera exibida."
$tokenSecure = Read-Host "Token JARVIS_ADMIN_RESET_TOKEN do Render" -AsSecureString
$tokenPtr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($tokenSecure)
try {
    $token = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($tokenPtr)
} finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($tokenPtr)
}

$passwordSecure = Read-Host "Nova senha (20 a 72 caracteres)" -AsSecureString
$passwordPtr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($passwordSecure)
try {
    $password = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($passwordPtr)
    if ($password.Length -lt 20 -or $password.Length -gt 72) {
        throw "A senha precisa ter entre 20 e 72 caracteres."
    }

    $confirmSecure = Read-Host "Digite a nova senha novamente" -AsSecureString
    $confirmPtr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($confirmSecure)
    try {
        $confirm = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($confirmPtr)
        if ($password -cne $confirm) {
            throw "As senhas nao coincidem."
        }
    } finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($confirmPtr)
        Remove-Variable confirm -ErrorAction SilentlyContinue
    }

    $headers = @{ "X-Jarvis-Reset-Token" = $token }
    $body = @{ new_password = $password } | ConvertTo-Json -Compress
    Invoke-RestMethod -Method Post -Uri $endpoint -Headers $headers -ContentType "application/json" -Body $body | Out-Null
    Write-Host "A API aceitou a redefinicao da senha." -ForegroundColor Green
    Write-Host "Por seguranca, remova JARVIS_ADMIN_RESET_TOKEN do Render apos confirmar o login."
} catch {
    Write-Error ("Falha ao redefinir senha: " + $_.Exception.Message)
    exit 1
} finally {
    Remove-Variable token,password,body,headers -ErrorAction SilentlyContinue
    $tokenSecure.Dispose()
    $passwordSecure.Dispose()
}
