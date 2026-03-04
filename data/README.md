# Diretório `data/`

Contém os arquivos de dados estáticos e de runtime utilizados pelo JARVIS.

## Arquivos

| Arquivo | Formato | Descrição |
|---------|---------|-----------|
| `nexus_registry.json` | JSON | Mapeamento de IDs de componentes para módulos Python |
| `nexus_registry.jrvs` | JRVS | Espelho binário do `nexus_registry.json` (leitura rápida) |
| `capabilities.json` | JSON | Inventário de capacidades (CAP-001 a CAP-102+) |
| `capabilities.jrvs` | JRVS | Espelho binário do `capabilities.json` |
| `master_crystal.json` | JSON | Metadados do sistema e registro de cristalização |
| `master_crystal.jrvs` | JRVS | Espelho binário do `master_crystal.json` |
| `architecture_rules.yml` | YAML | Regras de destino para o motor de cristalização |

## Formato `.jrvs`

O formato `.jrvs` é o formato binário interno do JARVIS para persistência de alta
performance.

**Características:**
- Magic header: `JRVS` (4 bytes)
- Compressão zlib integrada
- Verificação de integridade CRC32
- Leitura/escrita ~5–10× mais rápida que JSON para arquivos grandes
- **Exclusivo para uso interno** — não editar manualmente

**Uso programático:**
```python
from app.utils.document_store import document_store

# Leitura automática (qualquer formato)
data = document_store.read("data/nexus_registry.jrvs")

# Escrita
document_store.write("data/nexus_registry.jrvs", data)
```

## Fluxo de Atualização Tradutiva

Os arquivos `.jrvs` são gerados automaticamente a partir dos seus equivalentes
legíveis por humanos (`.json`, `.yml`, `.txt`) pelo `JrvsTranslator`.

**Ativar manualmente:**
```python
from app.application.services.jrvs_translator import JrvsTranslator

translator = JrvsTranslator()
translator.execute({"action": "sync_all", "data_dir": "data"})
```

**Via webhook (API):**
```http
POST /v1/translate/jrvs
Authorization: Bearer <token>
Content-Type: application/json

{"action": "sync_all", "data_dir": "data"}
```

> ⚠️ Os arquivos `.json` e `.yml` são a **fonte de verdade** — edite sempre o
> formato legível e execute a tradução para atualizar o `.jrvs`.
