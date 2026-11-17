# Nexus — composição e injeção de dependência

**Escopo:** mecanismo de resolução de componentes do núcleo Python. O Nexus não é o Universal Tool Registry e não concede permissões a ferramentas.

## Responsabilidade

O singleton exposto por app.core.nexus resolve componentes por identificador, aplica cache e delega discovery/instanciação ao conjunto de módulos do core. app/container.py é um wrapper de compatibilidade que usa o mesmo singleton.

Nem todo objeto, função ou módulo do repositório precisa ser um NexusComponent. A regra aplica-se aos componentes que são geridos pelo contrato Nexus e registrados/descobertos por esse mecanismo.

## Módulos principais

| Módulo | Responsabilidade |
|---|---|
| app/core/nexus.py | API pública e resolução de componentes. |
| app/core/nexus_exceptions.py | Exceções, CloudMock e parâmetros de timeout/circuit breaker. |
| app/core/nexus_discovery.py | Descoberta e instanciação de componentes. |
| app/core/nexus_registry.py | Leitura/escrita do registro de componentes. |
| app/core/nexuscomponent.py | Contrato/base class para componentes Nexus. |

## API de resolução

```python
from app.core.nexus import nexus

assistant = nexus.resolve("assistant_service")
if assistant is None:
    raise RuntimeError("assistant_service indisponível")

loaded_ids = nexus.list_loaded_ids()
nexus.invalidate_component("assistant_service")
```

A resolução pode retornar um CloudMock quando a política de falha/configuração aplicável assim determinar. O chamador deve verificar o resultado e não interpretar um mock como execução bem-sucedida.

Parâmetros e comportamento exatos devem ser confirmados na assinatura de app/core/nexus.py do branch utilizado. Não dependa de detalhes de cache ou fallback sem consultar os testes correspondentes.

## Configuração do circuit breaker e discovery

Os defaults abaixo são contrato testado por tests/test_nexus_docs_contract.py:

| Variável | Default |
|---|---:|
| `NEXUS_TIMEOUT` | 30s |
| `NEXUS_CIRCUIT_RESET` | 60s |
| `NEXUS_IMPORT_TIMEOUT` | 10s |
| `NEXUS_INSTANTIATE_TIMEOUT` | 5s |
| `NEXUS_STRICT_MODE` | false |

O teste compara a tabela com os valores do módulo app/core/nexus_exceptions.py. Se o código mudar, atualize este documento e o contrato de teste em conjunto.

## Registro de componentes

O registro versionado do projeto está em data/nexus_registry.json. Discovery e registro estático são mecanismos complementares: não trate a presença de um ID no arquivo como prova de que o módulo pode ser importado, instanciado ou executado no ambiente atual.

O arquivo data/nexus_registry.jrvs é um artefato de compatibilidade gerado sob demanda; não deve ser editado como fonte primária. O formato legível e versionado é a referência para alterações.

## Limites e distinções

- Nexus resolve componentes; não é um sistema de autenticação ou autorização.
- Nexus DI não substitui ToolRegistry/ToolDispatcher.
- AdapterRegistry é um catálogo separado de adapters/capabilities.
- A saúde de um provider externo depende de credenciais, rede e serviço de destino.
- Falhas de resolução não devem ser convertidas em sucesso silencioso.

## Validação

```bash
python -m pytest tests/test_nexus_docs_contract.py tests/test_nexus_circuit_breaker.py -q
python scripts/validate_architecture.py
```

O segundo comando executa verificações de arquitetura adicionais; consulte seu código para saber exatamente quais gates estão ativos.
