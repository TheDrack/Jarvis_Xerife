# Changelog

All notable changes to the Jarvis Assistant project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

#### Núcleo Proativo Multimodal com Memória Permanente (2026-03-03)

**Fase 1 – Estabilização de Infraestrutura**
- `app/core/nexus.py`: Adicionado `CloudMock` – absorvedor transparente injetado automaticamente quando um componente falha. Corrige `ImportError` em `intent_processor.py` (`from app.core.nexus import CloudMock`).
- `app/core/nexus.py`: Implementado **Circuit Breaker** no `JarvisNexus.resolve()`: timeout de 2 s abre o circuito, `CloudMock` retornado por 60 s, após o qual o circuito fecha e a instanciação é tentada novamente.
- `scripts/state_machine.py`: Novo `ErrorCategory` enum. `identify_error()` agora distingue `ENVIRONMENT_ERROR` (`PermissionError`, `FileNotFoundError: No such file or directory`, `OSError`, etc.) de `CODE_ERROR` — erros de ambiente pausam o sistema sem mutar código.
- `scripts/auto_fixer_logic.py`: Importa e usa `ErrorCategory`; `run_with_state_machine()` registra e pausa em erros de ambiente em vez de tentar auto-correção.

**Fase 2 – Memória Biográfica Vetorial**
- `app/application/ports/memory_provider.py`: Nova porta `MemoryProvider` com métodos `store_event()`, `query_similar()` e `clear()`.
- `app/adapters/infrastructure/vector_memory_adapter.py`: Adaptador `VectorMemoryAdapter` – armazena eventos como vetores (FAISS com fallback puro-Python offline). Registrado no Nexus como `vector_memory_adapter`.
- `app/application/services/assistant_service.py`: `process_command()` consulta a memória vetorial (últimos 30 dias) antes de cada resposta e armazena comando + resposta do LLM como vetores após cada interação.
- `requirements.txt`: Adicionadas dependências `numpy>=1.24.0` e `faiss-cpu>=1.7.4`.

**Fase 3 – Expansão Sensorial (Visão Computacional)**
- `app/adapters/infrastructure/vision_adapter.py`: Adaptador `VisionAdapter` – captura screenshot silencioso (mss/Pillow) ou frame de webcam (OpenCV) e envia ao **Gemini 1.5 Flash** com o prompt *"Descreva o contexto atual do usuário em 1 frase"*. Registrado no Nexus como `vision_adapter`.

**Fase 4 – Overwatch Daemon (Núcleo Proativo)**
- `scripts/overwatch_daemon.py`: Daemon de background `OverwatchDaemon` – monitora CPU/RAM, mudanças em `data/context.json` e inatividade do usuário (30 min). Após inatividade, usa `VisionAdapter` para verificar presença e sugere tarefa pendente do calendário. Todas as ações prefixadas `[PROACTIVE_CORE]`.
- `main.py`: `bootstrap_background_services()` inicia o `OverwatchDaemon` automaticamente; cada comando Telegram chama `notify_activity()` para reiniciar o timer de inatividade.

**Infraestrutura e Documentação**
- `data/nexus_registry.json`: `vector_memory_adapter` e `vision_adapter` registrados.
- `docs/NEXUS.md`: Tabela de componentes atualizada; seção de Circuit Breaker adicionada.
- `docs/ARQUIVO_MAP.md`: Todos os novos arquivos documentados.
- `docs/STATUS.md`: Status dos novos componentes ativos; seções de memória vetorial, visão e Overwatch Daemon.
- `scripts/README.md`: Documentação do `overwatch_daemon.py`.

### Changed

#### Refactoring Estrutural (2026-03-01)
- Consolidado `app/infrastructure/adapters/` em `app/adapters/infrastructure/` (pasta única)
- Removido `app/domain/adapters/` – adaptadores não pertencem ao domínio
- Removido `app/app/` – diretório aninhado incorreto
- Removido `app/adapters/cap_*_core.py` (root) – movidos para `.frozen/orphan_caps/`
- `action_provider.py` movido para `app/adapters/infrastructure/`
- Auto-evolução **PAUSADA** enquanto estrutura é reorganizada
- Documentação completamente reescrita (docs/ limpa e recriada)
- README atualizado com status atual e estrutura correta
- `data/nexus_registry.json` atualizado com novos caminhos dos componentes

## [1.0.0] - 2024-02-05

### Added

#### Core Features
- Complete refactoring from monolithic `assistente.pyw` to professional modular architecture
- `JarvisEngine` class for voice recognition and text-to-speech
- `SystemCommands` class for interface automation (PyAutoGUI/Keyboard)
- `WebNavigator` class for web browser automation
- `CommandProcessor` for routing voice commands to appropriate handlers
- Configuration management with pydantic-settings
- Type hints throughout the entire codebase

#### Project Structure
- Professional folder structure (app/core, app/actions, app/utils, tests, data, dags)
- README.md files in each module explaining responsibilities
- Main entry point via `main.py`

#### DevOps & Infrastructure
- Dockerfile for containerization
- docker-compose.yml for orchestration
- Airflow DAG example for workflow automation
- Makefile for common development tasks

#### Testing & Quality
- Comprehensive pytest test suite (24 tests, 100% passing)
- Test fixtures in conftest.py
- pytest configuration with coverage reporting
- mypy configuration for type checking
- Code formatting with Black and isort
- Test coverage reporting

#### Documentation
- Comprehensive README.md with usage instructions
- EXTENSIBILITY.md guide for adding new features
- CONTRIBUTING.md for development guidelines
- Project structure documentation
- Inline documentation with Google-style docstrings

#### Development Tools
- setup.py for package management
- requirements.txt with all dependencies
- .gitignore for Python projects
- .env.example for configuration template
- Utility helper functions (logging, file operations)

### Changed
- Migrated from procedural code to object-oriented architecture
- Separated concerns into distinct modules
- Improved error handling and type safety

### Removed
- Work-specific functions (4R system integration)
- Almoxarifado-specific functionality
- Material requisition features
- Cost center management
- All hard-coded file paths and credentials
- Excel spreadsheet dependencies for commands

### Security
- Removed hard-coded credentials
- Added configuration management for sensitive data
- Improved input validation and error handling

## [0.1.0] - Original

### Initial Release
- Basic voice recognition in Portuguese (pt-BR)
- Text-to-speech functionality
- PyAutoGUI automation
- Work-specific integrations

[1.0.0]: https://github.com/TheDrack/python/releases/tag/v1.0.0
[0.1.0]: https://github.com/TheDrack/python/releases/tag/v0.1.0
