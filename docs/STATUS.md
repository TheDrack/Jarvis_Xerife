# JARVIS – Status Atual do Projeto

> **Data:** 2026-03-06  
> **Situação geral:** Reorganização estrutural concluída. Refactoring de módulos grandes finalizado.

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
| **Overwatch Daemon (Núcleo Proativo)** | ✅ **Ativo** (CPU/RAM preditivo, perímetro tático) |
| **LocalRepairAgent (Self-Healing Local)** | ✅ **Ativo** (primeiro estágio, < 1 s) |
| **EvolutionOrchestrator** | ✅ **Ativo** (loop agêntico registrado no Nexus) |
| **OllamaAdapter (LLM local)** | ✅ **Ativo** (code_generation, self_repair) |
| **CostTracker (auditoria LLM)** | ✅ **Ativo** (SQLite, EMA por modelo) |
| **ProceduralMemory** | ✅ **Ativo** (índice vetorial de soluções) |
| **CapabilityIndexService** | ✅ **Ativo** (busca semântica top-k, EMA reliability) |
| Auto-Evolução (loop completo) | ⏸️ **PAUSADA** (reorganização em curso) |
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



Arquivos em `.frozen/` são código não utilizado atualmente.  
Eles ficam preservados até que sejam necessários.  
Para reativar um arquivo frozen:
1. Mova-o para o local correto em `app/`
2. Registre-o no Nexus via `data/nexus_registry.json`
3. Atualize esta documentação

---

## ⏸️ Auto-Evolução (PAUSADA)

O sistema de auto-evolução está **pausado** enquanto a reorganização estrutural é concluída.

- Workflow: `.github/workflows/auto_evolution_triggerV2.yml`
- Status: `workflow_dispatch` apenas (requer acionamento manual)
- Para reativar: revisar estrutura → estabilizar → remover pausa

---

## 🚧 Pendências

- [ ] Revisar `app/domain/gears/` – alguns `cap_*_core.py` pendentes de revisão
- [ ] Revisar `app/domain/capabilities/` – necessita limpeza
- [ ] Playwright Worker necessita revisão de integração
- [ ] Reativar auto-evolução completa após estabilização
