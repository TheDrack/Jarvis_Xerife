# Contributing to Jarvis Assistant

Thank you for your interest in contributing to Jarvis Assistant! This document provides guidelines for contributing to the project.

## Development Setup

### Prerequisites

- Python 3.9 or higher
- pip (Python package installer)
- Virtual environment (recommended)

### Setting Up Development Environment

1. Clone the repository:
```bash
git clone <repository-url>
cd python
```

2. Create and activate a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install development dependencies:
```bash
make install-dev
# or
pip install -r requirements.txt
pip install -e .[dev]
```

4. Configure the application:
```bash
# Opção A: Use o Setup Wizard interativo (recomendado)
python main.py  # O wizard iniciará automaticamente se .env não existir

# Opção B: Configuração manual
cp .env.example .env
# Edite .env e preencha: USER_ID, ASSISTANT_NAME, GEMINI_API_KEY, DATABASE_URL
```

> **💡 Dica**: O Setup Wizard facilita a configuração inicial do ambiente de desenvolvimento, incluindo captura automática da chave API do Gemini e validação da conexão com o banco de dados.

## Code Style

This project follows strict code quality standards:

### Formatting

- **Black**: Code formatter with 100 character line length
- **isort**: Import statement organizer

Format your code before committing:
```bash
make format
```

### Type Checking

All code must include type hints. Use mypy for type checking:
```bash
make lint
```

### Linting

Code must pass flake8 linting:
```bash
flake8 app/ tests/ --max-line-length=100
```

## Testing

### Running Tests

Run all tests with coverage:
```bash
make test
```

Run tests quickly without coverage:
```bash
make test-fast
```

### Writing Tests

- Place tests in the `tests/` directory
- Follow the naming convention: `test_*.py`
- Use pytest fixtures from `tests/conftest.py`
- Aim for high test coverage (>80%)

Example test:
```python
import pytest

class TestMyFeature:
    def test_basic_functionality(self):
        """Test basic feature functionality"""
        # Your test code here
        assert True
```

## Pull Request Process

1. **Create a Branch**: Create a feature branch from `main`
   ```bash
   git checkout -b feature/my-new-feature
   ```

2. **Make Changes**: Implement your changes following the code style

3. **Add Tests**: Write tests for new functionality

4. **Format Code**: Run code formatters
   ```bash
   make format
   ```

5. **Run Tests**: Ensure all tests pass
   ```bash
   make test
   ```

6. **Run Linters**: Check code quality
   ```bash
   make lint
   ```

7. **Commit Changes**: Write clear, descriptive commit messages
   ```bash
   git commit -m "Add feature: description of feature"
   ```

8. **Push Changes**: Push to your fork
   ```bash
   git push origin feature/my-new-feature
   ```

9. **Create PR**: Open a Pull Request with a clear description

## Commit Message Guidelines

Follow these guidelines for commit messages:

- Use present tense ("Add feature" not "Added feature")
- Use imperative mood ("Move cursor to..." not "Moves cursor to...")
- First line should be 50 characters or less
- Reference issues and pull requests when relevant

Examples:
```
Add voice command for web scraping
Fix bug in speech recognition timeout
Update documentation for AI integration
Refactor command processor for better modularity
```

## Project Structure

```
.
├── app/
│   ├── domain/             # Business logic (pure Python, cloud-ready)
│   │   ├── models/         # Entities (Command, Intent, Response)
│   │   └── services/       # Domain services
│   ├── application/        # Use cases and interfaces (Ports)
│   │   ├── ports/          # Abstract interfaces
│   │   └── services/       # Application services
│   ├── adapters/          # Infrastructure implementations
│   │   ├── edge/          # Hardware adapters (PyAutoGUI, speech)
│   │   └── infrastructure/ # Cloud/API adapters
│   └── container.py       # Dependency injection
├── docs/                  # 📚 All documentation
│   ├── architecture/      # Architecture and design docs
│   ├── api/              # API documentation
│   ├── guides/           # Setup and usage guides
│   ├── components/       # Component-specific docs
│   ├── deployment/       # Deployment guides
│   ├── development/      # Development guides
│   ├── summaries/        # Historical implementation summaries
│   └── examples/         # Code examples and demos
├── tests/                # Test suite (97-100% domain coverage)
│   ├── domain/           # Domain tests (no hardware!)
│   ├── application/      # Application tests
│   └── adapters/         # Adapter tests
├── scripts/              # Utility scripts
├── requirements/         # Modular dependencies
│   ├── core.txt         # Core (cloud-ready)
│   ├── edge.txt         # Edge (hardware)
│   ├── dev.txt          # Development
│   ├── prod-edge.txt    # Production edge
│   └── prod-cloud.txt   # Production cloud
├── main.py              # Application entry point
└── README.md            # Main documentation
```

## Adding New Features

See [docs/development/EXTENSIBILITY.md](docs/development/EXTENSIBILITY.md) for detailed guidance on extending the project.

### Basic Steps

1. Identify the appropriate layer (Domain, Application, or Adapter)
2. Create necessary interfaces (Ports) in `app/application/ports/`
3. Implement concrete adapters in `app/adapters/`
4. Add type hints to all functions
5. Write comprehensive tests
6. Update documentation

## Documentation

- Use Google-style docstrings
- Document all public functions and classes
- Update README.md for user-facing changes
- Update relevant docs in `docs/` directory for technical changes
- See [docs/README.md](docs/README.md) for full documentation index

Example docstring:
```python
def my_function(param: str) -> Optional[str]:
    """
    Brief description of what the function does
    
    Args:
        param: Description of parameter
        
    Returns:
        Description of return value
        
    Raises:
        ValueError: When param is invalid
    """
    pass
```

## Common Tasks

### Adding a New Command

1. Create command model in `app/domain/models/command.py`
2. Add interpretation logic in `app/domain/services/command_interpreter.py`
3. Create adapter for execution in appropriate `app/adapters/` subdirectory
4. Add tests in `tests/`
5. Update documentation

### Adding a New Port and Adapter

1. Create port interface in `app/application/ports/`
2. Implement adapter in `app/adapters/edge/` or `app/adapters/infrastructure/`
3. Register in dependency injection container
4. Add tests for both port and adapter
5. Update architecture documentation

### Adding Configuration

1. Add setting to `app/core/config.py`
2. Update `.env.example`
3. Document in README.md

### Adding Dependencies

1. Add to `requirements.txt`
2. Update `setup.py` if needed
3. Document why the dependency is needed

## Code Review

All contributions will be reviewed for:

- Code quality and style
- Test coverage
- Documentation
- Performance implications
- Security considerations

## Getting Help

- Open an issue for bugs or feature requests
- Use discussions for questions
- Check existing issues before creating new ones

## License

By contributing, you agree that your contributions will be licensed under the same license as the project.

## Thank You!

Your contributions help make Jarvis Assistant better for everyone!
