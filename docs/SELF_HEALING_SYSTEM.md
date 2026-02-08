# Jarvis Self-Healing System Documentation

## Visão Geral

O sistema de auto-correção (self-healing) do Jarvis permite que o assistente detecte erros críticos em produção, formule correções automaticamente e as envie para validação via GitHub Actions, sem intervenção manual.

## Arquitetura

```
┌─────────────────────────────────────────────────────────────┐
│                   Jarvis em Produção (Render)               │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  Gateway LLM Adapter                                 │  │
│  │  - Detecta erros críticos                            │  │
│  │  - Formular plano de correção usando Gemini         │  │
│  └──────────────────────────────────────────────────────┘  │
│                          │                                  │
│                          ▼                                  │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  GitHub Adapter                                      │  │
│  │  - Envia repository_dispatch event                  │  │
│  │  - Payload: issue_title, file_path, fix_code        │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                          │
                          │ HTTPS API Call
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                     GitHub Actions                          │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  jarvis_code_fixer.yml Workflow                      │  │
│  │  1. Checkout code                                    │  │
│  │  2. Create new branch                                │  │
│  │  3. Apply fix_code to file_path                      │  │
│  │  4. Run tests (pytest)                               │  │
│  │  5. If tests pass → Create Pull Request             │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                  Pull Request Criado                        │
│  - Review automático do código                              │
│  - Testes passaram ✅                                       │
│  - Aguarda aprovação humana                                 │
└─────────────────────────────────────────────────────────────┘
```

## Componentes

### 1. GitHub Actions Workflow (`.github/workflows/jarvis_code_fixer.yml`)

**Trigger:** `repository_dispatch` com `event_type: auto_fix`

**Payload esperado:**
```json
{
  "issue_title": "Fix model_decommissioned error",
  "file_path": "app/adapters/infrastructure/gemini_adapter.py",
  "fix_code": "base64_encoded_file_content",
  "test_command": "pytest tests/adapters/ -k gemini -v"
}
```

**Fluxo:**
1. Checkout do código
2. Criação de branch `jarvis/auto-fix-{issue_title}`
3. Aplicação do código corrigido
4. Instalação de dependências
5. Execução dos testes
6. Se sucesso: Commit + Push + Pull Request

**Segurança:**
- Usa `GITHUB_TOKEN` secreto automático
- Sanitiza nome do branch
- Valida existência do arquivo antes de aplicar fix
- Executa testes antes de criar PR

### 2. GitHub Adapter (`app/adapters/infrastructure/github_adapter.py`)

**Classe:** `GitHubAdapter`

**Métodos principais:**

#### `dispatch_auto_fix(issue_data: Dict[str, Any]) -> Dict[str, Any]`

Envia um evento `repository_dispatch` para disparar o workflow.

**Exemplo de uso:**
```python
from app.adapters.infrastructure.github_adapter import GitHubAdapter

adapter = GitHubAdapter()

issue_data = {
    "issue_title": "Fix deprecated model",
    "file_path": "app/adapters/infrastructure/gemini_adapter.py",
    "fix_code": "# Código corrigido aqui",
    "test_command": "pytest tests/adapters/"
}

result = await adapter.dispatch_auto_fix(issue_data)

if result["success"]:
    print(f"Workflow triggered: {result['workflow_url']}")
else:
    print(f"Error: {result['error']}")
```

**Autenticação:**
- Usa `GITHUB_TOKEN` da variável de ambiente
- Fallback para repositório padrão se não configurado

**Recursos:**
- Base64 encoding automático do código para evitar problemas com JSON
- Validação de campos obrigatórios
- Tratamento de erros robusto
- Suporte a async/await

### 3. Integração com Gateway LLM Adapter

**Localização:** `app/adapters/infrastructure/gateway_llm_adapter.py`

**Detecção de Erros Críticos:**

O método `_handle_critical_error()` detecta:
- `model_decommissioned` / `model has been decommissioned`
- `model not found`
- `test fail`
- `quota exceeded`
- `rate limit` (exceto Groq, que é tratado pelo gateway)
- `authentication failed`
- `api key invalid`

**Fluxo de Auto-Correção:**

1. **Erro capturado** no `except` block de `generate_conversational_response()`
2. **Verifica se é crítico** usando padrões de erro
3. **Formular plano de correção:**
   - Envia prompt diagnóstico para Gemini
   - Gemini analisa o erro e sugere correção
   - Sistema parseia resposta e cria fix_plan
4. **Dispara GitHub Actions:**
   - Chama `github_adapter.dispatch_auto_fix()`
   - Workflow executa correção
   - PR é criado automaticamente

**Exemplo de prompt diagnóstico:**
```
ERRO CRÍTICO DETECTADO EM PRODUÇÃO

Tipo de Erro: ModelDecommissionedError
Mensagem: model has been decommissioned
Input do Usuário: analise estes logs

Contexto: O Jarvis está rodando no Render e detectou este erro crítico.

TAREFA: Analise o erro e determine se é possível formular uma correção automática.
```

## Configuração

### Variáveis de Ambiente Necessárias

```bash
# Token do GitHub (gerado automaticamente em Actions)
GITHUB_TOKEN=ghp_xxxxxxxxxxxx

# Repositório (formato: owner/repo)
GITHUB_REPOSITORY=TheDrack/python

# OU separadamente:
GITHUB_REPOSITORY_OWNER=TheDrack
GITHUB_REPOSITORY_NAME=python

# Chaves de API para LLMs
GOOGLE_API_KEY=your_gemini_key
GROQ_API_KEY=your_groq_key
```

### Permissões do GitHub Token

O `GITHUB_TOKEN` precisa ter as seguintes permissões:

- ✅ **Contents:** write (para criar branches e commits)
- ✅ **Pull Requests:** write (para criar PRs)
- ✅ **Workflows:** write (para disparar repository_dispatch)

**Configuração no repositório:**
1. Settings → Actions → General
2. Workflow permissions → "Read and write permissions"
3. "Allow GitHub Actions to create and approve pull requests" → ✅

## Exemplos de Uso

### Exemplo 1: Erro de Modelo Depreciado

```python
# Erro detectado automaticamente durante execução
try:
    response = await self.gateway.generate_completion(messages)
except Exception as e:
    # e.g., "model has been decommissioned"
    # Sistema detecta automaticamente e:
    # 1. Identifica arquivo: gemini_adapter.py
    # 2. Atualiza model_name de "gemini-flash-latest" para "gemini-2.0-flash-exp"
    # 3. Cria PR com a correção
```

**Resultado:**
- Branch: `jarvis/auto-fix-model-decommissioned-error`
- Arquivo modificado: `app/adapters/infrastructure/gemini_adapter.py`
- PR criado com label `auto-fix` e `jarvis`

### Exemplo 2: Manual Dispatch (para testes)

```bash
# Usando GitHub CLI
gh api repos/TheDrack/python/dispatches \
  -f event_type=auto_fix \
  -F client_payload[issue_title]='Test fix' \
  -F client_payload[file_path]='app/test.py' \
  -F client_payload[fix_code]='cHJpbnQoImZpeGVkIikK' \
  -F client_payload[test_command]='pytest tests/'
```

## Testes

### Executar testes localmente

```bash
# Instalar dependências
pip install pytest pytest-asyncio httpx mock

# Rodar testes do GitHub Adapter
pytest tests/adapters/infrastructure/test_github_adapter.py -v

# Rodar testes da integração de self-healing
pytest tests/adapters/infrastructure/test_gateway_llm_self_healing.py -v
```

**Cobertura de testes:**
- 14 testes para GitHub Adapter (100% passing)
- 10 testes para integração de self-healing (100% passing)

### Testes incluídos:

**GitHub Adapter:**
- ✅ Inicialização com/sem token
- ✅ Geração de headers de autenticação
- ✅ Dispatch de auto-fix bem-sucedido
- ✅ Validação de campos obrigatórios
- ✅ Tratamento de erros da API
- ✅ Base64 encoding do código
- ✅ Gerenciamento de cliente HTTP

**Self-Healing:**
- ✅ Detecção de erros críticos
- ✅ Ignorar erros não-críticos
- ✅ Formulação de plano de correção
- ✅ Parsing de resposta do Gemini
- ✅ Integração com workflow de erro
- ✅ Logging de falhas

## Limitações e Considerações

### Limitações Atuais

1. **Parsing Simplificado:** A extração do plano de correção da resposta do Gemini usa heurísticas simples. Para produção, considere usar respostas estruturadas (JSON).

2. **Tipos de Erro Suportados:** Atualmente focado em:
   - Model deprecation/decommissioning
   - Para outros erros, o sistema logará mas pode não gerar correção

3. **Escopo de Correção:** Correções são limitadas a alterações em um único arquivo por vez.

4. **Rate Limits:** Sem throttling implementado - muitos erros simultâneos podem resultar em múltiplos dispatches.

### Melhorias Futuras

- [ ] Usar JSON structured output do Gemini para parsing robusto
- [ ] Implementar queue de correções para evitar duplicatas
- [ ] Adicionar métricas e monitoring (Prometheus/Grafana)
- [ ] Suporte a correções multi-arquivo
- [ ] Integração com sistema de rollback automático
- [ ] Learning loop: análise de PRs aceitos/rejeitados

## Segurança

### Validações Implementadas

1. **Sanitização de entrada:** Nomes de branch são sanitizados para remover caracteres especiais
2. **Validação de arquivo:** Workflow verifica existência do arquivo antes de aplicar fix
3. **Testes obrigatórios:** PR só é criado se todos os testes passarem
4. **Review humano:** PRs aguardam aprovação antes do merge
5. **Isolamento:** Cada correção é feita em branch separado

### Boas Práticas

- ✅ Nunca commit direto na `main`
- ✅ Sempre executar testes antes de criar PR
- ✅ Logs detalhados de todas as operações
- ✅ Token com permissões mínimas necessárias
- ✅ Base64 encoding para evitar injection

## Troubleshooting

### Workflow não dispara

**Problema:** `dispatch_auto_fix` retorna sucesso mas workflow não executa.

**Soluções:**
1. Verificar permissões do GITHUB_TOKEN
2. Confirmar que workflow está na branch `main`
3. Verificar logs em Actions → All workflows

### Testes falhando no CI

**Problema:** Testes passam localmente mas falham no CI.

**Soluções:**
1. Verificar versões de dependências no workflow
2. Confirmar variáveis de ambiente necessárias
3. Revisar logs do pytest no Actions

### PR não é criado

**Problema:** Workflow executa mas PR não aparece.

**Soluções:**
1. Verificar se testes passaram (step "Run Tests")
2. Confirmar que há mudanças para commit
3. Verificar permissões de PR write

### Erro de autenticação

**Problema:** `GITHUB_TOKEN not configured`.

**Soluções:**
1. Definir `GITHUB_TOKEN` como variável de ambiente
2. Para Render: Settings → Environment → Add GITHUB_TOKEN
3. Verificar que token tem scopes corretos

## Monitoramento

### Logs importantes

```python
# Logs de detecção de erro crítico
logger.warning(f"🔧 Critical error detected: {error_type} - {error}")

# Logs de dispatch
logger.info(f"Dispatching auto-fix for '{issue_title}' to {owner}/{repo}")

# Logs de sucesso
logger.info(f"✅ Auto-fix dispatched successfully: {workflow_url}")

# Logs de falha
logger.error(f"❌ Failed to dispatch auto-fix: {error}")
```

### Métricas recomendadas

- Número de erros críticos detectados por dia
- Taxa de sucesso de auto-fixes (PRs criados vs merged)
- Tempo médio entre erro e PR criado
- Tipos de erro mais comuns

## Contribuindo

Para adicionar suporte a novos tipos de erro:

1. Adicionar padrão de detecção em `_handle_critical_error()`
2. Implementar lógica de fix em `_parse_fix_plan_from_response()`
3. Adicionar testes em `test_gateway_llm_self_healing.py`
4. Documentar o novo tipo de erro neste README

---

**Documentação gerada para:** Jarvis Self-Healing System v1.0
**Última atualização:** 2026-02-08
