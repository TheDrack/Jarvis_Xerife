# Copilot Instructions for JARVIS

## Project Overview

JARVIS is a distributed voice assistant and automation platform built in Python. It interprets commands in Portuguese using LLMs (Groq/Gemini), recognizes speech, and orchestrates multiple devices (PC, mobile, IoT) using a hexagonal architecture.

## Architecture

The project follows **Hexagonal Architecture** (Ports and Adapters):

- `app/domain/` – Pure business logic (models, services). No external dependencies.
- `app/application/` – Use cases and port interfaces. Depends only on domain.
- `app/adapters/edge/` – Hardware adapters (voice, keyboard, automation).
- `app/adapters/infrastructure/` – Cloud/API adapters (LLM, DB, GitHub, REST API).
- `app/core/` – Nexus DI container, configuration, encryption.
- `app/plugins/` – Dynamic plugins.
- `app/runtime/` – Declarative pipeline runner.
- `.frozen/` – Inactive/preserved code awaiting reactivation or removal.

## Dependency Injection (Nexus)

All active components must be registered in the **Nexus** DI container (`app/core/nexus.py`). Use `nexus.resolve("component_name")` to instantiate components. Components not in use go into `.frozen/`.

## Code Style

- **Language**: Python 3.12+
- **Formatter**: Black (100 character line length)
- **Imports**: isort
- **Type hints**: Required on all public functions and classes
- **Linter**: flake8 (`--max-line-length=100`)
- **Type checker**: mypy
- **Docstrings**: Google-style

## Testing

- Framework: pytest
- Tests live in `tests/` mirroring the `app/` structure
- Domain tests (`tests/domain/`) must not depend on hardware or external services
- Run domain tests: `pytest tests/domain/ -v`
- Run all tests: `pytest tests/ -v`
- Target coverage: >80%

## Commands

```bash
make install-dev   # Install all development dependencies
make format        # Run Black + isort
make lint          # Run mypy + flake8
make test          # Run tests with coverage
make test-fast     # Run tests without coverage
```

## Environment

- Copy `.env.example` to `.env` and fill in: `USER_ID`, `ASSISTANT_NAME`, `GEMINI_API_KEY`, `DATABASE_URL`
- Cloud deployment: Render (API mode). Set `RENDER=true` or `PYTHON_ENV=production`.
- Edge deployment: local device with microphone/hardware.

## Contributing Guidelines

- New features belong to the correct architectural layer (Domain, Application, or Adapter)
- Always add port interfaces in `app/application/ports/` before implementing adapters
- Register new components in the Nexus container
- Write tests before or alongside implementation
- Follow commit message format: `Add feature: description` (present tense, imperative mood)
- Primary language for code comments and documentation: Portuguese or English (both accepted)
