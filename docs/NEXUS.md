# JARVIS — Nexus DI (Injeção de Dependência)

**Versão:** 2.0.0  
**Atualizado em:** 2026-03-10

---

## 🎯 Visão Geral

O **Nexus** é o container de injeção de dependência do JARVIS.

**Todos os componentes ativos devem ser `NexusComponent` e registrados no Nexus.**

---

## 📦 Módulos do Nexus

O Nexus foi dividido em quatro módulos focados:

| Módulo | Responsabilidade |
|--------|------------------|
| `nexus.py` | Container principal, API pública |
| `nexus_exceptions.py` | CloudMock, exceções, timeouts, circuit breaker |
| `nexus_discovery.py` | Discovery em disco, localização e instanciação |
| `nexus_registry.py` | I/O do registry local `.jrvs` e sync com Gist |

---

## 🔧 API Pública

### `nexus.resolve(component_id, use_cache=True)`

Resolve e instancia um componente pelo ID.

```python
from app.core.nexus import nexus

# Resolve um componente
assistant = nexus.resolve("assistant_service")
assistant.execute({"command": "hello"})

# Sem cache (força re-instanciação)
assistant = nexus.resolve("assistant_service", use_cache=False)
```

### `nexus.list_loaded_ids()`

Lista todos os IDs de componentes carregados.

```pythonids = nexus.list_loaded_ids()
print(f"Componentes: {len(ids)}")
```

### `nexus.invalidate_component(component_id)`

Invalida o cache de um componente específico.

```python
nexus.invalidate_component("assistant_service")
```

### `nexus.commit_memory()`

Persiste o estado atual do Nexus.

```python
nexus.commit_memory()
```

---

## 📋 Registry

### Registry Local

**Arquivos:** `data/nexus_registry.json` / `data/nexus_registry.jrvs`

```json
{
  "components": {
    "assistant_service": "app.application.services.assistant_service.AssistantService",
    "evolution_orchestrator": "app.application.services.evolution_orchestrator.EvolutionOrchestrator",
    "metabolism_core": "app.application.services.metabolism_core.MetabolismCore"
  }
}
```

### Tradução Automática

O **JrvsTranslator** sincroniza `.json`/`.yml` com `.jrvs`:

```bash
# Via API
curl -X POST /v1/translate/jrvs \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"action": "sync_all", "data_dir": "data"}'
```

```pythonfrom app.application.services.jrvs_translator import JrvsTranslator

translator = JrvsTranslator()
translator.execute({"action": "to_jrvs", "data_dir": "data"})
```

> ⚠️ Arquivos `.json`/`.yml` são a **fonte de verdade**. Edite sempre o formato legível.

---

## 🛡️ Circuit Breaker

O Nexus implementa Circuit Breaker para falhas de import/instanciação:

| Configuração | Variável de Ambiente | Padrão |
|--------------|---------------------|--------|
| Timeout de Import | `NEXUS_TIMEOUT` | 30s |
| Timeout de Instanciação | `NEXUS_INSTANTIATE_TIMEOUT` | 30s |
| Reset do Circuit Breaker | `NEXUS_CIRCUIT_RESET` | 300s |
| Modo Estrito | `NEXUS_STRICT_MODE` | false |

### CloudMock

Quando um componente falha, o Nexus injeta um `CloudMock`:

```python
from app.core.nexus import nexus, CloudMock

component = nexus.resolve("componente_que_nao_existe")
if isinstance(component, CloudMock):
    print("Componente indisponível — usando mock")
```

---

## 📊 Componentes Registrados

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
→ Veja [docs/ARQUIVO_MAP.md](docs/ARQUIVO_MAP.md) para lista completa.

---

## 🧪 Validação

```bash
# Validar registry vs código
python scripts/validate_registry_vs_code.py

# Validar docs vs código
python scripts/validate_docs_vs_code.py

# Validar arquitetura
python scripts/validate_architecture.py
```