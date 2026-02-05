# Jarvis Voice Assistant
[![Python Tests](https://github.com/TheDrack/python/actions/workflows/python-tests.yml/badge.svg?branch=main)](https://github.com/TheDrack/python/actions/workflows/python-tests.yml)

> **Note**: O badge de status do GitHub Actions só é visível para usuários autenticados com acesso a este repositório privado. Clique no badge para ver os resultados dos testes.

A professional, modular voice assistant built with Python, featuring **Hexagonal Architecture** for clean separation between business logic and infrastructure.

> **✨ Latest Update**: Successfully refactored to Hexagonal Architecture with 39 passing tests, 97-100% domain coverage, and full cloud-ready deployment support. See [REFACTORING_SUMMARY.md](REFACTORING_SUMMARY.md) for complete details.

## 🏗️ Architecture

This project follows **Hexagonal Architecture** (Ports and Adapters) pattern:

- **Domain Core**: Pure Python business logic, hardware-independent, cloud-ready
- **Application Layer**: Use cases and interfaces (Ports) for external services
- **Adapters**: Concrete implementations for Edge (hardware) and Cloud (infrastructure)
- **Dependency Injection**: Clean separation and testability

See [ARCHITECTURE.md](ARCHITECTURE.md) for detailed architecture documentation.

## Features

- **Voice Recognition**: Brazilian Portuguese (pt-BR) voice commands using Google Speech Recognition
- **Text-to-Speech**: Natural voice synthesis with pyttsx3
- **System Automation**: Interface control using PyAutoGUI and Keyboard
- **Web Navigation**: Browser automation and URL handling
- **Hexagonal Architecture**: Clean separation with Domain, Application, and Adapters layers
- **Cloud Ready**: Core logic runs without hardware dependencies (97-100% domain test coverage)
- **Dependency Injection**: All dependencies injected via container
- **Docker Support**: Containerized deployment with Docker and Docker Compose
- **Airflow Integration**: Example DAGs for scheduled automation tasks
- **Type Safety**: Full type hinting throughout the codebase
- **Testing**: Comprehensive test suite with 39 tests (30 domain + 9 application, all passing)

## Project Structure

```
.
├── app/
│   ├── domain/              # Domain Core (Pure Python, Cloud-ready)
│   │   ├── models/          # Business entities (Command, Intent, Response)
│   │   └── services/        # Domain services (CommandInterpreter, IntentProcessor)
│   ├── application/         # Application Layer
│   │   ├── ports/           # Interfaces (VoiceProvider, ActionProvider, etc.)
│   │   └── services/        # Use cases (AssistantService)
│   ├── adapters/            # Adapters (implementations)
│   │   ├── edge/            # Edge adapters (PyAutoGUI, SpeechRecognition, pyttsx3)
│   │   └── infrastructure/  # Infrastructure adapters (future: APIs, DBs)
│   ├── container.py         # Dependency Injection container
│   ├── bootstrap_edge.py    # Bootstrap for Edge deployment
│   ├── core/                # Legacy core (deprecated, kept for compatibility)
│   └── actions/             # Legacy actions (deprecated)
├── requirements/
│   ├── core.txt             # Core dependencies (cloud-ready, no hardware)
│   ├── edge.txt             # Edge dependencies (PyAutoGUI, speech, etc.)
│   ├── dev.txt              # Development dependencies (pytest, mypy, etc.)
│   ├── prod-edge.txt        # Production Edge deployment
│   └── prod-cloud.txt       # Production Cloud deployment
├── tests/
│   ├── domain/              # Domain tests (no hardware mocks!)
│   ├── application/         # Application tests
│   └── adapters/            # Adapter tests
├── dags/                    # Airflow DAGs
├── main.py                  # Entry point
├── ARCHITECTURE.md          # Architecture documentation
└── docker-compose.yml       # Docker orchestration
```

## Installation

### Local Setup (Edge Deployment)

1. Clone the repository:
```bash
git clone <repository-url>
cd python
```

2. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies (Edge deployment with hardware support):
```bash
pip install -r requirements.txt
```

> **Note**: The project documentation references modular requirements files (core.txt, edge.txt, dev.txt) for different deployment scenarios. See [requirements/README.md](requirements/README.md) for the planned dependency separation strategy.

4. Run the assistant:
```bash
python main.py
```

### Cloud Setup (Headless)

For cloud deployment without hardware dependencies:

```bash
pip install -r requirements.txt
# Note: Modular requirements files are planned for future releases
# Then integrate with your API/cloud service
```

### Docker Setup

1. Build and run with Docker Compose:
```bash
docker-compose up --build
```

2. Or build manually:
```bash
docker build -t jarvis-assistant .
docker run -it jarvis-assistant
```

## Configuration

Configuration is managed via `app/core/config.py` using pydantic-settings. You can customize settings by:

1. Creating a `.env` file in the project root
2. Setting environment variables
3. Modifying the Settings class defaults

Available settings:
- `APP_NAME`: Application name (default: "Jarvis Assistant")
- `LANGUAGE`: Recognition language (default: "pt-BR")
- `WAKE_WORD`: Activation phrase (default: "xerife")

## Usage

### Voice Commands

The assistant responds to the wake word "xerife" followed by commands:

- "xerife escreva [texto]" - Type text
- "xerife aperte [tecla]" - Press a key
- "xerife internet" - Open browser
- "xerife site [url]" - Open a website
- "fechar" - Exit the assistant

### Programmatic Usage

You can also use the assistant programmatically with dependency injection:

```python
from app.container import create_edge_container

# Create container with injected dependencies
container = create_edge_container(wake_word="xerife", language="pt-BR")

# Get the assistant service
assistant = container.assistant_service

# Process a single command
response = assistant.process_command("escreva hello world")
print(response.success, response.message)
```

### Extending Functionality

The hexagonal architecture allows easy extension:

#### 1. Add New Command Type

```python
# In app/domain/models/command.py
class CommandType(Enum):
    # ... existing types
    MY_NEW_COMMAND = "my_new_command"

# In app/domain/services/command_interpreter.py
# Add pattern to _command_patterns

# In app/application/services/assistant_service.py
# Add handler in _execute_command()
```

#### 2. Create Custom Adapter

```python
# Create new adapter implementing a port
from app.application.ports import VoiceProvider

class MyCustomVoiceAdapter(VoiceProvider):
    def speak(self, text: str) -> None:
        # Your custom implementation
        pass
    
    def listen(self, timeout: float = None) -> str:
        # Your custom implementation
        pass

# Inject in container
container = Container(voice_provider=MyCustomVoiceAdapter())
```

#### 3. Add New Port and Adapter

```python
# 1. Create port in app/application/ports/
from abc import ABC, abstractmethod

class MyNewPort(ABC):
    @abstractmethod
    def do_something(self) -> None:
        pass

# 2. Create adapter in app/adapters/edge/ or infrastructure/
class MyNewAdapter(MyNewPort):
    def do_something(self) -> None:
        # Implementation
        pass

# 3. Inject in AssistantService
```

## Testing

The project uses pytest with comprehensive test coverage:

```bash
# Run all tests
pytest

# Run domain tests only (no hardware dependencies!)
pytest tests/domain/ -v

# Run with coverage
pytest --cov=app tests/

# Run specific test file
pytest tests/domain/test_command_interpreter.py -v
```

### Test Structure

- **Domain tests**: Pure business logic, no mocks needed (30+ tests)
- **Application tests**: Use mocked ports for isolation
- **Adapter tests**: Test concrete implementations

Example domain test (no hardware!):
```python
def test_interpret_command():
    interpreter = CommandInterpreter(wake_word="test")
    intent = interpreter.interpret("escreva hello")
    
    assert intent.command_type == CommandType.TYPE_TEXT
    assert intent.parameters["text"] == "hello"
```

## Architecture Benefits

1. **Cloud Ready**: Core logic runs in headless Linux environments
2. **Testable**: Domain tests run without hardware mocks
3. **Flexible**: Swap implementations without changing business logic
4. **Scalable**: Multiple edge devices can connect to cloud brain
5. **Maintainable**: Clear separation of concerns

## Airflow Integration

The project includes example Airflow DAGs in the `dags/` directory. To use with Airflow:

1. Install Airflow: `pip install apache-airflow`
2. Set AIRFLOW_HOME to point to this directory
3. Initialize the database: `airflow db init`
4. Start the scheduler: `airflow scheduler`
5. Start the webserver: `airflow webserver`

## Development

### Code Quality

The project follows professional Python standards:

- **Type Hints**: All functions use type annotations
- **Docstrings**: Google-style docstrings for all public methods
- **Linting**: Black, flake8, isort compatible
- **Testing**: Pytest with comprehensive coverage

### Running Code Quality Tools

```bash
# Format code
black app/ tests/

# Sort imports
isort app/ tests/

# Type checking
mypy app/

# Linting
flake8 app/ tests/
```

## Deployment Scenarios

### 1. Edge Only (Local PC/Raspberry Pi)
- Install full edge requirements
- Run `python main.py`
- All processing happens locally

### 2. Cloud Only (Future)
- Install core requirements only
- Expose via FastAPI
- No hardware dependencies

### 3. Hybrid (Multiple Edges + Cloud)
- Cloud: Process intents and decisions
- Edge: Execute actions locally
- Communication via WebSocket/gRPC (future)

## License

This project is provided as-is for educational and personal use.

## Contributing

Future enhancements planned:
- FastAPI REST/WebSocket interface
- Cloud voice adapters (AWS Polly, Google TTS)
- LLM integration for natural language understanding
- Multi-device orchestration
- Natural language processing improvements
- Multi-language support

## Troubleshooting

### Audio Issues
If you encounter audio device errors:
- Ensure microphone permissions are granted
- Check PyAudio installation
- On Linux, install: `sudo apt-get install portaudio19-dev`

### Docker Audio
For audio in Docker containers:
- Uncomment device mappings in docker-compose.yml
- May require privileged mode for some systems

### Import Errors
If you get import errors:
- Make sure you're in the virtual environment
- Install correct requirements file for your deployment
- Check Python version (3.11+ recommended)

## Documentation

- [ARCHITECTURE.md](ARCHITECTURE.md) - Detailed hexagonal architecture documentation
- [REFACTORING_SUMMARY.md](REFACTORING_SUMMARY.md) - Complete refactoring summary with metrics and validation results
- [CONTRIBUTING.md](CONTRIBUTING.md) - Contribution guidelines
- [CHANGELOG.md](CHANGELOG.md) - Version history
- [MIGRATION.md](MIGRATION.md) - Migration guide from v0.1 to v1.0
- [EXTENSIBILITY.md](EXTENSIBILITY.md) - Guide for extending functionality

## Support

For issues and questions, please open an issue in the repository.
