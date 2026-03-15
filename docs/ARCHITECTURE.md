# 🏗️ JARVIS — Arquitetura do Sistema

**Versão:** 2.0.0  
**Atualizado em:** 2026-03-10

---

## 📋 Visão Geral

JARVIS segue **Arquitetura Hexagonal** com **Injeção de Dependência (Nexus DI)** e **Auto-Evolução Assistida por LLM**.

O sistema é organizado em 5 camadas principais:

```
┌─────────────────────────────────────────────────────────────────┐
│                    INTERFACE / CI-CD                            │
│  - GitHub Actions (homeostase.yml)                              │
│  - API REST (FastAPI)                                           │
│  - Telegram Bot (Webhook/Polling)                               │
│  - WebSocket (HUD em tempo real)                                │
├─────────────────────────────────────────────────────────────────┤
│                    ADAPTERS (Infra/Edge)                        │
│  - gateway_llm_adapter.py (Groq, Gemini, Ollama)                │
│  - telegram_adapter.py                                          │
│  - github_adapter.py / github_worker.py                         │
│  - ollama_adapter.py                                            │
│  - docker_sandbox.py (NOVO)                                     │
│  - persistent_shell_adapter.py                                  │
│  - vector_memory_adapter.py                                     │
│  - vision_adapter.py                                            │
│  - mqtt_home_adapter.py                                         │
│  - soldier_telemetry_adapter.py                                 │
├─────────────────────────────────────────────────────────────────┤
│                   APPLICATION (Services)                        │
│  - assistant_service.py                                         │
│  - jarvis_dev_agent.py (NOVO - Agente Autônomo)                 │
│  - jarvis_dev_agent/pipeline_builder.py (NOVO)                  │
│  - jarvis_dev_agent/actions.py (NOVO)                           │
│  - jarvis_dev_agent/prompt_builder.py (NOVO)                    │
│  - jarvis_dev_agent/code_discovery.py (NOVO)                    │
│  - jarvis_dev_agent/trajectory.py (NOVO)                        │
│  - evolution_orchestrator.py                                    │
│  - evolution_gatekeeper.py                                      │
│  - evolution_sandbox.py                                         │
│  - metabolism_core.py                                           │
│  - llm_router.py                                                │
│  - adapter_registry.py (NOVO)                                   │
│  - consolidated_context_service.py                              │
│  - crystallizer_engine.py                                       │
│  - local_repair_agent.py                                        │
│  - notification_service.py                                      │
│  - field_vision.py                                              │
│  - thought_log_service.py                                       │
│  - device_orchestrator_service.py                               │
│  - c2_orchestrator_service.py                                   │
│  - soldier_registry.py                                          │
├─────────────────────────────────────────────────────────────────┤
│                     DOMAIN (Core)                               │
│  - capability_manager.py                                        │
│  - capabilities/cap_001.py a cap_102.py                         │
│  - memory/semantic_memory.py                                    │
│  - memory/procedural_memory.py (NOVO)                           │
│  - memory/working_memory.py                                     │
│  - memory/prospective_memory.py (NOVO)                          │
│  - models/agent.py (NOVO - Action, Observation, Task)           │
│  - models/adapter_registry.py (NOVO)                            │
│  - services/command_interpreter.py                              │
│  - services/intent_processor.py                                 │
│  - services/system_state_tracker.py                             │
│  - services/reward_signal_provider.py                           │
│  - services/safety_guardian.py                                  │
├─────────────────────────────────────────────────────────────────┤
│                      CORE (Nexus DI)                            │
│  - nexus.py (Container DI + Circuit Breaker)                    │
│  - nexus_exceptions.py (CloudMock, TimeoutError)                │
│  - nexuscomponent.py (Classe base)                              │
│  - nexus_discovery.py (Descoberta automática)                   │
│  - nexus_registry.py (Registro local/remoto)                    │
│  - meta/policy_store.py                                         │
│  - meta/jrvs_compiler.py                                        │
│  - meta/decision_engine.py                                      │
│  - config.py (Environment variables)                            │
└─────────────────────────────────────────────────────────────────┘
```

---

## 🔄 Fluxo Principal (JarvisDevAgent)

**O JarvisDevAgent agora orquestra TODO o fluxo de desenvolvimento do sistema:**

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
│  ```yaml                                                        │
│  components:                                                    │
│    step_0_telegram_adapter:                                     │
│      id: "telegram_adapter"                                     │
│      config:                                                    │
│        action: "send_message"                                   │
│        message: "Sua mensagem"                                  │
│  ```                                                            │
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

---

## 🧩 Fluxos Secundários

### 1. Self-Healing (Auto-Cura)

```
┌─────────────────────────────────────────────────────────────────┐
│                    ERRO DETECTADO                               │
│  (via FieldVision, EvolutionGatekeeper, ou usuário)             │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│           LOCAL REPAIR AGENT (Analisa)                          │
│  1. Classifica erro (SyntaxError, ImportError, etc.)            │
│  2. Busca solução em ProceduralMemory                           │
│  3. Se não encontra → LLM gera patch                            │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│              EVOLUTION SANDBOX (Testa)                          │
│  1. Aplica patch em diretório temporário                        │
│  2. Executa pytest tests/                                       │
│  3. Valida se testes passam                                     │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│              EVOLUTION GATEKEEPER (Aprova)                      │
│  1. Verifica cobertura de testes                                │
│  2. Verifica estabilidade recente                               │
│  3. Verifica arquivos frozen                                    │
│  4. Verifica proteção do núcleo                                 │
│  5. Verifica sandbox                                            │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                    RESULTADO                                    │
│  ✅ Aprovado → GitHub Worker cria PR                            │
│  ❌ Reprovado → ThoughtLog registra falha                       │
└─────────────────────────────────────────────────────────────────┘
```

### 2. Auto-Evolution (Evolução Autônoma)

```
┌─────────────────────────────────────────────────────────────────┐
│              CAPABILITY GAP DETECTADO                           │
│  (via CapabilityGapReporter ou EvolutionOrchestrator)           │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│           EVOLUTION ORCHESTRATOR (Orquestra)                    │
│  1. Seleciona próxima capability por prioridade/dependência     │
│  2. Chama MetabolismCore para gerar código                      │
│  3. Registra em ThoughtLog                                      │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│              METABOLISM CORE (Gera)                             │
│  1. Seleciona LLM por complexidade (Ollama/Groq/Gemini)         │
│  2. Gera código com prompt estruturado                          │
│  3. Retorna código + testes                                     │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│              EVOLUTION GATEKEEPER (Aprova)                      │
│  (Mesmas 5 verificações do Self-Healing)                        │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                    RESULTADO                                    │
│  ✅ Aprovado → Capability registrada + PR criado                │
│  ❌ Reprovado → MetabolismStateMachine escala                   │
└─────────────────────────────────────────────────────────────────┘
```

### 3. Soldier Mesh (Edge Computing)

```
┌─────────────────────────────────────────────────────────────────┐
│                    DEVICE REGISTRA                              │
│  (via /v1/devices/register com GPS, capabilities)               │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│         DEVICE ORCHESTRATOR SERVICE (Registra)                  │
│  1. Valida token de autenticação                                │
│  2. Registra no SQLite/Supabase                                 │
│  3. Atribui soldier_id único                                    │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│           SOLDIER TELEMETRY ADAPTER (Ingesta)                   │
│  1. Recebe telemetry (battery, GPS, status)                     │
│  2. Armazena em VectorMemory                                    │
│  3. Atualiza last_seen                                          │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│              C2 ORCHESTRATOR (Comanda)                          │
│  1. Verifica distância entre devices                            │
│  2. Se >50km → Requer confirmação                               │
│  3. Se privacy-sensitive → Requer confirmação                   │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                    RESULTADO                                    │
│  ✅ Comando executado no device alvo                            │
│  ⚠️ Confirmação necessária → Notificação enviada                │
└─────────────────────────────────────────────────────────────────┘
```

---

## 🧠 Componentes Principais

### Nexus DI

Container de injeção de dependência que resolve componentes pelo ID:

```python
from app.core.nexus import nexus

# Resolve componente
adapter = nexus.resolve("telegram_adapter")

# Circuit breaker automático
if adapter and not getattr(adapter, "__is_cloud_mock__", False):
    adapter.execute({"action": "send_message", "message": "Olá"})

# Verifica se componente está disponível
if nexus._is_circuit_open("telegram_adapter"):
    print("Circuit breaker aberto — usando CloudMock")
```

**Features:**
- ✅ Thread-safe (double-checked locking)
- ✅ Circuit breaker com timeout configurável
- ✅ CloudMock fallback automático
- ✅ Descoberta automática por filesystem
- ✅ Cache de instâncias resolvidas

### JarvisDevAgent

Agente autônomo de desenvolvimento (Devin-style):

```python
from app.core.nexus import nexus

agent = nexus.resolve("jarvis_dev_agent")
result = agent.execute({
    "source": "user_request",
    "priority": "high",
    "description": "Crie pipeline para backup automático no Drive",
    "constraints": ["Não usar bibliotecas externas", "Seguir PEP8"],
    "success_criteria": "Pipeline funcional e testado"
})

print(f"Success: {result['success']}")
print(f"Iterations: {result['iterations']}")
print(f"Trajectory: {result['trajectory']}")
```

**Features:**
- ✅ Action-Observation Loop (até 15 iterações)
- ✅ AdapterRegistry para descobrir o que existe
- ✅ PipelineBuilder para criar pipelines YAML
- ✅ DockerSandbox para testes isolados
- ✅ ProceduralMemory para aprendizado

### AdapterRegistry

Registro simplificado de adapters (5KB vs 500KB do consolidated context):

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

**Adapters Registrados:**

| Adapter ID | Descrição | Capabilities |
|------------|-----------|--------------|
| `llm_router` | Roteamento de LLMs | code_generation, self_repair, planning |
| `github_worker` | Operações GitHub | create_pull_request, create_issue, push_commits |
| `telegram_adapter` | Interface Telegram | send_message, send_voice, receive_message |
| `persistent_shell_adapter` | Terminal stateful | run_shell_command, run_tests, browse_directory |
| `docker_sandbox` | Sandbox Docker | run_tests_isolated, validate_code |
| `evolution_sandbox` | Sandbox local | test_proposal, validate_code |
| `pipeline_builder` | Criador de pipelines | create_pipeline, run_pipeline |
| `ollama_adapter` | LLMs locais | local_inference, code_generation |
| `consolidated_context_service` | Snapshot do código | read_context, refresh_context |
| `capability_manager` | Gerenciamento de capabilities | list_capabilities, execute_capability |
| `procedural_memory` | Memória de padrões | store_pattern, find_similar |
| `semantic_memory` | Memória de eventos | store_event, query_similar |

### DockerSandbox

Isolamento de testes em containers Docker:

```python
from app.adapters.infrastructure.docker_sandbox import DockerSandbox

sandbox = DockerSandbox(image="python:3.11-slim")

# Executa testes em container isolado
success, output = sandbox.run_tests(
    code="def test_x(): assert 1+1==2",
    test_file="tests/test_x.py"
)

if success:
    print("✅ Testes passaram")
else:
    print(f"❌ Testes falharam: {output}")
```

**Features:**
- ✅ Container efêmero (auto-remove após execução)
- ✅ Sem rede (network_disabled=True)
- ✅ Sem capabilities Linux (cap_drop=["ALL"])
- ✅ Filesystem read-only (exceto /app)
- ✅ Timeout configurável (120s padrão)
- ✅ Fallback para sandbox local se Docker indisponível

### EvolutionGatekeeper

5 verificações antes de aprovar mudanças no código:

```python
from app.application.services.evolution_gatekeeper import EvolutionGatekeeper

gk = EvolutionGatekeeper()

proposed_change = {
    "files_modified": ["app/application/services/new_feature.py"],
    "before_state": {"tests_passing_rate": 0.9},
    "after_state": {"tests_passing_rate": 1.0},
}

approved, reason = gk._approve_or_reject(proposed_change)

if approved:
    print("✅ Mudança aprovada")
else:
    print(f"❌ Mudança reprovada: {reason}")
```

**5 Verificações:**
1. ✅ Cobertura de testes (mínimo 400 testes)
2. ✅ Estabilidade recente (sem falhas nas últimas 24h)
3. ✅ Proteção de arquivos frozen (não modificar .frozen/)
4. ✅ Proteção do núcleo (não modificar app/core/)
5. ✅ Sandbox (testes passam em isolamento)

---

## 📊 Camadas e Responsabilidades

| Camada | Responsabilidade | Exemplos |
|--------|-----------------|----------|
| **Interface** | Entrada/saída do sistema | API REST, Telegram, GitHub Actions, WebSocket |
| **Adapters** | Conexão com infraestrutura | LLMs, Telegram, GitHub, Docker, SQLite |
| **Application** | Casos de uso | JarvisDevAgent, AssistantService, EvolutionOrchestrator |
| **Domain** | Regras de negócio | CapabilityManager, Memory, Models |
| **Core** | Infraestrutura interna | Nexus DI, PolicyStore, JrvsCompiler |

---

## 🔒 Segurança

| Camada | Proteção |
|--------|----------|
| **DockerSandbox** | Isolamento de testes (sem rede, sem capabilities) |
| **EvolutionSandbox** | Sandbox local para testes rápidos |
| **EvolutionGatekeeper** | 5 verificações antes de aprovar código |
| **SafetyGuardian** | Validação de segurança de ações |
| **CapabilityAuthorizer** | Autorização de capabilities por usuário |
| **PIIRedactor** | Redação de dados sensíveis (CPF, email, etc.) |
| **EnvSecretsProvider** | Criptografia de secrets em .env |
| **C2Orchestrator** | Confirmação para ações remotas (>50km ou privacy-sensitive) |

---

## 📈 Escalabilidade

| Componente | Escala |
|------------|--------|
| **Nexus DI** | 91+ componentes registrados |
| **Adapters** | 15+ adapters disponíveis |
| **Capabilities** | 102 capabilities implementadas |
| **Pipelines** | YAML reutilizáveis (config/pipelines/) |
| **Memory** | Semantic + Procedural + Working + Prospective |
| **Soldiers** | Múltiplos devices (mobile, desktop, edge) |

---

## 🚀 Deploy

```bash
# Cloud (Render/Heroku)
pip install -r requirements/prod-cloud.txt
python main.py

# Edge (local)
pip install -r requirements/prod-edge.txt
python main.py

# Docker (sandbox)
docker run -it python:3.11-slim pytest tests/

# Docker Compose (produção)
docker-compose up -d
```

---

## 📚 Referências

- [README.md](../README.md) — Visão geral
- [STATUS.md](STATUS.md) — Status do projeto
- [ARQUIVO_MAP.md](ARQUIVO_MAP.md) — Mapa de arquivos
- [NEXUS.md](NEXUS.md) — Documentação do Nexus DI
- [PIPELINE_RUNNER.md](PIPELINE_RUNNER.md) — Pipelines YAML