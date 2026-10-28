# Acesso remoto prioritário ao Jarvis: RDC → Aperture → Tailscale → Jarvis

**Estado:** metodologia operacional principal, documentada em 2026-10-22.  
**Escopo:** acesso remoto de agentes às ferramentas de navegação visual do Jarvis no Windows.

## Decisão de arquitetura

A rota padrão e de maior prioridade é:

```
Agente / ChatGPT
      │
      ▼
RDC (conector MCP disponível ao agente)
      │
      ▼
Aperture (gateway MCP, grants e controle de acesso)
      │
      ▼
Tailscale Serve / HTTPS privado na tailnet
      │
      ▼
Jarvis Desktop MCP (Streamable HTTP, loopback 127.0.0.1:8765)
      │
      ▼
Sessão Windows interativa / ferramentas visuais do Jarvis
```

O caminho lógico deve ser tratado como **RDC → Aperture → Tailscale → Jarvis**. O RDC é o conector MCP do lado do agente; Aperture é o gateway intermediário e ponto central de controle; Tailscale fornece conectividade privada até o computador; Jarvis executa as ferramentas na sessão Windows.

Ao iniciar o PC, o Tailscale deve conectar-se automaticamente à tailnet. O serviço MCP do Jarvis e a publicação do endpoint também precisam estar ativos para que a rota completa funcione. A disponibilidade de rede antes do login não garante que o desktop gráfico esteja pronto: ações visuais dependem de uma sessão Windows interativa acessível.

## Endpoints conhecidos nesta instalação

- **Gateway MCP do Aperture para os agentes:** `https://aperture.tail350144.ts.net/v1/mcp`
- **Upstream MCP do Jarvis cadastrado no Aperture:** `https://multimetal.tail350144.ts.net/mcp`
- **Backend local do Jarvis MCP:** `http://127.0.0.1:8765`, publicado por Tailscale Serve em HTTPS privado.

Os endereços acima são específicos desta instalação. Não substituir o endpoint do gateway pelo upstream: os agentes usam o endpoint do Aperture; o conector `jarvis` do Aperture encaminha as chamadas para o endpoint privado do Jarvis.

## Estado do diagnóstico — 2026-10-23

- O upstream direto `https://multimetal.tail350144.ts.net/mcp` respondeu ao handshake MCP, listou 13 ferramentas e executou `observe_screen` com sucesso depois de mover o servidor para a sessão interativa do usuário.
- O gateway `https://aperture.tail350144.ts.net/v1/mcp` respondeu ao handshake, mas listou apenas 7 ferramentas administrativas do próprio Aperture; nenhuma ferramenta Jarvis foi exposta nessa chamada. Portanto, a rota P0 ainda precisa de validação/correção do conector ou das permissões no Aperture.
- A configuração remota do Aperture não foi alterada durante a correção local.

## Prioridade e alternativas

### P0 — Rota padrão: RDC → Aperture → Tailscale → Jarvis

Usar como caminho normal após o boot e sempre que o agente tiver acesso ao gateway Aperture. Benefícios:

- políticas e grants centralizados no Aperture;
- identidade e alcance de rede limitados pela tailnet Tailscale;
- ponto único de entrada para agentes e ferramentas MCP;
- evita criar uma conexão direta nova para cada agente;
- permite auditar e restringir quais conectores/ferramentas o gateway expõe.

Um agente só consegue usar as ferramentas que o Aperture efetivamente expõe e para as quais seu acesso está autorizado. “Qualquer agente” significa qualquer agente compatível com MCP e autorizado/configurado para acessar o gateway, não acesso público irrestrito.

### P1 — RDC diretamente ao Jarvis

Usar apenas em situações específicas, por exemplo quando o computador já está ligado, a ponte persistente JSONL do Jarvis está ativa e o cliente dispõe de Remote Desktop Commander autorizado para executar processos/ler arquivos nesse computador.

Esta rota usa o bridge `app/adapters/edge/jarvis_desktop_cli.py --serve` por meio do RDC. Ela é uma alternativa de recuperação/operação local, não substitui a rota principal via Aperture. Reutilizar o processo persistente existente; não iniciar uma instância por ação.

### P2 — Aperture diretamente ao Jarvis

Usar como alternativa técnica quando o cliente/agente pode acessar o Aperture, mas não dispõe do caminho RDC previsto, ou para diagnosticar o upstream. O conector do Aperture alcança o Jarvis via endpoint Tailscale privado. Não é uma conexão de agente que contorna o Aperture: o gateway continua sendo o ponto de entrada para o cliente.

### Fallback local — MCP stdio

Para desenvolvimento no próprio PC, um cliente MCP local pode iniciar `app/adapters/edge/jarvis_desktop_mcp.py` por stdio. Esse caminho é local e não deve ser confundido com a rota remota principal.

## Inicialização no boot

O comportamento esperado é:

1. Windows inicia.
2. Tailscale inicia automaticamente e conecta o PC à tailnet.
3. A tarefa SYSTEM mantém o supervisor RDC. No logon, a tarefa `Jarvis-Desktop-MCP-Interactive` inicia o Jarvis Desktop MCP na sessão gráfica interativa.
4. O Aperture consegue alcançar o upstream privado `/mcp`.
5. O gateway MCP do Aperture publica as ferramentas autorizadas para os agentes.
6. Quando uma ferramenta depende da interface gráfica, a sessão Windows interativa precisa estar disponível.

Scripts relacionados:

- `scripts/jarvis_magic.ps1` — instalação, status, diagnóstico e gerenciamento.
- `scripts/start-jarvis-boot.ps1` — supervisor SYSTEM do RDC, instalado em `%ProgramData%\Jarvis_Xerife` (ou `JARVIS_INSTALL_DIR`).
- `scripts/start-jarvis-mcp-interactive.ps1` — supervisor do MCP visual na sessão interativa, instalado em `%ProgramData%\Jarvis_Xerife`.
- `scripts/start_jarvis_tailscale.ps1` — inicialização do servidor MCP e Tailscale Serve.

Use `.\scripts\jarvis_magic.ps1 -Action doctor` e `.\scripts\jarvis_magic.ps1 -Action status` para verificar a configuração. Não declare o boot validado apenas porque a tarefa existe: o critério completo exige testar após reinicialização real e verificar Tailscale, servidor local, Serve, conector Aperture e uma chamada MCP. A autenticação do RDC como tarefa `SYSTEM` pode não compartilhar o perfil interativo; não é pré-requisito da rota P0 se o gateway já está disponível ao agente.

## Segurança e controle de acesso

- Manter o servidor MCP vinculado a `127.0.0.1:8765`; Tailscale Serve faz a publicação HTTPS privada.
- Não habilitar Tailscale Funnel, encaminhamento de porta público nem binding em `0.0.0.0` para contornar falhas.
- Manter validação Host/Origin do MCP.
- Usar grants/políticas do Aperture para autorizar os conectores e ferramentas. A existência de um conector não equivale à autorização de todos os agentes.
- Usar ACLs/identidade da tailnet para limitar quais dispositivos alcançam o host.
- Não colocar tokens, chaves, credenciais ou conteúdo de autenticação neste documento, em scripts versionados ou em logs.
- A rota principal centraliza o controle de acesso no Aperture e Tailscale; alternativas diretas devem ser usadas somente quando a situação exigir e dentro da mesma política de segurança.

## Conexão direta ChatGPT → Jarvis via Secure MCP Tunnel

**Objetivo:** permitir que um app MCP personalizado do ChatGPT chame o Jarvis sem usar o gateway Aperture e sem expor a porta local à internet.

O `tunnel-client` oficial já está instalado em `%LOCALAPPDATA%\Programs\tunnel-client\tunnel-client.exe` (nesta máquina). O helper `scripts/setup_chatgpt_jarvis_tunnel.ps1` foi criado e passou na validação sintática. Ele não cria credenciais automaticamente e não inicia o túnel até receber os valores de uma organização OpenAI autorizada.

Pré-requisitos externos:

1. Criar um tunnel em `https://platform.openai.com/settings/organization/tunnels` e associá-lo ao workspace do ChatGPT correto.
2. Criar uma runtime API key com permissão `Tunnels Read + Use`. Não usar uma admin key no daemon.
3. Ter permissão para criar e usar um app MCP personalizado no ChatGPT. A disponibilidade e o nível de ações permitidas dependem do plano, das políticas do workspace e das permissões do usuário; confirme as opções efetivamente exibidas na interface. O suporte completo a ações de escrita/modificação tem requisitos de plano/workspace distintos do acesso somente de leitura.
4. No Windows, executar o helper no contexto do usuário interativo, quando o Jarvis estiver escutando em `127.0.0.1:8765`:

```powershell
.\scripts\setup_chatgpt_jarvis_tunnel.ps1 -Action configure
```

O helper solicita o `tunnel_id` e a runtime key em entrada oculta; guarda a chave cifrada com DPAPI para o usuário Windows atual, cria o perfil `jarvis-direct-chatgpt`, valida com `tunnel-client doctor` e instala a tarefa de logon `Jarvis-OpenAI-Secure-MCP-Tunnel`. A chave não deve ser enviada pelo chat, gravada em texto simples ou colocada na linha de comando. Depois, no ChatGPT web, adicionar um app MCP personalizado, selecionar `Connection: Tunnel`, escolher o mesmo túnel e testar `observe_screen`.

Estado observado em 2026-10-23: o executável está instalado, mas não há perfil de túnel, runtime key, tunnel ID ou tarefa configurados. A rota direta ainda não foi ativada; falta provisionar o recurso e as credenciais na organização OpenAI e confirmar que a conta/workspace ChatGPT permite adicionar o app. Não usar Funnel, ngrok nem abrir a porta 8765 publicamente como atalho.

## Critérios de aceitação

A rota P0 está operacional quando todos os itens abaixo forem verificados:

- [ ] Tailscale conecta automaticamente após boot e mostra o PC na tailnet.
- [ ] Jarvis MCP escuta somente em `127.0.0.1:8765`.
- [ ] Tailscale Serve publica HTTPS privado para o endpoint `/mcp`.
- [ ] O conector `jarvis` no Aperture usa o upstream correto e descobre as ferramentas.
- [ ] O agente autorizado conecta ao `/v1/mcp` do Aperture.
- [ ] Uma chamada de ferramenta não destrutiva (por exemplo, listar templates ou observar tela) termina sem erro.
- [ ] Uma reinicialização real confirma a cadeia completa, incluindo disponibilidade da sessão visual quando necessário.

## Referências do repositório

- [Guia de uso](GUIA_DE_USO.md)
- [Navegação visual](NAVEGACAO_VISUAL.md)
- [Instalação Windows](INSTALACAO_WINDOWS.md)
- [Guia do agente](AGENT_GUIDE.md)
