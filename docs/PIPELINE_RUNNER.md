# PIPELINE RUNNER

Executor de pipelines declarativos em YAML. Cada pipeline é uma sequência de
passos que resolvem componentes pelo Nexus e executam seus `execute(context)`.

- Código: `app/runtime/pipeline_runner.py`
- Configurações: `config/pipelines/<nome>.yml`

---

## Uso

```bash
# Pipeline declarado em config/pipelines/sync_drive.yml
PIPELINE=sync_drive python app/runtime/pipeline_runner.py

# Modo estrito global (aborta no primeiro passo com falha)
PIPELINE=sync_drive PIPELINE_STRICT=true python app/runtime/pipeline_runner.py

# Sem PIPELINE definido o runner imprime a ajuda e sai com código 1
python app/runtime/pipeline_runner.py
```

O runner deve ser executado a partir do **root do projeto** (os caminhos de
pipeline e os artefatos gerados são relativos ao diretório atual). O root é
injetado automaticamente no `sys.path`, portanto não é necessário exportar
`PYTHONPATH` para a execução direta.

### Códigos de saída

| Situação | Código | `status` do contexto |
|----------|--------|----------------------|
| Todos os passos OK | 0 | `success` |
| Algum passo falhou (sem strict) | 1 | `partial` |
| Falha em strict mode | 1 | `failed` (aborta e retorna o contexto) |

---

## Formato do pipeline

```yaml
# config/pipelines/<nome>.yml
description: "Descrição curta do objetivo do pipeline"
strict: false            # default global; sobrescrito por PIPELINE_STRICT=true

components:
  nome_do_passo:
    id: "componente_nexus"          # ID resolvido via nexus.resolve()
    hint_path: "app/adapters/infrastructure/componente_nexus"  # opcional
    singleton: true                 # opcional (metadado do componente)
    action: "backup"                # opcional (vai no contexto entregue ao componente)
    config:
      strict_mode: true             # sobrescreve o strict só para este passo
```

Regras do passo:

1. `id` (ou o nome do passo) é resolvido com `nexus.resolve(target_id=..., hint_path=...)`.
2. Se o Nexus devolver um `CloudMock` (circuit breaker aberto ou componente
   inexistente), o passo **falha**: o `execute()` do mock nunca é chamado, para
   não mascarar indisponibilidade como sucesso.
3. `execute(context)` é chamado quando existe; caso contrário o componente é
   chamado diretamente se for callable.
4. O dicionário retornado é mesclado no contexto compartilhado, exceto as chaves
   estruturais `results`, `pipeline` e `status`.
5. `config.strict_mode: true` no passo (ou `strict: true` no pipeline) faz a
   falha levantar exceção e abortar o restante do pipeline.

---

## Pipelines existentes

| Pipeline | Objetivo |
|----------|----------|
| `sync_drive.yml` | Snapshot consolidado → Drive, Telegram e Gist |
| `auto_evolution.yml` | Ciclo de auto-evolução |
| `jarvis_chat.yml` | Fluxo de conversa do assistente |
| `build_installer.yml` | Build do instalador |

---

## Onde isso é executado

- `.github/workflows/consolidador.yml` e `.github/workflows/sync_to_drive.yml`
  rodam `PIPELINE=sync_drive python app/runtime/pipeline_runner.py`.
- `scripts/validate_self_awareness.py` verifica se o snapshot consolidado
  (`CORE_LOGIC_CONSOLIDATED.txt`), gerado pelo `consolidator` deste pipeline,
  está disponível para os consumidores de long context.

---

## Testes

```bash
python -m pytest tests/test_pipeline_runner.py -q
```

Cobrem detecção de `CloudMock`, encaminhamento de `hint_path` e execução normal
de componentes.
