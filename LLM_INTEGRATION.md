# LLM Integration Guide

## Overview

This project now supports two command interpretation modes:
1. **Rule-based** (original): Pattern matching using predefined keywords
2. **LLM-based** (new): Gemini AI with function invocation capabilities

The LLM integration maintains full compatibility with existing Intent/Command architecture through the `LLMCommandAdapter`, which acts as a drop-in replacement for `CommandInterpreter`.

## Architecture

### Components

**AgentService** (`app/domain/services/agent_service.py`)
- Pure domain logic defining available automation functions
- Provides function schemas matching ActionProvider interface
- Contains system prompt configuring the AI's personality (customizable via `get_system_instruction()`)
- Maps Gemini function responses to CommandType enum values

> **🎭 Personalidade Customizável**: O comportamento do assistente é definido em `get_system_instruction()`. Você pode modificar este método para criar diferentes personalidades - desde assistentes formais e técnicos até versões mais casuais e divertidas. Veja [INSTALLER_README.md](INSTALLER_README.md) para exemplos de personalidades customizadas.

**LLMCommandAdapter** (`app/adapters/infrastructure/gemini_adapter.py`)  
- Infrastructure adapter implementing same interface as CommandInterpreter
- Manages Gemini API communication with async support using the new `google-genai` library
- Converts function call responses into Intent objects
- Handles uncertainty by invoking VoiceProvider for clarification

### Design Decisions

The implementation preserves hexagonal architecture principles:
- Domain layer remains independent (AgentService has no external dependencies)
- Infrastructure adapter encapsulates Gemini SDK usage
- Container provides configuration flexibility through `use_llm` flag
- Existing IntentProcessor and AssistantService require no modifications

## Setup Instructions

### Quick Setup (Recomendado)

A maneira mais fácil de configurar a API do Gemini é através do **Setup Wizard interativo**:

```bash
python main.py  # Se o .env não existir, o wizard iniciará automaticamente
```

O wizard irá:
- Abrir automaticamente o Google AI Studio no navegador
- Detectar a chave API copiada via clipboard
- Salvar de forma segura com criptografia baseada em hardware

### Prerequisites

Install the new Gemini SDK:
```bash
pip install google-genai
```

### API Credentials

Obtain a Gemini API key from Google AI Studio, then configure via environment:

```bash
export GOOGLE_API_KEY="your-actual-key-here"
export GEMINI_MODEL="gemini-2.0-flash"  # optional, this is default
```

Or add to `.env` file (recommended for local development):
```env
GOOGLE_API_KEY=your-actual-key-here
GEMINI_MODEL=gemini-2.0-flash
```

**Note:** The adapter supports both `GOOGLE_API_KEY` and `GEMINI_API_KEY` environment variables for backward compatibility. `GOOGLE_API_KEY` takes precedence if both are set.

### Activation

Modify your container initialization to enable LLM mode:

```python
from app.container import create_edge_container

# Traditional rule-based approach
traditional_container = create_edge_container()

# New LLM-powered approach  
llm_container = create_edge_container(use_llm=True)

# The rest of your code remains unchanged
service = llm_container.assistant_service
service.start()
```

## How It Works

### Function Calling Flow

1. User speaks: "xerife, write my name"
2. VoiceProvider transcribes to text
3. LLMCommandAdapter receives raw input
4. Wake word removed, text sent to Gemini using new `client.models.generate_content` API
5. Gemini analyzes against available function schemas
6. Gemini invokes `type_text` function with appropriate argument
7. Adapter converts function call to Intent(TYPE_TEXT, {"text": "my name"})
8. IntentProcessor validates and creates Command
9. AssistantService executes via ActionProvider

### Clarification Mechanism

When Gemini cannot confidently map input to a function:
- Returns text response instead of function call
- Adapter detects this and invokes `voice_provider.speak(clarification_text)`
- Returns Intent with UNKNOWN type and low confidence
- User can provide additional information

### Available Functions

The agent knows these automation capabilities:

| Function | Portuguese Trigger | Parameters | Action |
|----------|-------------------|------------|--------|
| type_text | "escreva", "digite" | text | Types keyboard input |
| press_key | "aperte", "pressione" | key | Presses single key |
| open_browser | "internet", "navegador" | - | Opens web browser |
| open_url | "site", "abrir" | url | Navigates to URL |
| search_on_page | "procurar", "clicar" | search_text | Finds text on page |

## Testing

The implementation includes comprehensive test coverage:

### Domain Tests (11 tests)
```bash
pytest tests/domain/test_agent_service.py -v
```

Validates:
- Function schema structure correctness
- CommandType mapping accuracy  
- System instruction content
- Portuguese language usage

### Adapter Tests (14 tests)  
```bash
pytest tests/adapters/infrastructure/test_gemini_adapter.py -v
```

Validates:
- API initialization and configuration
- Function call to Intent conversion
- Error handling and recovery
- Clarification request mechanism
- AsyncIO operation

### Full Suite
```bash
pytest tests/ -v
```

All 88 tests pass, confirming backward compatibility.

## Performance Considerations

### Async Design

LLMCommandAdapter uses AsyncIO to prevent blocking:
- API calls run in separate threads via `asyncio.to_thread()`
- Voice loop continues processing while waiting for responses
- Falls back to synchronous mode if event loop unavailable

### Latency

Typical response times:
- Rule-based: <1ms (instant pattern matching)
- LLM-based: 500-2000ms (network + inference)

The async design ensures voice interface remains responsive during LLM processing.

## Extending Function Capabilities

To add new automation functions:

1. **Update ActionProvider** (if needed) with new methods
2. **Extend AgentService.get_function_declarations()** with new schema
3. **Add mapping** in `AgentService.map_function_to_command_type()`
4. **Update CommandType** enum with new type
5. **Implement execution** in AssistantService._execute_command()

Example adding a screenshot function:

```python
# In agent_service.py
{
    "name": "capture_screen",
    "description": "Captura uma imagem da tela atual",
    "parameters": {
        "type": "object",
        "properties": {
            "filename": {
                "type": "string",
                "description": "Nome do arquivo para salvar"
            }
        },
        "required": ["filename"]
    }
}

# In mapping
"capture_screen": CommandType.SCREENSHOT
```

## Security Considerations

### API Key Protection
- Never commit API keys to version control
- Use environment variables or secure vaults
- Rotate keys periodically

### Input Validation
- LLMCommandAdapter validates all function arguments
- IntentProcessor performs secondary validation
- ActionProvider enforces type safety

### Rate Limiting
- Gemini API has usage quotas
- Consider implementing local caching for repeated queries
- Monitor API usage through Google Cloud Console

## Troubleshooting

### "GEMINI_API_KEY not found" or "GOOGLE_API_KEY not found"
Ensure environment variable is set before importing Container.

### "ModuleNotFoundError: google.genai"
Install SDK: `pip install google-genai`

### "Failed to initialize Gemini client"
- Verify your API key is correct and valid
- Check that you have internet connectivity
- Ensure you're not hitting rate limits

### Slow responses
- Check network connectivity
- Verify API quota hasn't been exceeded
- Consider using gemini-2.0-flash for improved performance
- gemini-1.5-flash is also available as a more stable alternative

### Incorrect function calls
- Review AgentService system instruction
- Adjust function descriptions for clarity
- Add examples to system prompt

### 404 Errors
The new `google-genai` library resolves 404 errors that were occurring with the older `google-generativeai` library when using certain API endpoints or configurations.

## Migration Path

Projects currently using rule-based interpretation can migrate gradually:

**Phase 1**: Install dependencies and test in development
```python
if os.getenv("ENVIRONMENT") == "development":
    container = create_edge_container(use_llm=True)
else:
    container = create_edge_container(use_llm=False)
```

**Phase 2**: A/B test with subset of users
**Phase 3**: Full rollout after validation
**Phase 4**: Remove rule-based code if desired (optional)

The modular design ensures both modes can coexist indefinitely.
