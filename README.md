# 🤖 JARVIS – Plataforma de Assistente e Automação Distribuída

[![🧬 JARVIS: PyTest e Auto-Cura](https://github.com/TheDrack/Jarvis_Xerife/actions/workflows/homeostase.yml/badge.svg?branch=main)](https://github.com/TheDrack/Jarvis_Xerife/actions/workflows/homeostase.yml)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

**Versão:** 2.0.0  
**Última Atualização:** 2026-03-10  
**Status:** ✅ Operacional

---

## 🎯 Visão Geral

JARVIS é um sistema de software autônomo que combina **Arquitetura Hexagonal**, **Injeção de Dependência (Nexus DI)** e **Auto-Evolução Assistida por LLM**.

O sistema é capaz de:
- ✅ Interpretar comandos em linguagem natural
- ✅ Executar código existente (prioritário sobre criar)
- ✅ Criar novo código apenas se necessário (JarvisDevAgent)
- ✅ Testar em sandbox isolado (Docker ou local)
- ✅ Aprender com cada interação (ProceduralMemory)
- ✅ Auto-corrigir erros (Self-Healing)
- ✅ Evoluir autonomamente (EvolutionOrchestrator)

---

## Rota remota principal: RDC → Aperture → Tailscale → Jarvis

**Prioridade P0.** Ao ligar o PC, o Tailscale deve conectar automaticamente à tailnet. Agentes compatíveis com MCP e autorizados usam o gateway do Aperture: `https://aperture.tail350144.ts.net/v1/mcp`. O conector `jarvis` do Aperture encaminha as chamadas ao upstream privado `https://multimetal.tail350144.ts.net/mcp`, publicado pelo Tailscale Serve para o servidor local `127.0.0.1:8765`.

O Aperture centraliza grants e exposição de ferramentas; as ACLs/identidade do Tailscale limitam o alcance de rede. “Qualquer agente” significa qualquer agente compatível e autorizado, não acesso público irrestrito.

RDC diretamente ao bridge JSONL e Aperture diretamente ao upstream Jarvis são alternativas para situações específicas, por exemplo diagnóstico local ou quando a rota principal não pode ser usada. Não são a metodologia padrão. A sessão visual do Windows ainda precisa estar acessível para ferramentas que controlam a interface gráfica.

Detalhes, boot, segurança e critérios de aceitação: `docs/ACESSO_REMOTO_RDC_APERTURE_TAILSCALE.md`.


## 🏗️ Arquitetura

```
┌─────────────────────────────────────────┐
│         INTERFACE / CI-CD               │
│  - GitHub Actions                       │
│  - API REST                             │
│  - Telegram Bot                         │
├─────────────────────────────────────────┤
│         ADAPTERS (Infra/Edge)           │
│  - gateway_llm_adapter.py               │
│  - telegram_adapter.py                  │
│  - github_adapter.py                    │
│  - ollama_adapter.py                    │
│  - docker_sandbox.py                    │
│  - persistent_shell_adapter.py          │
├─────────────────────────────────────────┤
│        APPLICATION (Services)           │
│  - assistant_service.py                 │
│  - jarvis_dev_agent/ (agent.py)         │
│  - evolution_orchestrator.py            │
│  - metabolism_core.py                   │
│  - llm_router.py                        │
│  - consolidated_context_service.py      │
├─────────────────────────────────────────┤
│          DOMAIN (Core)                  │
│  - capability_manager.py                │
│  - memory/ (semantic, procedural, etc)  │
│  - models/ (agent, adapter_registry)    │
├─────────────────────────────────────────┤
│       CORE (Nexus DI)                   │
│  - nexus.py                             │
│  - nexus_exceptions.py                  │
│  - nexuscomponent.py                    │
└─────────────────────────────────────────┘
```

---

## 🤖 JarvisDevAgent (Fluxo Principal)

**Inspirado no Devin/OpenHands**, o JarvisDevAgent é o **motor autônomo de desenvolvimento** que agora orquestra todo o fluxo do JARVIS:

### Fluxo de Execução

```
┌─────────────────────────────────────────────────────────────────┐
│                    USUÁRIO SOLICITA                             │
│  "Crie pipeline para enviar notificação no Telegram"            │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│              JARVIS DEV AGENT (Analisa)                         │
│  1. Seleciona a capability executável (CapabilityManager)       │
│  2. Consulta SemanticMemory por soluções similares (few-shot)   │
│  3. Gera código via LLMRouter → proposta + PR (com gatekeeper)  │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│              PIPELINE YAML (Declara)                            │
│  Define: config/pipelines/<nome>.yml (passos + componentes)     │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│              PIPELINE RUNNER (Executa)                          │
│  PIPELINE=<nome> python app/runtime/pipeline_runner.py          │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                    RESULTADO                                    │
│  ✅ Capability executada / proposta gerada                       │
│  ✅ Gatekeeper validou (sandbox + testes)                        │
│  ✅ Ciclo registrado em SemanticMemory                           │
└─────────────────────────────────────────────────────────────────┘
```

### Casos de Uso

| Fonte | Exemplo | Endpoint |
|-------|---------|----------|
| **User Request** | "Crie script de backup" | POST /v1/dev-agent/run |
| **Self-Healing** | Erro detectado → corrigir | Auto-trigger |
| **Auto-Evolution** | Gap de capability → implementar | EvolutionOrchestrator |
| **Proactive** | Oportunidade → otimizar | ProactiveCore |

### Exemplo de Uso

```bash
# Via API
curl -X POST http://localhost:8000/v1/dev-agent/run \
  -H "Content-Type: application/json" \
  -d '{
    "source": "user_request",
    "description": "Crie pipeline para backup automático no Drive"
  }'

# Via Python
from app.core.nexus import nexus

agent = nexus.resolve("jarvis_dev_agent")
result = agent.execute({
    "description": "Envie notificação no Telegram",
    "source": "user_request"
})
```

---

## 📦 AdapterRegistry

Registro simplificado do que o Jarvis **PODE fazer** (5KB vs 500KB do consolidated context):

```python
from app.core.nexus import nexus

registry = nexus.resolve("adapter_registry")

# Lista todos os adapters
adapters = registry.execute({"action": "list"})

# Verifica se adapter existe
adapter = registry.execute({
    "action": "get",
    "adapter_id": "telegram_adapter"
})

# Identifica gaps (o que falta criar)
gap = registry.execute({
    "action": "find_gap",
    "capability": "enviar email"
})
```

### Adapters Registrados

| Adapter ID | Descrição | Capabilities |
|------------|-----------|--------------|
| `llm_router` | Roteamento dinâmico de LLMs | code_generation, self_repair, planning |
| `github_worker` | Operações no GitHub | create_pull_request, create_issue, push_commits |
| `persistent_shell_adapter` | Terminal stateful | run_shell_command, run_tests, browse_directory |
| `telegram_adapter` | Interface via Telegram | send_message, send_voice, receive_message |
| `consolidated_context_service` | Snapshot do código | read_context, refresh_context |
| `capability_manager` | Gerenciamento de capabilities | list_capabilities, execute_capability |
| `procedural_memory` | Memória de padrões | store_pattern, find_similar |
| `semantic_memory` | Memória de eventos | store_event, query_similar |

> A lista acima é a do registry estático (`app/domain/models/adapter_registry.py`).
> O Nexus Discovery completa o registro com os demais componentes em runtime — a
> lista viva está em `data/nexus_registry.json`.
>
> Estado atual: o `AdapterRegistry` responde a `list`/`get`/`find_gap`, mas ainda
> **não é consultado automaticamente** pelo agente nem pelo ciclo de evolução — a
> integração "consulte o que já existe antes de criar" está pendente. Veja
> [docs/VERIFICACAO_ENTREGAS.md](docs/VERIFICACAO_ENTREGAS.md).

---

## 🧪 Validação

```bash
# Validar arquitetura (camadas, ports, adapters, DI container)
python scripts/validate_architecture.py

# Validar autoconsciência via Long Context (contexto consolidado)
python scripts/validate_self_awareness.py

# Testar JarvisDevAgent
python -c "from app.application.services.jarvis_dev_agent import JarvisDevAgent; print('✅ OK')"
python -c "from app.domain.models.adapter_registry import AdapterRegistry; print('✅ OK')"
python -c "from app.adapters.infrastructure.docker_sandbox import DockerSandbox; print('✅ OK')"
```

---

## 📊 Status

| Fase | Status | Descrição |
|------|--------|-----------|
| Phase 1 | ✅ Completo | Arquitetura Hexagonal + Nexus DI |
| Phase 2 | ⏸️ Pausado | Autoevolução fail-closed por padrão; recuperação e curiosidade em validação |
| Phase 3 | ✅ Completo | JarvisDevAgent + AdapterRegistry |
| Phase 4 | 🟡 Em Progresso | Soldier Mesh (Edge Computing) |

---

## 📚 Documentação

- → Veja [docs/ARQUIVO_MAP.md](docs/ARQUIVO_MAP.md) para lista completa de arquivos
- → Veja [docs/MULTI_AGENT_USAGE.md](docs/MULTI_AGENT_USAGE.md) para o guia de uso dos multiagentes (fila, workers, concorrência e falhas)
- → Veja [docs/RESPAN_GATEWAY.md](docs/RESPAN_GATEWAY.md) para ligar o Respan Gateway (open-source, in-process) como camada de roteamento do `AIGateway`, com o guia oficial e o resultado da verificação local
- → Veja [docs/skills-connectors/CONTEXT_MEMORY_PROTOCOL.md](docs/skills-connectors/CONTEXT_MEMORY_PROTOCOL.md) para o protocolo de inicialização e consolidação de memória das IAs.
- → Veja [docs/STATUS.md](docs/STATUS.md) para status detalhado
- → Veja [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) para arquitetura completa
- → Veja [docs/architecture/JARVIS_OS_HARNESS.md](docs/architecture/JARVIS_OS_HARNESS.md) para a arquitetura do harness e do Jarvis OS.
- → Veja [docs/JARVIS_OS_FOUNDATION.md](docs/JARVIS_OS_FOUNDATION.md) para o plano de implementação JOF 0.1.
- → Veja [docs/NEXUS.md](docs/NEXUS.md) para documentação do Nexus DI
- → Veja [docs/CURIOSITY_PROTOCOL.md](docs/CURIOSITY_PROTOCOL.md) para transformar descobertas em oportunidades verificáveis.
- → A saudação de reencontro usa `reconnection_briefing` para resumir descobertas, PRs e testes com status verificado.
- → Veja [docs/AUTOEVOLUTION_RECOVERY.md](docs/AUTOEVOLUTION_RECOVERY.md) para recuperação controlada e critérios para reativar a autoevolução.

---

## 🚀 Quick Start

```bash
# 1. Instalar dependências
pip install -r requirements/core.txt

# 2. Configurar variáveis de ambiente
cp .env.example .env
# Edite .env com suas chaves de API

# 3. Iniciar o JARVIS
python main.py

# 4. Testar via API
curl http://localhost:8000/health
```

---

## 📄 Licença

MIT License — veja [LICENSE](LICENSE) para detalhes.

**Made with ❤️ by the Jarvis Team**


## Guia de uso e modos de opera??o

Consulte [docs/GUIA_DE_USO.md](docs/GUIA_DE_USO.md) para os modos de opera??o e [docs/NAVEGACAO_VISUAL.md](docs/NAVEGACAO_VISUAL.md) para navega??o do desktop.

## Pós-instalação e primeiro uso obrigatório

Antes de considerar uma instalação operacional, toda IA que usar Jarvis deve executar a **Verificação Inicial de Vôo (VIV)**: [procedimento de pós-instalação](docs/POS_INSTALACAO.md). O protocolo também está referenciado nas instruções de agentes e no [prompt inicial portátil](docs/skills-connectors/STARTUP_PROMPT.md), para runtimes que não carregam arquivos do repositório automaticamente.
