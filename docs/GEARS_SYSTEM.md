# Sistema de Marchas (Gears System) - Jarvis AI Gateway

## Visão Geral

O Jarvis AI Gateway agora implementa um sistema inteligente de "marchas" que otimiza custos, desempenho e resiliência ao usar múltiplos modelos de IA de forma automática.

## Arquitetura de Marchas

### 🏎️ Marcha Alta (High Gear)
- **Modelo Padrão**: `llama-3.3-70b-versatile` (Groq)
- **Alternativa**: `llama-4-scout` (quando disponível)
- **Uso**: Processamento padrão, rápido e eficiente
- **Características**:
  - Alto desempenho
  - Bom custo-benefício
  - Utilizado por padrão para todas as requisições

### ⚙️ Marcha Baixa (Low Gear)
- **Modelo Padrão**: `llama-3.1-8b-instant` (Groq)
- **Alternativa**: `qwen-3-32b`
- **Uso**: Fallback interno quando a Marcha Alta atinge rate limit
- **Características**:
  - Mais econômico
  - Menor latência
  - Ativado automaticamente em situações de rate limit
  - Sistema retorna automaticamente para Marcha Alta após recuperação

### 🚀 Tiro de Canhão (Cannon Shot)
- **Modelo**: `gemini-1.5-pro` (Google Gemini)
- **Uso**: Fallback externo quando todo o provedor Groq falha
- **Características**:
  - Maior capacidade de contexto (até 2M tokens)
  - Suporte multimodal (imagens, vídeo)
  - Usado apenas quando Groq está completamente indisponível

## Fluxo de Operação

```
Requisição → Marcha Alta (Groq Llama-3.3-70b)
    ↓ (Rate Limit)
    → Marcha Baixa (Groq Llama-3.1-8b)
        ↓ (Rate Limit ou Falha Total)
        → Tiro de Canhão (Gemini-1.5-Pro)
```

## Configuração

### Variáveis de Ambiente

```bash
# Marcha Alta (High Gear) - Modelo principal
GROQ_MODEL=llama-3.3-70b-versatile

# Marcha Baixa (Low Gear) - Fallback interno (opcional)
GROQ_LOW_GEAR_MODEL=llama-3.1-8b-instant

# Tiro de Canhão (Cannon Shot) - Fallback externo
GEMINI_MODEL=gemini-1.5-pro

# API Keys
GROQ_API_KEY=your_groq_api_key
GOOGLE_API_KEY=your_google_api_key
```

### Uso no Código

```python
from app.adapters.infrastructure.ai_gateway import AIGateway

# Inicialização básica (usa configuração padrão)
gateway = AIGateway(
    groq_api_key="your_key",
    gemini_api_key="your_key"
)

# Inicialização customizada
gateway = AIGateway(
    groq_api_key="your_key",
    gemini_api_key="your_key",
    groq_high_gear_model="llama-3.3-70b-versatile",
    groq_low_gear_model="llama-3.1-8b-instant",
    gemini_model="gemini-1.5-pro",
    enable_auto_repair=True  # Ativa auto-reparo
)

# Gerar completion
messages = [
    {"role": "user", "content": "Olá, como você está?"}
]

response = await gateway.generate_completion(messages)
print(f"Resposta de: {response['provider']}")
print(f"Modelo usado: {response['model']}")
print(f"Marcha: {response.get('gear', 'N/A')}")
```

## Sistema de Auto-Reparo

O AI Gateway agora inclui um sistema de auto-reparo que:

1. **Captura erros críticos** com traceback completo
2. **Identifica erros que podem ser corrigidos** automaticamente
3. **Envia para GitHub Actions** para correção automática

### Tipos de Erros Detectados

- **Erros de Autenticação**: 401, 403, unauthorized
- **Erros de Sintaxe**: SyntaxError, IndentationError
- **Erros de Importação**: ImportError, ModuleNotFoundError
- **Erros de Tipo**: AttributeError, TypeError, NameError

### Configuração do Auto-Reparo

```python
from app.adapters.infrastructure.ai_gateway import AIGateway
from app.adapters.infrastructure.github_adapter import GitHubAdapter

# Criar GitHub adapter para auto-reparo
github_adapter = GitHubAdapter(
    token=os.getenv("GITHUB_TOKEN")
)

# Inicializar gateway com auto-reparo
gateway = AIGateway(
    groq_api_key="your_key",
    gemini_api_key="your_key",
    enable_auto_repair=True,
    github_adapter=github_adapter
)
```

## Testes

### Executar Testes Unitários

```bash
# Testar o sistema de marchas
pytest tests/adapters/test_ai_gateway_gears.py -v

# Testar compatibilidade com testes existentes
pytest tests/adapters/test_ai_gateway.py -v

# Testar todos os componentes do AI Gateway
pytest tests/adapters/test_ai_gateway*.py -v
```

### Teste de Fogo (Fire Test)

Validar o sistema de auto-reparo:

```bash
# Testar erro de importação
python test_auto_repair.py --error-type import

# Testar erro de sintaxe
python test_auto_repair.py --error-type syntax

# Testar vírgula faltando
python test_auto_repair.py --error-type missing-comma

# Testar todos os tipos de erro
python test_auto_repair.py --error-type all
```

## Benefícios

### 🎯 Resiliência
- Múltiplas camadas de fallback garantem disponibilidade contínua
- Sistema auto-ajustável que se recupera automaticamente de rate limits

### 💰 Otimização de Custos
- Usa modelos menores (Low Gear) quando necessário
- Minimiza uso do Gemini (mais caro) apenas quando essencial

### ⚡ Performance
- Marcha Baixa oferece respostas mais rápidas em situações de alta demanda
- Troca automática entre marchas sem intervenção manual

### 🔧 Auto-Healing
- Detecta e corrige erros críticos automaticamente
- Reduz tempo de downtime e necessidade de intervenção manual

## Monitoramento

### Logs de Marchas

O sistema registra todas as trocas de marcha:

```
INFO - AI Gateway initialized with Gears System:
  - High Gear (Marcha Alta): llama-3.3-70b-versatile
  - Low Gear (Marcha Baixa): llama-3.1-8b-instant
  - Cannon Shot (Tiro de Canhão): gemini-1.5-pro
  - Default provider: groq
  - Groq available: True
  - Gemini available: True
  - Auto-repair: True

WARNING - 🔧 Shifting to Low Gear (Marcha Baixa): llama-3.1-8b-instant
INFO - ✅ Shifting back to High Gear (Marcha Alta): llama-3.3-70b-versatile
WARNING - 🚀 Firing Cannon Shot (Tiro de Canhão): Gemini
```

### Métricas Recomendadas

Monitore:
- Taxa de uso de cada marcha
- Frequência de fallbacks para Gemini
- Taxa de sucesso do auto-reparo
- Tempo médio de resposta por marcha

## Compatibilidade

O sistema mantém **100% de compatibilidade** com código existente:

```python
# Código antigo continua funcionando
gateway = AIGateway(
    groq_api_key="key",
    gemini_api_key="key",
    groq_model="llama-3.3-70b-versatile"  # Deprecated, mas ainda funciona
)

# O parâmetro groq_model é automaticamente convertido para groq_high_gear_model
assert gateway.groq_model == "llama-3.3-70b-versatile"
```

## Roadmap

Próximas melhorias planejadas:

- [ ] Métricas automáticas de custo por marcha
- [ ] Dashboard de monitoramento em tempo real
- [ ] Machine learning para prever quando mudar de marcha
- [ ] Suporte a mais modelos (OpenAI, Anthropic, etc.)
- [ ] Auto-tuning de thresholds de token
- [ ] Análise preditiva de rate limits

## Contribuindo

Para contribuir com melhorias no sistema de marchas:

1. Fork o repositório
2. Crie uma branch para sua feature
3. Adicione testes para novas funcionalidades
4. Execute todos os testes: `pytest tests/ -v`
5. Submeta um Pull Request

## Suporte

Para problemas ou dúvidas:
- Abra uma issue no GitHub
- Consulte a documentação em `docs/`
- Entre em contato com @TheDrack

---

**Versão**: 1.0.0  
**Última Atualização**: 2026-02-08  
**Autor**: TheDrack com assistência do GitHub Copilot
