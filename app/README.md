# App Module

This directory contains the main application code for the Jarvis voice assistant, following **Hexagonal Architecture** (Ports and Adapters pattern).

## Structure

### Core Layers

- **`domain/`**: Domain Core - Pure Python business logic (cloud-ready)
  - `models/`: Business entities (Command, Intent, Response, CommandType)
  - `services/`: Domain services (CommandInterpreter, IntentProcessor, AgentService)

- **`application/`**: Application Layer - Use cases and orchestration
  - `ports/`: Interfaces/contracts (VoiceProvider, ActionProvider, etc.)
  - `services/`: Application services (AssistantService)

- **`adapters/`**: Adapters - Concrete implementations
  - `edge/`: Hardware adapters (voice, TTS, automation, keyboard, web)
  - `infrastructure/`: Infrastructure adapters (API server, database, authentication, LLM)

### Support Modules

- **`container.py`**: Dependency Injection container
- **`bootstrap_edge.py`**: Bootstrap for edge deployment
- **`core/`**: Configuration and settings
- **`actions/`**: Legacy action modules (deprecated, kept for compatibility)
- **`utils/`**: Utility functions and helpers

For detailed architecture documentation, see [ARCHITECTURE.md](../ARCHITECTURE.md).
