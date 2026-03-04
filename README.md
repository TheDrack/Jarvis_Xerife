# JARVIS – Plataforma de Assistente e Automação Distribuída

[![🧬 JARVIS: PyTest e Auto-Cura](https://github.com/TheDrack/Jarvis_Xerife/actions/workflows/homeostase.yml/badge.svg?branch=main)](https://github.com/TheDrack/Jarvis_Xerife/actions/workflows/homeostase.yml)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

> Assistente de voz distribuído com orquestração multi-dispositivo, integração com LLMs e arquitetura hexagonal.

---

## 🎯 O que é o JARVIS?

O JARVIS é uma plataforma de automação e assistência que:

- 🧠 **Interpreta comandos** em português usando LLMs (Groq/Gemini)
- 🎤 **Reconhece voz** com Google Speech Recognition
- 🌐 **Orquestra múltiplos dispositivos** (PC, celular, IoT) por capacidade e proximidade
- 🔧 **Auto-repara erros** via GitHub Copilot (self-healing)
- 💾 **Memória biográfica vetorial** – recorda interações dos últimos 30 dias (FAISS)
- 👁️ **Visão computacional** – descreve o contexto visual atual via Gemini 1.5 Flash
- 🔭 **Núcleo Proativo (Overwatch)** – monitora CPU/RAM, contexto e inatividade do usuário
- 🏗️ **Arquitetura Hexagonal** – domínio puro, testável e cloud-ready
- 🧬 **Nexus** – container de injeção de dependência com discovery automático e Circuit Breaker

---

## ⚙️ Status Atual

| Componente | Status |
|---|---|
| API REST (FastAPI) | ✅ Ativo |
| Nexus (DI + Circuit Breaker) | ✅ Ativo |
| Adaptadores LLM (Groq, Gemini) | ✅ Ativo |
| Reconhecimento de voz | ✅ Ativo |
| Orquestração de dispositivos | ✅ Ativo |
| **Memória Vetorial (FAISS)** | ✅ **Ativo** |
| **Visão Computacional (Gemini Flash)** | ✅ **Ativo** |
| **Overwatch Daemon (Núcleo Proativo)** | ✅ **Ativo** |
| **DocumentStore (I/O Universal)** | ✅ **Ativo** |
| **Formato .jrvs (binário interno)** | ✅ **Ativo** |
| **JrvsTranslator (fluxo tradutivo)** | ✅ **Ativo** |
| Auto-Evolução | ⏸️ **PAUSADA** |

> Auto-evolução está **pausada** enquanto a estrutura do repositório é reorganizada.

---

## 🗂️ Estrutura do Projeto

```
app/
├── core/               # Nexus, configuração, criptografia
├── domain/             # Lógica de negócio (modelos, serviços, LLM gears)
├── application/        # Casos de uso e portas (interfaces)
│   ├── ports/          # Contratos dos adaptadores
│   └── services/       # Orquestrador, assistente, etc.
├── adapters/
│   ├── edge/           # Hardware (voz, teclado, automação)
│   └── infrastructure/ # Cloud (LLM, DB, GitHub, API)
├── plugins/            # Plugins dinâmicos
└── runtime/            # Pipeline runner declarativo

.frozen/                # Código inativo (aguardando uso ou descarte)
config/                 # Configurações de LLM e pipelines
data/                   # Registry Nexus, capabilities, regras
docs/                   # Documentação
tests/                  # Testes automatizados
```

---

## 🚀 Como Executar

### Modo Cloud (API REST)

```bash
# Instalar dependências
pip install -r requirements.txt

# Configurar variáveis de ambiente
cp .env.example .env
# edite .env com suas chaves de API

# Iniciar servidor
python -m app.application.services.serve
# ou
uvicorn app.adapters.infrastructure.api_server:app --reload
```

### Docker

```bash
docker-compose up --build
# API disponível em http://localhost:8000
```

### Modo Edge (dispositivo local)

```bash
python app/bootstrap_edge.py
```

---

## 🧬 Nexus – Sistema de Instanciação

O **Nexus** é o container de DI do JARVIS. Todo componente ativo deve ser registrado:

```python
from app.core.nexus import nexus

# Resolve e instancia um componente
component = nexus.resolve("audit_logger")
component.execute(context)
```

Componentes não utilizados ficam em `.frozen/` até serem necessários.

→ Veja [docs/NEXUS.md](docs/NEXUS.md) para detalhes.

---

## 📦 DocumentStore & Formato .jrvs

O **DocumentStore** é o sistema universal de leitura/escrita de documentos.
Ele detecta automaticamente o formato pelo sufixo do arquivo:

```python
from app.utils.document_store import document_store

# Lê qualquer formato (.json, .yml, .txt, .jrvs)
data = document_store.read("data/nexus_registry.json")

# Grava no formato correto para o sufixo
document_store.write("data/nexus_registry.jrvs", data)
```

### Formato `.jrvs`

O `.jrvs` é o formato binário interno do JARVIS — compacto, verificado por CRC32
e ~5–10× mais rápido para leitura do que JSON para arquivos grandes.

```
┌──────────────────────────────────────────────────┐
│  Magic  │ Version │  Flags  │  CRC32  │   Len   │
│ 4 bytes │ 2 bytes │ 2 bytes │ 4 bytes │ 4 bytes │
├──────────────────────────────────────────────────┤
│          Dados (JSON + zlib comprimido)           │
└──────────────────────────────────────────────────┘
```

### Fluxo de Atualização Tradutiva

O **JrvsTranslator** sincroniza arquivos `.jrvs` com seus equivalentes legíveis.
Pode ser ativado manualmente ou via webhook:

```bash
# Via API (requer autenticação)
curl -X POST /v1/translate/jrvs \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"action": "sync_all", "data_dir": "data"}'
```

```python
from app.application.services.jrvs_translator import JrvsTranslator

translator = JrvsTranslator()
translator.execute({"action": "to_jrvs", "data_dir": "data"})
```

> ⚠️ Arquivos `.json`/`.yml` são a **fonte de verdade**. Edite sempre o formato
> legível e execute a tradução para atualizar o `.jrvs`.

---

## 🧊 Política Frozen

Arquivos em `.frozen/` são código preservado mas inativo.  
Para reativar: mova para `app/`, registre no Nexus, documente.

---

## 🧪 Testes

```bash
# Instalar dependências de dev
pip install -r requirements/dev.txt

# Executar testes do domínio (sem hardware)
pytest tests/domain/ -v

# Executar todos os testes
pytest tests/ -v
```

---

## 📖 Documentação

| Documento | Descrição |
|---|---|
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

---

**Made with ❤️ by the Jarvis Team**
