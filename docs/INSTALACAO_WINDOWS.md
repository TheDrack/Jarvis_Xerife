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

O repositório inclui `scripts/jarvis_magic.ps1`, `scripts/start-jarvis-boot.ps1` e `scripts/start-jarvis-mcp-interactive.ps1` para instalação e inicialização separadas. Para preparar a conexão direta ChatGPT → Jarvis por meio do Secure MCP Tunnel oficial, consulte `docs/ACESSO_REMOTO_RDC_APERTURE_TAILSCALE.md` e use `scripts/setup_chatgpt_jarvis_tunnel.ps1 -Action configure` somente depois de provisionar o tunnel ID e a runtime API key na organização OpenAI. A tarefa SYSTEM mantém o bridge RDC; a tarefa `Jarvis-Desktop-MCP-Interactive` inicia o MCP de desktop no logon do usuário, porque captura de tela e automação visual não funcionam corretamente a partir da Session 0 isolada do Windows. Tailscale Serve continua publicando o endpoint privado para o MCP em `127.0.0.1:8765`.

Para instalar ou sincronizar as duas tarefas, execute PowerShell como Administrador na raiz do repositório:

```powershell
.\scripts\jarvis_magic.ps1 -Action install -IncludeRdc
```

A existência de uma tarefa agendada ou de um processo ativo não prova que toda a cadeia funciona após reinicialização. Validar a rota P0 após um boot real, verificando cada camada e fazendo uma chamada MCP não destrutiva. A autenticação do RDC iniciada como `SYSTEM` pode não compartilhar o perfil/sessão autenticada do usuário; isso não deve ser confundido com o caminho principal via Aperture.

## Rede e segurança

- Manter o servidor Jarvis vinculado a `127.0.0.1:8765`.
- Usar Tailscale Serve para HTTPS privado na tailnet.
- Não habilitar Tailscale Funnel, encaminhamento de portas públicas ou binding em `0.0.0.0` para contornar falhas.
- Não desativar validação Host/Origin do servidor MCP.
- Não publicar tokens, chaves, credenciais ou sessões autenticadas em documentos, logs ou commits.
- Autorizar os agentes pelo gateway/grants do Aperture e limitar dispositivos por ACLs do Tailscale.

## Logs úteis

- Jarvis MCP (sessão interativa): `%LOCALAPPDATA%\Jarvis_Xerife\logs\jarvis-mcp.stdout.log` e `jarvis-mcp.stderr.log`.
- Supervisor RDC (SYSTEM): `%ProgramData%\Jarvis_Xerife\logs\supervisor.log`.
- Supervisor MCP interativo: `%LOCALAPPDATA%\Jarvis_Xerife\logs\jarvis-mcp-supervisor.log`.
- Tailscale: `tailscale status` e `tailscale serve status`.
- Porta local: `Get-NetTCPConnection -State Listen -LocalPort 8765`.
- Tarefa: `Get-ScheduledTask -TaskName Jarvis-RDC-Boot-Connect`.

## Caminhos configuráveis

Os supervisores não carregam caminhos fixos desta máquina. A resolução (em `scripts/jarvis-machine.ps1`) usa, nesta ordem: variável de ambiente, `machine.paths.json` ao lado do script instalado e detecção automática.

| Variável | Padrão |
|---|---|
| `JARVIS_USER_HOME` | perfil do usuário interativo |
| `JARVIS_REPO_ROOT` | clone encontrado subindo a partir do script |
| `JARVIS_INSTALL_DIR` | `%ProgramData%\Jarvis_Xerife` |
| `JARVIS_NODE_ROOT` | `%ProgramFiles%\nodejs` |

`jarvis_magic.ps1 -Action install` grava `machine.paths.json` com os valores resolvidos nesta máquina, para que a tarefa SYSTEM funcione antes de qualquer logon. Trocar a variável de ambiente sobrescreve o arquivo sem editar script.

## Critérios de aceitação

- [ ] Tailscale conecta automaticamente após reinicialização.
- [ ] Jarvis MCP escuta em `127.0.0.1:8765`.
- [ ] Tailscale Serve publica o endpoint privado `/mcp`.
- [ ] O conector `jarvis` do Aperture aponta ao upstream correto e descobre ferramentas.
- [ ] O agente autorizado conecta ao gateway `/v1/mcp` do Aperture.
- [ ] Uma chamada de observação/listagem termina sem erro.
- [ ] A disponibilidade da sessão gráfica foi testada separadamente, quando necessário.

Não marque todos os critérios como concluídos sem evidência de uma reinicialização real e chamada MCP ponta a ponta.

## Pós-instalação obrigatória — Verificação Inicial de Vôo (VIV)

Depois da instalação/configuração inicial, antes de considerar o Jarvis operacional, execute a [Verificação Inicial de Vôo](POS_INSTALACAO.md). O procedimento exige leitura do repositório e da arquitetura, inventário das ferramentas/conectores/skills/capacidades e permissões, teste seguro de cada item acessível, registro de falhas e pesquisa de soluções por falha. Correções devem ser isoladas, cobertas por testes de regressão e validadas pela suíte completa; nunca desabilite testes válidos. Não faça mutações em produção, deploys, migrações ou alterações de grants/credenciais sem autorização explícita. Só declare aprovação com evidência, incluindo a rota MCP ponta a ponta quando aplicável.
