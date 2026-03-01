# JARVIS – Nexus

> O Nexus é o container de injeção de dependência do JARVIS.  
> **Regra:** Todo componente ativo deve ser instanciado pelo Nexus.

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
from app.core.nexuscomponent import NexusComponent

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
| `llm_engine` | `LLMEngine` | `app/domain/gears/llm_engine.py` |
| `system_executor` | `SystemExecutor` | `app/adapters/infrastructure/system_executor.py` |
| `orchestrator` | `JARVISOrchestrator` | `app/application/services/orchestrator_service.py` |
| `context_memory` | `ContextMemory` | `app/domain/capabilities/context_memory.py` |
| `interface_bridge` | `InterfaceBridge` | `app/application/services/interface_bridge.py` |
| `audit_logger` | `AuditLogger` | `app/adapters/infrastructure/audit_logger.py` |

> **Nota:** `context_memory` ainda está em `app/domain/capabilities/` – pendente de revisão.

---

## Discovery automático

Se um componente não está no registry local, o Nexus faz discovery percorrendo `app/`:

```python
nexus.resolve("meu_componente", hint_path="adapters/infrastructure")
```

O parâmetro `hint_path` acelera a busca limitando o diretório.

---

## NexusComponent – Interface

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
