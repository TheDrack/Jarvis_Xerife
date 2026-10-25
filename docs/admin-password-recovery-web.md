# Recuperação de acesso administrativo do Jarvis

A interface web de recuperação fica em `/recover` no mesmo domínio da API do Jarvis.

1. No Render, abra o serviço **Jarvis-api** e confirme que `JARVIS_ADMIN_RESET_TOKEN` está configurado em **Environment**.
2. No celular, abra `https://jarvis-api-c47i.onrender.com/recover`.
3. Cole o valor de `JARVIS_ADMIN_RESET_TOKEN` do Render.
4. Digite a nova senha (20–72 caracteres) duas vezes e toque em **Redefinir senha**.
5. Se a API confirmar a operação, tente entrar no Jarvis com a nova senha.
6. Depois de confirmar que o login funciona, remova `JARVIS_ADMIN_RESET_TOKEN` do Render e salve a alteração.

O formulário não grava o token nem a senha no armazenamento do navegador; envia os dados em uma requisição HTTPS ao endpoint da própria API.

## Erros possíveis

- **Token inválido ou conta não encontrada:** confira o token e se a conta administrativa esperada existe no banco configurado.
- **Erro 503:** a API não conseguiu acessar o banco administrativo. Verifique as credenciais Supabase e os logs do serviço.
- **Login continua falhando:** não presuma que a redefinição foi concluída; confirme o resultado da API e a configuração de autenticação.
