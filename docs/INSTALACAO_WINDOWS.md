# Instalação e operação remota do Jarvis no Windows

Este documento descreve a metodologia de acesso remoto preferencial. A especificação completa está em [ACESSO_REMOTO_RDC_APERTURE_TAILSCALE.md](ACESSO_REMOTO_RDC_APERTURE_TAILSCALE.md).

## Rota padrão

**RDC → Aperture → Tailscale → Jarvis** é a rota principal e de maior prioridade.

- Gateway MCP usado pelos agentes autorizados: `https://aperture.tail350144.ts.net/v1/mcp`
- Upstream do conector `jarvis` no Aperture: `https://multimetal.tail350144.ts.net/mcp`
- Servidor MCP no PC: `127.0.0.1:8765`, publicado privadamente por Tailscale Serve.
- O Tailscale deve conectar automaticamente ao iniciar o PC.
- Grants do Aperture controlam quais conectores/ferramentas são expostos; ACLs do Tailscale controlam o alcance de rede.

RDC diretamente ao bridge JSONL e Aperture diretamente ao upstream Jarvis são rotas alternativas para diagnóstico ou situações específicas, não o padrão.

## Componentes locais

- **Tailscale:** conectividade privada à tailnet.
- **Jarvis Desktop MCP:** servidor Streamable HTTP em loopback na porta `8765`.
- **Tailscale Serve:** publica o endpoint HTTPS privado `/mcp` e encaminha ao loopback.
- **Aperture:** gateway MCP; o conector `jarvis` aponta para o upstream Tailscale do Jarvis.
- **RDC:** conector MCP do lado do agente. Não confundir RDC com o servidor MCP do Jarvis.

## Inicialização e diagnóstico

Na raiz do repositório, abra PowerShell:

```powershell
.\scripts\jarvis_magic.ps1 -Action doctor
.\scripts\jarvis_magic.ps1 -Action status
```

O repositório inclui `scripts/jarvis_magic.ps1`, `scripts/start-jarvis-boot.ps1` e `scripts/start_jarvis_tailscale.ps1` para instalação, diagnóstico e inicialização. A configuração do boot deve garantir que o Tailscale conecta, que o servidor MCP e Tailscale Serve estão disponíveis e que o conector do Aperture consegue alcançar o upstream.

A existência de uma tarefa agendada ou de um processo ativo não prova que toda a cadeia funciona após reinicialização. Validar a rota P0 após um boot real, verificando cada camada e fazendo uma chamada MCP não destrutiva. A autenticação do RDC iniciada como `SYSTEM` pode não compartilhar o perfil/sessão autenticada do usuário; isso não deve ser confundido com o caminho principal via Aperture.

## Secure MCP Tunnel para produtos OpenAI

O Secure MCP Tunnel é uma rota adicional para produtos OpenAI compatíveis, não um substituto da rota principal Aperture + Tailscale. Ele permite que ChatGPT, Codex e outras superfícies OpenAI compatíveis alcancem o MCP privado sem publicar a porta local. Não é um túnel universal para todos os provedores de IA; outros agentes devem usar uma rota MCP que suportem e para a qual estejam autorizados.

Cada usuário deve criar/selecionar seu próprio túnel e usar sua própria runtime key com permissão `Tunnels Read + Use`. Não compartilhe `tunnel_id`, chaves ou perfis com segredos entre usuários. A criação do túnel e a associação ao workspace ChatGPT são vinculadas à conta/organização e às permissões do usuário.

Depois de instalar o cliente oficial `tunnel-client`, configure a conexão local com:

```powershell
.\scripts\setup_chatgpt_jarvis_tunnel.ps1 -Action configure
.\scripts\setup_chatgpt_jarvis_tunnel.ps1 -Action status
```

O script solicita o `tunnel_id` e a runtime key em entrada segura, armazena o segredo com DPAPI no perfil do usuário e registra uma tarefa agendada no logon interativo. O script não cria o túnel hospedado nem registra o app no ChatGPT: o usuário precisa concluir essas etapas na página Platform Tunnels e em ChatGPT → Plugins → + → Add custom MCP server → Connection: Tunnel.

Antes de diagnosticar com `tunnel-client doctor`, se o cliente já estiver ativo e ocupando a porta de health configurada, passe `--health-listen-addr 127.0.0.1:0` para usar uma porta temporária sem interromper o túnel. Aceite como pontos de verificação separados: MCP local inicializado, `/readyz` retornando `ready`, cliente conectado/polling, ferramentas descobertas no ChatGPT e uma chamada de ferramenta ponta a ponta.

O guia completo está em [SECURE_MCP_TUNNEL.md](SECURE_MCP_TUNNEL.md).

## Rede e segurança

- Manter o servidor Jarvis vinculado a `127.0.0.1:8765`.
- Usar Tailscale Serve para HTTPS privado na tailnet.
- Não habilitar Tailscale Funnel, encaminhamento de portas públicas ou binding em `0.0.0.0` para contornar falhas.
- Não desativar validação Host/Origin do servidor MCP.
- Não publicar tokens, chaves, credenciais ou sessões autenticadas em documentos, logs ou commits.
- Autorizar os agentes pelo gateway/grants do Aperture e limitar dispositivos por ACLs do Tailscale.

## Logs úteis

- Jarvis MCP: `%LOCALAPPDATA%\Jarvis_Xerife\logs\desktop-mcp.stdout.log` e `desktop-mcp.stderr.log` (os caminhos podem variar se o processo for iniciado como `SYSTEM`).
- Supervisor: `%LOCALAPPDATA%\Jarvis_Xerife\logs\rdc-boot.log`.
- Tailscale: `tailscale status` e `tailscale serve status`.
- Porta local: `Get-NetTCPConnection -State Listen -LocalPort 8765`.
- Tarefa: `Get-ScheduledTask -TaskName Jarvis-RDC-Boot-Connect`.
- Secure MCP Tunnel: `%LOCALAPPDATA%\Jarvis_Xerife\logs\openai-tunnel-client.log` (sanitizar antes de compartilhar).

## Critérios de aceitação

- [ ] Tailscale conecta automaticamente após reinicialização.
- [ ] Jarvis MCP escuta em `127.0.0.1:8765`.
- [ ] Tailscale Serve publica o endpoint privado `/mcp`.
- [ ] O conector `jarvis` do Aperture aponta ao upstream correto e descobre ferramentas.
- [ ] O agente autorizado conecta ao gateway `/v1/mcp` do Aperture.
- [ ] Uma chamada de observação/listagem termina sem erro.
- [ ] A disponibilidade da sessão gráfica foi testada separadamente, quando necessário.
- [ ] Se Secure MCP Tunnel for usado, `/readyz` retorna `ready` e uma chamada do app registrado no ChatGPT passa ponta a ponta.

Não marque todos os critérios como concluídos sem evidência de uma reinicialização real e chamada MCP não destrutiva ponta a ponta.
