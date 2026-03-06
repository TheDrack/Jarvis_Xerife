# JARVIS – Status Atual do Projeto

> **Data:** 2026-03-06  
> **Situação geral:** Reorganização estrutural concluída. Etapas 1–9 do plano de evolução arquitetural implementadas. Auto-evolução reativada com loop completo e Gatekeeper.

---

## ⚙️ Estado do Projeto

| Componente | Status |
|---|---|
| Nexus (Injeção de Dependência) | ✅ Ativo |
| Nexus Circuit Breaker | ✅ Ativo (import: 10 s, instantiate: 5 s, reset: 60 s) |
| Nexus Meta Layer (PolicyStore, JrvsCompiler, DecisionEngine) | ✅ Ativo |
| API REST (FastAPI) | ✅ Ativo |
| Adaptadores de Borda (Voz, Teclado) | ✅ Ativo |
| Adaptadores de Infraestrutura (LLM, DB, GitHub) | ✅ Ativo |
| Domínio (Modelos, Serviços) | ✅ Ativo |
| **Memória Vetorial (FAISS)** | ✅ **Ativo** (biográfica, 30 dias) |
| **Visão Computacional (Gemini Flash)** | ✅ **Ativo** (screenshot / webcam) |
| **Overwatch Daemon (Núcleo Proativo)** | ✅ **Ativo** (CPU/RAM preditivo, perímetro tático, consolidação semântica, fine-tuning trigger) |
| **LocalRepairAgent (Self-Healing Local)** | ✅ **Ativo** (primeiro estágio, < 1 s) |
| **EvolutionOrchestrator** | ✅ **Ativo** (loop agêntico + Gatekeeper + MetaReflection + CapabilityManager) |
| **OllamaAdapter (LLM local)** | ✅ **Ativo** (code_generation, self_repair) |
| **CostTracker (auditoria LLM)** | ✅ **Ativo** (SQLite, EMA por modelo) |
| **ProceduralMemory** | ✅ **Ativo** (índice vetorial de soluções) |
| **CapabilityIndexService** | ✅ **Ativo** (busca semântica top-k, EMA reliability) |
| **LLMRouter (ETAPA 1)** | ✅ **Ativo** (seleção dinâmica por task_type + fallback por confiabilidade + `preferred_provider`) |
| **WorkingMemory (ETAPA 2)** | ✅ **Ativo** (deque circular em RAM, 50 entradas, volátil) |
| **SemanticMemory (ETAPA 2)** | ✅ **Ativo** (grafo de conhecimento, NetworkX opcional) |
| **EvolutionGatekeeper (ETAPA 3)** | ✅ **Ativo** (5 verificações: testes, estabilidade, frozen, núcleo, **sandbox**) |
| **MetaReflection (ETAPA 4)** | ✅ **Ativo** (reflexão periódica, data/meta_reflection_latest.jrvs) |
| **Grafo de Dependências de Capabilities (ETAPA 5)** | ✅ **Ativo** (DAG, caminho crítico, executable capabilities) |
| **Auto-Evolução (loop completo com Gatekeeper) (ETAPA 6)** | ✅ **Ativo (loop completo com Gatekeeper)** |
| **JarvisDevAgent (ETAPA 7)** | ✅ **Ativo** (agente autônomo de desenvolvimento, `POST /v1/dev-agent/run`) |
| **EvolutionSandbox (ETAPA 8)** | ✅ **Ativo** (testes isolados antes de aplicar propostas) |
| **FineTuneDatasetCollector (ETAPA 9)** | ✅ **Ativo** (coleta pares JSONL para fine-tuning LoRA) |
| **FineTuneTriggerService (ETAPA 9)** | ✅ **Ativo** (disparo automático via OverwatchDaemon a cada 100 ticks/semana) |
| **Capabilities (cap_*.py) — Correção Crítica A** | ✅ **Corrigido** (78 arquivos: nomes de classe, imports e aliases inválidos) |
| **LLMRouter/AIGateway — Correção Crítica B** | ✅ **Unificado** (LLMRouter é a política; AIGateway é o executor) |
| Playwright Worker | 🔧 Em revisão |
| Instalador PyInstaller | 🔧 Em revisão |

---

## 🗂️ Estrutura de Pastas

```
app/
├── core/               # Nexus, NexusComponent, Config, Encryption, LLM config
├── domain/             # Lógica de negócio pura (modelos, serviços, AI, gears)
├── application/        # Casos de uso, portas (interfaces) e serviços
│   ├── ports/          # Interfaces que os adaptadores devem implementar
│   └── services/       # Serviços de aplicação (orchestrator, assistant, etc.)
├── adapters/           # Implementações das portas
│   ├── edge/           # Adaptadores de hardware (voz, teclado, automação)
│   └── infrastructure/ # Adaptadores de infraestrutura (LLM, DB, GitHub, API)
├── plugins/            # Sistema de plugins dinâmicos
├── runtime/            # Pipeline runner (orquestração declarativa)
└── utils/              # Utilitários gerais

.frozen/                # Arquivos não instanciados (aguardando uso)
├── caps/               # Capabilities não ativas
├── domain_adapters/    # Adaptadores que estavam no domain (movidos)
├── infrastructure/     # Duplicatas antigas de infrastructure
└── orphan_caps/        # Capabilities órfãs de app/adapters root
```

---

## 🧬 Nexus – Sistema de Injeção de Dependência

O **Nexus** (`app/core/nexus.py`) é o sistema central de instanciação.  
**Todos os componentes ativos devem ser NexusComponent e registrados no Nexus.**

A partir do refactoring estrutural, o Nexus foi dividido em quatro módulos focados:

| Módulo | Responsabilidade |
|---|---|
| `nexus.py` | Container principal, API pública |
| `nexus_exceptions.py` | CloudMock, exceções, timeouts, circuit breaker |
| `nexus_discovery.py` | Discovery em disco, localização e instanciação |
| `nexus_registry.py` | I/O do registry local `.jrvs` e sync com Gist |

- Componentes não instanciados pelo Nexus → movidos para `.frozen/`
- Registry local: `data/nexus_registry.json` / `data/nexus_registry.jrvs`
- Registry remoto: Gist do GitHub (sincronizado automaticamente)
- **Circuit Breaker:** import timeout 10 s, instantiation timeout 5 s, circuit open 30 s, reset 60 s.
- **Strict Mode:** `NEXUS_STRICT_MODE=true` desabilita discovery em disco.

---

## 🧠 Meta Layer – Cognição Adaptativa (Ativo)

O diretório `app/core/meta/` fornece a camada cognitiva do Nexus:

| Componente | Responsabilidade |
|---|---|
| `PolicyStore` | Persiste políticas por módulo em `.jrvs`; dispara recompilação ao atingir threshold |
| `JrvsCompiler` | Compila snapshots binários `.jrvs` por módulo com validação SHA-256 |
| `DecisionEngine` | Scoring multi-objetivo com epsilon-greedy adaptativo e guardrail de estabilidade |
| `ExplorationController` | Descobre novas ferramentas e gerencia promoção ao registro primário |

---

## 🧠 Memória Vetorial (Ativo desde 2026-03-03)

O JARVIS agora possui **memória biográfica persistente** via `VectorMemoryAdapter`:

- Implementa a porta `MemoryProvider` (`app/application/ports/memory_provider.py`).
- Usa **FAISS** (com fallback puro-Python offline) para busca por similaridade.
- Vetores gerados via bag-of-hashed-words (sem necessidade de modelo externo).
- A cada resposta, o `AssistantService` consulta os **30 dias anteriores** por contexto similar e armazena o comando do usuário e a resposta do JARVIS.
- Registrado no Nexus como `vector_memory_adapter`.

---

## 👁️ Visão Computacional (Ativo desde 2026-03-03)

O `VisionAdapter` (`app/adapters/infrastructure/vision_adapter.py`) permite que o JARVIS "veja":

- Captura silenciosa de screenshot (mss/Pillow) ou frame de webcam (OpenCV).
- Envia a imagem ao **Gemini 1.5 Flash** com o prompt: *"Descreva o contexto atual do usuário em 1 frase"*.
- Todas as dependências são opcionais (fallback `None` se indisponíveis).
- Registrado no Nexus como `vision_adapter`.

---

## 🔭 Overwatch Daemon – Núcleo Proativo (Ativo)

O `OverwatchDaemon` (`app/adapters/infrastructure/overwatch_adapter.py`) roda em background, independente do loop de comandos. Dividido em mixins focados:

| Mixin | Arquivo | Responsabilidade |
|---|---|---|
| `OverwatchDaemon` | `overwatch_adapter.py` | Daemon principal, coordena os mixins |
| `ResourceMonitor` | `overwatch_resource_monitor.py` | CPU/RAM reativo e preditivo (janela de 10 leituras) |
| `PerimeterMonitor` | `overwatch_perimeter.py` | Monitoramento tático de perímetro (MAC/ARP) |

| Monitoramento | Ação |
|---|---|
| CPU > 85% ou tendência ascendente | Alerta reativo e `[PROACTIVE_CORE][PREDICTIVE]` |
| RAM > 85% ou tendência ascendente | Alerta reativo e preditivo |
| Mudança em `data/context.json` | Recarrega contexto |
| Inatividade > 30 min | Usa `VisionAdapter` para verificar presença; se presente, sugere tarefa pendente |
| MAC/ARP desconhecido na rede | Alerta de intrusão tática |

Todas as ações são logadas com o prefixo `[PROACTIVE_CORE]`.  
Registrado no Nexus como `overwatch_daemon`.

## 🛠️ Self-Healing Local (Ativo)

O `LocalRepairAgent` é o primeiro estágio do pipeline de auto-reparo:

- Detecta e corrige erros comuns em < 1 s (sem chamar GitHub Actions).
- Suporta auto-instalação segura de dependências via `SAFE_AUTO_INSTALL` (frozenset).
- Integra com `ThoughtLogService` para rastreabilidade.
- Registrado no Nexus como `local_repair_agent`.

O `FieldVision` complementa o self-healing monitorando logs do sistema:

- Monitora `logs/jarvis.log` em busca de `ERROR`/`CRITICAL`.
- Classifica tipo de erro e aciona o workflow `homeostase.yml` via API do GitHub.
- Registrado no Nexus como `field_vision`.

---

## ✅ Auto-Evolução — Loop Completo com Gatekeeper (ETAPA 6)

O sistema de auto-evolução está **ativo** com loop completo:

- **Workflow:** `.github/workflows/auto_evolution_triggerV2.yml`
- **Schedule:** `0 2 * * *` (diário às 02:00 UTC) + `workflow_dispatch` manual
- **Pipeline:** MetaReflection → CapabilityManager → Gatekeeper (5 checks) → Proposta → PR
- **Gatekeeper:** 5 verificações: testes, estabilidade, frozen, núcleo, **sandbox**

---

## 🤖 JarvisDevAgent (ETAPA 7)

Agente autônomo de desenvolvimento do próprio JARVIS:

- Seleciona capability via `CapabilityManager.get_executable_capabilities()`
- Consulta `SemanticMemory` por soluções similares (few-shot)
- Gera código via `LLMRouter` com `task_type=code_generation`
- Submete ao `EvolutionGatekeeper` antes de criar PR
- Registra cada ciclo na `SemanticMemory` como `dev_cycle`
- **API:** `POST /v1/dev-agent/run` (assíncrono, retorna `job_id`)
- Registrado no Nexus como `jarvis_dev_agent`

---

## 🏖️ EvolutionSandbox (ETAPA 8)

Sandbox de execução isolada para propostas de código:

- Cria diretório temporário em `data/sandbox/<timestamp>/`
- Copia arquivo-alvo, aplica proposta e executa `pytest tests/ -x`
- Integrado ao `EvolutionGatekeeper` como 5ª verificação
- Configurável via `SANDBOX_ENABLED` no `.env` (padrão `true`)
- Registrado no Nexus como `evolution_sandbox`

---

## 🎓 Fine-Tuning Pipeline (ETAPA 9)

Infraestrutura para fine-tuning LoRA do modelo local:

- **`FineTuneDatasetCollector`:** coleta pares `(prompt, código)` com reward ≥ threshold
- **`FineTuneTriggerService`:** dispara quando há ≥ 50 novos pares
- **`OverwatchDaemon`:** executa o trigger a cada 100 ticks ou 1x/semana
- Dataset exportado em `data/finetune/dataset_<timestamp>.jsonl`
- Metadados em `data/finetune/trigger_latest.json`
- Registrados no Nexus como `finetune_dataset_collector` e `finetune_trigger_service`

---

## 🔧 Otimizações Fase 3

Aplicadas em 2026-03-06 (Blocos A, B e C):

### Bloco A — `__slots__` e Value Objects

- **A.1** `Intent`, `Command`, `Response` convertidos para `@dataclass(slots=True)` — redução de memória em criações de alta frequência.
- **A.2** `EvolutionReward` (SQLModel/Pydantic) — sem modificação (Pydantic gerencia slots internamente).
- **A.3** `ResourceReading @dataclass(slots=True)` adicionado ao `overwatch_resource_monitor.py`. `_cpu_history` / `_ram_history` mantidos para compatibilidade; novo `_resource_history: Deque[ResourceReading]` unifica cpu+ram+timestamp.
- **A.4** `WorkingMemoryEntry @dataclass(slots=True)` adicionado a `working_memory.py`. `push()` aceita tanto `dict` quanto `WorkingMemoryEntry`.

### Bloco B — Correções de Bugs

- **B.1** `execute()` movido para após `__init__` em `DependencyManager` e `GitHubCorrectionAdapter`.
- **B.2** `def execute(context=None):` → `def execute(self, context=None):` em 13 arquivos de `.frozen/domain_adapters/`.
- **B.3** `from app.core.nexuscomponent import NexusComponent` → `from app.core.nexus import NexusComponent` em 130 arquivos `.frozen/`.
- **B.4** Cache TTL de 30 s adicionado a `_load_capabilities_json()` no `CapabilityManager`.
- **B.5** `LLMConfig` convertido para classmethods dinâmicos (`use_llm_command_interpretation()`, etc.). Aliases de classe mantidos para retrocompatibilidade.
- **B.6** `EvolutionSandbox`: timestamp do diretório sandbox ganhou sufixo `uuid4().hex[:8]` para unicidade absoluta.
- **B.7** `POST /v1/dev-agent/run`: retorna HTTP 429 se `JarvisDevAgent` já estiver em execução (`_agent_running` flag em módulo).

### Bloco C — Melhorias de Qualidade

- **C.1** `WorkingMemory`: adicionados `__iter__`, `__bool__` e `to_list()`. Testes cobrindo os novos métodos em `tests/test_memory_modules.py`.
- **C.2** `SemanticMemory.query_facts()`: parâmetro opcional `keyword: str` para busca por substring (case-insensitive). Testes adicionados.
- **C.3** `CapabilityManager.get_evolution_progress()`: campo `critical_path_length` adicionado ao retorno.
- **C.4** `EvolutionGatekeeper`: rejeições persistidas em `data/gatekeeper_rejections.jsonl` com campos `timestamp`, `reason`, `check_failed`, `files_modified`.

---
