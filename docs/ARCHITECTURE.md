
# JARVIS — Arquitetura do Sistema

**Versão:** 2.0.0  
**Atualizado em:** 2026-03-10

---

## 🏗️ Visão Geral

JARVIS segue **Arquitetura Hexagonal** com **Injeção de Dependência (Nexus DI)**.

```
┌─────────────────────────────────────────┐
│         INTERFACE / CI-CD               │
│   - GitHub Actions                      │
│   - API REST                            │
│   - Telegram Bot                        │
├─────────────────────────────────────────┤
│         ADAPTERS (Infra/Edge)           │
│   - gateway_llm_adapter.py              │
│   - telegram_adapter.py                 │
│   - github_adapter.py                   │
│   - ollama_adapter.py                   │
├─────────────────────────────────────────┤
│         APPLICATION (Services)          │
│   - assistant_service.py                │
│   - evolution_orchestrator.py           │
│   - metabolism_core.py                  │
│   - llm_router.py                       │
├─────────────────────────────────────────┤
│         DOMAIN (Regras de Negócio)      │
│   - capabilities/ (102 capabilities)    │
│   - services/ (llm_command_interpreter) │
│   - models/ (thought_log, device)       │
├─────────────────────────────────────────┤
│         CORE (Nexus/DI)                 │
│   - nexus.py                            │
│   - nexus_exceptions.py                 │
│   - nexus_discovery.py                  │
│   - nexus_registry.py                   │
└─────────────────────────────────────────┘
```

---

## 🔄 Fluxo de Execução

```
1. Comando do Usuário (Telegram/API)
         ↓
2. GatewayLLMAdapter → interpreta comando
         ↓
3. AssistantService → processa comando
         ↓
4. Nexus DI → resolve componentes necessários
         ↓
5. Adapters → executam ações (GitHub, Telegram, etc.)
         ↓
6. Response → retorna ao usuário
```

---

## 🧬 Auto-Evolução

```
1. Erro/Gap detectado (FieldVision ou usuário)
         ↓
2. EvolutionOrchestrator → inicia ciclo
         ↓
3. EvolutionGatekeeper → valida proposta
         ↓
4. EvolutionSandbox → testa código gerado
         ↓
5. GitHubWorker → cria PR
         ↓
6. CI/CD → valida e mergeia
```

---

## 🧠 Multi-LLM com Fallback

O **MetabolismCore** gerencia uma frota de LLMs:

| Provider | Modelo | Uso |
|----------|--------|-----|
| Groq | llama-3.3-70b-versatile | Padrão (rápido, barato) |
| Gemini | gemini-2.0-flash | Fallback para payloads grandes |
| Ollama | qwen2.5-coder:14b | Local, zero custo |

**Roteamento:** `LLMRouter` seleciona o melhor adapter por `task_type`.

---

## 📦 Nexus DI — Injeção de Dependência

### Componentes Registrados

| ID | Classe | Localização |
|----|--------|-------------|
| `assistant_service` | `AssistantService` | `app/application/services/assistant_service.py` |
| `evolution_orchestrator` | `EvolutionOrchestrator` | `app/application/services/evolution_orchestrator.py` |
| `metabolism_core` | `MetabolismCore` | `app/application/services/metabolism_core.py` |
| `llm_router` | `LLMRouter` | `app/application/services/llm_router.py` |
| `gateway_llm_adapter` | `GatewayLLMCommandAdapter` | `app/adapters/infrastructure/gateway_llm_adapter.py` |
| `telegram_adapter` | `TelegramAdapter` | `app/adapters/infrastructure/telegram_adapter.py` |
| `github_adapter` | `GitHubAdapter` | `app/adapters/infrastructure/github_adapter.py` |
| `consolidator` | `Consolidator` | `app/adapters/infrastructure/consolidator.py` |
| `crystallizer_engine` | `CrystallizerEngine` | `app/application/services/crystallization/crystallizer_engine.py` |
| `structured_logger` | `StructuredLogger` | `app/application/services/structured_logger.py` |
| `thought_log_service` | `ThoughtLogService` | `app/application/services/thought_log_service.py` |
| `capability_manager` | `CapabilityManager` | `app/domain/services/capability_manager.py` |
| `llm_command_interpreter` | `LLMCommandInterpreter` | `app/domain/services/llm_command_interpreter.py` |
| `semantic_memory` | `SemanticMemory` | `app/application/services/semantic_memory.py` |
| `field_vision` | `FieldVision` | `app/application/services/field_vision.py` |
| `local_repair_agent` | `LocalRepairAgent` | `app/application/services/local_repair_agent.py` |
| `jarvis_dev_agent` | `JarvisDevAgent` | `app/application/services/jarvis_dev_agent.py` |
| `evolution_gatekeeper` | `EvolutionGatekeeper` | `app/application/services/evolution_gatekeeper.py` |
| `evolution_sandbox` | `EvolutionSandbox` | `app/application/services/evolution_sandbox.py` |
| `cost_tracker_adapter` | `CostTrackerAdapter` | `app/adapters/infrastructure/cost_tracker_adapter.py` |
| `sqlite_history_adapter` | `SQLiteHistoryAdapter` | `app/adapters/infrastructure/sqlite_history_adapter.py` |
| `ai_gateway` | `AIGateway` | `app/adapters/infrastructure/ai_gateway.py` |
| `ollama_adapter` | `OllamaAdapter` | `app/adapters/infrastructure/ollama_adapter.py` |
| `github_worker` | `GitHubWorker` | `app/adapters/infrastructure/github_worker.py` |
| `audit_logger` | `AuditLogger` | `app/application/services/audit_logger.py` |
| `finetune_dataset_collector` | `FineTuneDatasetCollector` | `app/application/services/finetune_dataset_collector.py` |
| `jrvs_translator` | `JrvsTranslator` | `app/application/services/jrvs_translator.py` |
| `capability_index_service` | `CapabilityIndexService` | `app/application/services/capability_index_service.py` |
| `proactive_core` | `ProactiveCore` | `app/application/services/proactive_core.py` |
| `overwatch_daemon` | `OverwatchDaemon` | `app/application/services/overwatch_daemon.py` |
| `jrvs_cloud_storage` | `JrvsCloudStorage` | `app/adapters/infrastructure/jrvs_cloud_storage.py` |
| `drive_uploader` | `DriveUploader` | `app/adapters/infrastructure/drive_uploader.py` |
| `gist_uploader` | `GistUploader` | `app/adapters/infrastructure/gist_uploader.py` |

→ Veja [docs/NEXUS.md](docs/NEXUS.md) para detalhes completos.

---

## 🔒 Segurança

| Componente | Responsabilidade |
|------------|------------------|
| `CapabilityAuthorizer` | Allowlist de capabilities + payload injection detection |
| `SafetyGuardian` | Resource quotas + emergency stop |
| `EnvSecretsProvider` | Único ponto de acesso a secrets |
| `PiiRedactor` | Redação de PII antes de indexar |

---

## 📊 Monitoramento

| Componente | Responsabilidade |
|------------|------------------|
| `FieldVision` | Monitoramento de logs e saúde |
| `OverwatchDaemon` | Daemon de monitoramento de recursos |
| `ThoughtLogService` | Log de raciocínio interno |
| `AuditLogger` | Log de auditoria imutável |

---

## 🧪 Testes

```bash
# Testes de domínio (sem hardware)
pytest tests/domain/ -v

# Testes de aplicação
pytest tests/application/ -v

# Testes de adapters
pytest tests/adapters/ -v

# Todos os testes
pytest tests/ -v
```

**Cobertura atual:** ~60% (alvo: 80%)

---

## 📈 Roadmap

| Fase | Status | Descrição |
|------|--------|-----------|
| Phase 1 | ✅ Completo | Arquitetura Hexagonal + Nexus DI |
| Phase 2 | 🟡 Em Progresso | Auto-Evolução + Self-Healing |
| Phase 3 | ⚪ Pendente | Soldier Mesh (Edge Computing) |
| Phase 4 | ⚪ Pendente | Fine-Tuning Contínuo |
