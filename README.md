# JARVIS – Plataforma de Assistente e Automação Distribuída

[![🧬 JARVIS: PyTest e Auto-Cura](https://github.com/TheDrack/Jarvis_Xerife/actions/workflows/homeostase.yml/badge.svg?branch=main)](https://github.com/TheDrack/Jarvis_Xerife/actions/workflows/homeostase.yml)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)



**Versão:** 2.0.0  
**Última Atualização:** 2026-03-10  
**Status:** ✅ Operacional

---

## 🎯 Visão Geral

JARVIS é um sistema de software autônomo que combina **Arquitetura Hexagonal**, **Injeção de Dependência (Nexus DI)** e **Auto-Evolução Assistida por LLM**.

O sistema é capaz de:
- Interpretar comandos em linguagem natural
- Executar ações via adapters (Telegram, GitHub, APIs)
- Auto-corriger erros via self-healing
- Evoluir capacidades através do EvolutionOrchestrator

---

## 🏗️ Arquitetura

```
┌─────────────────────────────────────────┐
│         INTERFACE / CI-CD               │
├─────────────────────────────────────────┤
│         ADAPTERS (Infra/Edge)           │
│   - gateway_llm_adapter.py              │
│   - telegram_adapter.py                 │
│   - github_adapter.py                   │
├─────────────────────────────────────────┤
│         APPLICATION (Services)          │
│   - assistant_service.py                │
│   - evolution_orchestrator.py           │
│   - metabolism_core.py                  │
├─────────────────────────────────────────┤
│         DOMAIN (Regras de Negócio)      │
│   - capabilities/ (102 capabilities)    │
│   - services/ (llm_command_interpreter) │
├─────────────────────────────────────────┤
│         CORE (Nexus/DI)                 │
│   - nexus.py                            │
│   - nexus_exceptions.py                 │
│   - nexus_discovery.py                  │
│   - nexus_registry.py                   │
└─────────────────────────────────────────┘
```

---

## 🚀 Início Rápido

### Pré-requisitos
```bash
Python 3.12+
pip install -r requirements/core.txt
pip install -r requirements/dev.txt  # Para testes
```

### Configuração
```bash
# Variáveis de ambiente necessárias
export GROQ_API_KEY="sua-chave-groq"
export GEMINI_API_KEY="sua-chave-gemini"
export GITHUB_TOKEN="seu-token-github"
export TELEGRAM_BOT_TOKEN="seu-token-telegram"
export TELEGRAM_CHAT_ID="seu-chat-id"
```

### Execução
```bash
# Rodar testes do domínio
pytest tests/domain/ -v

# Rodar todos os testes
pytest tests/ -v

# Validar arquitetura
python scripts/validate_architecture.py
```

---

## 📦 Nexus DI — Injeção de Dependência

**Todos os componentes ativos devem ser NexusComponent e registrados no Nexus.**

```python
from app.core.nexus import nexus

# Resolve e instancia um componente
component = nexus.resolve("assistant_service")
component.execute(context)
```

### Módulos do Nexus

| Módulo | Responsabilidade |
|--------|------------------|
| `nexus.py` | Container principal, API pública |
| `nexus_exceptions.py` | CloudMock, exceções, circuit breaker |
| `nexus_discovery.py` | Discovery em disco, instanciação |
| `nexus_registry.py` | I/O do registry local `.jrvs` |

**Registry local:** `data/nexus_registry.json` / `data/nexus_registry.jrvs`

→ Veja [docs/NEXUS.md](docs/NEXUS.md) para detalhes completos.

---

## 📦 DocumentStore & Formato .jrvs

O **DocumentStore** é o sistema universal de leitura/escrita de documentos.

```python
from app.utils.document_store import document_store

# Lê qualquer formato (.json, .yml, .txt, .jrvs)
data = document_store.read("data/nexus_registry.json")

# Grava no formato correto para o sufixo
document_store.write("data/nexus_registry.jrvs", data)
```

### Formato .jrvs

Arquivos `.jrvs` são JSON comprimido com zlib, com cabeçalho binário:

```
┌─────────────────────────────────────────┐
│ Magic │ Version │ Flags │ CRC32 │ Len  │
│ 4 bytes│ 2 bytes │ 2 bytes │ 4 bytes │ 4 bytes │
├─────────────────────────────────────────┤
│ Dados (JSON + zlib comprimido)          │
└─────────────────────────────────────────┘
```

→ Veja [data/README.md](data/README.md) para detalhes.

---

## 🧪 Testes

```bash
# Instalar dependências de dev
pip install -r requirements/dev.txt

# Executar testes do domínio (sem hardware)
pytest tests/domain/ -v

# Executar todos os testes
pytest tests/ -v

# Validar arquitetura
python scripts/validate_architecture.py
```

---

## 📖 Documentação

| Documento | Descrição |
|-----------|-----------|
| [docs/STATUS.md](docs/STATUS.md) | Situação atual do projeto |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Arquitetura do sistema |
| [docs/NEXUS.md](docs/NEXUS.md) | Sistema de injeção de dependência |
| [docs/ARQUIVO_MAP.md](docs/ARQUIVO_MAP.md) | Mapa de todos os arquivos ativos |
| [data/README.md](data/README.md) | Formatos de dados: JSON, YAML, .jrvs |
| [padrão_estrutural.md](padrão_estrutural.md) | Padrão de pipelines e arquitetura |

---

## 🤝 Contribuindo

Veja [CONTRIBUTING.md](CONTRIBUTING.md) para diretrizes.

---

## 📄 Licença

MIT – veja [LICENSE](LICENSE).

**Made with ❤️ by the Jarvis Team**
