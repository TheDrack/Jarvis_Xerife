# JARVIS – Mapa de Arquivos Ativos

**Atualizado em:** 2026-03-10  
**Versão:** 2.0.0

> Este documento lista **apenas arquivos existentes** no repositório.

## `app/core/`

| Arquivo | Responsabilidade |
|---------|-----------------|
| `nexus.py` | Container de injeção de dependência. Resolve componentes pelo ID. |
| `nexus_exceptions.py` | CloudMock, CircuitBreaker, exceções customizadas |
| `nexuscomponent.py` | Classe base para todos os componentes Nexus |
| `nexus_registry.py` | Registro local/remoto de componentes |
| `config.py` | Configurações via environment variables |
| `meta/policy_store.py` | Políticas de evolução e aprovação |
| `meta/jrvs_compiler.py` | Compilação de arquivos .jrvs |
| `meta/decision_engine.py` | Motor de decisões do sistema |
| `meta/exploration_controller.py` | Controle de exploração de novas ferramentas |

## `app/domain/`

| Arquivo | Responsabilidade |
|---------|-----------------|
| `capability_manager.py` | Gerenciamento de capabilities |
| `memory/semantic_memory.py` | Memória semântica de longo prazo |
| `memory/procedural_memory.py` | Memória de padrões aprendidos |
| `memory/working_memory.py` | Memória de trabalho (curto prazo) |
| `memory/prospective_memory.py` | Memória prospectiva (futuro/agenda) |
| `models/agent.py` | Modelos do JarvisDevAgent (Action, Observation, Task) |
| `models/adapter_registry.py` | Registro de adapters disponíveis |
| `services/command_interpreter.py` | Interpretação de comandos |
| `services/intent_processor.py` | Processamento de intenções |
| `services/system_state_tracker.py` | Rastreamento de estado do sistema |
| `services/reward_signal_provider.py` | Sinais de recompensa para RL |
| `services/safety_guardian.py` | Validação de segurança |

## `app/application/`

| Arquivo | Responsabilidade |
|---------|-----------------|
| `services/assistant_service.py` | Serviço central do assistente |
| `services/evolution_orchestrator.py` | Orquestração da auto-evolução |
| `services/evolution_gatekeeper.py` | Aprovação de mudanças no código |
| `services/evolution_sandbox.py` | Sandbox de testes local |
| `services/jarvis_dev_agent.py` | **Agente autônomo de desenvolvimento** |
| `services/jarvis_dev_agent/pipeline_builder.py` | **Criador de pipelines YAML** |
| `services/jarvis_dev_agent/actions.py` | **Executor de ações do agente** |
| `services/jarvis_dev_agent/prompt_builder.py` | **Construtor de prompts** || `services/jarvis_dev_agent/code_discovery.py` | **Descoberta de código existente** |
| `services/jarvis_dev_agent/trajectory.py` | **Gerenciador de trajetória** |
| `services/llm_router.py` | Roteamento dinâmico de LLMs |
| `services/metabolism_core.py` | Núcleo de metabolismo (LLM fleet) |
| `services/local_repair_agent.py` | Agente de auto-reparo local |
| `services/notification_service.py` | Serviço de notificações |
| `services/consolidated_context_service.py` | Snapshot do código consolidado |
| `services/crystallization/crystallizer_engine.py` | Cristalização do codebase |
| `services/jrvs_translator.py` | Tradução .jrvs ↔ JSON/YAML |
| `services/structured_logger.py` | Logger estruturado |
| `services/status_service.py` | Diagnóstico do sistema |
| `services/location_service.py` | Serviço de localização |
| `services/field_vision.py` | Monitor proativo de logs |
| `services/thought_log_service.py` | Log de pensamentos do sistema |
| `services/auto_evolutionV2.py` | Auto-evolução de capabilities |
| `services/evolution_loop.py` | Loop de evolução com RL |
| `services/meta_reflection.py` | Reflexão periódica do sistema |
| `services/model_orchestrator.py` | Orquestração de modelos |
| `services/finetune_dataset_collector.py` | Coleta de dataset para fine-tune |
| `services/finetune_trigger_service.py` | Trigger de fine-tune |
| `services/browser_manager.py` | Gerenciamento de browser |
| `services/task_runner.py` | Executor de tarefas |
| `services/strategist_service.py` | Planejamento estratégico |
| `services/soldier_registry.py` | Registro de soldados (edge) |
| `services/capability_index_service.py` | Índice de capabilities |
| `services/capability_blueprint_service.py` | Blueprints de capabilities |
| `services/capability_gap_reporter.py` | Report de gaps de capabilities |
| `security/capability_authorizer.py` | Autorização de capabilities |
| `security/pii_redactor.py` | Redação de PII |
| `security/env_secrets_provider.py` | Provedor de secrets |
| `security/safety_guardian.py` | Guardião de segurança |

## `app/adapters/`

| Arquivo | Responsabilidade |
|---------|-----------------|
| `infrastructure/telegram_adapter.py` | Interface Telegram |
| `infrastructure/github_adapter.py` | Interface GitHub |
| `infrastructure/github_worker.py` | Worker de operações GitHub |
| `infrastructure/ollama_adapter.py` | LLMs locais via Ollama |
| `infrastructure/gemini_adapter.py` | LLMs via Gemini |
| `infrastructure/gateway_llm_adapter.py` | Gateway de LLMs |
| `infrastructure/ai_gateway.py` | Gateway de IA unificado |
| `infrastructure/persistent_shell_adapter.py` | Terminal stateful |
| `infrastructure/docker_sandbox.py` | **Sandbox em containers Docker** |
| `infrastructure/evolution_sandbox.py` | Sandbox de evolução local |
| `infrastructure/consolidator.py` | Consolidador de contexto |
| `infrastructure/gist_uploader.py` | Upload para GitHub Gist |
| `infrastructure/drive_uploader.py` | Upload para Google Drive |
| `infrastructure/auth_adapter.py` | Autenticação || `infrastructure/sqlite_history_adapter.py` | Histórico em SQLite |
| `infrastructure/vision_adapter.py` | Processamento de visão |
| `infrastructure/cost_tracker_adapter.py` | Rastreamento de custos |
| `infrastructure/overwatch_adapter.py` | Daemon de monitoramento |
| `infrastructure/osint_search.py` | Busca OSINT |
| `infrastructure/eagle_osint_adapter.py` | Adapter OSINT Eagle |
| `infrastructure/active_recruiter_adapter.py` | Recruiter ativo |
| `infrastructure/github_workflow_adapter.py` | Workflows do GitHub |
| `infrastructure/vector_memory_adapter.py` | Memória vetorial |
| `infrastructure/audit_logger.py` | Logger de auditoria |
| `infrastructure/system_executor.py` | Executor de sistema |
| `infrastructure/interface_bridge.py` | Ponte de interface |
| `infrastructure/context_memory.py` | Memória de contexto |
| `infrastructure/orchestrator_service.py` | Serviço orquestrador |

## `app/utils/`

| Arquivo | Responsabilidade |
|---------|-----------------|
| `document_store.py` | Leitura/escrita universal de documentos |
| `jrvs_codec.py` | Codec de arquivos .jrvs |

## `app/runtime/`

| Arquivo | Responsabilidade |
|---------|-----------------|
| `pipeline_runner.py` | Executor de pipelines YAML |

## `app/plugins/`

| Arquivo | Responsabilidade |
|---------|-----------------|
| `plugin_loader.py` | Carregador dinâmico de plugins |
| `dynamic/` | Plugins carregados automaticamente |

## `config/`

| Arquivo | Responsabilidade |
|---------|-----------------|
| `pipelines/*.yml` | Pipelines YAML (sync_drive.yml, etc) |

## `data/`

| Arquivo | Responsabilidade |
|---------|-----------------|
| `nexus_registry.json` | Registro de componentes Nexus |
| `nexus_registry.jrvs` | Registro em formato .jrvs |
| `capabilities.jrvs` | Inventário de capabilities |
| `context.json` | Contexto atual do sistema |
| `architecture_rules.yml` | Regras de arquitetura || `dev_agent_jobs.jsonl` | Log de jobs do JarvisDevAgent |
| `evolution_proposals/` | Propostas de evolução |
| `jrvs-snapshots/` | Snapshots do sistema |
| `logs/` | Logs do sistema |

## `scripts/`

| Arquivo | Responsabilidade |
|---------|-----------------|
| `cristalize_project.py` | Cristalização do projeto |
| `evolve_all_pending.py` | Evolução em lote de capabilities |
| `fix_frozen_references.py` | Correção de referências frozen |
| `migrate_to_nexus_di.py` | Migração para Nexus DI |
| `validate_registry_vs_code.py` | Validação registry vs código |
| `validate_docs_vs_code.py` | Validação docs vs código |
| `validate_architecture.py` | Validação de arquitetura |

## `docs/`

| Arquivo | Responsabilidade |
|---------|-----------------|
| `README.md` | Visão geral do projeto |
| `STATUS.md` | Status do projeto |
| `ARQUIVO_MAP.md` | Mapa de arquivos |
| `ARCHITECTURE.md` | Arquitetura completa |
| `NEXUS.md` | Documentação do Nexus DI |
| `PIPELINE_RUNNER.md` | Documentação de pipelines |

## `tests/`

| Categoria | Tests | Status |
|-----------|-------|--------|
| Domain | 400+ | ✅ Verde |
| Application | 500+ | ✅ Verde |
| Adapters | 300+ | ✅ Verde |
| Security | 50+ | ✅ Verde |
| Privacy | 50+ | ✅ Verde |
| Integration | 26+ | ✅ Verde |