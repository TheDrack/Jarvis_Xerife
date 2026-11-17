# Pipeline Runner

O Pipeline Runner executa definições YAML em config/pipelines/. Ele preserva o caminho legado que resolve componentes pelo Nexus e possui uma rota separada para etapas declaradas com tool_id.

**Importante:** a existência da rota tool_id não significa que a execução de ferramentas esteja habilitada. A composição atual do runner cria ToolDispatcher sem fornecer ToolAuthorizationPolicy. O dispatcher recusa chamadas sem uma política confiável. O campo tool_approvals apenas preenche metadados da requisição; não constitui, por si só, uma aprovação verificável.

## Código e configuração

- Runner: app/runtime/pipeline_runner.py
- Manifests: config/tool_registry.json
- Dispatcher: app/runtime/toolbox/
- Toolchains: config/toolchains/
- Pipelines: config/pipelines/

O runner aceita arquivos .yml e .yaml, procurando primeiro o sufixo .yml.

Pipelines presentes no branch de referência:
- auto_evolution.yml
- build_installer.yml
- jarvis_chat.yml
- osint_geo_discovery.yaml
- sync_drive.yml

Consulte o conteúdo YAML do branch para conhecer os passos e dependências de cada pipeline.

## Execução

Execute a partir da raiz do repositório:

```bash
PIPELINE=sync_drive python app/runtime/pipeline_runner.py
PIPELINE=sync_drive PIPELINE_STRICT=true python app/runtime/pipeline_runner.py
```

Sem PIPELINE, o runner imprime a forma de uso e termina com código 1.

Também é possível chamar a API Python:

```python
from app.runtime.pipeline_runner import run_pipeline

result = run_pipeline(
    "sync_drive",
    global_strict=False,
    inputs={"correlation_id": "manual-run-001"},
)
```

## Contexto de execução

O contexto inicial contém:
- pipeline
- strict
- results
- artifacts

inputs pode adicionar valores de runtime, mas não pode sobrescrever as chaves reservadas pipeline, strict, results, artifacts ou component_config.

Cada passo executa em ordem de declaração no YAML. O retorno em formato dict pode acrescentar dados ao contexto, mas não pode sobrescrever results, pipeline ou status.

## Tipos de passo

### Passo legado — resolução Nexus

Exemplo de forma declarativa:

```yaml
components:
  sync_step:
    id: "consolidator"
    hint_path: "app/adapters/infrastructure/consolidator.py"
    config:
      strict_mode: false
```

O runner:
1. resolve id (ou o nome do passo) via nexus.resolve();
2. encaminha hint_path, inclusive quando ausente;
3. recusa CloudMock sem chamar execute();
4. chama execute(context) ou, se o objeto for callable, chama o objeto;
5. mescla retorno dict no contexto respeitando as chaves estruturais.

A chave config é disponibilizada ao componente em component_config. strict no pipeline e config.strict_mode controlam a falha/aborto; a opção do passo torna a execução estrita para aquele passo.

### Passo de ferramenta — Tool Dispatcher

Uma etapa com tool_id segue a rota ToolRequest → ToolDispatcher → ToolRegistry/manifest. Os campos relevantes no código incluem:
- tool_id e tool_version;
- capability;
- arguments ou arguments_from_context;
- tool_approvals, que fornece scope, approval_id e idempotency_key à requisição.

Não coloque arguments e arguments_from_context juntos. O runner rejeita essa combinação.

**Limite atual:** _get_tool_dispatcher() instancia ToolDispatcher com registry e sink JSONL, mas sem authorizer. O dispatcher exige authorize_tool de uma ToolAuthorizationPolicy confiável e falha fechada quando ela não existe. Portanto, não considere um passo tool_id executável apenas porque o manifest existe ou porque tool_approvals contém approval_id. A aprovação precisa ser validada por uma composição confiável, que não está fornecida por este runner.

## Strict mode e resultados

- Sem strict: o runner tenta os passos seguintes e retorna status success ou partial.
- Com strict: a primeira falha encerra o pipeline com status failed.
- Pipeline inexistente, YAML inválido ou falha fatal resulta em erro.
- O CLI retorna 0 apenas quando o contexto final tem status success; estados partial/failed retornam 1.

## Segurança

- Não trate valores YAML como autorização.
- Não passe segredos em inputs, config ou arquivos de pipeline.
- Passos tool_id devem permanecer bloqueados até existir uma composição com identidade, sessão e política confiáveis.
- A autorização deve ocorrer no dispatcher/host, antes de qualquer efeito externo.
- Não confunda logs JSONL locais com auditoria durável/distribuída.

## Testes

```bash
python -m pytest tests/test_pipeline_runner.py -q
```

Os testes atuais cobrem, entre outros pontos, resolução Nexus, encaminhamento de hint_path, comportamento de CloudMock e modo estrito. Consulte os testes do runtime/toolbox para os contratos do dispatcher. Não afirme cobertura de ponta a ponta para execução de tool_id sem um teste com política confiável real/fake e autorização validada.
