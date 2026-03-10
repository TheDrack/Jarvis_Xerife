# JARVIS – Mapa de Arquivos Ativos

**Atualizado em:** 2026-03-10  
**Versão:** 2.0.0

> Este documento lista **apenas arquivos existentes** no repositório.

---

## `app/core/`

| Arquivo | Responsabilidade |
|---------|------------------|
| `nexus.py` | Container de injeção de dependência. Resolve componentes pelo ID. Re-exporta `NexusComponent` e `CloudMock`. |
| `nexus_exceptions.py` | `CloudMock`, `_CircuitBreakerEntry`, exceções customizadas, timeouts configuráveis. |
| `nexus_discovery.py` | `_NexusDiscoveryMixin` – busca em disco, localização de classes e instanciação com timeout. |
| `nexus_registry.py` | I/O do registry local `.jrvs` e sync com Gist. |
| `llm_config.py` | Configurações de LLM (uso de interpretação, modelos padrão). |

---

## `app/domain/`

### `app/domain/capabilities/`
| Arquivo | Responsabilidade |
|---------|------------------|
| `cap_001.py` a `cap_102.py` | 102 capabilities ativas do sistema. |

### `app/domain/services/`
| Arquivo | Responsabilidade |
|---------|------------------|
| `llm_command_interpreter.py` | Interpretação de comandos via LLM. |
| `capability_manager.py` | Gerenciamento de capabilities. |
| `reward_signal_provider.py` | Provider de sinais de recompensa para RL. |

### `app/domain/models/`
| Arquivo | Responsabilidade |
|---------|------------------|
| `thought_log.py` | Modelo de log de raciocínio interno. |
| `device.py` | Modelo de dispositivo (Edge computing). |

---

## `app/application/`

### `app/application/services/`
| Arquivo | Responsabilidade |
|---------|------------------|
| `assistant_service.py` | Serviço central do assistente. |
| `evolution_orchestrator.py` | Orquestrador de auto-evolução. || `evolution_gatekeeper.py` | Gatekeeper para aprovar mudanças. |
| `evolution_sandbox.py` | Sandbox para testar código gerado. |
| `metabolism_core.py` | Frota multi-LLM com fallback. |
| `llm_router.py` | Roteamento dinâmico de LLMs por tarefa. |
| `jarvis_dev_agent.py` | Agente de desenvolvimento autônomo. |
| `local_repair_agent.py` | Auto-reparo local de erros. |
| `finetune_dataset_collector.py` | Coleta de dados para fine-tuning. |
| `field_vision.py` | Monitoramento de logs e saúde. |
| `capability_gap_reporter.py` | Report de gaps de capacidade. |
| `thought_log_service.py` | Serviço de log de pensamentos. |
| `cost_tracker_adapter.py` | Tracking de custos de LLM. |
| `structured_logger.py` | Logger estruturado. |
| `audit_logger.py` | Logger de auditoria. |
| `context_manager.py` | Gerenciamento de contexto. |
| `semantic_memory.py` | Memória semântica (grafo de fatos). |
| `proactive_core.py` | Núcleo proativo de consolidação. |
| `overwatch_daemon.py` | Daemon de monitoramento de recursos. |
| `jrvs_translator.py` | Tradução entre .json/.yml e .jrvs. |
| `capability_index_service.py` | Índice de confiabilidade de capabilities. |

### `app/application/services/crystallization/`
| Arquivo | Responsabilidade |
|---------|------------------|
| `crystallizer_engine.py` | Motor de cristalização de componentes. |

### `app/application/security/`
| Arquivo | Responsabilidade |
|---------|------------------|
| `capability_authorizer.py` | Autorização de capabilities. |
| `safety_guardian.py` | Guardião de segurança e quotas. |
| `env_secrets_provider.py` | Provider de secrets via env. |
| `pii_redactor.py` | Redator de PII para privacidade. |

---

## `app/adapters/`

### `app/adapters/infrastructure/`
| Arquivo | Responsabilidade |
|---------|------------------|
| `ai_gateway.py` | Gateway unificado para múltiplos LLMs. |
| `gemini_adapter.py` | Adapter para Google Gemini. |
| `gateway_llm_adapter.py` | Adapter LLM com roteamento inteligente. |
| `telegram_adapter.py` | Interface de voz/texto via Telegram. |
| `github_adapter.py` | Integração com GitHub (issues, PRs). |
| `github_worker.py` | Worker para operações GitHub. |
| `ollama_adapter.py` | Adapter para Ollama local. |
| `sqlite_history_adapter.py` | Histórico de comandos em SQLite. |
| `consolidator.py` | Consolidador de contexto Skeleton-Dense. |
| `drive_uploader.py` | Upload para Google Drive. || `gist_uploader.py` | Upload para GitHub Gist. |
| `jrvs_cloud_storage.py` | Storage em nuvem para snapshots .jrvs. |
| `api_server.py` | Servidor API REST. |
| `websocket_manager.py` | Gerenciador WebSocket (se implementado). |
| `overwatch_adapter.py` | Adapter de monitoramento de recursos. |
| `reward_logger.py` | Logger de recompensas. |
| `cost_tracker_adapter.py` | Tracking de custos. |
| `vector_memory_adapter.py` | Memória vetorial FAISS (se implementado). |
| `vision_adapter.py` | Adapter de visão computacional (se implementado). |

### `app/adapters/edge/`
| Arquivo | Responsabilidade |
|---------|------------------|
| `worker_pc.py` | Worker para edge computing. |
| `active_recruiter_adapter.py` | Recruiter de dispositivos edge. |

### `app/adapters/infrastructure/routers/`
| Arquivo | Responsabilidade |
|---------|------------------|
| `github.py` | Rotas API para GitHub. |
| `evolution.py` | Rotas API para evolução. |

---

## `scripts/`

| Arquivo | Responsabilidade |
|---------|------------------|
| `cleanup_repo.py` | Limpeza de arquivos inúteis do repositório. |
| `migrate_to_nexus_di.py` | Migração de imports diretos para Nexus DI. |
| `fix_inconsistencies.py` | Correção de divergências docs vs código. |
| `validate_registry_vs_code.py` | Valida registry vs arquivos reais. |
| `validate_docs_vs_code.py` | Valida documentação vs código. |
| `evolution_mutator.py` | Motor de mutação de capacidades. |
| `show_evolution_status.py` | Mostra status da evolução. |
| `show_rl_status.py` | Mostra status de RL. |
| `metabolism_analyzer.py` | Analisador do MetabolismCore. |
| `validate_architecture.py` | Validação de arquitetura. |
| `crystallizer_engine.py` | Engine de cristalização (standalone). |
| `project_stabilizer.py` | Estabilização de projeto. |
| `fix_cap_stubs.py` | Correção de stubs de capabilities. |
| `evolve_all_pending.py` | Evolui todas as capabilities pendentes. |

---

## `tests/`

| Arquivo | Responsabilidade |
|---------|------------------|
| `test_nexus.py` | Testes do Nexus DI. || `test_document_store.py` | Testes do DocumentStore. |
| `test_jrvs_codec.py` | Testes do codec .jrvs. |
| `domain/` | Testes de domínio. |
| `application/` | Testes de aplicação. |
| `adapters/` | Testes de adapters. |
| `security/` | Testes de segurança. |
| `privacy/` | Testes de privacidade. |

---

## `config/`

### `config/pipelines/`
| Arquivo | Responsabilidade |
|---------|------------------|
| `build_installer.yml` | Pipeline de build do installer. |
| `sync_drive.yml` | Pipeline de sync com Google Drive. |
| `self_healing.yml` | Pipeline de self-healing. |
| `evolution.yml` | Pipeline de evolução. |

---

## `data/`

| Arquivo | Responsabilidade |
|---------|------------------|
| `nexus_registry.json` | Registry de componentes Nexus. |
| `nexus_registry.jrvs` | Registry em formato .jrvs. |
| `capabilities.json` | Inventário de capabilities. |
| `context.json` | Contexto atual do sistema. |
| `architecture_rules.yml` | Regras de arquitetura. |
| `evolution_proposals/` | Propostas de evolução. |
| `jrvs/` | Políticas compiladas (.jrvs). |
| `README.md` | Documentação de formatos de dados. |

---

## `docs/`

| Arquivo | Responsabilidade |
|---------|------------------|
| `STATUS.md` | Status atual do projeto. |
| `ARCHITECTURE.md` | Arquitetura do sistema. |
| `NEXUS.md` | Sistema de injeção de dependência. |
| `ARQUIVO_MAP.md` | Este arquivo — mapa de arquivos. |

---

## Raiz do Projeto
| Arquivo | Responsabilidade |
|---------|------------------|
| `README.md` | Documentação principal. |
| `CONTRIBUTING.md` | Diretrizes de contribuição. |
| `LICENSE` | Licença MIT. |
| `padrão_estrutural.md` | Padrão de pipelines e arquitetura. |
| `requirements/core.txt` | Dependências principais. |
| `requirements/dev.txt` | Dependências de desenvolvimento. |
| `.github/workflows/` | Workflows do GitHub Actions. |
| `.backups/` | Backups automáticos. |
| `logs/` | Logs de execução. |