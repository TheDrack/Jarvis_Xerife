# Core Module

Contém o núcleo central do JARVIS — sistema de injeção de dependência, configuração e camada cognitiva adaptativa.

## Módulos Nexus

O sistema de DI foi dividido em quatro módulos focados (≤ 250 linhas cada):

- `nexus.py`: Container principal `JarvisNexus`. API pública: `resolve()`, `resolve_class()`, `commit_memory()`. Re-exporta `NexusComponent` e `CloudMock`.
- `nexus_exceptions.py`: `CloudMock` (fallback transparente), `_CircuitBreakerEntry`, exceções customizadas (`ImportTimeoutError`, `InstantiateTimeoutError`, `AmbiguousComponentError`) e timeouts configuráveis via env.
- `nexus_discovery.py`: `_NexusDiscoveryMixin` – busca em disco (`app/`), localização de classes por ID e instanciação com timeout.
- `nexus_registry.py`: `_NexusRegistryMixin` – leitura/escrita do registry local `.jrvs` e sincronização remota com GitHub Gist.
- `nexuscomponent.py`: Interface base `NexusComponent` (ABC) com `execute(context)`. Exporta helpers privados usados por testes.

## Outros arquivos

- `config.py`: Carregamento de configurações do ambiente (`.env`, variáveis de ambiente).
- `encryption.py`: Funções de criptografia para credenciais e configurações sensíveis.
- `llm_config.py`: Configuração da frota de LLMs (`config/llm_fleet.json`).

## meta/

Camada cognitiva adaptativa do Nexus:

- `policy_store.py`: Persiste políticas por módulo cognitivo em `.jrvs`.
- `jrvs_compiler.py`: Compila snapshots binários `.jrvs` com validação SHA-256/CRC32.
- `decision_engine.py`: Motor de decisão com scoring multi-objetivo e epsilon-greedy adaptativo.
- `exploration_controller.py`: Descoberta e promoção de novas ferramentas ao registro.
- `compile_lock.py`: Lock de arquivo para evitar compilações concorrentes.

## Import correto

```python
# CORRETO – sempre importar de app.core.nexus
from app.core.nexus import NexusComponent, nexus, CloudMock

# INCORRETO – não usar nexuscomponent diretamente em código de componente
# from app.core.nexuscomponent import NexusComponent
```

