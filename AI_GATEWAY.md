# AI Gateway - Intelligent LLM Provider Routing

## Overview

The AI Gateway is an intelligent routing system that manages multiple LLM providers (Groq and Gemini) for the Jarvis Assistant. It automatically selects the best provider based on payload characteristics, with built-in cost optimization and automatic failover.

## Features

### 1. Cost Priority (Prioridade de Custo)
- **Default Provider**: Groq (Llama-3-70b)
- **Use Cases**: 
  - Log analysis
  - Short internal monologues
  - Quick conversational responses
- **Benefits**: High speed, zero/low cost

### 2. Context Escalation (Escalonamento por Contexto)
- **Automatic Switch to Gemini 1.5** when:
  - Payload exceeds 10,000 tokens
  - Multimodal analysis required (images/video)
- **Benefits**: Higher capacity, multimodal support

### 3. Automatic Fallback (Fallback Automático)
- **Transparent Migration**: If Groq hits rate limit, automatically switches to Gemini
- **Zero Downtime**: Ensures the auto-evolution cycle never stops
- **Bidirectional**: Works both ways (Groq ↔ Gemini)

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    AssistantService                         │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│              GatewayLLMCommandAdapter                       │
│  (Integrates AI Gateway with LLM command interpretation)    │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│                     AI Gateway                              │
│                                                             │
│  ┌─────────────────┐        ┌─────────────────┐           │
│  │ Token Counter   │        │ Provider Selector│           │
│  │ (tiktoken)      │───────▶│ (Smart Routing) │           │
│  └─────────────────┘        └─────────┬───────┘           │
│                                        │                    │
│            ┌───────────────────────────┴─────────┐         │
│            ▼                                     ▼         │
│  ┌──────────────────┐              ┌──────────────────┐   │
│  │  Groq Client     │              │  Gemini Client   │   │
│  │ (Llama-3-70b)    │              │ (Gemini 1.5)     │   │
│  └──────────────────┘              └──────────────────┘   │
│         Fast, Cheap                  Powerful, Multimodal  │
└─────────────────────────────────────────────────────────────┘
```

## Configuration

### Environment Variables

Add the following to your `.env` file:

```bash
# Groq Configuration
GROQ_API_KEY=your_groq_api_key_here
GROQ_MODEL=llama-3.3-70b-versatile

# Gemini Configuration
GOOGLE_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-flash-latest
```

### Get API Keys

1. **Groq API Key**: Sign up at [console.groq.com](https://console.groq.com)
2. **Gemini API Key**: Get from [Google AI Studio](https://makersuite.google.com/app/apikey)

## Usage

### Automatic Mode (Recommended)

The AI Gateway is automatically enabled in the Container when API keys are provided:

```python
from app.container import create_edge_container

# Create container with AI Gateway enabled (default)
container = create_edge_container(
    use_llm=True,
    use_ai_gateway=True  # Default: True
)

assistant = container.assistant_service
```

### Direct Usage

You can also use the AI Gateway directly:

```python
from app.adapters.infrastructure import AIGateway, LLMProvider

# Initialize gateway
gateway = AIGateway(
    groq_api_key="your_groq_key",
    gemini_api_key="your_gemini_key",
)

# Automatic provider selection
messages = [
    {"role": "user", "content": "Analyze this short log message"}
]
result = gateway.generate_completion(messages)
# Uses Groq for short messages

# Large context automatically uses Gemini
large_messages = [
    {"role": "user", "content": "word " * 15000}  # >10k tokens
]
result = gateway.generate_completion(large_messages)
# Automatically escalates to Gemini

# Force specific provider
result = gateway.generate_completion(
    messages,
    force_provider=LLMProvider.GEMINI
)
```

## Token Threshold

- **Default Threshold**: 10,000 tokens
- **Below threshold**: Uses Groq (fast, cheap)
- **Above threshold**: Escalates to Gemini (powerful, large context)

You can modify the threshold in `ai_gateway.py`:

```python
class AIGateway:
    TOKEN_THRESHOLD = 10000  # Adjust as needed
```

## Routing Logic

The AI Gateway uses the following decision tree:

```
1. Is provider forced?
   └─ Yes → Use forced provider (if available)
   └─ No  → Continue to 2

2. Is multimodal analysis required?
   └─ Yes → Use Gemini (Groq doesn't support multimodal)
   └─ No  → Continue to 3

3. Count tokens in payload
   └─ > 10,000 tokens → Use Gemini (large context)
   └─ ≤ 10,000 tokens → Continue to 4

4. Is Groq available?
   └─ Yes → Use Groq (default, cost-optimized)
   └─ No  → Use Gemini (fallback)

5. On rate limit error:
   └─ Groq rate limit → Fallback to Gemini
   └─ Gemini rate limit → Fallback to Groq
```

## Real-World Scenarios

### Scenario 1: Log Analysis
```
Input: "ERROR: Connection timeout on line 145"
Tokens: ~10
Provider: Groq (fast, cheap for short logs)
```

### Scenario 2: Extensive Report
```
Input: Large system metrics report (50k characters)
Tokens: ~12,500
Provider: Gemini (automatically escalated)
```

### Scenario 3: Self-Reflection
```
Input: "Analyzing my performance over the last 24h..."
Tokens: ~15
Provider: Groq (quick internal monologue)
```

### Scenario 4: Code Analysis
```
Input: Full codebase analysis (100+ files)
Tokens: ~25,000
Provider: Gemini (large context required)
```

## Testing

Run the comprehensive test suite:

```bash
# Run AI Gateway tests
pytest tests/adapters/test_ai_gateway.py -v

# Run demo script
python demo_ai_gateway.py
```

## Performance Characteristics

### Groq (Llama-3-70b)
- **Speed**: ⚡⚡⚡ Very Fast (~100 tokens/sec)
- **Cost**: 💰 Free/Very Low
- **Context**: 32K tokens max
- **Best for**: Quick responses, short contexts

### Gemini 1.5
- **Speed**: ⚡⚡ Fast (~50 tokens/sec)
- **Cost**: 💰💰 Moderate
- **Context**: 1M+ tokens
- **Multimodal**: ✓ Images, Video, Audio
- **Best for**: Large contexts, multimodal analysis

## Fallback Behavior

### Rate Limit Handling

When a provider hits its rate limit:

1. **Detection**: Automatic detection of rate limit errors (429, "quota exceeded", etc.)
2. **Fallback**: Transparent switch to alternative provider
3. **Logging**: Warning logged with fallback information
4. **User Impact**: Zero - the request completes successfully

Example:
```
[INFO] Using Groq as default provider
[WARNING] Rate limit hit on groq, attempting fallback
[INFO] Groq rate limit reached, falling back to Gemini
[SUCCESS] Response generated by: gemini (fallback_from: groq)
```

## Troubleshooting

### Issue: "No LLM providers available"
**Solution**: Ensure at least one API key is configured in `.env`

### Issue: "Failed to initialize tokenizer"
**Cause**: No internet connection to download tiktoken encoding
**Impact**: Token counting uses character approximation (1 token ≈ 4 chars)
**Solution**: This is a fallback mode and still works correctly

### Issue: All requests go to Gemini
**Check**: 
1. Is Groq API key configured?
2. Are payloads < 10,000 tokens?
3. Check logs for initialization errors

### Issue: Rate limit errors persist
**Solution**: 
1. Verify both API keys are configured
2. Check rate limits on both provider dashboards
3. Consider implementing request queuing for high-volume usage

## Monitoring

Enable debug logging to monitor provider selection:

```python
import logging
logging.getLogger('app.adapters.infrastructure.ai_gateway').setLevel(logging.DEBUG)
```

This will show:
- Token counts for each request
- Provider selection reasoning
- Fallback events
- Performance metrics

## Future Enhancements

Planned features for future versions:

1. **Additional Providers**
   - OpenAI GPT-4
   - Anthropic Claude
   - Local models (Ollama)

2. **Advanced Routing**
   - Quality-based routing
   - Response time optimization
   - Cost budgeting

3. **Caching**
   - Response caching for common queries
   - Reduced API calls

4. **Analytics**
   - Usage tracking
   - Cost analysis
   - Performance metrics dashboard

## License

This component is part of the Jarvis Assistant project and follows the same license.

## Contributing

Contributions are welcome! Please ensure:
1. All tests pass: `pytest tests/adapters/test_ai_gateway.py`
2. Code follows the project style
3. Add tests for new features
4. Update documentation

## Support

For issues or questions:
1. Check the troubleshooting section
2. Review test cases in `tests/adapters/test_ai_gateway.py`
3. Run the demo: `python demo_ai_gateway.py`
4. Open an issue on GitHub
