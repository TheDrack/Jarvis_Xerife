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

## Rota adicional para produtos OpenAI: Secure MCP Tunnel

O Secure MCP Tunnel é uma rota complementar para produtos OpenAI compatíveis, como ChatGPT, Codex e Responses API. O cliente `tunnel-client` inicia conexões HTTPS de saída e encaminha chamadas ao MCP local sem expor sua porta à internet pública.

**Esta rota não substitui P0 e não é um túnel universal para todos os provedores de IA.** Agentes de outros provedores devem usar uma rota MCP compatível e autorizada, como o gateway Aperture + Tailscale. Não compartilhe o túnel pessoal do desenvolvedor com outros usuários: cada usuário/ambiente deve provisionar seu próprio `tunnel_id` e runtime key com permissões adequadas.

No Windows, o setup assistido está documentado em [SECURE_MCP_TUNNEL.md](SECURE_MCP_TUNNEL.md) e pode ser executado por `scripts/setup_chatgpt_jarvis_tunnel.ps1`. O script configura o cliente local e a tarefa agendada; o usuário ainda precisa criar/selecionar o túnel na Platform e registrar o app no workspace ChatGPT. Só declare sucesso após uma chamada de ferramenta no app registrado.

## Inicialização no boot

O comportamento esperado é:

1. Windows inicia.
2. Tailscale inicia automaticamente e conecta o PC à tailnet.
3. O supervisor/Agendador inicia ou verifica o servidor Jarvis MCP HTTP e Tailscale Serve.
4. O Aperture consegue alcançar o upstream privado `/mcp`.
5. O gateway MCP do Aperture publica as ferramentas autorizadas para os agentes.
6. Quando uma ferramenta depende da interface gráfica, a sessão Windows interativa precisa estar disponível.

Scripts e estado do repositório:

- `scripts/setup_chatgpt_jarvis_tunnel.ps1` — configurador específico do Secure MCP Tunnel, incluído nesta PR.
- Os caminhos `scripts/jarvis_magic.ps1`, `scripts/start-jarvis-boot.ps1` e `scripts/start_jarvis_tailscale.ps1` citados por versões anteriores da documentação não foram encontrados no branch `main` durante esta verificação. Não os execute nem considere o Magic Executor integrado até que seu entrypoint canônico seja restaurado e testado.

Para o túnel, use `scripts/setup_chatgpt_jarvis_tunnel.ps1 -Action status`. Não declare o boot da rota P0 validado apenas porque uma tarefa existe: o critério completo exige testar após reinicialização real e verificar Tailscale, servidor local, Serve, conector Aperture e uma chamada MCP. A autenticação do RDC como tarefa `SYSTEM` pode não compartilhar o perfil interativo; não é pré-requisito da rota P0 se o gateway já está disponível ao agente.

## Segurança e controle de acesso

- Manter o servidor MCP vinculado a `127.0.0.1:8765`; Tailscale Serve faz a publicação HTTPS privada.
- Não habilitar Tailscale Funnel, encaminhamento de porta público nem binding em `0.0.0.0` para contornar falhas.
- Manter validação Host/Origin do MCP.
- Usar grants/políticas do Aperture para autorizar os conectores e ferramentas. A existência de um conector não equivale à autorização de todos os agentes.
- Usar ACLs/identidade da tailnet para limitar quais dispositivos alcançam o host.
- Não colocar tokens, chaves, credenciais ou conteúdo de autenticação neste documento, em scripts versionados ou em logs.
- A rota principal centraliza o controle de acesso no Aperture e Tailscale; alternativas diretas devem ser usadas somente quando a situação exigir e dentro da mesma política de segurança.

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
- [Secure MCP Tunnel: instalação por usuário](SECURE_MCP_TUNNEL.md)
