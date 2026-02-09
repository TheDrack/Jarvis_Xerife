# Jarvis Voice Assistant - Orquestrador de Dispositivos Distribuído
[![Python Tests](https://github.com/TheDrack/python/actions/workflows/python-tests.yml/badge.svg?branch=main)](https://github.com/TheDrack/python/actions/workflows/python-tests.yml)

> **Note**: O badge de status do GitHub Actions só é visível para usuários autenticados com acesso a este repositório privado. Clique no badge para ver os resultados dos testes.

## 🧠 Visão Geral

**Jarvis evoluiu!** Não é apenas uma API ou assistente de voz - é um **cérebro na nuvem** que coordena múltiplos dispositivos ("Soldados") através de um sistema inteligente de **orquestração distribuída baseada em capacidades**.

Imagine um xerife que gerencia uma cidade inteira de dispositivos - celulares, PCs, Raspberry Pi, dispositivos IoT - cada um com suas próprias habilidades. Jarvis identifica qual dispositivo está mais próximo e adequado para cada tarefa, considerando:
- 🎯 **Localização física** (GPS)
- 🌐 **Proximidade de rede** (mesmo WiFi/IP)
- ⚡ **Capacidades disponíveis** (câmera, automação, controle IR, etc.)

**Exemplo Real**: Você está viajando e diz "tire uma selfie" - Jarvis usa a câmera do seu celular atual, não o PC em casa. Mas quando diz "ligue a TV", ele roteia para o dispositivo IoT na mesma sala.

A professional, modular voice assistant built with Python, featuring **Hexagonal Architecture** for clean separation between business logic and infrastructure.

> **✨ Latest Update**: Successfully refactored to Hexagonal Architecture with 39 passing tests, 97-100% domain coverage, and full cloud-ready deployment support. See [REFACTORING_SUMMARY.md](REFACTORING_SUMMARY.md) for complete details.

## 🚀 Quick Start

### Instalação Instantânea (Recomendada) ⚡

**A forma mais rápida de começar - sem instalar Python!**

1. Acesse a aba [**Releases**](../../releases) deste repositório
2. Baixe o arquivo `Jarvis_Installer.exe` mais recente
3. Execute o arquivo baixado
4. O **Setup Wizard** fará tudo automaticamente! ✨

**Pronto!** Não precisa instalar Python, pip ou bibliotecas. O executável já contém tudo!

### Instalação via Python (Desenvolvedores)

Se você já tem Python instalado, pode usar em **3 passos simples**:

```bash
# 1. Clone e configure o ambiente
git clone <https://github.com/TheDrack/python> && cd python
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

## 📦 O que vem no Instalador?

O arquivo `Jarvis_Installer.exe` é um **executável standalone completo** que inclui:

- ✅ Python 3.11+ embarcado
- ✅ Todas as bibliotecas necessárias (PyAutoGUI, pyttsx3, Google Gemini AI, etc.)
- ✅ Setup Wizard interativo
- ✅ Suporte completo a voz em português brasileiro
- ✅ Interface de linha de comando amigável

> **💡 Tecnologia**: Criado com PyInstaller em modo **onefile** - tudo em um único executável!
> 
> **🖥️ Plataforma**: Atualmente disponível apenas para Windows. Para Linux/Mac, use a [instalação via Python](#instalação-via-python-desenvolvedores).

## 🏗️ Architecture

This project follows **Hexagonal Architecture** (Ports and Adapters) pattern:

- **Domain Core**: Pure Python business logic, hardware-independent, cloud-ready
- **Application Layer**: Use cases and interfaces (Ports) for external services
- **Adapters**: Concrete implementations for Edge (hardware) and Cloud (infrastructure)
- **Dependency Injection**: Clean separation and testability

See [ARCHITECTURE.md](ARCHITECTURE.md) for detailed architecture documentation.

## ✨ Features Principais

### 🎯 Orquestração Inteligente de Dispositivos
- **Roteamento por Capacidades**: Jarvis sabe quais dispositivos podem fazer o quê (câmera, automação, controle IoT)
- **Hierarquia de Proximidade**: Prioriza dispositivos usando 3 níveis:
  1. ✅ **Mesmo Dispositivo** - Se o dispositivo de origem tem a capacidade
  2. 🌐 **Mesma Rede/IP** - Dispositivos no mesmo WiFi ou IP público
  3. 📍 **GPS Próximo** - Dispositivos fisicamente próximos (<1km, <50km)
- **Conscientização Espacial**: O "Xerife" sempre considera sua localização física antes de agir
- **Validação de Conflitos**: Pede confirmação ao rotear comandos para dispositivos distantes (>50km) ou em redes diferentes

### 🤖 Inteligência Artificial
- **🎭 Personalidade Selecionável**: Escolha o nome e customize o comportamento do seu assistente durante a instalação
- **🚀 Setup Wizard Interativo**: Instalação guiada com captura automática de credenciais e validação
- **🏎️ Sistema de Marchas (Gears System)**: IA multinível com fallback automático:
  - **Marcha Alta** (High Gear): Llama-3.3-70b (Groq) - rápido e econômico
  - **Marcha Baixa** (Low Gear): Llama-3.1-8b (Groq) - fallback interno em rate limits
  - **Tiro de Canhão** (Cannon Shot): Gemini-1.5-Pro - fallback externo com contexto massivo
  - **Auto-Repair**: Sistema de auto-correção que detecta e corrige erros automaticamente
  - Veja [docs/GEARS_SYSTEM.md](docs/GEARS_SYSTEM.md) para detalhes
- **Voice Recognition**: Brazilian Portuguese (pt-BR) voice commands using Google Speech Recognition
- **Text-to-Speech**: Natural voice synthesis with pyttsx3
- **Dual Command Interpretation**: 
  - Rule-based pattern matching for fast, reliable command processing
  - Gemini AI integration with spatial awareness for natural language understanding (see [LLM_INTEGRATION.md](LLM_INTEGRATION.md))
- **System Automation**: Interface control using PyAutoGUI and Keyboard
- **Web Navigation**: Browser automation and URL handling

### 🔧 Jarvis Self-Healing Workshop (Novo!)
- **🤖 Resolução Automática de Issues**: Sistema completo de auto-correção usando LLMs
  - Detecta automaticamente quando Issues são criadas ou workflows CI/CD falham
  - Usa IA (Groq/Gemini) para analisar erros e gerar correções
  - Cria Pull Requests automaticamente com as correções propostas
  - Suporta correção de bugs, atualização de documentação e implementação de features
- **🔄 Auto-Heal CI Failures**: Monitora workflows do GitHub Actions e auto-corrige falhas
- **⚡ Direct GitHub Integration**: Requests from GitHub Actions/Issues bypass Jarvis identifier and go directly to AI
  - GitHub-sourced errors are processed immediately without intent identification overhead
  - User API requests still use full Jarvis intent identification
  - Optimized workflow for automated fixes
- **📊 Detecção Inteligente**: Extrai caminhos de arquivos de tracebacks Python e identifica arquivos comuns
- **🎯 Prevenção de Duplicatas**: Verifica issues existentes antes de criar novas
- **📚 Documentação Completa**: Veja [JARVIS_SELF_HEALING_GUIDE.md](JARVIS_SELF_HEALING_GUIDE.md) para setup e uso

### 🏗️ Arquitetura & Deployment
- **REST API**: FastAPI-based headless control interface with authentication and device management (see [API_README.md](API_README.md))
  - **Request Source Routing**: Intelligent routing based on request origin (GitHub vs User)
  - **Bypass Logic**: GitHub Actions/Issues bypass Jarvis identifier for direct AI processing
- **Distributed Mode**: Cloud brain orchestrates local "soldiers" (devices) via capabilities (see [DISTRIBUTED_MODE.md](DISTRIBUTED_MODE.md))
- **Hexagonal Architecture**: Clean separation with Domain, Application, and Adapters layers (see [ARCHITECTURE.md](ARCHITECTURE.md))
- **Cloud Ready**: Core logic runs without hardware dependencies (97-100% domain test coverage)
- **Dependency Injection**: All dependencies injected via container
- **Docker Support**: Containerized deployment with Docker Compose and PostgreSQL
- **Database Integration**: SQLModel with PostgreSQL and SQLite support for device registry and history
- **Modular Requirements**: Separate dependency files for edge, cloud, and development scenarios
- **Type Safety**: Full type hinting throughout the codebase
- **Comprehensive Testing**: 60+ passing tests covering domain, application, and adapter layers

### 🎯 Xerife Strategist - Sistema de Propostas Autônomas

O **Xerife Strategist** é um módulo avançado que dá ao Jarvis a capacidade de propor e implementar melhorias de forma autônoma, mas sob rigoroso filtro de custo-benefício e segurança.

**Características Principais:**
- 📊 **Análise de Viabilidade (ROI)**: Matriz tridimensional de Custo/Impacto/Risco antes de qualquer implementação
- 💰 **Budget Cap**: Teto de gastos por missão com rastreamento de custos de API e tokens
- 🔒 **Sandbox Mode**: Execução segura de código gerado em ambiente isolado
- 📝 **RFC Automático**: Geração de Request for Comments para propostas aprovadas
- 🧠 **Monólogo Interno**: Decisões autônomas seguem filtros rigorosos (ROI mínimo, nível de risco)
- 🛡️ **Travas de Segurança**: Rejeita automaticamente propostas com risco CRITICAL ou security concerns sem mitigação
- 📈 **Análise de Logs**: Sugestões de refatoração preventiva baseadas em padrões de erro
- 🎭 **Interface de Decisão**: Prompts formatados para aprovação do comandante antes da implementação

**Exemplo de Uso:**

```python
from app.application.services.strategist_service import StrategistService
from app.domain.models.viability import CostEstimate, ImpactEstimate, RiskEstimate, ImpactLevel, RiskLevel

strategist = StrategistService(default_budget_cap=10.0, min_roi_threshold=0.5)

matrix = strategist.generate_viability_matrix(
    proposal_title="Adicionar Redis Cache",
    proposal_description="Implementar cache distribuído para melhorar performance",
    cost=CostEstimate(api_cost_usd=0.10, development_time_hours=3.0),
    impact=ImpactEstimate(performance_gain_percent=35.0, user_utility_level=ImpactLevel.HIGH),
    risk=RiskEstimate(risk_level=RiskLevel.MEDIUM, mitigation_strategy="Adicionar testes de regressão"),
)

if matrix.is_viable():
    rfc_path = strategist.generate_rfc(matrix)
    prompt = strategist.format_decision_prompt(matrix)
    print(prompt)  # Pede aprovação ao comandante
```

**Demo Interativo:**
```bash
python docs/examples/demo_xerife_strategist.py
```

Para documentação completa, veja [docs/XERIFE_STRATEGIST.md](docs/XERIFE_STRATEGIST.md).


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
├── docs/
│   └── examples/            # Demo scripts and examples
├── scripts/                 # Utility scripts and tools
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

### 🚀 Opção 1: Instalador Executável (Recomendado para Usuários)

**A forma mais fácil - sem instalar nada!**

1. Vá em [**Releases**](../../releases) e baixe `Jarvis_Installer.exe`
2. Execute o arquivo
3. Siga o Setup Wizard interativo

> **✨ Novidade**: Graças às melhorias recentes no build com PyInstaller, o instalador agora é um único arquivo executável que contém tudo que você precisa!

### 🎯 Opção 2: Instalação via Python (Desenvolvedores)

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

### 🔧 Opção 3: Instalação Manual (Avançada)

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

### Render Deployment (Cloud)

For production cloud deployment with optimized caching and monitoring:

1. **Quick Deploy with Blueprint** (Recommended):
   - Fork this repository to your GitHub account
   - Go to [Render Dashboard](https://render.com/) → "New" → "Blueprint"
   - Connect your GitHub repository
   - Render will automatically read `render.yaml` and deploy the application
   - Set required environment variables (API keys) in the dashboard

2. **Features**:
   - ✅ Automatic PostgreSQL database provisioning
   - ✅ Optimized dependency caching with `uv` (10-100x faster than pip)
   - ✅ Docker BuildKit cache mounts for faster rebuilds
   - ✅ Comprehensive health check endpoint (`/health`)
   - ✅ GitHub Actions monitoring workflow

3. **Performance**:
   - First build: ~5-10 minutes
   - Subsequent builds (with cache): ~2-3 minutes
   - Code-only changes: ~1-2 minutes

📖 **See [DEPLOYMENT.md](DEPLOYMENT.md) for complete deployment guide**, including:
- Detailed configuration steps
- Caching strategy explanation
- Health monitoring setup
- Troubleshooting guide

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

### Audio Issues (Optional for Cloud/API Mode)
**Note:** Audio dependencies (pyaudio, pyttsx3) are **optional** for cloud/API deployments. The assistant can run in headless mode using only text-based API interactions.

If you want to use voice features locally and encounter audio device errors:
- Ensure microphone permissions are granted
- Install system audio libraries:
  - On Linux: `sudo apt-get install portaudio19-dev python3-pyaudio`
  - On macOS: `brew install portaudio`
  - On Windows: Install via pip (usually works without system deps)
- Install Python audio packages: `pip install pyaudio pyttsx3`

### Docker Audio
For audio in Docker containers:
- Uncomment device mappings in docker-compose.yml
- May require privileged mode for some systems
- **Not required for API-only deployments**

### Import Errors
If you get import errors:
- Make sure you're in the virtual environment
- Install correct requirements file for your deployment
- Check Python version (3.11+ recommended)

## 📚 Quick Reference: Distributed Orchestration

### Device Registration (for "Soldiers")

```bash
# 1. Get authentication token
curl -X POST "http://localhost:8000/token" \
  -d "username=admin&password=admin"

# 2. Register your device
curl -X POST "http://localhost:8000/v1/devices/register" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "MyPhone",
    "type": "mobile",
    "capabilities": [
      {"name": "camera", "description": "12MP camera"},
      {"name": "type_text", "description": "Virtual keyboard"}
    ],
    "network_id": "Home-WiFi",
    "network_type": "wifi",
    "lat": -23.5505,
    "lon": -46.6333
  }'

# 3. Send heartbeat every 30-60 seconds
curl -X PUT "http://localhost:8000/v1/devices/{device_id}/heartbeat" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{"status": "online"}'
```

### Sending Commands with Context

```bash
# Command will be routed intelligently based on capabilities and location
curl -X POST "http://localhost:8000/v1/execute" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "command": "tire uma selfie",
    "metadata": {
      "source_device_id": 42,
      "network_id": "Home-WiFi"
    }
  }'
```

### Device Routing Hierarchy

```
🎯 Jarvis chooses device using this priority:
  100 → Same Device (if has capability)
   80 → Same Network (WiFi SSID or public IP)
   70 → Very Close (<1km GPS distance)
   40 → Same City (<50km GPS distance)
   10 → Other online devices (asks confirmation)
```

## Documentation

### Architecture & Design
- [ARCHITECTURE.md](ARCHITECTURE.md) - Detailed hexagonal architecture documentation (Portuguese)
- [ARCHITECTURE_IMPROVEMENTS.md](ARCHITECTURE_IMPROVEMENTS.md) - Architecture improvements and recommendations
- [REFACTORING_SUMMARY.md](REFACTORING_SUMMARY.md) - Complete refactoring summary with metrics and validation results

### Integration Guides
- [API_README.md](API_README.md) - REST API documentation and usage guide
- [LLM_INTEGRATION.md](LLM_INTEGRATION.md) - Gemini AI integration guide
- [DISTRIBUTED_MODE.md](DISTRIBUTED_MODE.md) - Cloud + local worker setup guide

### Development
- [CONTRIBUTING.md](CONTRIBUTING.md) - Contribution guidelines
- [EXTENSIBILITY.md](EXTENSIBILITY.md) - Guide for extending functionality
- [requirements/README.md](requirements/README.md) - Modular requirements documentation
- [docs/examples/](docs/examples/) - Demo scripts and usage examples

### Project History
- [CHANGELOG.md](CHANGELOG.md) - Version history
- [MIGRATION.md](MIGRATION.md) - Migration guide from v0.1 to v1.0

## Support

For issues and questions, please open an issue in the repository.
