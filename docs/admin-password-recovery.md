# Recuperação da senha administrativa do Jarvis

## Redefinir a senha no Windows

1. No Render, abra o serviço **Jarvis-api** e confirme que `JARVIS_ADMIN_RESET_TOKEN` está configurado em **Environment**.
2. Baixe o repositório Jarvis_Xerife ou atualize sua cópia local.
3. Abra PowerShell na raiz do repositório e execute:

   ```powershell
   .\scripts\reset_admin_password.ps1
   ```

4. Cole o valor de `JARVIS_ADMIN_RESET_TOKEN` quando solicitado. O token não será exibido.
5. Digite uma nova senha de 20 a 72 caracteres duas vezes. A senha não será exibida.
6. Depois de confirmar que consegue entrar com a nova senha, remova `JARVIS_ADMIN_RESET_TOKEN` do Render e salve a alteração.

O script envia a senha somente para o endpoint HTTPS da API do Jarvis. Não coloque token ou senha em argumentos de linha de comando, arquivos de texto, issues ou logs.

## Limitações

A API precisa ter credenciais administrativas válidas do Supabase e uma conta com `username=admin` e `email=admin@jarvis.ai`. O script informa erro se a API rejeitar a requisição; não garante que a conta exista nem que o login funcione até isso ser testado.
