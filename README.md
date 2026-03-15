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
│  - jarvis_dev_agent.py                  │
│  - evolution_orchestrator.py            │
│  - metabolism_core.py                   │
│  - llm_router.py                        │
│  - pipeline_builder.py                  │
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
│  1. Consulta AdapterRegistry (o que existe?)                    │
│  2. Verifica: telegram_adapter existe? → SIM                    │
│  3. Decide: Não preciso criar, só usar                          │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│              PIPELINE BUILDER (Cria)                            │
│  Gera: config/pipelines/auto_telegram_notification.yml          │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│              PIPELINE RUNNER (Executa)                          │
│  python app/runtime/pipeline_runner.py --pipeline auto_telegram │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                    RESULTADO                                    │
│  ✅ Notificação enviada                                         │
│  ✅ Pipeline salvo para reuso                                   │
│  ✅ Aprendizado registrado em ProceduralMemory                  │
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
| `llm_router` | Roteamento de LLMs | code_generation, self_repair, planning |
| `github_worker` | Operações GitHub | create_pull_request, create_issue |
| `telegram_adapter` | Interface Telegram | send_message, send_voice |
| `persistent_shell_adapter` | Terminal stateful | run_shell_command, run_tests |
| `docker_sandbox` | Sandbox Docker | run_tests_isolated |
| `evolution_sandbox` | Sandbox local | test_proposal, validate_code |
| `pipeline_builder` | Criador de pipelines | create_pipeline, run_pipeline |

---

## 🧪 Validação

```bash
# Validar registry vs código
python scripts/validate_registry_vs_code.py

# Validar docs vs código
python scripts/validate_docs_vs_code.py

# Validar arquitetura
python scripts/validate_architecture.py

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
| Phase 2 | ✅ Completo | Auto-Evolução + Self-Healing |
| Phase 3 | ✅ Completo | JarvisDevAgent + AdapterRegistry |
| Phase 4 | 🟡 Em Progresso | Soldier Mesh (Edge Computing) |

---

## 📚 Documentação

- → Veja [docs/ARQUIVO_MAP.md](docs/ARQUIVO_MAP.md) para lista completa de arquivos
- → Veja [docs/STATUS.md](docs/STATUS.md) para status detalhado
- → Veja [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) para arquitetura completa
- → Veja [docs/NEXUS.md](docs/NEXUS.md) para documentação do Nexus DI

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