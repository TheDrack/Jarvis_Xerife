# JARVIS – Mapa de Arquivos Ativos

> Cada arquivo ativo e o que ele faz.  
> Atualizado em: 2026-03-06

---

## `app/core/`

| Arquivo | Responsabilidade |
|---|---|
| `nexus.py` | Container de injeção de dependência. Resolve componentes pelo ID. Re-exporta `NexusComponent` e `CloudMock`. |
| `nexus_exceptions.py` | `CloudMock`, `_CircuitBreakerEntry`, exceções customizadas (`ImportTimeoutError`, `InstantiateTimeoutError`, `AmbiguousComponentError`), timeouts configuráveis e `nexus_guarded_instantiate`. |
| `nexus_discovery.py` | `_NexusDiscoveryMixin` – busca em disco, localização de classes e instanciação com timeout. |
| `nexus_registry.py` | `_NexusRegistryMixin` – leitura/escrita do registry local `.jrvs` e sincronização com GitHub Gist. |
| `nexuscomponent.py` | Interface base (`ABC`) que todos os componentes do Nexus devem implementar. Define `execute(context)`. Também exporta helpers privados `_class_to_component_id` e `_nexus_context` usados por testes. |
| `config.py` | Carregamento de configurações do ambiente (`.env`, variáveis de ambiente). |
| `encryption.py` | Funções de criptografia para proteger credenciais e configurações sensíveis. |
| `llm_config.py` | Configuração da frota de LLMs (`config/llm_fleet.json`). Define modelos disponíveis. |

### `app/core/meta/`

> Camada cognitiva adaptativa do Nexus.

| Arquivo | Responsabilidade |
|---|---|
| `policy_store.py` | Persiste políticas brutas por módulo em `.jrvs`. Dispara recompilação ao atingir `JRVS_RECOMPILE_THRESHOLD`. |
| `jrvs_compiler.py` | Compila snapshots binários `.jrvs` por módulo cognitivo com validação SHA-256 e CRC32. Escritas atômicas. |
| `decision_engine.py` | Motor de decisão adaptativo: scoring multi-objetivo, epsilon-greedy adaptativo, guardrail de estabilidade (`global_success_ema < 0.4`). |
| `exploration_controller.py` | Descobre novas ferramentas, persiste em `PolicyStore` e gerencia promoção ao registro primário. |
| `compile_lock.py` | Lock utilitário para evitar compilações concorrentes em `data/jrvs/.compile.lock`. |

---

## `app/domain/`

### `models/`

| Arquivo | Responsabilidade |
|---|---|
| `capability.py` | Modelo de dados `Capability` – representa uma habilidade/capacidade do sistema. |
| `command.py` | Modelos `CommandType` e `Intent` – representa um comando interpretado do usuário. |
| `device.py` | Modelo `Device` – representa um dispositivo orquestrado (PC, telefone, IoT). |
| `evolution_reward.py` | Modelo `EvolutionReward` – registro de recompensas do sistema de RL. |
| `mission.py` | Modelo `Mission` – unidade de trabalho para a auto-evolução. |
| `system_state.py` | Modelo `SystemState` – estado atual do sistema. |
| `thought_log.py` | Modelo `ThoughtLog` – log estruturado de pensamentos/decisões do assistente. |
| `viability.py` | Modelo `Viability` – avaliação de viabilidade de uma ação ou missão. |

### `services/`

| Arquivo | Responsabilidade |
|---|---|
| `agent_service.py` | Define as function declarations para o Gemini (function calling). Mapeia funções para `CommandType`. |
| `command_interpreter.py` | Interpreta comandos de voz em `Intent` usando regras de palavras-chave. |
| `intent_processor.py` | Processa um `Intent` e executa a ação correspondente via portas. |
| `llm_command_interpreter.py` | Interpretador de comandos usando LLM (wrapper assíncrono). |
| `soldier_shield.py` | Validação de segurança de comandos – impede ações não autorizadas. |
| `state_manager.py` | Gerencia a máquina de estados do sistema (idle, listening, executing, error). |
| `vocal_orchestrator.py` | Orquestra o fluxo de voz: escuta → interpreta → executa → fala. |

### `gears/`

> Contém o sistema de engrenagens (multi-tier LLM).  
> **Nota:** Muitos arquivos `cap_*_core.py` aqui precisam ser revisados e possivelmente movidos para `.frozen/`.

| Arquivo | Responsabilidade |
|---|---|
| `cognitive_router.py` | Roteador cognitivo – decide qual engrenagem (LLM) usar para cada comando. |
| `llm_engine.py` | Motor LLM – executa prompts via Groq/Gemini com fallback automático. |

### `context/`

| Arquivo | Responsabilidade |
|---|---|
| `context_manager.py` | **[MELHORIA 5]** Gerencia `data/context.json` com validação via `SystemContext` (Pydantic). Expõe `read_context()`, `write_context()`, `update_context_field()`. Escritas inválidas são rejeitadas com warning. |

### `ai/`

| Arquivo | Responsabilidade |
|---|---|
| `gemini_service.py` | Serviço de integração com Google Gemini para tarefas de IA complexas. |

### `orchestration/`

| Arquivo | Responsabilidade |
|---|---|
| `central_orchestrator.py` | Orquestrador central – coordena domínio e adaptadores via Nexus. |

### `missions/`

| Arquivo | Responsabilidade |
|---|---|
| `mission_selector.py` | Seleciona próxima missão de evolução do pool disponível. |

### `analysis/`

| Arquivo | Responsabilidade |
|---|---|
| `performance_analyzer.py` | Analisa performance dos componentes e identifica gargalos. |

---

## `app/application/`

### `ports/`

> Interfaces (ABCs) que os adaptadores devem implementar.

| Arquivo | Responsabilidade |
|---|---|
| `action_provider.py` | Interface para execução de ações de UI (digitar, pressionar tecla, abrir URL). |
| `history_provider.py` | Interface para acesso ao histórico de comandos. |
| `memory_provider.py` | Interface para memória vetorial/biográfica (`store_event`, `query_similar`, `clear`). |
| `osint_provider.py` | Interface para inteligência de código aberto (OSINT). |
| `reward_provider.py` | Interface para registro de recompensas/punições do RL. |
| `security_provider.py` | Interface para validação de segurança e autenticação. |
| `soldier_provider.py` | Interface para comunicação com Soldiers (dispositivos da mesh tática). |
| `system_controller.py` | Interface para controle do sistema operacional. |
| `tactical_command_port.py` | Interface para envio de comandos táticos aos Soldiers via SSH/WebSocket. |
| `voice_provider.py` | Interface para entrada e saída de voz. |
| `web_provider.py` | Interface para interações com o navegador web. |

### `services/`

| Arquivo | Responsabilidade |
|---|---|
| `assistant_service.py` | Serviço principal do assistente – processa entrada do usuário end-to-end. Integra memória vetorial (últimos 30 dias) e memória semântica de longo prazo. |
| `auto_evolutionV2.py` | Lógica de auto-evolução (Versão 2) – gerencia missões e mutations. **PAUSADA.** |
| `browser_manager.py` | Gerencia sessões de navegador (Playwright). |
| `c2_orchestrator_service.py` | Orquestrador C2 com sessões persistentes para a Soldier Mesh (SSH/WebSocket). |
| `capability_blueprint_service.py` | Geração de blueprints técnicos e validação de requisitos de recursos de capabilities. Extraído de `capability_manager.py`. |
| `capability_detectors.py` | Funções standalone para detectar o status de implementação de capabilities. |
| `capability_gap_reporter.py` | Reporta gaps de capabilities ao repositório via Pull Requests. |
| `capability_impact_analyzer.py` | Analisa impacto de uma capability antes de ativá-la. |
| `capability_index_service.py` | **[Melhoria 4]** Índice vetorial de capabilities (FAISS + fallback). Busca semântica top-k. Atualiza `reliability_score` via EMA. Registrado como `capability_index_service`. |
| `capability_manager.py` | Carrega, valida e gerencia capabilities ativas. |
| `dependency_manager.py` | Resolve dependências de capabilities dinamicamente. |
| `device_capability_service.py` | Roteamento de dispositivos por capacidade. Extraído de `device_service.py`. |
| `device_location_service.py` | Cálculo de distância geográfica (Haversine) para roteamento. Extraído de `device_service.py`. |
| `device_orchestrator_service.py` | Registry C2 de dispositivos Soldier autorizados (Soldier Mesh Protocol). |
| `device_service.py` | Gerencia dispositivos orquestrados (registro, descoberta, roteamento). |
| `evaluate_risks_service.py` | Avalia riscos antes de executar uma ação ou evolução. |
| `evolution_loop.py` | Loop principal de evolução (RL feedback loop). **PAUSADO.** |
| `evolution_orchestrator.py` | **[Melhoria 1]** Orquestrador do loop agêntico de auto-evolução. Chama crystallizer → context → memória procedural → LLM → valida sintaxe → cria PR. Registrado como `evolution_orchestrator`. |
| `extension_manager.py` | Gerencia extensões e plugins adicionais. |
| `field_vision.py` | Monitor proativo de logs do sistema (`logs/jarvis.log`). Classifica erros e aciona `homeostase.yml`. |
| `github_worker.py` | Interações com a API do GitHub (criar issues, PRs, etc.). |
| `human_intervention_service.py` | Gerencia escalação para intervenção humana. |
| `identify_mission_critical_capabilities.py` | Identifica quais capabilities são essenciais para o sistema. |
| `interface_bridge.py` | Bridge entre a camada de domínio e a interface do usuário. |
| `jrvs_translator.py` | `JrvsTranslator` – sincroniza arquivos `.jrvs` com seus equivalentes legíveis. Registrado como `jrvs_translator`. |
| `llm_capability_detector.py` | Usa LLM para detectar capabilities relevantes para um comando. |
| `llm_capability_prompt_builder.py` | Construção de prompts para detecção de capabilities via LLM. Extraído de `llm_capability_detector.py`. |
| `llm_service.py` | Serviço LLM de alto nível para geração de respostas. |
| `local_bridge.py` | Bridge para comunicação com agente local (dispositivos na rede). |
| `local_repair_agent.py` | **[PR #494]** `LocalRepairAgent` – primeiro estágio do pipeline de self-healing. Repara erros comuns em < 1 s sem CI. Registrado como `local_repair_agent`. |
| `location_service.py` | Serviço de localização para roteamento por proximidade. |
| `memory_manager.py` | `MemoryManager` – gerenciador de memória semântica de longo prazo (até 500 interações). |
| `metabolism_core.py` | Núcleo do sistema de metabolismo – controla ciclos de mutação/evolução. |
| `notification_service.py` | Despacho de mensagens agnóstico à interface (Telegram, WhatsApp, Discord). Registrado como `notification_service`. |
| `orchestrator_service.py` | `OrchestratorService` – orquestrador registrado no Nexus. |
| `prioritizer_service.py` | Prioriza comandos e tarefas por urgência e impacto. |
| `run_workflow.py` | Acionamento de workflows do GitHub Actions via API. |
| `scavenger_hunt.py` | Serviço de descoberta de componentes e capabilities no codebase. |
| `serve.py` | Inicialização do servidor FastAPI. |
| `status_service.py` | `StatusService` – diagnóstico do JARVIS (saúde do sistema e do Nexus). |
| `strategist_service.py` | Estrategista – decide qual ação tomar dado o contexto atual. |
| `structured_logger.py` | Logger estruturado para o Nexus. Registrado como `structured_logger`. |
| `tactical_map_service.py` | Consolida dados de todos os Soldiers em um mapa tático unificado. |
| `task_runner.py` | Executor de tarefas assíncronas com isolamento. |
| `technical_analysis_service.py` | Análise técnica de código e arquitetura. |
| `thought_log_service.py` | Serviço de log de pensamentos (armazena decisões do assistente). |
| `vocal_orchestration_service.py` | Orquestração completa do fluxo vocal (end-to-end). |

### `crystallization/`

| Arquivo | Responsabilidade |
|---|---|
| `crystallizer_engine.py` | Motor de cristalização – consolida o codebase em formato para LLMs. |

### `communication/`

| Arquivo | Responsabilidade |
|---|---|
| `human_intervention.py` | Protocolo de comunicação para escalação humana. |

---

## `app/adapters/edge/`

> Adaptadores para hardware e dispositivos de borda.

| Arquivo | Responsabilidade |
|---|---|
| `active_recruiter_adapter.py` | Recruta ativamente dispositivos disponíveis na rede. |
| `automation_adapter.py` | Adaptador de automação desktop (pyautogui). Implementa `ActionProvider`. |
| `combined_voice_provider.py` | Combina múltiplos provedores de voz em uma interface unificada. |
| `hardware_controller.py` | Controla hardware periférico (câmera, IR, etc.). |
| `jarvis_local_agent.py` | Agente local – roda no dispositivo de borda e recebe comandos do cloud. |
| `keyboard_adapter.py` | Adaptador de teclado – captura e injeta teclas. |
| `tts_adapter.py` | Adaptador de Text-to-Speech (converte texto em fala). |
| `voice_adapter.py` | Adaptador de reconhecimento de voz (Speech-to-Text). |
| `voice_engine.py` | Motor de voz – coordena TTS e STT. |
| `web_adapter.py` | Adaptador web – controla navegador via Playwright. Implementa `WebProvider`. |
| `worker_pc.py` | Worker para execução de tarefas em PC desktop. |

---

## `app/adapters/infrastructure/`

> Adaptadores para infraestrutura de nuvem e serviços externos.

| Arquivo | Responsabilidade |
|---|---|
| `action_provider.py` | Implementação de `ActionProvider` via pyautogui. Registrada no Nexus. |
| `ai_gateway.py` | Gateway de IA – roteamento entre múltiplos LLMs (Groq/Gemini/Ollama). Roteamento por `task_type`: `code_generation`/`self_repair` → OllamaAdapter; `reasoning`/`vision` → Gemini. |
| `ai_gateway_enums.py` | Enums `LLMProvider` e `GroqGear` (Marchas) usados pelo AI Gateway. |
| `ai_gateway_token_utils.py` | Utilitários de contagem de tokens (tiktoken com fallback estimativo). |
| `api_models.py` | Modelos Pydantic para a API REST. |
| `api_server.py` | Servidor FastAPI – define rotas e autenticação OAuth2. |
| `audit_logger.py` | Logger de auditoria – persiste logs de execução em JSON. Registrado no Nexus. |
| `auth_adapter.py` | Autenticação e autorização (JWT, OAuth2). |
| `auto_repair_mixin.py` | Mixin de auto-reparo para `GatewayLLMCommandAdapter`: analisa erros com Gemini e abre PRs de correção. |
| `consolidator.py` | Consolida o codebase em um arquivo único para contexto de LLMs. |
| `copilot_context_provider.py` | Fornece contexto do repositório para o GitHub Copilot. |
| `cost_tracker_adapter.py` | **[Melhoria 7]** Auditoria de custos de chamadas LLM. Persiste em SQLite. Expõe `log()` e `get_cost_summary()`. Registrado como `cost_tracker_adapter`. |
| `drive_uploader.py` | Uploader de arquivos para Google Drive. |
| `dummy_voice_provider.py` | Provedor de voz fictício para testes headless. |
| `extension_manager.py` | Gerenciador de extensões de infraestrutura. |
| `gateway_llm_adapter.py` | Adaptador principal do gateway LLM (auto-repair, self-healing). |
| `gemini_adapter.py` | Adaptador Google Gemini – interpretação de comandos com function calling. |
| `gemini_response_helpers.py` | Utilitários para construção de contexto e mapeamento de respostas Gemini para objetos de domínio. |
| `gist_uploader.py` | Uploader de arquivos para GitHub Gist (persistência de DNA). |
| `github_adapter.py` | Adaptador GitHub principal – fachada que delega às classes especializadas. |
| `github_correction_adapter.py` | Criação de PRs de correção automática e gerenciamento de conteúdo de arquivos. |
| `github_issue_adapter.py` | Criação e gerenciamento de issues no GitHub. |
| `github_issue_mixin.py` | Mixin para reportar falhas de infraestrutura (503/UNAVAILABLE) como issues. |
| `github_workflow_adapter.py` | Monitoramento de workflow runs no GitHub. |
| `http_client.py` | Cliente HTTP genérico baseado em `requests`. NexusComponent. |
| `mqtt_home_adapter.py` | Adaptador MQTT para dispositivos IoT domésticos. |
| `ollama_adapter.py` | **[Melhoria 2]** Adaptador para LLMs locais via Ollama. Suporta `OLLAMA_BASE_URL`, `/api/generate`, `is_available()`. Registrado como `ollama_adapter`. |
| `overwatch_adapter.py` | `OverwatchDaemon` – daemon de monitoramento proativo. Compõe `ResourceMonitor` e `PerimeterMonitor`. Registrado como `overwatch_daemon`. |
| `overwatch_perimeter.py` | `PerimeterMonitor` mixin – monitoramento tático de perímetro (MAC/ARP). |
| `overwatch_resource_monitor.py` | `ResourceMonitor` mixin – CPU/RAM reativo e preditivo com janela deslizante de 10 leituras. |
| `playwright_worker.py` | Worker Playwright para automação de browser (cloud). |
| `procedural_memory_adapter.py` | **[Melhoria 3]** Índice vetorial de soluções bem-sucedidas do ThoughtLog. Busca por similaridade (limiar padrão 0.80). Registrado como `procedural_memory_adapter`. |
| `pyinstaller_builder.py` | Gera instalador Windows com PyInstaller. Worker do pipeline. |
| `reward_adapter.py` | Adaptador de recompensas. `update_capability_reliability()` atualiza `reliability_score` via EMA em `data/capabilities.json`. |
| `reward_logger.py` | Logger de rewards do RL (arquivo de log). |
| `setup_wizard.py` | Wizard de configuração inicial do sistema. |
| `socket_client.py` | Cliente de sockets para comunicação com agentes locais. NexusComponent. |
| `sqlite_history_adapter.py` | Histórico de comandos em SQLite. Implementa `HistoryProvider`. |
| `system_executor.py` | Executa automações de sistema (screenshot, digitar, abrir URL). Registrado no Nexus. |
| `telegram_adapter.py` | Notificações e interação via Telegram. |
| `vector_memory_adapter.py` | Memória biográfica vetorial (FAISS + fallback puro-Python). Implementa `MemoryProvider`. Registrado no Nexus. |
| `vision_adapter.py` | Visão computacional via Gemini Flash – captura screenshot/webcam e gera descrição contextual. Registrado no Nexus. |

---

## `app/runtime/`

| Arquivo | Responsabilidade |
|---|---|
| `pipeline_runner.py` | Runner de pipelines declarativos – lê YAML, resolve componentes via Nexus, executa em ordem. |

---

## `app/plugins/`

| Arquivo | Responsabilidade |
|---|---|
| `plugin_loader.py` | Carrega plugins dinamicamente da pasta `dynamic/`. |
| `dynamic/example_plugin.py` | Exemplo de plugin customizado. |

---

## `app/utils/`

| Arquivo | Responsabilidade |
|---|---|
| `helpers.py` | Funções utilitárias gerais (formatação, parse, etc.). |

---

## `app/bootstrap_edge.py`

Inicializa o modo edge (dispositivo local) – carrega adaptadores de voz, teclado e automação.

---

## Outros arquivos raiz

| Arquivo | Responsabilidade |
|---|---|
| `config/llm_fleet.json` | Configuração da frota de LLMs (modelos, endpoints, chaves, preços por 1k tokens). |
| `config/pipelines/*.yml` | Definições de pipelines declarativos (build, sync, chat). |
| `data/nexus_registry.json` | Registry local do Nexus com mapeamento ID → módulo. Fonte de verdade legível por humanos. |
| `data/nexus_registry.jrvs` | Versão binária do registry (gerada automaticamente pelo Nexus após sync). |
| `data/jrvs/` | Snapshots cognitivos compilados: `llm.jrvs`, `tools.jrvs`, `meta.jrvs` e equivalentes `.json`. |
| `data/capabilities.json` | Capabilities disponíveis com metadados. Cada capability tem campo `reliability_score` (float 0–1, EMA). |
| `data/context.json` | Estado do sistema validado pelo `SystemContext` Pydantic. Campos: `current_goal`, `active_capabilities`, `recent_errors`, `user_last_interaction`, `system_health`, `evolution_state`, `trend`. |
| `data/architecture_rules.yml` | Regras de arquitetura validadas automaticamente. |
| `data/evolution_proposals/` | Patches Python gerados pelo `EvolutionOrchestrator` (um arquivo `<timestamp>.py` por ciclo). |
| `migrations/*.sql` | Migrations do banco de dados. |
| `scripts/auto_fixer_logic.py` | Orquestrador principal do self-healing: lê erro, extrai arquivo, chama AI, aplica fix, cria PR. |
| `scripts/fix_applier.py` | Utilitários de I/O de arquivos, interação com GitHub Copilot CLI e validação de correções via pytest. |
| `scripts/issue_parser.py` | Classificação do tipo de issue (bug, doc, feature) e localização do arquivo afetado no traceback. |
| `scripts/pr_manager.py` | Operações Git/GitHub: criação de branches, commits, push, abertura de PRs e ciclo de vida de issues. |
| `scripts/overwatch_daemon.py` | **Legado** – wrapper de compatibilidade. O daemon proativo agora está em `app/adapters/infrastructure/overwatch_adapter.py`. |
| `Makefile` | Comandos utilitários (`make test`, `make lint`, etc.). |
| `Dockerfile` / `docker-compose.yml` | Containerização para deploy em cloud. |
| `render.yaml` | Configuração de deploy no Render. |
| `padrão_estrutural.md` | Padrão obrigatório de pipelines e arquitetura. |
