# 🗺️ Orientação ao Agente/LLM — JARVIS

**Versão:** 1.0.0
**Atualizado em:** 2026-03-10

> Este documento não existe para o humano ler besteira.
> Ele existe para o agente/LLM entender o repo como um todo, saber onde
> está o que, e saber como o **Nexus** direciona a composição/execução
> do sistema.

---

## Rota remota principal: RDC → Aperture → Tailscale → Jarvis

**Prioridade P0.** Ao ligar o PC, o Tailscale deve conectar automaticamente à tailnet. Agentes compatíveis com MCP e autorizados usam o gateway do Aperture: `https://aperture.tail350144.ts.net/v1/mcp`. O conector `jarvis` do Aperture encaminha as chamadas ao upstream privado `https://multimetal.tail350144.ts.net/mcp`, publicado pelo Tailscale Serve para o servidor local `127.0.0.1:8765`.

O Aperture centraliza grants e exposição de ferramentas; as ACLs/identidade do Tailscale limitam o alcance de rede. “Qualquer agente” significa qualquer agente compatível e autorizado, não acesso público irrestrito.

RDC diretamente ao bridge JSONL e Aperture diretamente ao upstream Jarvis são alternativas para situações específicas, por exemplo diagnóstico local ou quando a rota principal não pode ser usada. Não são a metodologia padrão. A sessão visual do Windows ainda precisa estar acessível para ferramentas que controlam a interface gráfica.

Detalhes, boot, segurança e critérios de aceitação: `docs/ACESSO_REMOTO_RDC_APERTURE_TAILSCALE.md`.


## 1) O que é este repositório

JARVIS é um sistema assistente/autônomo Python, organizado em 5 camadas:

```
Interface / CI-CD
Adapters (Infra/Edge)
Application (Services)
Domain (Core)
Core (Nexus DI)
```

O coração do sistema é o **Nexus**, container de injeção de dependência que
resolve componentes pelo ID, com circuit breaker e fallback automático.

O sistema também tem uma camada de **auto-evolução e desenvolvimento
autônomo** (JarvisDevAgent, AdapterRegistry, PipelineBuilder, sandboxes),
mas isso é opcional para o agente ler de uma vez: prima com o que existe,
descobre gaps, e só cria código quando necessário.

---

## 2) Mapa rápido do repo

### Raiz
- `main.py` — ponto de entrada principal
- `serve.py` — variante de bootstrap/server
- `Makefile` — tarefas de dev/formatting/lint/test
- `.env.example` — modelo de configuração
- `Dockerfile` — containerização
- `setup.py` — empacotamento
- `requirements.txt` — dependências de referência

### Camadas de código

#### `app/core/`
- `nexus.py` — container DI principal, API pública
- `nexus_exceptions.py` — CloudMock, circuit breaker, exceções customizadas
- `nexuscomponent.py` — classe base de todos os componentes
- `nexus_registry.py` — I/O do registry local `.jrvs` e sync com Gist
- `nexus_discovery.py` — descoberta em disco, instanciação com timeout
- `config.py` — configuração via environment
- `encryption.py` — utilitários de criptografia relacionados ao sistema
- `meta/*.py` — policy_store, jrvs_compiler, decision_engine, exploration_controller

#### `app/domain/`
- `capability_manager.py` — gerenciamento de capabilities
- `memory/` — semantic, procedural, working, prospective
- `models/agent.py` — Action, Observation, Task (JarvisDevAgent)
- `models/adapter_registry.py` — registro de adapters
- `services/` — command_interpreter, intent_processor, system_state_tracker,
  reward_signal_provider, safety_guardian

#### `app/application/`
- `services/assistant_service.py` — serviço central do assistente
- `services/evolution_orchestrator.py` — orquestração de auto-evolução
- `services/evolution_gatekeeper.py` — aprovação de mudanças
- `services/evolution_sandbox.py` — sandbox local de testes
- `services/jarvis_dev_agent/agent.py` — agente autônomo de desenvolvimento
  (pacote `services/jarvis_dev_agent/`; o antigo módulo único virou o pacote,
  com os caminhos de artefatos em `__init__.py` para permitir override em runtime)
- `services/llm_router.py` — roteamento dinâmico de LLMs
- `services/consolidated_context_service.py` — snapshot do código
- `services/thought_log_service.py` — log de pensamentos
- `services/field_vision.py` — monitor proativo de logs
- `services/metabolism_core.py` — núcleo de metabolismo/LLM fleet
- `services/crystallization/crystallizer_engine.py`
- `services/local_repair_agent.py`
- `services/notification_service.py`
- `security/` — capability_authorizer, pii_redactor, env_secrets_provider, safety_guardian

#### `app/adapters/infrastructure/`
- `telegram_adapter.py`
- `github_adapter.py` / `github_worker.py`
- `drive_uploader.py`
- `gist_uploader.py`
- `consolidator.py`
- `docker_sandbox.py`
- `evolution_sandbox.py`
- `ollama_adapter.py`, `gemini_adapter.py`, `gateway_llm_adapter.py`
- `ai_gateway.py` e submódulos
- `persistent_shell_adapter.py`
- `vector_memory_adapter.py`
- `vision_adapter.py`
- `overwatch_adapter.py` e submódulos
- `system_executor.py`
- `audit_logger.py`
- `auth_adapter.py`
- `interface_bridge.py`
- `context_memory.py`
- `orchestrator_service.py`

#### `app/runtime/`
- `pipeline_runner.py` — executor de pipelines YAML

#### `config/`
- `pipelines/*.yml` — pipelines declarativos

#### `data/`
- `nexus_registry.json` — registry do Nexus (o `.jrvs` correspondente é criado sob demanda)
- `capabilities.json` — inventário de capabilities (fallback quando o `.jrvs` não existe)
- `context.json` — estado atual do sistema
- `architecture_rules.yml` — regras de destino da cristalização
- `master_crystal.json` — metadados de cristalização
- `dev_agent_jobs.jsonl` — auditoria dos ciclos do JarvisDevAgent
- `experience_replay.jsonl` / `gatekeeper_rejections.jsonl`
- `jrvs/` — espelhos `.jrvs` + `.json` (llm, meta, tools)
- `evolution_proposals/` — criado em runtime (propostas de mudança)

#### `scripts/`
- `cristalize_project.py`
- `evolve_all_pending.py`
- `migrate_to_nexus_di.py`
- `validate_architecture.py`
- `validate_self_awareness.py`
- submódulos de auto-fixer

#### `docs/`
- `README.md`
- `STATUS.md`
- `ARQUIVO_MAP.md`
- `ARCHITECTURE.md`
- `NEXUS.md`
- `PIPELINE_RUNNER.md`

#### `tests/`
- domain, application, adapters, security, privacy, integration

---

## 3) Como o Nexus direciona a composição/execução

### Contratos públicos do Nexus

O Nexus é o ponto principal pelo qual o agente deve pensar ao descobrir ou
executar algo no sistema.

Importação:

```python
from app.core.nexus import nexus
```

Resolução:

```python
component = nexus.resolve(component_id, use_cache=True)
```

Lista carregada:

```python
ids = nexus.list_loaded_ids()
```

Invalidação de cache:

```python
nexus.invalidate_component(component_id)
```

Persistência de estado:

```python
nexus.commit_memory()
```

### Como a resolução funciona

O Nexus:
- resolve componentes pelo ID,
- usa discovery em disco por `hint_path` quando relevante,
- aplica timeout de import e instanciação,
- injeta `CloudMock` quando um componente falha ou não está disponível,
- aplica circuit breaker.

Isso significa que o agente **não deve supor** que cada componente está
obrigatoriamente disponível como uma implementação real. O resultado de
`resolve()` pode ser um `CloudMock`.

Documentação associada:
- `docs/NEXUS.md`
- `app/core/nexus.py`
- `app/core/nexus_exceptions.py`
- `app/core/nexus_discovery.py`
- `app/core/nexus_registry.py`
- `app/core/nexuscomponent.py`

### Tabela mental de IDs comuns

O agente pode usar isso como ponto de partida para inspecionar o que existe.

Esses IDs são documentados ou observados no sistema. Nem todo ID é exportação
pública no registry: alguns são usados internamente pelo agente/assinante
(por exemplo `evolution_gatekeeper`, acionado pelo `evolution_orchestrator`).

Lista completa e atualizada está em:

- `data/nexus_registry.json`
- `docs/ARQUIVO_MAP.md`
- `docs/NEXUS.md`

| ID | O que é |
|----|---------|
| `assistant_service` | serviço central do assistente |
| `evolution_orchestrator` | orquestração de auto-evolução |
| `metabolism_core` | núcleo de metabolismo/LLM fleet |
| `llm_router` | roteamento de LLMs |
| `telegram_adapter` | interface Telegram |
| `github_adapter` | interface GitHub |
| `github_worker` | worker de operações GitHub |
| `consolidator` | consolidador de contexto |
| `crystallizer_engine` | cristalização do codebase |
| `structured_logger` | logger estruturado |
| `jarvis_dev_agent` | agente autônomo de desenvolvimento |
| `adapter_registry` | registro simplificado de adapters |
| `docker_sandbox` | sandbox Docker |
| `evolution_gatekeeper` | aprovação/rejeição de mudanças propostas |
| `procedural_memory_adapter` | memória procedural de soluções |
| `consolidated_context_service` | snapshot do código consolidado |
| `capability_manager` | gerenciamento de capabilities |
| `procedural_memory` | memória de padrões |
| `semantic_memory` | memória de eventos |

---

## 4) Funções únicas e centrais que o agente deve conhecer

### JarvisDevAgent

Agente autônomo de desenvolvimento. Ele é o exemplo mais direto de como o
sistema pensa em "executar tarefas de desenvolvimento".

Responsabilidade:
- analisar a solicitação,
- descobrir o que já existe via AdapterRegistry,
- criar código apenas se houver gap,
- testar em sandbox,
- aprender com a interação em ProceduralMemory,
- criar pipelines YAML reutilizáveis.

### AdapterRegistry

Registro simplificado de adapters. É o mecanismo de "o que existe?" antes de
criar qualquer coisa.

Responsabilidade:
- listar adapters,
- verificar existência,
- detectar gaps por capacidade.

### PipelineBuilder

Cria pipelines YAML para o Pipeline Runner.

Responsabilidade:
- gerar pipelines declarativos,
- integrar com o Pipeline Runner existente,
- suportar multi-step pipelines.

### Pipeline Runner

Executa pipelines YAML.

Responsabilidade:
- ler pipeline declarativo,
- resolver componentes via Nexus,
- executar em ordem,
- aplicar strict mode quando configurado.

Documentação associada:
- `app/runtime/pipeline_runner.py`
- `config/pipelines/`
- `docs/PIPELINE_RUNNER.md`

### Consolidador

Gera snapshots consolidados do contexto do sistema para downstream (Drive,
Telegram, Gist, etc).

### Circuit Breaker / CloudMock

Proteção transparente: se um componente não pode ser resolvido, o Nexus
retorna um `CloudMock`. O agente deve tratar isso como uma falha de
disponibilidade real, não como "o componente não existe no código".

---

## 5) Regras básicas que o agente deve respeitar

### 5.1) Execução segue autoridade

O fluxo obrigatório de execução de capabilities é:

```
AssistantService → CapabilityAuthorizer → Executor
```

Nenhuma capability deve ser executada diretamente sem autorização prévia.

### 5.2) Capabilities sensíveis exigem confirmação humana

Capabilities classificadas como sensíveis exigem `human_confirmed: true` no
payload de execução.

As sensíveis listadas no documento de guardrails incluem:

- `system_executor`
- `auto_evolution`
- `github_worker`
- `pyinstaller_builder`
- `drive_uploader`
- `gist_uploader`

### 5.3) Segredos têm porta obrigatória

Nenhum módulo deve usar `os.environ` diretamente para recuperar segredos.
O ponto de acesso autorizado é a porta `SecretsProvider`, e o único leitor
autorizado de `os.environ` para segredos é `EnvSecretsProvider`.

### 5.4) PII tem pipeline obrigatório

Nenhum dado bruto de PII deve ser indexado no vector store. O fluxo obrigatório é:

```
Entrada → PiiRedactor → Embedding → FAISS
```

Categorias de PII de interesse: email, CPF, telefone.

### 5.5) Publicação é responsabilidade do CI/CD

O código não publica.

Publicação é feita exclusivamente no CI/CD (artifact upload, release, etc).
O pipeline descreve. O runner orquestra. O código executa.

### 5.6) Caminhos sensíveis têm proteção especial

Mudanças auto-aprovadas não devem tocar cegamente em:

- `capabilities/`
- `app/adapters/infrastructure/` (arquivos relacionados à execução)
- `app/application/security/`

Alterações em arquivos de capability exigem revisão humana.

### 5.7) Testes são obrigatórios em caminhos de segurança

Componentes relacionados à segurança devem ter testes dedicados.
PRs que tocam caminhos de execução de capability exigem testes de segurança
passando.

### 5.8) Evolução tem gatekeeper

Antes de aprovar mudanças no código, o sistema aplica verificações como:

- cobertura de testes
- estabilidade recente
- proteção de arquivos frozen
- proteção do núcleo
- sandbox de validação

O agente deve manter essa ideia em mente ao sugerir ou gerar alterações.

---

## 6) O que o agente deve checar antes de tocar em algo

Antes de ler ou alterar qualquer coisa, o agente deve preferir:

1. perguntar ao Nexus o que existe:
   - `nexus.resolve(id)`,
   - `nexus.list_loaded_ids()`,
2. usar o AdapterRegistry para descobrir adapters existentes,
3. checar `docs/ARQUIVO_MAP.md` para ver onde um arquivo pode estar,
4. checar `docs/NEXUS.md` para ver se um componente é registry-driven,
5. checar `docs/STATUS.md` para ver estágio atual do projeto,
6. checar pipelines em `config/pipelines/` se o objetivo é orquestrar,
7. checar `docs/padrão_estrutural.md` se o objetivo é criar ou alterar um pipeline.

---

## 7) Formatos e artefatos que o agente pode encontrar

- registry local: `data/nexus_registry.json` (o espelho `data/nexus_registry.jrvs`
  é criado sob demanda pelo `document_store`)
- inventário de capabilities: `data/capabilities.json` (consumidores como
  `evolve_all_pending.py` e `AutoEvolutionServiceV2` caem para o `.json` quando o
  `.jrvs` não existe)
- contexto atual: `data/context.json`
- regras de arquitetura: `data/architecture_rules.yml`
- jobs do agente: `data/dev_agent_jobs.jsonl`
- propostas de evolução: `data/evolution_proposals/`
- snapshots: `data/jrvs-snapshots/`
- logs: `data/logs/`

Regra prática:
- `.json`/`.yml` são a fonte de verdade legível.
- `.jrvs` é maintainido por tradução automática.

---

## 8) Documentação de referência

Se o agente precisar aprofundar, a ordem sugerida é:

1. `docs/NEXUS.md`
2. `docs/ARCHITECTURE.md`
3. `docs/ARQUIVO_MAP.md`
4. `docs/STATUS.md`
5. `docs/PIPELINE_RUNNER.md`
6. `SECURITY_GUARDRAILS.md`
7. `padrão_estrutural.md`
8. `CONTRIBUTING.md`
9. `CHANGELOG.md`

---

## 9) Resumo de uma linha para o agente

Este repo é um sistema Python autônomo/documentado/resolvido-pelo-Nexus.
O agente deve resolver antes de criar, checar existência antes de declarar
gap, tratar CloudMock como indisponibilidade real, e não publicar nada pelo
código.
