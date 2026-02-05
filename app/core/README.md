# JarvisEngine - Voice Logic Module

## Overview

This module (`app/core/engine.py`) contains the extracted voice recognition and text-to-speech logic from `assistente.pyw`. The logic has been refactored into a clean, maintainable `JarvisEngine` class.

## Key Features

- **Type Hints**: All methods use proper Python type hints for better code clarity and IDE support
- **Logging**: Replaced all `print` statements with proper logging for better debugging
- **Error Handling**: Improved error handling with try-catch blocks for speech recognition errors
- **Optional Return**: The `Ligar_microfone` method returns `Optional[str]` as specified

## Class: JarvisEngine

### Initialization

```python
from app.core.engine import JarvisEngine

engine = JarvisEngine()
```

The `__init__` method initializes:
- `pyttsx3` engine for text-to-speech
- `speech_recognition.Recognizer` for voice recognition
- Logger for debugging and monitoring

### Methods

#### `falar(fala: str) -> None`

Speaks the given text using text-to-speech.

**Parameters:**
- `fala`: Text to be spoken

**Example:**
```python
engine.falar("Olá, como posso ajudar?")
```

#### `Ligar_microfone() -> Optional[str]`

Listens to the microphone and recognizes speech. Returns the recognized command or `None` if cancelled/stopped.

**Returns:**
- `str`: The recognized command in lowercase
- `None`: If command was cancelled, stopped, or closed

**Special Commands:**
- "cancelar" - Cancels the current action and returns `None`
- "fechar" - Closes the assistant
- "parar" - Stops listening and returns `None`

**Example:**
```python
comando = engine.Ligar_microfone()
if comando:
    print(f"Comando recebido: {comando}")
```

#### `chamarAXerife() -> None`

Main voice assistant loop. Listens for the wake word "xerife" and processes commands.

**Behavior:**
- Continuously listens for voice input
- Responds when "xerife" is detected in the command
- Logs unrecognized commands to `arq01.txt`
- Exits when "fechar" command is received

**Example:**
```python
engine.chamarAXerife()  # Starts the main assistant loop
```

## Logging

The engine uses Python's built-in `logging` module with the following levels:

- **INFO**: Command recognition, actions performed
- **WARNING**: Audio not understood
- **ERROR**: Speech recognition errors, exceptions

Log format: `%(asctime)s - %(name)s - %(levelname)s - %(message)s`

## Changes from Original

### Refactored Functions

| Original Function | New Method | Changes |
|------------------|------------|---------|
| `falar(fala)` | `falar(fala: str) -> None` | Added type hints, logging |
| `Ligar_microfone()` | `Ligar_microfone() -> Optional[str]` | Added type hints, logging, error handling, Optional return type |
| `chamarAXerife()` | `chamarAXerife() -> None` | Added type hints, logging, error handling |

### Improvements

1. **Type Safety**: All methods now have proper type hints
2. **Logging**: All `print` statements replaced with `self.logger` calls
3. **Error Handling**: Added try-except blocks for speech recognition errors
4. **Documentation**: Added docstrings for class and all methods
5. **Maintainability**: Encapsulated voice logic in a single class

## Dependencies

- `pyttsx3`: Text-to-speech engine
- `speech_recognition`: Voice recognition
- `logging`: Standard Python logging (built-in)
- `typing`: Type hints support (built-in)

## Usage Example

See `app/core/example_usage.py` for a complete example of how to use the `JarvisEngine` class.

## Integration

To integrate the new `JarvisEngine` into the existing `assistente.pyw`:

```python
from app.core.engine import JarvisEngine

# Replace the old initialization
# audio = sr.Recognizer()
# maquina = pyttsx3.init()

# With the new engine
engine = JarvisEngine()

# Replace function calls:
# falar("texto") → engine.falar("texto")
# Ligar_microfone() → engine.Ligar_microfone()
# chamarAXerife() → engine.chamarAXerife()
```
