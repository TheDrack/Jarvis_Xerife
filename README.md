# Jarvis - Intelligent Voice Assistant & Distributed Automation Platform

[![Python Tests](https://github.com/TheDrack/python/actions/workflows/python-tests.yml/badge.svg?branch=main)](https://github.com/TheDrack/python/actions/workflows/python-tests.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

> **Jarvis evolved beyond a simple voice assistant** - It's now a distributed orchestration platform that intelligently coordinates multiple devices ("Soldiers") based on their capabilities, location, and network proximity.

## 🎯 What is Jarvis?

Jarvis is a **cloud-native voice assistant** with distributed device orchestration that:

- 🧠 **Intelligently routes commands** to the right device based on capabilities, location, and network
- 🎤 **Understands voice commands** in Brazilian Portuguese with Google Speech Recognition
- 🤖 **Self-heals** using AI to automatically fix bugs and update documentation
- 🌐 **Scales horizontally** - Run on multiple devices (PCs, phones, Raspberry Pi, IoT)
- 🏗️ **Built with Hexagonal Architecture** - Clean, testable, and cloud-ready
- ⚡ **Multi-tier AI system** - Uses Groq (Llama) for speed and Gemini for complex tasks

### Real-World Example

> "Jarvis, tire uma selfie" 
> - If you're traveling: Uses your phone's camera
> - If you're home: Routes to your local PC or tablet

> "Jarvis, ligue a TV"
> - Routes to the IR-capable device in the same room
> - Confirms before routing to distant devices (>50km)

## ✨ Key Features

### 🎯 Intelligent Device Orchestration
- **Capability-based routing** - Knows which devices can do what
- **3-tier proximity hierarchy**:
  1. Same device (if capable)
  2. Same network/WiFi
  3. GPS proximity (<1km, <50km)
- **Conflict validation** - Confirms cross-network or distant commands

### 🤖 AI-Powered Intelligence
- **Multi-tier LLM system** (Gears):
  - High Gear: Llama-3.3-70b (Groq) - Fast & economical
  - Low Gear: Llama-3.1-8b (Groq) - Fallback for rate limits
  - Cannon Shot: Gemini-1.5-Pro - Complex reasoning
- **LLM-based identification** - Replaces keyword matching with AI understanding
- **Natural language understanding** with context awareness
- **Gemini AI integration** for complex command interpretation
- **GitHub Copilot integration** - Provides repository context to GitHub Agents

### 🔧 Self-Healing & Auto-Correction
- **Automatic bug fixing** using GitHub Copilot
- **CI/CD failure detection** and auto-repair
- **Pull Request generation** for proposed fixes
- **State machine** for autonomous error handling

### 🏗️ Architecture & Deployment
- **Hexagonal Architecture** - Clean domain logic, testable
- **Cloud-ready** - Core runs headless without hardware
- **REST API** - FastAPI with OAuth2 authentication
- **Docker support** - PostgreSQL & containerized deployment
- **97-100% domain test coverage**

## 🚀 Quick Start

### Option 1: Installer (Windows - Recommended for Users)

1. Download `Jarvis_Installer.exe` from [Releases](../../releases)
2. Run the installer
3. Follow the Setup Wizard
4. Done! 🎉

### Option 2: Python Installation (Developers)

```bash
# Clone the repository
git clone https://github.com/TheDrack/python
cd python

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run setup wizard
python main.py
```

The **Setup Wizard** will guide you through:
- 🎭 Choosing your assistant name (Jarvis, Friday, Ultron, etc.)
- 🔑 Configuring Gemini API key
- 🗄️ Setting up the database (SQLite/PostgreSQL)
- 💾 Generating encrypted `.env` file

### Option 3: Docker (Production)

```bash
# Start with Docker Compose (includes PostgreSQL)
docker-compose up --build

# Access API at http://localhost:8000
# Web interface at http://localhost:8000
```

## 🌐 Web Interface

Access the **Stark Industries-themed web interface** at `http://localhost:8000`:

- 🔐 Secure login with OAuth2
- 🎤 Voice commands via Web Speech API
- 💻 Direct command execution
- ⚡ Real-time feedback
- 🔒 Auto-logout (30min inactivity)

Default credentials: `admin` / `admin123`

## 📖 Documentation

### Getting Started
- [Installation Guide](docs/guides/INSTALLER_README.md) - Detailed setup instructions
- [Local Setup](docs/guides/LOCAL_SETUP.md) - Development environment setup
- [Quick Start - Self-Healing](docs/guides/SELF_HEALING_QUICK_START.md) - Auto-correction setup

### Architecture & Design
- [Hexagonal Architecture](docs/architecture/ARCHITECTURE.md) - System design
- [Device Orchestration](docs/architecture/DEVICE_ORCHESTRATION.md) - Multi-device coordination
- [Self-Healing System](docs/architecture/SELF_HEALING_ARCHITECTURE.md) - Auto-correction architecture

### API & Integration
- [REST API Documentation](docs/api/API_README.md) - API reference
- [LLM Integration](docs/api/LLM_INTEGRATION.md) - AI integration guide
- [AI Gateway](docs/api/AI_GATEWAY.md) - Gateway architecture

### Deployment
- [Production Deployment](docs/deployment/DEPLOYMENT.md) - Deploy to production
- [Distributed Mode](docs/guides/DISTRIBUTED_MODE.md) - Multi-device setup
- [Render Deployment](docs/guides/RENDER_QUICKSTART.md) - Cloud deployment

### Advanced Features
- [Gears System](docs/GEARS_SYSTEM.md) - Multi-tier LLM system
- [Xerife Strategist](docs/XERIFE_STRATEGIST.md) - Autonomous decision-making
- [Extensibility](docs/development/EXTENSIBILITY.md) - Extending Jarvis

📚 **[Full Documentation Index](docs/README.md)** - Complete documentation listing

## 🎯 Voice Commands

```
"xerife escreva [texto]"     - Type text
"xerife aperte [tecla]"      - Press a key  
"xerife internet"            - Open browser
"xerife site [url]"          - Open website
"xerife tire uma selfie"     - Take a photo (routes to device with camera)
"xerife ligue a TV"          - Control TV (routes to IR device)
"fechar"                     - Exit assistant
```

## 🛠️ Development

### Project Structure

```
.
├── app/
│   ├── domain/              # Business logic (pure Python)
│   ├── application/         # Use cases and ports
│   ├── adapters/            # Infrastructure implementations
│   │   ├── edge/            # Hardware adapters
│   │   └── infrastructure/  # Cloud/API adapters
│   └── container.py         # Dependency injection
├── docs/                    # 📚 All documentation
├── tests/                   # Test suite (97-100% domain coverage)
├── scripts/                 # Utility scripts
└── requirements/            # Modular dependencies
```

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=app tests/

# Run domain tests only (no hardware!)
pytest tests/domain/ -v
```

### Code Quality

```bash
# Format code
black app/ tests/

# Type checking
mypy app/

# Linting
flake8 app/ tests/
```

## 🗺️ Roadmap

### ✅ Current (Q1 2026)
- [x] Hexagonal Architecture refactoring
- [x] Self-healing with GitHub Copilot
- [x] Multi-tier LLM system (Gears)
- [x] Device orchestration
- [ ] Stabilize TaskRunner with ephemeral environments
- [ ] Playwright integration

### 📅 Next (Q2-Q3 2026)
- [ ] Enhanced voice interface
- [ ] Wake word detection (offline)
- [ ] Device monitoring dashboard
- [ ] Real-time WebSocket support

### 🤔 Future (Q4 2026+)
- [ ] Local AI models (TinyLLM)
- [ ] Mobile app
- [ ] Home Assistant integration
- [ ] Extension marketplace

📖 **[Full Roadmap](docs/ROADMAP.md)** - Detailed project roadmap

## 🤝 Contributing

We welcome contributions! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

### Quick Contribution Guide

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Run tests (`pytest`)
5. Submit a Pull Request

## 📊 Project Stats

- **Architecture**: Hexagonal (Ports & Adapters)
- **Test Coverage**: 97-100% (domain layer)
- **Languages**: Python 3.11+, Portuguese (pt-BR)
- **AI Models**: Groq (Llama 3.3 70b, Llama 3.1 8b), Gemini 1.5 Pro
- **Deployment**: Docker, Render, Local

## 🙏 Acknowledgments

- **Google Gemini** - AI integration
- **Groq** - Fast LLM inference
- **GitHub Copilot** - Self-healing automation
- **FastAPI** - REST API framework

## 📄 License

This project is provided as-is for educational and personal use. See [LICENSE](LICENSE) for details.

## 📞 Support

- 📖 [Documentation](docs/README.md)
- 🐛 [Report Issues](../../issues)
- 💬 [Discussions](../../discussions)
- 📧 [Contact](mailto:your-email@example.com)

---

**Made with ❤️ by the Jarvis Team**

> "Sometimes you gotta run before you can walk." - Tony Stark
