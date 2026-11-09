# Changelog

All notable changes to the Jarvis Assistant project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

#### Grafo OSINT — aresta persistida por escopo (2026-11-06)

- `GraphStorePort.get_edge(edge_id, scope_id=None)` e
  `SQLiteGraphStore.get_edge`: busca uma aresta pelo id derivado,
  opcionalmente restrita ao escopo. Recusa silenciosa não existe: id
  desconhecido ou fora do escopo retorna `None`.
- `app/application/services/graph_store_setup.py`: `graph_db_path()` lê
  `JARVIS_GRAPH_DB` (padrão `jarvis_graph.sqlite` na raiz do repositório) e
  `get_graph_store()` abre o `SQLiteGraphStore` uma vez por processo;
  `reset_graph_store()` fecha no shutdown/testes.
- `osint.graph.explain` agora aceita `edge_id` + `scope_id` em vez do dump:
  carrega a aresta e os dois endpoints do store e recalcula a confiança
  canônica, com `resolved_from: "store"`. Id inexistente ou de outro escopo
  retorna `success: false`/`LookupError`; `edge` e `edge_id` juntos ou
  ausentes são recusados.
- Testes: busca escopada no store, wiring singleton/caminho e resolução da
  aresta persistida com recálculo, isolamento de escopo e exclusividade da
  fonte.
- `osint.ip.enrich` passa a persistir o delta (nós antes das arestas) no store
  durável e devolve `persisted` com inseridos/duplicados; `persist=false`
  mantém a chamada sem estado. Falha de disco não descarta a evidência: a
  expansão continua em `success: true` e o erro aparece em `persisted`.
- `JARVIS_GRAPH_DB` entra na allowlist de `intelligence.env` do desktop e é
  documentado em `desktop/README.md`.

#### Grafo OSINT — `osint.graph.explain` via MCP (2026-11-06)

- `app/adapters/edge/osint_mcp_tools.py`: ferramenta atômica `osint.graph.explain`
  que explica uma aresta sem rede nem estado: recebe o dump da `Edge` e,
  opcionalmente, os descritores dos nós de origem/destino. Revalida a aresta
  (id derivado, limites, teto de pivô fraco), expõe `selector_used`, `source`,
  fator do pivô, fator de escopo cruzado e teto de pivô fraco, e recalcula a
  confiança canônica quando os dois endpoints são informados.
- Divergência entre confiança informada e recalculada não é corrigida em
  silêncio: retorna `consistent: false` com o `expected` e o check
  `expected_confidence` reprovado. Endpoints com id divergente, `same_scope`
  falso e `selector_used` que não é o literal de um endpoint aparecem como
  checks/caveats.
- `tests/adapters/edge/test_osint_mcp_tools.py`: cobre aresta coerente, modo
  sem endpoints, confiança incoerente, id forjado, penalidade de escopo
  cruzado e teto do pivô fraco.

#### Grafo OSINT — `osint.ip.enrich` via MCP (2026-11-06)

- `app/adapters/edge/osint_mcp_tools.py`: ferramenta atômica `osint.ip.enrich`
  que expande um IP **um salto** pelo `get_graph_expander_registry()` de
  produção, sem cascatear para o loop e sem tocar em adapters diretamente.
  Aceita `radius_km`, `scope_id` e um filtro opcional de `capabilities`;
  devolve `nodes`, `edges`, quais expanders rodaram, as capabilities
  bloqueadas por rate limit e o `gap` para nós `IP`. IP inválido é recusado
  pela normalização do `Node`; ausência de expander retorna o gap em vez de
  inventar capacidade.
- `tests/adapters/edge/test_osint_mcp_tools.py`: cobre registro, expansão de
  um salto, filtro por capability, `RateLimitExceeded` reportado sem abortar
  o restante e o caso sem expanders.

#### Grafo OSINT — Fase 3: composição de produção (2026-11-06)

- `app/application/services/graph_expander_setup.py`:
  `configure_graph_expanders(registry, adapters=...)` monta os cinco expanders
  a partir do `OSINTAdapterRegistry` já configurado, sem instanciar adapter,
  ler credencial ou fazer rede. Só registra expander de provider disponível.
- `DEFAULT_RATE_LIMITS` por capability (IPinfo/ASN 60/min, consultas
  geográficas 6/min, WiGLE 4/min), aplicados apenas às capabilities
  registradas; `ExpanderRegistry.rate_limit()` expõe a janela configurada.
- `get_graph_expander_registry()`: entrada de produção preguiçosa e
  process-local, reutilizando `get_osint_registry()` e o cache do Nexus.

#### Grafo OSINT — Fase 3: expanders de infraestrutura (2026-11-06)

- `app/adapters/infrastructure/osint/expanders.py`: `IPInfoExpander` (IP →
  `COORDINATE` + `ASN`, com `geo_confidence` limitado a 0.3 para conexão móvel
  ou proxy; `ORG` só como efeito observável derivado pelo `Resolver`),
  `CensysExpander`/`ShodanExpander` (coordenada/CIDR → `HOST`),
  `WigleExpander` (centro + raio → `SIGNAL`) e `AsnExpander` (IP/ASN/ORG →
  `CIDR`). Nenhum adapter novo de rede: os expanders reutilizam `IPInfoAdapter`,
  `CensysAdapter`, `ShodanAdapter` e `WigleAdapter`.
- `CensysExpander` e `ShodanExpander` compartilham a capability
  `osint.passive.geo_query` e o mesmo contrato de saída: trocar um pelo outro
  não muda o pipeline. Todo `HOST` produzido carrega `geo_confidence`, mesmo
  0.0 quando não há coordenada.
- `ExpanderRegistry.set_rate_limit` com `RateLimit` (janela deslizante por
  capability, compartilhada entre chamadas) e `RateLimitExceeded`.
- `EnrichmentLoop` para com `STOP_RATE_LIMITED` e reporta
  `rate_limited_capabilities`, sem descartar o grafo já construído.
- Fixtures JSON em `tests/fixtures/osint/` e testes com `httpx.MockTransport`
  para os cinco expanders, incluindo a equivalência Censys ↔ Shodan e a
  conversão centro+raio → bbox dentro do adapter WiGLE.

#### Grafo OSINT — Fase 2: expanders, loop e fusão (2026-11-06)

- `app/domain/graph/expander.py`: `ExpanderSpec` (name, accepts, produces,
  capability, cost, active, legal_gated), `Expansion` e o protocolo `Expander`.
- `app/domain/graph/registry.py`: `ExpanderRegistry` com `find_expanders`
  (tipo + capability + gate) e `find_gap`, que separa `missing` de `gated`
  (flag desligada ou `legal_gated` não é falha; `ready` só olha `missing`).
- `app/domain/graph/loop.py`: `EnrichmentLoop` com fila de prioridade
  determinística (`prior`), orçamento, profundidade, `min_confidence` e
  parada por estagnação de cobertura.
- `app/domain/graph/fuse.py`: `Fuse.apply` marca `interest` em
  `{confirmed, discrepancy, novel}` com regras geo (haversine, limiar de 50 km)
  e relacionais (mesmo pivô com seletor divergente; pivô distinto corrobora).
- `app/application/services/graph_enrichment.py`: executa o loop por escopo,
  aplica `Resolver.derive_person_org` e persiste apenas o que é novo.
- `Node.interest` e `Edge.interest`, persistidos no store principal e no cofre.

#### Grafo OSINT — Fase 1: persistência, derivação e retenção (2026-11-06)

- `app/domain/graph/graph.py`: `Graph` imutável com integridade referencial e
  export JSON determinístico; `GraphDelta` para lotes parciais de adapter.
- `app/application/ports/graph_store.py`: `GraphStorePort` e `UpsertReport`
  (`inserted`/`duplicates`), mantendo o domínio independente de SQLite.
- `app/adapters/infrastructure/graph/store.py`: `SQLiteGraphStore` com índices
  `(type, selector, scope_id)`, `src`, `dst`, `pivot` e `scope_id`; upsert
  idempotente; recusa nós sensíveis; exporta subgrafo por `scope_id` em JSON.
- `app/domain/graph/resolver.py`: `Resolver.merge` (dedup estrutural e recusa de
  `PERSON`/`ORG` vindos de adapter) e `Resolver.derive_person_org` — cluster de
  identidade por ≥ 2 seletores ou pivô forte; `ORG` por sufixo de domínio,
  `whois_registrant`, e-mail corporativo, ASN e razão social de CNPJ; ligação
  `PERSON → ORG` por e-mail corporativo e `cnpj_owner`.
- `app/domain/graph/sensitive_store.py` e
  `app/adapters/infrastructure/graph/sensitive_store.py`: cofre separado com TTL
  curto e log de acesso append-only que nunca registra o seletor.
- `app/domain/graph/pruner.py`: TTL por tipo, `min_confidence`, movimentação de
  nós sensíveis para o cofre e agregação de densidade `SIGNAL → SIGNAL_SET`.
- `app/application/services/graph_retention.py`: aplica o `Pruner` e persiste
  remoções e agregações no `GraphStorePort`.
- `Node.last_seen` (retenção por TTL) e o pivô `domain_owner`, exigido pelas
  arestas `DOMAIN → ORG` da regra de derivação de organização.

#### Fundação do grafo OSINT — Fase 0 (2026-11-06)

- `app/domain/graph/nodes.py`: `Node` imutável com identidade derivada
  `sha256(type, seletor normalizado, scope_id)` e `NodeType` completo. Cada
  tipo tem um normalizador único (e-mail lowercase, CNPJ só dígitos com
  dígitos verificadores, domínio IDNA, BSSID hex lower, coordenada com
  precisão fixa). `CPF` não existe como tipo; só `CPF_HASH`, sempre
  `sensitive`, e o seletor precisa ser um digest `sha256:`.
- `app/domain/graph/edges.py`: `Edge` imutável carregando `selector_used`,
  `source` e `confidence`, com id derivado da evidência. `PivotType` cobre
  infraestrutura, identidade e pivôs brasileiros; `vehicle_owner` nasce
  `pivot_weak` com teto de confiança 0.4.
- `app/domain/graph/confidence.py`: tabela `PIVOT_FACTOR` como fonte única de
  confiança, `edge_confidence(src, dst, pivot)` com penalidade de escopo
  cruzado e `STRONG_PIVOTS` (`commit_email`, `whois_registrant`, `cnpj_owner`)
  para o `Resolver` da Fase 1.
- `app/domain/graph/policy.py`: `ScopePolicy` (escopo obrigatório e gate de
  pivô sensível) e `SensitivityPolicy` (HMAC-SHA256 de CPF com pepper, nó
  `CPF_HASH` e recusa de CPF em texto claro).
- `tests/domain/graph/`: testes de normalização por tipo, identidade
  determinística, imutabilidade, tabela de confiança e políticas.

#### Auditoria de entregas (2026-10-16)

- `docs/VERIFICACAO_ENTREGAS.md`: confronta cada promessa da documentação (README,
  STATUS, NEXUS, SECURITY_GUARDRAILS, AUTORREGULACAO, padrões) com evidência
  executável, classificando em entregue / parcial / não entregue. Achados
  principais: métrica de capabilities conta stubs (78/102), ciclo de evolução não
  detecta código existente, `AdapterRegistry` sem consumidor, `CapabilityAuthorizer`
  fora do fluxo principal, `DockerSandbox` órfão e 35 arquivos acima de 300 linhas.
- `tests/test_nexus_docs_contract.py`: garante que a tabela de timeouts do
  `docs/NEXUS.md` continue igual aos defaults de `app/core/nexus_exceptions.py`.

#### Teste de contrato da documentação (2026-10-16)

- `tests/test_docs_references.py` extrai as referências a arquivos (`.py`, `.yml`,
  `.md`, …) de `README.md`, `docs/AGENT_GUIDE.md`, `docs/STATUS.md`,
  `docs/NEXUS.md`, `docs/PIPELINE_RUNNER.md` e `scripts/README.md` e falha quando
  alguma aponta para um arquivo/script/workflow inexistente — a classe de erro que
  já colocou `scripts/evolution_mutator.py`, `pipeline_builder.py` e
  `ci-failure-to-issue.yml` na documentação.
- Resolve caminhos relativos ao documento (`../ARCHITECTURE.md`), ao root e formas
  abreviadas (`services/assistant_service.py`); ignora badges/URLs e placeholders
  (`config/pipelines/<nome>.yml`).
- Exceções (artefatos gerados em runtime, nomes usados em exemplos de log) ficam em
  `_ALLOWED_MISSING`, cada uma com motivo, e são auditadas: exceção que voltou a
  existir ou que nenhum doc usa mais reprova o teste.
- `docs/ARQUIVO_MAP.md` fica fora do contrato por ser gerado pelo `scripts/autodoc.py`.

#### Refactoring Estrutural – Split de Módulos Grandes (2026-03-06)

**Objetivo:** Nenhum arquivo de código deve ultrapassar 300 linhas. Cada responsabilidade em seu próprio módulo, respeitando o contrato Nexus.

**`app/core/nexus.py`** – dividido em 4 módulos:
- `nexus_exceptions.py`: `CloudMock`, `_CircuitBreakerEntry`, exceções customizadas (`ImportTimeoutError`, `InstantiateTimeoutError`, `AmbiguousComponentError`), timeouts configuráveis (`NEXUS_IMPORT_TIMEOUT=10s`, `NEXUS_INSTANTIATE_TIMEOUT=5s`, `CIRCUIT_BREAKER_TIMEOUT=30s`).
- `nexus_discovery.py`: `_NexusDiscoveryMixin` – busca em disco, localização de classes e instanciação com timeout.
- `nexus_registry.py`: `_NexusRegistryMixin` – I/O do registry local `.jrvs` e sync com GitHub Gist.

**`app/adapters/infrastructure/ai_gateway.py`** – dividido:
- `ai_gateway_enums.py`: Enums `LLMProvider` e `GroqGear`.
- `ai_gateway_token_utils.py`: Utilitários de contagem de tokens (tiktoken + fallback).

**`app/adapters/infrastructure/gateway_llm_adapter.py`** – dividido:
- `auto_repair_mixin.py`: Lógica de auto-reparo (análise com Gemini, abertura de PRs).

**`app/adapters/infrastructure/gemini_adapter.py`** – dividido:
- `gemini_response_helpers.py`: Funções utilitárias de resposta e mapeamento para objetos de domínio.

**`app/adapters/infrastructure/github_adapter.py`** – dividido:
- `github_correction_adapter.py`: Criação de PRs de correção automática.
- `github_issue_adapter.py`: CRUD de issues.
- `github_issue_mixin.py`: Mixin para reportar falhas de infraestrutura como issues.
- `github_workflow_adapter.py`: Monitoramento de workflow runs.

**`app/adapters/infrastructure/overwatch_adapter.py`** – dividido:
- `overwatch_resource_monitor.py`: `ResourceMonitor` mixin – CPU/RAM reativo e preditivo.
- `overwatch_perimeter.py`: `PerimeterMonitor` mixin – monitoramento tático MAC/ARP.

**`app/application/services/capability_manager.py`** – dividido:
- `capability_blueprint_service.py`: Geração de blueprints e validação de recursos.
- `capability_detectors.py`: Funções standalone de detecção de capabilities.
- `capability_gap_reporter.py`: Relatório de gaps via PR.

**`app/application/services/device_service.py`** – dividido:
- `device_capability_service.py`: Roteamento por capacidade.
- `device_location_service.py`: Cálculo de distância geográfica (Haversine).

**`app/application/services/llm_capability_detector.py`** – dividido:
- `llm_capability_prompt_builder.py`: Construção de prompts.

**`scripts/auto_fixer_logic.py`** – dividido em módulos focados:
- `scripts/fix_applier.py`: I/O de arquivos, Copilot CLI, validação pytest.
- `scripts/issue_parser.py`: Classificação de issue e localização de arquivo.
- `scripts/pr_manager.py`: Git/GitHub ops (branch, commit, push, PR, issue lifecycle).

#### Self-Healing Pipeline (2026-03-04)

- `app/application/services/local_repair_agent.py`: `LocalRepairAgent` – primeiro estágio do pipeline de auto-reparo local (< 1 s, sem CI). Detecta e corrige erros comuns, auto-instala dependências via `SAFE_AUTO_INSTALL` (frozenset). Registrado no Nexus como `local_repair_agent`.
- `app/application/services/field_vision.py`: `FieldVision` – monitor de logs com ciclo de homeostase. Aciona `homeostase.yml` ao detectar `ERROR`/`CRITICAL`.
- `app/adapters/infrastructure/ollama_adapter.py`: Integração com LLMs locais via Ollama para `code_generation`/`self_repair`. Registrado como `ollama_adapter`.



**Fase 1 – Estabilização de Infraestrutura**
- `app/core/nexus.py`: Adicionado `CloudMock` – absorvedor transparente injetado automaticamente quando um componente falha. Corrige `ImportError` em `intent_processor.py` (`from app.core.nexus import CloudMock`).
- `app/core/nexus.py`: Implementado **Circuit Breaker** no `JarvisNexus.resolve()`: timeout de 2 s abre o circuito, `CloudMock` retornado por 60 s, após o qual o circuito fecha e a instanciação é tentada novamente.
- `scripts/state_machine.py`: Novo `ErrorCategory` enum. `identify_error()` agora distingue `ENVIRONMENT_ERROR` (`PermissionError`, `FileNotFoundError: No such file or directory`, `OSError`, etc.) de `CODE_ERROR` — erros de ambiente pausam o sistema sem mutar código.
- `scripts/auto_fixer_logic.py`: Importa e usa `ErrorCategory`; `run_with_state_machine()` registra e pausa em erros de ambiente em vez de tentar auto-correção.

**Fase 2 – Memória Biográfica Vetorial**
- `app/application/ports/memory_provider.py`: Nova porta `MemoryProvider` com métodos `store_event()`, `query_similar()` e `clear()`.
- `app/adapters/infrastructure/vector_memory_adapter.py`: Adaptador `VectorMemoryAdapter` – armazena eventos como vetores (FAISS com fallback puro-Python offline). Registrado no Nexus como `vector_memory_adapter`.
- `app/application/services/assistant_service.py`: `process_command()` consulta a memória vetorial (últimos 30 dias) antes de cada resposta e armazena comando + resposta do LLM como vetores após cada interação.
- `requirements.txt`: Adicionadas dependências `numpy>=1.24.0` e `faiss-cpu>=1.7.4`.

**Fase 3 – Expansão Sensorial (Visão Computacional)**
- `app/adapters/infrastructure/vision_adapter.py`: Adaptador `VisionAdapter` – captura screenshot silencioso (mss/Pillow) ou frame de webcam (OpenCV) e envia ao **Gemini 1.5 Flash** com o prompt *"Descreva o contexto atual do usuário em 1 frase"*. Registrado no Nexus como `vision_adapter`.

**Fase 4 – Overwatch Daemon (Núcleo Proativo)**
- `scripts/overwatch_daemon.py`: Daemon de background `OverwatchDaemon` – monitora CPU/RAM, mudanças em `data/context.json` e inatividade do usuário (30 min). Após inatividade, usa `VisionAdapter` para verificar presença e sugere tarefa pendente do calendário. Todas as ações prefixadas `[PROACTIVE_CORE]`.
- `main.py`: `bootstrap_background_services()` inicia o `OverwatchDaemon` automaticamente; cada comando Telegram chama `notify_activity()` para reiniciar o timer de inatividade.

**Infraestrutura e Documentação**
- `data/nexus_registry.json`: `vector_memory_adapter` e `vision_adapter` registrados.
- `docs/NEXUS.md`: Tabela de componentes atualizada; seção de Circuit Breaker adicionada.
- `docs/ARQUIVO_MAP.md`: Todos os novos arquivos documentados.
- `docs/STATUS.md`: Status dos novos componentes ativos; seções de memória vetorial, visão e Overwatch Daemon.
- `scripts/README.md`: Documentação do `overwatch_daemon.py`.

### Changed

#### Sincronização de documentação (2026-10-16)

- `README.md`: tabela de adapters passa a refletir o registry estático; comandos de
  validação apontam para scripts que existem; invocação do runner corrigida
  (`PIPELINE=<nome> python app/runtime/pipeline_runner.py`).
- `docs/AGENT_GUIDE.md`: pacote `jarvis_dev_agent/`, IDs e arquivos de `data/` reais;
  removidas referências a módulos/scripts inexistentes
  (`pipeline_builder`, `meteorology_core`, `notificação_service`,
  `fix_frozen_references.py`, `validate_*_vs_code.py`).
- `docs/STATUS.md`: métricas atualizadas (1367 testes, 87 componentes Nexus,
  68/102 capabilities).
- `docs/PIPELINE_RUNNER.md`: novo documento do runner (formato YAML, modos estrito,
  `CloudMock` e códigos de saída).
- `scripts/README.md`: workflows de auto-cura corretos (`homeostase.yml` +
  `jarvis_healer.py`) e tabela dos demais utilitários/validadores.

#### Refactoring Estrutural (2026-03-01)
- Consolidado `app/infrastructure/adapters/` em `app/adapters/infrastructure/` (pasta única)
- Removido `app/domain/adapters/` – adaptadores não pertencem ao domínio
- Removido `app/app/` – diretório aninhado incorreto
- Removido `app/adapters/cap_*_core.py` (root) – movidos para `.frozen/orphan_caps/`
- `action_provider.py` movido para `app/adapters/infrastructure/`
- Auto-evolução **PAUSADA** enquanto estrutura é reorganizada
- Documentação completamente reescrita (docs/ limpa e recriada)
- README atualizado com status atual e estrutura correta
- `data/nexus_registry.json` atualizado com novos caminhos dos componentes

### Fixed

#### Contratos quebrados entre docs e código (2026-10-16)

- `nexus.resolve(..., use_cache=False)` era documentado em `docs/NEXUS.md` e
  **silenciosamente ignorado**; agora invalida o cache antes de resolver (com
  testes de cache e de circuit breaker aberto).
- `docs/NEXUS.md`: tabela de timeouts alinhada ao código (`NEXUS_INSTANTIATE_TIMEOUT`
  5s e não 30s, `NEXUS_CIRCUIT_RESET` 60s e não 300s, `NEXUS_IMPORT_TIMEOUT`
  incluído) e assinatura de `resolve()` corrigida.
- `README.md`/`docs/STATUS.md`: afirmações alinhadas ao comportamento real
  (sandbox via gatekeeper, `DockerSandbox` sem consumidor, `AdapterRegistry` sem
  consumidor automático, métrica de capabilities, `CostTrackerAdapter` já ativo).

#### Coerência da auto-evolução, do runner e dos validadores (2026-10-16)

**Auto-evolução sem motor de mutação** — `scripts/evolution_mutator.py` foi
removido do repositório, mas `AutoEvolutionServiceV2`, `scripts/evolve_all_pending.py`
e o workflow `auto_evolution_triggerV2.yml` ainda o importavam (ImportError na
largada). Todos passaram a usar o `EvolutionOrchestrator` via Nexus:

- `EvolutionOrchestrator.execute()` aceita `cap_id`/`cap_title`/`roadmap_context`,
  permitindo evoluir uma capability explícita em vez de só a seleção automática.
- `AutoEvolutionServiceV2` resolve o orchestrator no Nexus, tenta até
  `max_attempts` ciclos e reporta erro explícito quando ele não existe.
- `scripts/evolve_all_pending.py` deixou de importar o módulo removido e ganhou
  `--roadmap-context`.
- O workflow determina a `CAP-ID` da missão e chama `evolve_all_pending.py`
  (em vez do script inexistente).

**Inventário de capabilities ignorado** — `AutoEvolutionServiceV2` procurava
`data/capabilities.jrvs`; como o inventário versionado é `capabilities.json`, o
serviço respondia `empty_inventory` e nenhuma missão era encontrada. Agora há
fallback automático `.jrvs → .json` (mesmo padrão de `evolve_all_pending.py`),
expondo as 34 capabilities pendentes.

**Pipeline Runner não importava o Nexus** — ao rodar direto
(`PIPELINE=sync_drive python app/runtime/pipeline_runner.py`) o `sys.path` recebia
apenas `app/runtime`, o import falhava e **todos** os passos retornavam
"Nexus engine não inicializado" (só o CI funcionava por causa do `PYTHONPATH`
exportado). O root do projeto agora é injetado antes do import.

**Validadores quebrados** — `scripts/validate_architecture.py` rodava 0/6
(`No module named 'app'`) e agora valida 5/6 com 1 skip justificado (camada edge
sem as dependências de hardware). `scripts/validate_self_awareness.py`
estourava `FileNotFoundError` por apontar para o módulo `jarvis_dev_agent.py`, que
virou pacote, e agora valida o pacote, tolera arquivos ausentes e retorna código
de saída adequado.

**Auto-evolução sem autoconsciência** — o contexto consolidado estava registrado
no Nexus mas nenhum consumidor o usava. `load_consolidated_context()` (tolerante a
falhas, com truncagem) foi adicionado ao `ConsolidatedContextService` e ligado ao
`EvolutionOrchestrator` e ao `JarvisDevAgent`, injetando o snapshot do codebase no
prompt do LLM.

## [1.0.0] - 2024-02-05

### Added

#### Core Features
- Complete refactoring from monolithic `assistente.pyw` to professional modular architecture
- `JarvisEngine` class for voice recognition and text-to-speech
- `SystemCommands` class for interface automation (PyAutoGUI/Keyboard)
- `WebNavigator` class for web browser automation
- `CommandProcessor` for routing voice commands to appropriate handlers
- Configuration management with pydantic-settings
- Type hints throughout the entire codebase

#### Project Structure
- Professional folder structure (app/core, app/actions, app/utils, tests, data, dags)
- README.md files in each module explaining responsibilities
- Main entry point via `main.py`

#### DevOps & Infrastructure
- Dockerfile for containerization
- docker-compose.yml for orchestration
- Airflow DAG example for workflow automation
- Makefile for common development tasks

#### Testing & Quality
- Comprehensive pytest test suite (24 tests, 100% passing)
- Test fixtures in conftest.py
- pytest configuration with coverage reporting
- mypy configuration for type checking
- Code formatting with Black and isort
- Test coverage reporting

#### Documentation
- Comprehensive README.md with usage instructions
- EXTENSIBILITY.md guide for adding new features
- CONTRIBUTING.md for development guidelines
- Project structure documentation
- Inline documentation with Google-style docstrings

#### Development Tools
- setup.py for package management
- requirements.txt with all dependencies
- .gitignore for Python projects
- .env.example for configuration template
- Utility helper functions (logging, file operations)

### Changed
- Migrated from procedural code to object-oriented architecture
- Separated concerns into distinct modules
- Improved error handling and type safety

### Removed
- Work-specific functions (4R system integration)
- Almoxarifado-specific functionality
- Material requisition features
- Cost center management
- All hard-coded file paths and credentials
- Excel spreadsheet dependencies for commands

### Security
- Removed hard-coded credentials
- Added configuration management for sensitive data
- Improved input validation and error handling

## [0.1.0] - Original

### Initial Release
- Basic voice recognition in Portuguese (pt-BR)
- Text-to-speech functionality
- PyAutoGUI automation
- Work-specific integrations

[1.0.0]: https://github.com/TheDrack/python/releases/tag/v1.0.0
[0.1.0]: https://github.com/TheDrack/python/releases/tag/v0.1.0
