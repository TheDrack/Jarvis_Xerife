# Jarvis AI Integration - Arquitetura Multi-LLM

## 🎯 Visão Geral

Jarvis utiliza uma arquitetura multi-LLM inteligente que combina diferentes modelos de IA para otimizar performance, custo e confiabilidade. O sistema prioriza **Jarvis (Groq/Llama)** como LLM principal e usa **Gemini** apenas como fallback.

## 🤖 Por que "Jarvis" e não "Gemini"?

### Jarvis = Groq (Llama Models)
- **Modelo principal**: Llama-3.3-70b-versatile via Groq
- **Características**:
  - ⚡ Extremamente rápido (infraestrutura otimizada Groq)
  - 💰 Muito econômico (free tier generoso)
  - 🎯 Excelente para comandos de voz e automação
  - 🔄 Auto-recuperação de rate limits

### Gemini = Fallback Externo
- **Uso**: Apenas quando Groq está completamente indisponível
- **Características**:
  - 📚 Maior contexto (2M tokens)
  - 🎨 Suporte multimodal
  - 💡 Melhor raciocínio complexo
  - 💵 Mais caro (usado apenas em emergências)

## 🏎️ Sistema de Marchas (Gears)

### 1. Marcha Alta (High Gear) - PADRÃO
```
Modelo: llama-3.3-70b-versatile (Groq)
Uso: 95% das requisições
Performance: Excelente
Custo: Muito baixo
```

### 2. Marcha Baixa (Low Gear) - Fallback Interno
```
Modelo: llama-3.1-8b-instant (Groq)
Uso: Quando High Gear atinge rate limit
Performance: Boa
Custo: Muito baixo
```

### 3. Tiro de Canhão (Cannon Shot) - Fallback Externo
```
Modelo: gemini-1.5-pro (Google)
Uso: Quando Groq está completamente indisponível
Performance: Excelente
Custo: Médio/Alto
```

## 📋 Configuração Recomendada

### Opção 1: Apenas Jarvis (Groq) - Recomendada

```bash
# .env
GROQ_API_KEY=gsk_xxxxxxxxxxxxxxxxxxxxx
GROQ_MODEL=llama-3.3-70b-versatile
GROQ_LOW_GEAR_MODEL=llama-3.1-8b-instant
```

**Vantagens**:
- ✅ Gratuito (free tier generoso)
- ✅ Muito rápido
- ✅ Suficiente para 99% dos casos
- ✅ Auto-recuperação de rate limits

**Limitações**:
- ⚠️ Sem fallback se Groq ficar offline
- ⚠️ Rate limits (mas muito altos no free tier)

### Opção 2: Jarvis + Gemini (Híbrido) - Mais Robusto

```bash
# .env
GROQ_API_KEY=gsk_xxxxxxxxxxxxxxxxxxxxx
GOOGLE_API_KEY=AIza-xxxxxxxxxxxxxxxxxxxxx
GROQ_MODEL=llama-3.3-70b-versatile
GROQ_LOW_GEAR_MODEL=llama-3.1-8b-instant
GEMINI_MODEL=gemini-1.5-flash  # ou gemini-1.5-pro
```

**Vantagens**:
- ✅ Máxima confiabilidade
- ✅ Fallback automático
- ✅ Melhor para ambientes de produção

**Considerações**:
- 💵 Gemini tem custos após o free tier
- 🔄 Usado apenas em emergências

### Opção 3: Apenas Gemini (Não Recomendado)

```bash
# .env
GOOGLE_API_KEY=AIza-xxxxxxxxxxxxxxxxxxxxx
GEMINI_MODEL=gemini-1.5-flash
```

**Por que não recomendamos**:
- ❌ Mais caro que Groq
- ❌ Mais lento para comandos simples
- ❌ Sem sistema de marchas

## 🔄 Fluxo de Decisão Automático

```
┌─────────────────────────────────────┐
│  Usuário: "Jarvis, abra o Chrome"  │
└──────────────┬──────────────────────┘
               │
               v
       ┌───────────────┐
       │ AI Gateway    │
       └───────┬───────┘
               │
               v
       ┌───────────────────────┐
       │ Tentativa 1:          │
       │ High Gear (Llama-3.3) │ ← Usado em 95% dos casos
       └───────┬───────────────┘
               │
               │ Rate Limit?
               v
       ┌───────────────────────┐
       │ Tentativa 2:          │
       │ Low Gear (Llama-3.1)  │ ← Usado em 4% dos casos
       └───────┬───────────────┘
               │
               │ Groq offline?
               v
       ┌───────────────────────┐
       │ Tentativa 3:          │
       │ Cannon Shot (Gemini)  │ ← Usado em <1% dos casos
       └───────┬───────────────┘
               │
               v
       ┌───────────────┐
       │ Resposta      │
       └───────────────┘
```

## 🎓 Como Funciona na Prática

### Exemplo 1: Comando Normal
```
Usuário: "Jarvis, escreva 'olá mundo'"
├─ AI Gateway recebe comando
├─ ✅ High Gear (Llama-3.3) responde em 0.8s
└─ Comando executado
```

### Exemplo 2: Rate Limit
```
Usuário: "Jarvis, abra 10 programas"
├─ AI Gateway recebe comando
├─ High Gear (Llama-3.3) → Rate Limit (429)
├─ ✅ Low Gear (Llama-3.1) responde em 0.5s
└─ Comando executado
```

### Exemplo 3: Groq Offline (Raro)
```
Usuário: "Jarvis, faça uma pesquisa"
├─ AI Gateway recebe comando
├─ High Gear → Groq offline (503)
├─ Low Gear → Groq offline (503)
├─ ✅ Cannon Shot (Gemini) responde em 1.2s
└─ Comando executado
```

## 🚀 Obtendo as API Keys

### Groq (Jarvis) - GRÁTIS
1. Acesse: https://console.groq.com
2. Crie uma conta (GitHub/Google)
3. Vá em "API Keys"
4. Clique "Create API Key"
5. Copie a chave: `gsk_...`
6. Cole no `.env`: `GROQ_API_KEY=gsk_...`

**Free Tier**:
- 14,400 requests/dia
- 30 requests/minuto
- Mais que suficiente para uso pessoal

### Google Gemini (Fallback) - OPCIONAL
1. Acesse: https://aistudio.google.com/app/apikey
2. Faça login com Google
3. Clique "Get API Key"
4. Copie a chave: `AIza...`
5. Cole no `.env`: `GOOGLE_API_KEY=AIza...`

**Free Tier**:
- 60 requests/minuto
- 1,500 requests/dia
- Suficiente para fallback

## ⚙️ Configuração no Setup Wizard

Quando você executar `python main.py`, o Setup Wizard perguntará:

```
🤖 Configuração de IA

Jarvis pode usar dois provedores de IA:
1. Groq (Llama) - Recomendado, gratuito, rápido
2. Google Gemini - Fallback opcional

Você tem chave API do Groq? (recomendado) [y/N]:
```

**Responda**:
- `y` → Cole a chave do Groq (prefira esta opção)
- `N` → Vai pedir Gemini como fallback

## 🔍 Verificando qual LLM está sendo usado

### Via Logs
```python
# Os logs mostram qual modelo foi usado
logger.info(f"✓ Response from {provider} using {model}")

# Exemplo de saída:
# ✓ Response from groq using llama-3.3-70b-versatile
```

### Via API Response
```python
response = await ai_gateway.generate_completion(messages)
print(f"Provider: {response['provider']}")  # "groq" ou "gemini"
print(f"Model: {response['model']}")        # nome do modelo
print(f"Gear: {response.get('gear')}")      # "high", "low", ou "cannon"
```

## 🎯 Decisão: Usar Jarvis (Groq) ou Gemini?

### Use APENAS Groq (Jarvis) se:
- ✅ Você quer gratuito
- ✅ Você quer rápido
- ✅ Comandos de voz e automação são o foco
- ✅ Você está OK com downtime ocasional do provedor

### Use Groq + Gemini (Híbrido) se:
- ✅ Você precisa de máxima confiabilidade
- ✅ Você está em produção
- ✅ Downtime não é aceitável
- ✅ Você pode pagar pelo Gemini (após free tier)

### Use APENAS Gemini se:
- ⚠️ Groq está bloqueado na sua região
- ⚠️ Você precisa de contexto massivo (>128k tokens)
- ⚠️ Você precisa de multimodalidade (imagens/vídeo)

## 📚 Documentação Adicional

- [Sistema de Marchas Completo](./GEARS_SYSTEM.md)
- [AI Gateway Architecture](./AI_GATEWAY.md)
- [LLM Integration Guide](../api/LLM_INTEGRATION.md)

## 💡 Resumo

> **Jarvis usa Groq (Llama) por padrão e Gemini apenas como fallback.**
>
> Para uso pessoal, GROQ_API_KEY é suficiente. Para produção, configure ambas as chaves para máxima confiabilidade.

---

*Última atualização: 2026-02-10*
*Mantido pela Equipe Jarvis*
