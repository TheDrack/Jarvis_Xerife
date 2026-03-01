# JARVIS – Mapa de Arquivos Ativos

> Cada arquivo ativo e o que ele faz.  
> Gerado em: 2026-03-01

---

## `app/core/`

| Arquivo | Responsabilidade |
|---|---|
| `nexus.py` | Container de injeção de dependência. Resolve componentes pelo ID. Suporta discovery local e sincronização remota via Gist. |
| `nexuscomponent.py` | Interface base (`ABC`) que todos os componentes do Nexus devem implementar. Define `execute(context)`. |
| `config.py` | Carregamento de configurações do ambiente (`.env`, variáveis de ambiente). |
| `encryption.py` | Funções de criptografia para proteger credenciais e configurações sensíveis. |
| `llm_config.py` | Configuração da frota de LLMs (`config/llm_fleet.json`). Define modelos disponíveis. |

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
| `context_manager.py` | Gerencia contexto de conversa – mantém histórico para conversações contínuas. |

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
| `reward_provider.py` | Interface para registro de recompensas/punições do RL. |
| `security_provider.py` | Interface para validação de segurança e autenticação. |
| `system_controller.py` | Interface para controle do sistema operacional. |
| `voice_provider.py` | Interface para entrada e saída de voz. |
| `web_provider.py` | Interface para interações com o navegador web. |

### `services/`

| Arquivo | Responsabilidade |
|---|---|
| `assistant_service.py` | Serviço principal do assistente – processa entrada do usuário end-to-end. |
| `auto_evolutionV2.py` | Lógica de auto-evolução (Versão 2) – gerencia missões e mutations. **PAUSADA.** |
| `browser_manager.py` | Gerencia sessões de navegador (Playwright). |
| `capability_impact_analyzer.py` | Analisa impacto de uma capability antes de ativá-la. |
| `capability_manager.py` | Carrega, valida e gerencia capabilities ativas. |
| `dependency_manager.py` | Resolve dependências de capabilities dinamicamente. |
| `device_service.py` | Gerencia dispositivos orquestrados (registro, descoberta, roteamento). |
| `evaluate_risks_service.py` | Avalia riscos antes de executar uma ação ou evolução. |
| `evolution_loop.py` | Loop principal de evolução (RL feedback loop). **PAUSADO.** |
| `extension_manager.py` | Gerencia extensões e plugins adicionais. |
| `github_worker.py` | Interações com a API do GitHub (criar issues, PRs, etc.). |
| `human_intervention_service.py` | Gerencia escalação para intervenção humana. |
| `identify_mission_critical_capabilities.py` | Identifica quais capabilities são essenciais para o sistema. |
| `interface_bridge.py` | Bridge entre a camada de domínio e a interface do usuário. |
| `llm_capability_detector.py` | Usa LLM para detectar capabilities relevantes para um comando. |
| `local_bridge.py` | Bridge para comunicação com agente local (dispositivos na rede). |
| `location_service.py` | Serviço de localização para roteamento por proximidade. |
| `main.py` | Ponto de entrada principal da aplicação (modo cloud). |
| `metabolism_core.py` | Núcleo do sistema de metabolismo – controla ciclos de mutação/evolução. |
| `orchestrator_service.py` | `JARVISOrchestrator` – orquestrador registrado no Nexus. |
| `prioritizer_service.py` | Prioriza comandos e tarefas por urgência e impacto. |
| `scavenger_hunt.py` | Serviço de descoberta de componentes e capabilities no codebase. |
| `serve.py` | Inicialização do servidor FastAPI. |
| `strategist_service.py` | Estrategista – decide qual ação tomar dado o contexto atual. |
| `structured_logger.py` | Logger estruturado para o Nexus. Registrado como `structured_logger`. |
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
| `ai_gateway.py` | Gateway de IA – roteamento entre múltiplos LLMs (Groq/Gemini). |
| `api_models.py` | Modelos Pydantic para a API REST. |
| `api_server.py` | Servidor FastAPI – define rotas e autenticação OAuth2. |
| `audit_logger.py` | Logger de auditoria – persiste logs de execução em JSON. Registrado no Nexus. |
| `auth_adapter.py` | Autenticação e autorização (JWT, OAuth2). |
| `consolidator.py` | Consolida o codebase em um arquivo único para contexto de LLMs. |
| `copilot_context_provider.py` | Fornece contexto do repositório para o GitHub Copilot. |
| `dummy_voice_provider.py` | Provedor de voz fictício para testes headless. |
| `extension_manager.py` | Gerenciador de extensões de infraestrutura. |
| `gateway_llm_adapter.py` | Adaptador principal do gateway LLM (auto-repair, self-healing). |
| `gemini_adapter.py` | Adaptador Google Gemini – interpretação de comandos com function calling. |
| `gist_uploader.py` | Uploader de arquivos para GitHub Gist (persistência de DNA). |
| `github_adapter.py` | Adaptador GitHub – cria issues, PRs, comenta, lê repositório. |
| `http_client.py` | Cliente HTTP genérico baseado em `requests`. NexusComponent. |
| `playwright_worker.py` | Worker Playwright para automação de browser (cloud). |
| `pyinstaller_builder.py` | Gera instalador Windows com PyInstaller. Worker do pipeline. |
| `reward_adapter.py` | Adaptador de recompensas – persiste e lê rewards do banco. |
| `reward_logger.py` | Logger de rewards do RL (arquivo de log). |
| `setup_wizard.py` | Wizard de configuração inicial do sistema. |
| `socket_client.py` | Cliente de sockets para comunicação com agentes locais. NexusComponent. |
| `sqlite_history_adapter.py` | Histório de comandos em SQLite. Implementa `HistoryProvider`. |
| `system_executor.py` | Executa automações de sistema (screenshot, digitar, abrir URL). Registrado no Nexus. |
| `telegram_adapter.py` | Notificações e interação via Telegram. |

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
| `config/llm_fleet.json` | Configuração da frota de LLMs (modelos, endpoints, chaves). |
| `config/pipelines/*.yml` | Definições de pipelines declarativos (build, sync, chat). |
| `data/nexus_registry.json` | Registry local do Nexus com mapeamento ID → módulo. |
| `data/capabilities.json` | Capabilities disponíveis com metadados. |
| `data/architecture_rules.yml` | Regras de arquitetura validadas automaticamente. |
| `migrations/*.sql` | Migrations do banco de dados. |
| `scripts/` | Scripts utilitários (análise, estado, cristalização). |
| `Makefile` | Comandos utilitários (`make test`, `make lint`, etc.). |
| `Dockerfile` / `docker-compose.yml` | Containerização para deploy em cloud. |
| `render.yaml` | Configuração de deploy no Render. |
| `padrão_estrutural.md` | Padrão obrigatório de pipelines e arquitetura. |
