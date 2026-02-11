# LLM-Based Identification System

## Overview

This document describes the LLM-based identification system that replaces keyword-based pattern matching with AI-powered understanding for improved accuracy and flexibility.

## Features

### 1. LLM-Based Command Interpretation

**Traditional Approach (Keyword-Based):**
- Hardcoded patterns like "escreva", "aperte", "internet"
- Limited to exact matches or simple variations
- Cannot understand context or intent variations
- Requires manual updates for new command patterns

**New Approach (LLM-Based):**
- Uses AI (Groq/Gemini) to understand user intent
- Handles natural language variations automatically
- Higher accuracy in command classification
- Learns from context and adapts to user patterns
- Automatic fallback to keyword-based on errors

**Example:**
```python
# Traditional: Only matches "escreva hello"
interpreter.interpret("escreva hello")  # TYPE_TEXT

# LLM: Understands variations
interpreter.interpret("digite hello")    # TYPE_TEXT
interpreter.interpret("write hello")     # TYPE_TEXT
interpreter.interpret("quero escrever hello")  # TYPE_TEXT
```

### 2. LLM-Based Capability Detection

**Traditional Approach (Keyword-Based):**
- Searches files for specific keywords
- Cannot understand code semantics
- Binary detection (present/absent)
- No quality assessment

**New Approach (LLM-Based):**
- Analyzes code semantics and intent
- Understands partial vs complete implementations
- Provides confidence scores
- Offers recommendations for improvement
- Detects capabilities even with different naming

**Example:**
```python
# Detect capability using LLM
result = await detector.detect_capability_async(
    capability_id=1,
    capability_name="User Authentication",
    capability_description="Ability to authenticate users"
)

# Result:
{
    "status": "partial",
    "confidence": 0.85,
    "evidence": [
        "Found login function in auth.py",
        "Missing password reset functionality",
        "No multi-factor authentication"
    ],
    "files_found": ["app/auth.py", "app/models/user.py"],
    "recommendations": [
        "Add password reset feature",
        "Implement MFA for security",
        "Add rate limiting to prevent brute force"
    ]
}
```

### 3. GitHub Copilot Context Provider

**Purpose:**
- Generates intelligent context about the repository
- Helps GitHub Agents make better decisions
- Provides architectural guidance
- Identifies integration points

**Features:**
- Repository structure analysis
- Architecture pattern detection
- Code convention identification
- Best practices extraction
- Issue-specific guidance

**Usage:**
```python
from app.adapters.infrastructure.copilot_context_provider import GitHubCopilotContextProvider

provider = GitHubCopilotContextProvider(ai_gateway=gateway)

# Generate general repository context
context = await provider.generate_repository_context()

# Generate context for a specific issue
issue_context = await provider.generate_context_for_issue(
    "Add user profile photo upload feature"
)

# Save for GitHub Agents
provider.save_context_for_github_agents(context)
```

## Configuration

### Environment Variables

```bash
# Enable/disable LLM-based command interpretation (default: true)
JARVIS_USE_LLM_COMMANDS=true

# Enable/disable LLM-based capability detection (default: true)
JARVIS_USE_LLM_CAPABILITIES=true

# Enable/disable GitHub Copilot context generation (default: true)
JARVIS_USE_COPILOT_CONTEXT=true

# LLM provider for commands (groq, gemini, auto)
JARVIS_COMMAND_LLM_PROVIDER=auto

# LLM provider for capabilities (groq, gemini, auto)
JARVIS_CAPABILITY_LLM_PROVIDER=auto

# Minimum confidence for command interpretation (0.0-1.0)
JARVIS_MIN_COMMAND_CONFIDENCE=0.6

# Minimum confidence for capability detection (0.0-1.0)
JARVIS_MIN_CAPABILITY_CONFIDENCE=0.7
```

### Factory Functions

The system provides factory functions for easy integration:

```python
from app.core.llm_config import (
    create_command_interpreter,
    create_capability_manager,
    create_copilot_context_provider
)

# Create command interpreter (automatically selects LLM or keyword-based)
interpreter = create_command_interpreter(
    wake_word="jarvis",
    ai_gateway=gateway
)

# Create capability manager (automatically selects LLM or standard)
manager = create_capability_manager(
    engine=db_engine,
    ai_gateway=gateway
)

# Create Copilot context provider
copilot = create_copilot_context_provider(
    repository_root=Path.cwd(),
    ai_gateway=gateway
)
```

## Architecture

### Component Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                     User Input / Issue                       │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│                    LLM Config                                │
│  (Decides LLM-based or keyword-based)                       │
└─────────────┬───────────────────────┬───────────────────────┘
              │                       │
              ▼                       ▼
┌─────────────────────┐   ┌──────────────────────────────────┐
│ LLM Command         │   │ LLM Capability                    │
│ Interpreter         │   │ Detector                          │
│                     │   │                                   │
│ - Intent extraction │   │ - Code analysis                   │
│ - Parameter parsing │   │ - Status detection                │
│ - Confidence score  │   │ - Recommendations                 │
└──────────┬──────────┘   └──────────┬───────────────────────┘
           │                         │
           └────────────┬────────────┘
                        │
                        ▼
            ┌───────────────────────┐
            │   AI Gateway          │
            │                       │
            │   - Groq (fast)       │
            │   - Gemini (accurate) │
            │   - Auto-fallback     │
            └───────────┬───────────┘
                        │
                        ▼
            ┌───────────────────────┐
            │  GitHub Copilot       │
            │  Context Provider     │
            │                       │
            │  - Repo analysis      │
            │  - Context generation │
            │  - Agent guidance     │
            └───────────────────────┘
```

## Integration with GitHub Agents

### Workflow Integration

The LLM-based system integrates with GitHub Agents through:

1. **Repository Context File**: `.github/repository_context.json`
2. **Issue-Specific Context**: Generated on-demand for each issue
3. **Autonomous Instructions**: Enhanced with LLM insights

**Example Workflow:**

```yaml
# .github/workflows/jarvis_code_fixer.yml
- name: Generate Repository Context
  run: |
    python -c "
    import asyncio
    from app.core.llm_config import create_copilot_context_provider
    from app.adapters.infrastructure.ai_gateway import AIGateway
    
    async def main():
        gateway = AIGateway()
        provider = create_copilot_context_provider(ai_gateway=gateway)
        context = await provider.generate_repository_context()
        provider.save_context_for_github_agents(context)
    
    asyncio.run(main())
    "
```

### Context Usage in GitHub Agents

GitHub Agents can read the context file to make informed decisions:

```python
import json

# Read repository context
with open('.github/repository_context.json') as f:
    context = json.load(f)

# Use context to guide implementation
architecture = context['architecture']  # "Hexagonal Architecture"
integration_points = context['integration_points']
best_practices = context['best_practices']

# Make context-aware changes
if architecture == "Hexagonal Architecture":
    # Add adapter in the right location
    create_adapter_in_infrastructure_layer()
```

## Benefits

### 1. Higher Accuracy
- LLM understands context and intent
- Handles natural language variations
- Reduces false positives/negatives

### 2. Flexibility
- No need to update keyword lists manually
- Adapts to new command patterns automatically
- Works in multiple languages (with multilingual LLMs)

### 3. Better GitHub Agent Integration
- Provides architectural guidance
- Suggests implementation approaches
- Identifies risks and best practices
- Improves auto-fix quality

### 4. Maintainability
- Less hardcoded logic
- Self-documenting through LLM reasoning
- Easier to extend and modify

## Performance Considerations

### Token Usage

**Estimated token usage (based on testing with cl100k_base encoding):**
- Command interpretation: ~200-500 tokens per request
- Capability detection: ~1000-3000 tokens per capability
- Repository context: ~3000-8000 tokens one-time

**Note:** These are estimates. Actual usage may vary based on:
- Command/prompt complexity
- Code size being analyzed
- Provider-specific tokenization

**Configuration:** Adjust `MAX_CODE_CONTEXT_CHARS` in `LLMCapabilityDetector` to control token usage.

### Latency
- Groq: ~200-500ms average
- Gemini: ~1-2s average
- Fallback to keywords: <10ms

### Cost Optimization
- Use Groq for fast, cheap operations (commands)
- Use Gemini for complex analysis (capabilities)
- Cache repository context (regenerate weekly)
- Fallback to keywords when LLM unavailable

## Migration Guide

### From Keyword-Based to LLM-Based

1. **Enable LLM features gradually:**
   ```bash
   # Start with command interpretation only
   export JARVIS_USE_LLM_COMMANDS=true
   export JARVIS_USE_LLM_CAPABILITIES=false
   export JARVIS_USE_COPILOT_CONTEXT=false
   ```

2. **Monitor confidence scores:**
   ```python
   intent = await interpreter.interpret_async("command")
   if intent.confidence < 0.7:
       logger.warning(f"Low confidence: {intent.confidence}")
   ```

3. **Enable capability detection:**
   ```bash
   export JARVIS_USE_LLM_CAPABILITIES=true
   ```

4. **Enable Copilot context:**
   ```bash
   export JARVIS_USE_COPILOT_CONTEXT=true
   ```

### Rollback Strategy

If issues occur, disable LLM features:

```bash
# Disable all LLM features
export JARVIS_USE_LLM_COMMANDS=false
export JARVIS_USE_LLM_CAPABILITIES=false
export JARVIS_USE_COPILOT_CONTEXT=false

# System will fallback to keyword-based automatically
```

## Testing

### Unit Tests

```bash
# Run LLM integration tests
pytest tests/test_llm_integration.py -v

# Run with coverage
pytest tests/test_llm_integration.py --cov=app/domain/services --cov=app/application/services
```

### Integration Tests

```bash
# Test with real API (requires API keys)
GROQ_API_KEY=your_key pytest tests/test_llm_integration.py --real-api
```

## Troubleshooting

### LLM Not Responding

**Issue:** LLM-based interpretation returns errors

**Solutions:**
1. Check API keys are set correctly
2. Verify network connectivity
3. Check rate limits
4. System will fallback to keyword-based automatically

### Low Confidence Scores

**Issue:** LLM returns low confidence scores

**Solutions:**
1. Adjust `JARVIS_MIN_COMMAND_CONFIDENCE` threshold
2. Provide more context in prompts
3. Use better-quality LLM models
4. Check for ambiguous commands

### High Latency

**Issue:** LLM responses are slow

**Solutions:**
1. Use Groq instead of Gemini for speed
2. Reduce prompt size
3. Cache common results
4. Enable async processing

## Future Enhancements

1. **Fine-tuned Models:** Train custom models on repository-specific patterns
2. **Multi-language Support:** Add support for more languages
3. **Voice Commands:** Direct LLM integration with voice input
4. **Auto-learning:** Learn from user corrections
5. **Context Caching:** Cache and reuse repository context

## References

- [AI Gateway Documentation](../api/AI_GATEWAY.md)
- [LLM Integration Guide](../api/LLM_INTEGRATION.md)
- [GitHub Actions Integration](../architecture/SELF_HEALING_ARCHITECTURE.md)
