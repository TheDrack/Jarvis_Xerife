# Secure MCP Tunnel: instalação por usuário

## Objetivo e escopo

Este guia conecta o Jarvis Desktop MCP local a produtos OpenAI compatíveis usando o Secure MCP Tunnel. O cliente `tunnel-client` abre uma conexão HTTPS de saída para a OpenAI e encaminha solicitações ao servidor MCP privado; não é necessário publicar a porta local na internet.

**O túnel não substitui a rota universal principal do Harness Jarvis.** Para agentes e provedores diferentes, mantenha a rota MCP controlada por Aperture + Tailscale como padrão. Secure MCP Tunnel é uma rota específica para superfícies OpenAI compatíveis (por exemplo, ChatGPT, Codex e Responses API). Não presuma que Claude ou qualquer outro provedor possa usar um `tunnel_id` OpenAI diretamente.

## Modelo de provisionamento

Cada usuário/ambiente deve configurar seu próprio túnel, com seu próprio `tunnel_id` e chave de runtime autorizada. Não distribua o túnel pessoal de desenvolvimento, sua chave ou um arquivo de perfil com segredo para outros usuários.

O Magic Executor pode automatizar a configuração local e a verificação, mas não deve fabricar nem reutilizar credenciais. A criação do túnel e a emissão da chave exigem uma conta/organização OpenAI com as permissões adequadas. O fluxo assistido é:

1. O usuário cria ou seleciona seu túnel em [Platform → Tunnels](https://platform.openai.com/settings/organization/tunnels).
2. Associa o túnel à organização Platform e ao workspace ChatGPT que realmente o utilizarão.
3. Cria/obtém uma runtime API key com `Tunnels Read + Use`. Não use uma chave de runtime de outro usuário.
4. Instala o cliente oficial `tunnel-client` conforme as instruções da página Tunnels.
5. Executa o configurador local abaixo. A chave é solicitada em entrada segura e armazenada com DPAPI no perfil Windows do usuário; não deve ser copiada para o repositório, para o chat ou para logs.
6. Registra o servidor no ChatGPT em **Plugins → + → Add custom MCP server**, escolhe **Connection: Tunnel**, seleciona/insere o `tunnel_id`, configura a autenticação MCP conforme o servidor, aceita o aviso de risco e cria o plugin.
7. Testa uma ferramenta de leitura/observação em uma conversa nova. A tarefa agendada e a prontidão local, isoladamente, não provam o funcionamento ponta a ponta.

## Windows: configuração assistida

Pré-requisitos:
- Windows PowerShell 5.1 ou posterior.
- Jarvis Desktop MCP em `http://127.0.0.1:8765/mcp`.
- `tunnel-client.exe` instalado em `%LOCALAPPDATA%\Programs\tunnel-client\tunnel-client.exe`.
- `tunnel_id` criado para o próprio usuário e runtime key com `Tunnels Read + Use`.

Na raiz do repositório, execute:

```powershell
.\scripts\setup_chatgpt_jarvis_tunnel.ps1 -Action configure
.\scripts\setup_chatgpt_jarvis_tunnel.ps1 -Action status
```

O configurador cria o perfil `jarvis-direct-chatgpt`, grava a referência à chave de runtime de forma protegida por DPAPI e registra a tarefa `Jarvis-OpenAI-Secure-MCP-Tunnel` para iniciar no logon interativo. A tarefa tem política de reinício para até cinco falhas, com intervalo de um minuto, e execução sem limite de tempo. O túnel é executado no contexto do usuário que configurou a chave; não copie o segredo para a conta SYSTEM nem execute o perfil DPAPI por outra conta.

Ações disponíveis:
- `configure`: solicita o `tunnel_id` e a runtime key, valida o MCP local, cria o perfil e registra/inicia a tarefa.
- `status`: mostra a presença do cliente, perfil, segredo protegido, tarefa e prontidão.
- `start`: inicia a tarefa já configurada.
- `run`: executa o cliente em primeiro plano para diagnóstico.
- `stop`: interrompe a tarefa/cliente dedicado do Jarvis.
- `uninstall`: remove a tarefa, o perfil dedicado e o segredo DPAPI do usuário. Use somente quando realmente quiser desinstalar esta integração.

O script não cria um túnel hospedado nem registra o app dentro do ChatGPT; essas duas etapas dependem da conta e do workspace do usuário. O Magic Executor pode chamar este script como etapa assistida, mas deve deixar a entrada da chave no terminal seguro e nunca capturar, registrar ou reenviar seu valor.

## Bateria de testes e critérios de aceite

Execute na máquina que hospeda o Jarvis:

1. `tunnel-client doctor --profile jarvis-direct-chatgpt --explain`. Se o cliente já estiver rodando e ocupando a porta de health configurada, use uma porta temporária para o diagnóstico: `--health-listen-addr 127.0.0.1:0`. Não encerre o túnel ativo só para executar o diagnóstico.
2. Confirme `http://127.0.0.1:8767/healthz` = `live` e `/readyz` = `ready`.
3. Confirme no log `poller started`, `mcp session initialized` e `tunnel-client started`. Não compartilhe logs sem remover dados de identificação ou material sensível.
4. Faça um handshake MCP `initialize`, `tools/list` e uma chamada não destrutiva como `observe_screen` no endpoint local.
5. No ChatGPT, selecione o app criado e repita uma chamada de leitura. Somente esta última etapa valida a rota completa através do produto OpenAI.

O endpoint local pode responder HTTP 406 a um GET simples e ainda aceitar MCP Streamable HTTP por POST; não use um GET de navegador como prova de falha ou sucesso. Uma mensagem de descoberta OAuth também deve ser investigada separadamente: não desative autenticação nem invente metadados para eliminá-la.

## Magic Executor e automação futura

O caminho recomendado é um comando explícito de instalação/diagnóstico do Harness que:
- verifica Windows, servidor MCP local e cliente oficial;
- solicita ao usuário criar/selecionar seu túnel e fornecer uma runtime key em entrada segura;
- chama este configurador sem passar a chave em argumentos;
- executa `doctor`, verifica readiness e inicialização MCP;
- apresenta o passo manual de registrar o app no workspace ChatGPT;
- registra apenas resultados sanitizados e separa `local MCP`, `tunnel ready`, `tool discovery` e `end-to-end call`.

A automação local não deve criar uma falsa conclusão de que o app do ChatGPT está registrado, nem reutilizar IDs/segredos do computador de desenvolvimento. A criação remota do túnel só deve ser automatizada quando houver uma API oficialmente suportada e um fluxo de autorização seguro com permissões de gerenciamento; a chave de runtime `Read + Use` não deve ser tratada como chave de gerenciamento.

## Referências oficiais

- [Secure MCP Tunnel](https://developers.openai.com/api/docs/guides/secure-mcp-tunnels)
- [Cliente oficial tunnel-client](https://github.com/openai/tunnel-client)
- [Conectar servidores MCP personalizados no ChatGPT](https://help.openai.com/pt-br/articles/12584461-connecting-custom-mcp-servers-in-chatgpt)
