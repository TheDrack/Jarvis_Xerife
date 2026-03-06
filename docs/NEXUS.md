# JARVIS – Nexus

> O Nexus é o container de injeção de dependência do JARVIS.  
> **Regra:** Todo componente ativo deve ser instanciado pelo Nexus.

---

## Módulos do Nexus

O `nexus.py` original foi dividido em quatro módulos focados (≤ 250 linhas cada):

| Arquivo | Responsabilidade |
|---|---|
| `app/core/nexus.py` | Classe principal `JarvisNexus`, API pública (`resolve`, `resolve_class`, `commit_memory`). Re-exporta `NexusComponent` e `CloudMock`. |
| `app/core/nexus_exceptions.py` | `CloudMock`, `_CircuitBreakerEntry`, exceções customizadas (`ImportTimeoutError`, `InstantiateTimeoutError`, `AmbiguousComponentError`), timeouts configuráveis e `nexus_guarded_instantiate`. |
| `app/core/nexus_discovery.py` | `_NexusDiscoveryMixin` – lógica de busca em disco e instanciação com timeout. |
| `app/core/nexus_registry.py` | `_NexusRegistryMixin` – leitura/escrita do registry local `.jrvs` e sincronização com GitHub Gist. |

---

## Como funciona

```python
from app.core.nexus import nexus

# Instancia (ou reutiliza singleton) um componente pelo ID
component = nexus.resolve("audit_logger")
component.execute({"metadata": {...}, "artifacts": {...}})
```

---

## Registrar um novo componente

1. Crie uma classe que herda de `NexusComponent`:

```python
# app/adapters/infrastructure/meu_componente.py
from app.core.nexus import NexusComponent  # Importar sempre de app.core.nexus

class MeuComponente(NexusComponent):
    def execute(self, context):
        # implementação
        return {"success": True}
```

2. Adicione ao `data/nexus_registry.json`:

```json
{
  "components": {
    "meu_componente": "app.adapters.infrastructure.meu_componente.MeuComponente"
  }
}
```

3. Resolva via Nexus:

```python
comp = nexus.resolve("meu_componente")
comp.execute(context)
```

---

## Componentes Registrados

| ID | Classe | Localização |
|---|---|---|
| `cognitive_router` | `CognitiveRouter` | `app/domain/gears/cognitive_router.py` |
| `llm_engine` | `LlmEngine` | `app/domain/gears/llm_engine.py` |
| `system_executor` | `SystemExecutor` | `app/adapters/infrastructure/system_executor.py` |
| `orchestrator` | `OrchestratorService` | `app/application/services/orchestrator_service.py` |
| `context_memory` | `ContextMemory` | `app/domain/capabilities/context_memory.py` |
| `interface_bridge` | `InterfaceBridge` | `app/application/services/interface_bridge.py` |
| `audit_logger` | `AuditLogger` | `app/adapters/infrastructure/audit_logger.py` |
| `consolidator` | `Consolidator` | `app/adapters/infrastructure/consolidator.py` |
| `telegram_adapter` | `TelegramAdapter` | `app/adapters/infrastructure/telegram_adapter.py` |
| `gist_uploader` | `GistUploader` | `app/adapters/infrastructure/gist_uploader.py` |
| `drive_uploader` | `DriveUploader` | `app/adapters/infrastructure/drive_uploader.py` |
| `vector_memory_adapter` | `VectorMemoryAdapter` | `app/adapters/infrastructure/vector_memory_adapter.py` |
| `vision_adapter` | `VisionAdapter` | `app/adapters/infrastructure/vision_adapter.py` |
| `document_store` | `DocumentStore` | `app/utils/document_store.py` |
| `jrvs_translator` | `JrvsTranslator` | `app/application/services/jrvs_translator.py` |
| `policy_store` | `PolicyStore` | `app/core/meta/policy_store.py` |
| `jrvs_compiler` | `JrvsCompiler` | `app/core/meta/jrvs_compiler.py` |
| `decision_engine` | `DecisionEngine` | `app/core/meta/decision_engine.py` |
| `exploration_controller` | `ExplorationController` | `app/core/meta/exploration_controller.py` |
| `notification_service` | `NotificationService` | `app/application/services/notification_service.py` |
| `overwatch_daemon` | `OverwatchDaemon` | `app/adapters/infrastructure/overwatch_adapter.py` |
| `auto_evolution_service` | `AutoEvolutionServiceV2` | `app/application/services/auto_evolutionV2.py` |
| `local_repair_agent` | `LocalRepairAgent` | `app/application/services/local_repair_agent.py` |
| `metabolism_core` | `MetabolismCore` | `app/application/services/metabolism_core.py` |
| `evolution_loop` | `EvolutionLoopService` | `app/application/services/evolution_loop.py` |
| `ollama_adapter` | `OllamaAdapter` | `app/adapters/infrastructure/ollama_adapter.py` |
| `evolution_orchestrator` | `EvolutionOrchestrator` | `app/application/services/evolution_orchestrator.py` |
| `procedural_memory_adapter` | `ProceduralMemoryAdapter` | `app/adapters/infrastructure/procedural_memory_adapter.py` |
| `capability_index_service` | `CapabilityIndexService` | `app/application/services/capability_index_service.py` |
| `cost_tracker_adapter` | `CostTrackerAdapter` | `app/adapters/infrastructure/cost_tracker_adapter.py` |

> **Nota:** `context_memory` ainda está em `app/domain/capabilities/` – pendente de revisão.

---

## Discovery automático

Se um componente não está no registry local, o Nexus faz discovery percorrendo `app/`:

```python
nexus.resolve("meu_componente", hint_path="adapters/infrastructure")
```

O parâmetro `hint_path` acelera a busca limitando o diretório.

Quando mais de um arquivo candidato é encontrado para o mesmo ID, o Nexus lança `AmbiguousComponentError` em vez de resolver silenciosamente.

---

## Circuit Breaker

O Nexus possui um mecanismo de Circuit Breaker embutido para proteger o sistema de travamentos causados por componentes lentos ou indisponíveis.

**Comportamento:**
- Se o **import** do módulo demorar mais de **`NEXUS_IMPORT_TIMEOUT`** (padrão: **10 s**), lança `ImportTimeoutError`.
- Se a **instanciação** da classe demorar mais de **`NEXUS_INSTANTIATE_TIMEOUT`** (padrão: **5 s**), lança `InstantiateTimeoutError`.
- Se qualquer timeout ocorrer, o circuito abre por **`CIRCUIT_BREAKER_TIMEOUT`** (padrão: **30 s**). Durante esse período, `nexus.resolve()` retorna imediatamente um `CloudMock`.
- Após o timeout do circuit breaker (padrão **60 s de reset**), o circuito fecha e a próxima chamada tenta instanciar novamente.

Todos os timeouts são configuráveis via variáveis de ambiente:

| Variável | Padrão | Descrição |
|---|---|---|
| `NEXUS_IMPORT_TIMEOUT` | `10.0` | Timeout de import do módulo (s) |
| `NEXUS_INSTANTIATE_TIMEOUT` | `5.0` | Timeout de instanciação da classe (s) |
| `NEXUS_TIMEOUT` | `30.0` | Janela de abertura do circuit breaker (s) |
| `NEXUS_CIRCUIT_RESET` | `60.0` | Cooldown antes do circuito fechar (s) |
| `NEXUS_STRICT_MODE` | `false` | Se `true`, desabilita discovery em disco |

**`CloudMock`** é um absorvedor transparente: aceita qualquer chamada de método sem erro, permitindo que o sistema continue operando em modo degradado.

```python
from app.core.nexus import nexus, CloudMock

component = nexus.resolve("algum_componente")
if isinstance(component, CloudMock):
    # componente indisponível — modo fallback
    pass
```

---

## NexusComponent – Interface

> **Import correto:** sempre use `from app.core.nexus import NexusComponent`.

```python
class NexusComponent(ABC):
    def configure(self, config: dict) -> None:
        """Configuração opcional antes da execução."""
        pass

    @abstractmethod
    def execute(self, context: dict) -> dict:
        """Execução principal. Deve retornar evidência de efeito."""
        pass
```

---

## Política Frozen

Componentes não registrados no Nexus e não importados em nenhum arquivo ativo  
devem ser movidos para `.frozen/`.

Para reativar:
1. Mova o arquivo para o local correto em `app/`
2. Adicione ao `data/nexus_registry.json`
3. Documente em `docs/ARQUIVO_MAP.md`
