# Jarvis Voice Assistant
[![Python Tests](https://github.com/TheDrack/python/actions/workflows/python-tests.yml/badge.svg?branch=main)](https://github.com/TheDrack/python/actions/workflows/python-tests.yml)

> **Note**: O badge de status do GitHub Actions só é visível para usuários autenticados com acesso a este repositório privado. Clique no badge para ver os resultados dos testes.

A professional, modular voice assistant built with Python, featuring **Hexagonal Architecture** for clean separation between business logic and infrastructure.

> **✨ Latest Update**: Successfully refactored to Hexagonal Architecture with 39 passing tests, 97-100% domain coverage, and full cloud-ready deployment support. See [REFACTORING_SUMMARY.md](REFACTORING_SUMMARY.md) for complete details.

## 🚀 Quick Start

Começar com o Jarvis nunca foi tão fácil! Apenas **3 passos simples**:

```bash
# 1. Clone e configure o ambiente
git clone <repository-url> && cd python
python -m venv venv && source venv/bin/activate  # Windows: venv\Scripts\activate

# 2. Instale as dependências
pip install -r requirements.txt

# 3. Execute - o Setup Wizard fará o resto! ✨
python main.py
```

O **Setup Wizard interativo** irá guiá-lo através de:
- 🎭 Escolha o nome do seu assistente (Jarvis, Friday, Ultron, ou crie o seu!)
- 🔑 Configuração automática da API do Gemini (com captura via clipboard)
- 🗄️ Configuração do banco de dados (SQLite ou PostgreSQL)
- 💾 Geração automática do arquivo `.env` com criptografia

Pronto! Seu assistente personalizado está configurado e pronto para uso. Veja a [seção de Instalação](#installation) para mais opções.

## 🏗️ Architecture

This project follows **Hexagonal Architecture** (Ports and Adapters) pattern:

- **Domain Core**: Pure Python business logic, hardware-independent, cloud-ready
- **Application Layer**: Use cases and interfaces (Ports) for external services
- **Adapters**: Concrete implementations for Edge (hardware) and Cloud (infrastructure)
- **Dependency Injection**: Clean separation and testability

See [ARCHITECTURE.md](ARCHITECTURE.md) for detailed architecture documentation.

## Features

- **🎭 Personalidade Selecionável**: Escolha o nome e customize o comportamento do seu assistente durante a instalação
- **🚀 Setup Wizard Interativo**: Instalação guiada com captura automática de credenciais e validação
- **Voice Recognition**: Brazilian Portuguese (pt-BR) voice commands using Google Speech Recognition
- **Text-to-Speech**: Natural voice synthesis with pyttsx3
- **Dual Command Interpretation**: 
  - Rule-based pattern matching for fast, reliable command processing
  - Gemini AI integration for natural language understanding (see [LLM_INTEGRATION.md](LLM_INTEGRATION.md))
- **System Automation**: Interface control using PyAutoGUI and Keyboard
- **Web Navigation**: Browser automation and URL handling
- **REST API**: FastAPI-based headless control interface with authentication (see [API_README.md](API_README.md))
- **Distributed Mode**: Cloud API with local workers for remote command execution (see [DISTRIBUTED_MODE.md](DISTRIBUTED_MODE.md))
- **Hexagonal Architecture**: Clean separation with Domain, Application, and Adapters layers (see [ARCHITECTURE.md](ARCHITECTURE.md))
- **Cloud Ready**: Core logic runs without hardware dependencies (97-100% domain test coverage)
- **Dependency Injection**: All dependencies injected via container
- **Docker Support**: Containerized deployment with Docker Compose and PostgreSQL
- **Database Integration**: SQLModel with PostgreSQL and SQLite support
- **Modular Requirements**: Separate dependency files for edge, cloud, and development scenarios
- **Type Safety**: Full type hinting throughout the codebase
- **Comprehensive Testing**: 60+ passing tests covering domain, application, and adapter layers

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
│   │   └── infrastructure/  # Infrastructure adapters (API server, database, auth, LLM)
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

### 🚀 Quick Start (Recomendado)

O Jarvis agora possui um **assistente de instalação interativo** que configura tudo automaticamente!

1. Clone o repositório:
```bash
git clone <repository-url>
cd python
```

2. Crie um ambiente virtual e instale as dependências:
```bash
python -m venv venv
source venv/bin/activate  # No Windows: venv\Scripts\activate
pip install -r requirements.txt
```

3. Execute o assistente - o **Setup Wizard será iniciado automaticamente**:
```bash
python main.py
```

O Setup Wizard irá guiá-lo através de:
- ✨ **Personalização do Assistente**: Escolha o nome do seu assistente (Jarvis, Ultron, Friday, ou qualquer outro!)
- 🔑 **Configuração da API do Gemini**: Captura automática da chave API via clipboard
- 🗄️ **Configuração do Banco de Dados**: SQLite local (padrão) ou PostgreSQL/Supabase
- 💾 **Persistência Automática**: Gera arquivo `.env` com todas as configurações

> **💡 Dica**: Veja o [INSTALLER_README.md](INSTALLER_README.md) para detalhes completos sobre o assistente de instalação.

### Personalização do Assistente 🎭

Um dos recursos mais legais do Jarvis é a **personalidade selecionável**! Durante a instalação, você pode:

- **Escolher o nome do assistente**: Não precisa ser "Jarvis" - pode ser "Ultron", "Friday", "Karen", ou qualquer nome que você preferir!
- **Personalizar o comportamento**: O assistente usa a configuração `ASSISTANT_NAME` no arquivo `.env` para se identificar.

A personalidade base é definida pelo sistema de IA (Gemini), que atua como um assistente focado em produtividade e automação. O comportamento padrão inclui:
- Respostas concisas e eficientes
- Foco em ações, não em explicações longas
- Comunicação em português brasileiro
- Tom profissional mas amigável

> **📝 Nota**: Para customização avançada da personalidade com exemplos de código, veja a seção de [Personalidade do Assistente](INSTALLER_README.md#personalidade-do-assistente-) no INSTALLER_README.md.

### Instalação Manual (Avançada)

Se você preferir configurar manualmente sem o wizard:

1. Clone o repositório:
```bash
git clone <repository-url>
cd python
```

2. Crie um ambiente virtual:
```bash
python -m venv venv
source venv/bin/activate  # No Windows: venv\Scripts\activate
```

3. Instale as dependências:

**Opção A - Deployment Edge completo (suporte a hardware):**
```bash
pip install -r requirements.txt
# OU use requirements modulares:
pip install -r requirements/edge.txt
```

**Opção B - Desenvolvimento (com ferramentas de teste):**
```bash
pip install -r requirements/dev.txt
```

> **Nota**: O projeto agora suporta arquivos de requirements modulares para diferentes cenários de deployment. Veja [requirements/README.md](requirements/README.md) para detalhes sobre core.txt, edge.txt, dev.txt, prod-edge.txt, e prod-cloud.txt.

4. Copie o arquivo de exemplo e configure manualmente:
```bash
cp .env.example .env
# Edite o .env e preencha: USER_ID, ASSISTANT_NAME, GEMINI_API_KEY, DATABASE_URL
```

5. Execute o assistente:
```bash
python main.py
```

### Cloud Setup (Headless)

For cloud deployment without hardware dependencies:

```bash
# Install only core dependencies (cloud-ready, no hardware)
pip install -r requirements/core.txt

# Or for production cloud deployment
pip install -r requirements/prod-cloud.txt

# Then integrate with your API/cloud service
```

### Docker Setup

The project now uses **PostgreSQL** as the default database when running with Docker Compose.

1. Build and run with Docker Compose:
```bash
docker-compose up --build
```

This will:
- Start a PostgreSQL 15 database container
- Start the Jarvis assistant container
- Automatically configure the assistant to use PostgreSQL
- Create a persistent volume for database data

2. **Customize database credentials (optional)**:

Create a `.env` file in the project root with your own credentials:
```bash
POSTGRES_USER=your_user
POSTGRES_PASSWORD=your_secure_password
POSTGRES_DB=your_database
```

The docker-compose.yml will automatically use these values.

3. Stop the services:
```bash
docker-compose down
```

4. Stop and remove volumes (⚠️ this will delete all data):
```bash
docker-compose down -v
```

For manual Docker build (without PostgreSQL):
```bash
docker build -t jarvis-assistant .
docker run -it jarvis-assistant
```

**Note**: When running with Docker Compose, the application uses PostgreSQL. For local development without Docker, SQLite is used by default.

## Configuration

O Setup Wizard configura automaticamente todas as opções necessárias. Para configuração manual ou ajustes, o gerenciamento de configuração é feito via `app/core/config.py` usando pydantic-settings. Você pode customizar as configurações:

1. Criando um arquivo `.env` na raiz do projeto (recomendado)
2. Definindo variáveis de ambiente
3. Modificando os valores padrão da classe Settings

Configurações disponíveis:
- `APP_NAME`: Nome da aplicação (padrão: "Jarvis Assistant")
- `USER_ID`: ID único do usuário (configurado pelo wizard)
- `ASSISTANT_NAME`: Nome personalizado do assistente (ex: "Jarvis", "Friday", "Ultron") 🎭
- `LANGUAGE`: Idioma de reconhecimento (padrão: "pt-BR")
- `WAKE_WORD`: Palavra de ativação (padrão: "xerife")
- `GEMINI_API_KEY`: Chave da API do Google Gemini (configurada pelo wizard)
- `DATABASE_URL`: String de conexão com o banco de dados
  - SQLite (padrão local): `sqlite:///jarvis.db`
  - PostgreSQL (Docker Compose): `postgresql://user:password@host:port/database`

> **🔒 Segurança**: O Setup Wizard criptografa automaticamente valores sensíveis (`GEMINI_API_KEY` e `DATABASE_URL`) usando uma chave baseada em hardware. Isso significa que o arquivo `.env` só funcionará na máquina onde foi criado.

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
- Install edge requirements: `pip install -r requirements/edge.txt`
- Run `python main.py`
- All processing happens locally with full hardware support

### 2. Cloud API (Headless)
- Install core requirements: `pip install -r requirements/core.txt`
- Expose via FastAPI: `python serve.py`
- No hardware dependencies - perfect for cloud deployment
- Access at `http://localhost:8000/docs`

### 3. Hybrid (Multiple Edges + Cloud)
- Cloud: Runs API server for command orchestration
- Edge: Executes actions locally via worker
- Communication via PostgreSQL task queue (see [DISTRIBUTED_MODE.md](DISTRIBUTED_MODE.md))
- Future: WebSocket/gRPC support for real-time communication

## License

This project is provided as-is for educational and personal use.

## Contributing

✅ **Implemented Features:**
- FastAPI REST interface with authentication
- Cloud deployment support (headless mode)
- LLM integration with Gemini AI
- Distributed mode with cloud API and local workers
- Database integration (PostgreSQL/SQLite)
- Comprehensive testing suite

🔮 **Future Enhancements:**
- WebSocket support for real-time communication
- Cloud voice adapters (AWS Polly, Google Cloud TTS)
- Multi-device orchestration improvements
- Multi-language support beyond pt-BR
- Event sourcing and command replay
- Monitoring and metrics integration

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

### Architecture & Design
- [ARCHITECTURE.md](ARCHITECTURE.md) - Detailed hexagonal architecture documentation (Portuguese)
- [REFACTORING_SUMMARY.md](REFACTORING_SUMMARY.md) - Complete refactoring summary with metrics and validation results

### Integration Guides
- [API_README.md](API_README.md) - REST API documentation and usage guide
- [LLM_INTEGRATION.md](LLM_INTEGRATION.md) - Gemini AI integration guide
- [DISTRIBUTED_MODE.md](DISTRIBUTED_MODE.md) - Cloud + local worker setup guide

### Development
- [CONTRIBUTING.md](CONTRIBUTING.md) - Contribution guidelines
- [EXTENSIBILITY.md](EXTENSIBILITY.md) - Guide for extending functionality
- [requirements/README.md](requirements/README.md) - Modular requirements documentation

### Project History
- [CHANGELOG.md](CHANGELOG.md) - Version history
- [MIGRATION.md](MIGRATION.md) - Migration guide from v0.1 to v1.0

## Support

For issues and questions, please open an issue in the repository.
