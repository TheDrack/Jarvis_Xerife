# Migration Guide: From assistente.pyw to Jarvis Assistant v1.0

This guide helps you understand the changes from the original `assistente.pyw` to the new professional architecture.

## Overview of Changes

The project has been completely refactored from a single monolithic file into a professional, modular Python application.

## What Stayed the Same

✅ **Core Functionality Preserved:**
- Voice recognition in Portuguese (pt-BR)
- Text-to-speech (TTS) with pyttsx3
- PyAutoGUI automation
- Keyboard control with pynput
- Web browser navigation

✅ **Wake Word:**
- Still uses "xerife" as the wake word
- Still responds to "fechar" to exit

## What Changed

### Project Structure

**Before:**
```
assistente.pyw  (single 418-line file)
```

**After:**
```
├── app/
│   ├── core/
│   │   ├── engine.py    (JarvisEngine class)
│   │   └── config.py    (Configuration)
│   ├── actions/
│   │   └── system_commands.py  (Commands)
│   └── utils/
│       └── helpers.py   (Utilities)
├── tests/               (Test suite)
├── dags/                (Airflow DAGs)
├── main.py              (Entry point)
└── [documentation & config files]
```

### Code Organization

| Old Function | New Location | Notes |
|--------------|--------------|-------|
| `falar()` | `JarvisEngine.speak()` | Now a method in engine class |
| `Ligar_microfone()` | `JarvisEngine.listen()` | Improved error handling |
| `digitar()` | `SystemCommands.type_text()` | Part of SystemCommands class |
| `aperta()` | `SystemCommands.press_key()` | Part of SystemCommands class |
| `abrirsite()` | `WebNavigator.open_url()` | Dedicated web navigation |
| `comandos()` | `CommandProcessor.process()` | Improved routing |

### What Was Removed

The following work-specific features were removed to create a general-purpose assistant:

❌ **Removed Functions:**
- `FazerRequisicaoPT1()` / `FazerRequisicaoPT2()` - Work requisition system
- `FazerRequisicaoSulfite()` - Sulfite requisition
- `AbrirAlmox()` - Warehouse system (4R)
- `AbrirPlanilha()` - Specific spreadsheet automation
- `AtualizarInventario()` - Inventory updates
- `ImprimirBalancete()` - Balance sheet printing
- `ConsultarEstoque()` - Stock consultation
- `EscolherCentroDeCusto()` - Cost center selection
- `Cod4rMaterial()` / `QuantMaterial()` - Material code functions
- All Excel file dependencies for commands

❌ **Removed Hard-coded Paths:**
- No more `C:\Users\jesus.anhaia\OneDrive\...` paths
- No more hard-coded credentials
- No more hard-coded image paths

## How to Use the New Version

### Starting the Assistant

**Old Way:**
```bash
python assistente.pyw
```

**New Way:**
```bash
python main.py
```

Or using the package:
```bash
make run
```

Or with Docker:
```bash
docker-compose up
```

### Configuration

**Old Way:**
- Hard-coded values in the script

**New Way:**
- Create a `.env` file:
```env
LANGUAGE=pt-BR
WAKE_WORD=xerife
PYAUTOGUI_PAUSE=0.4
```

Or use environment variables:
```bash
export LANGUAGE=pt-BR
python main.py
```

### Available Commands

The new version keeps the essential commands:

| Command | Action |
|---------|--------|
| "xerife escreva [texto]" | Type text |
| "xerife aperte [tecla]" | Press a key |
| "xerife internet" | Open browser |
| "xerife site [url]" | Open specific website |
| "fechar" | Exit assistant |

### Adding Custom Commands

**Old Way:**
- Modify `comandos()` function directly in assistente.pyw
- Add to `TuplaDeComandos` tuple

**New Way:**
- Create a new module in `app/actions/`
- Register in `CommandProcessor.commands_map`
- See [EXTENSIBILITY.md](EXTENSIBILITY.md) for details

Example:
```python
# app/actions/my_feature.py
class MyFeature:
    def execute(self, param: str) -> None:
        print(f"Executing: {param}")

# In system_commands.py CommandProcessor.__init__:
self.my_feature = MyFeature()
self.commands_map['meu_comando'] = lambda p: self.my_feature.execute(p)
```

## Testing

**New Addition:**
```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=app

# Use Make
make test
```

## Docker Support

**New Addition:**
```bash
# Build image
docker build -t jarvis-assistant .

# Run with docker-compose
docker-compose up

# Stop
docker-compose down
```

## Airflow Integration

**New Addition:**
For scheduled tasks, create DAGs in `dags/` directory:

```python
# dags/my_task.py
from airflow import DAG
from airflow.operators.python import PythonOperator

def my_scheduled_task():
    from app.core.engine import JarvisEngine
    engine = JarvisEngine()
    engine.speak("Task executed")

dag = DAG('my_task', ...)
```

## Migration Checklist

If you had customizations in the old `assistente.pyw`:

- [ ] Identify custom functions you added
- [ ] Create new module in `app/actions/` for each feature
- [ ] Register commands in `CommandProcessor`
- [ ] Add tests in `tests/`
- [ ] Update configuration in `.env` or `config.py`
- [ ] Test thoroughly with `pytest`
- [ ] Update documentation

## Benefits of New Architecture

1. **Modularity**: Easy to add/remove features
2. **Testability**: 24 comprehensive tests
3. **Type Safety**: Full type hints throughout
4. **Documentation**: Extensive docs and examples
5. **Extensibility**: Clear patterns for adding features
6. **DevOps**: Docker, Airflow support
7. **Code Quality**: Black, isort, mypy, pytest
8. **Maintainability**: Separate concerns, clean code

## Getting Help

- Read [README.md](README.md) for usage instructions
- Check [EXTENSIBILITY.md](EXTENSIBILITY.md) for adding features
- See [CONTRIBUTING.md](CONTRIBUTING.md) for development
- Review [CHANGELOG.md](CHANGELOG.md) for all changes

## Questions?

Open an issue in the repository with the `question` label.
