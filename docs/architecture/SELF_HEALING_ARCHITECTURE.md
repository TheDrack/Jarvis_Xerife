# Self-Healing Orchestrator Architecture

## Visão Geral

O "Self-Healing Orchestrator" é a camada de auto-evolução do Jarvis, permitindo que o sistema gerencie seu próprio ciclo de desenvolvimento, detecte falhas, e aplique correções automaticamente.

## Conceito Fundamental

Jarvis não é apenas um assistente que executa comandos - é um sistema que pode **raciocinar sobre problemas**, **tentar soluções**, e **aprender com falhas**. Quando uma tentativa falha 3 vezes, o sistema reconhece suas limitações e pede ajuda ao Comandante humano.

## Arquitetura de Camadas

```
┌─────────────────────────────────────────────────────────────────┐
│                  COMMANDER (Human Gateway)                      │
│  - Recebe alertas após 3 falhas                                 │
│  - Revisa consolidated logs                                     │
│  - Toma decisões finais                                         │
└─────────────────────────────────────────────────────────────────┘
                              ↕
                      (Escalation Trigger)
                              ↕
┌─────────────────────────────────────────────────────────────────┐
│              SELF-HEALING ORCHESTRATOR (Jarvis Brain)           │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ Dual Reasoning Layer                                     │  │
│  │  - USER_INTERACTION: Respostas visíveis ao usuário       │  │
│  │  - INTERNAL_MONOLOGUE: Raciocínio técnico interno        │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ ThoughtLog (Persistence Layer)                           │  │
│  │  - Armazena tentativas de solução                        │  │
│  │  - Conta retries automáticos                             │  │
│  │  - Gera logs consolidados                                │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ Auto-Correction Loop                                     │  │
│  │  1. Detecta falha (CI/CD)                                │  │
│  │  2. Baixa logs (gh run view --log)                       │  │
│  │  3. Analisa erro (INTERNAL_MONOLOGUE)                    │  │
│  │  4. Gera correção                                        │  │
│  │  5. Aplica patch (file_write)                            │  │
│  │  6. Commit & Push                                        │  │
│  │  7. Retry (max 3x)                                       │  │
│  │  8. Escalate se falhar 3x                                │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              ↕
┌─────────────────────────────────────────────────────────────────┐
│              DEVELOPMENT ARMS (GitHub Worker)                   │
│  - create_feature_branch()                                      │
│  - submit_pull_request()                                        │
│  - fetch_ci_status()                                            │
│  - download_ci_logs()                                           │
│  - file_write() (apply patches)                                 │
└─────────────────────────────────────────────────────────────────┘
                              ↕
┌─────────────────────────────────────────────────────────────────┐
│          EPHEMERAL EXECUTION (TaskRunner + Browser)             │
│  - TaskRunner: Cria venvs temporários                           │
│  - PersistentBrowserManager: CDP para Playwright                │
│  - Executa scripts da nuvem localmente                          │
└─────────────────────────────────────────────────────────────────┘
```

## Componentes Principais

### 1. Dual Reasoning Layer

**Objetivo**: Separar raciocínio interno de respostas ao usuário.

#### InteractionStatus Enum

```python
class InteractionStatus(str, Enum):
    USER_INTERACTION = "user_interaction"      # Visível ao usuário
    INTERNAL_MONOLOGUE = "internal_monologue"  # Apenas logs internos
```

#### System Prompts Diferenciados

- **USER_INTERACTION**: Prompt focado em clareza e comunicação
- **INTERNAL_MONOLOGUE**: Prompt 100% técnico, focado em debugging e patches

**Exemplo de Uso:**

```python
# Resposta ao usuário
assistant_service.process_command(
    "como está o build?",
    interaction_status=InteractionStatus.USER_INTERACTION
)
# → Response: "O build falhou. Estou investigando."

# Raciocínio interno
thought_log_service.create_thought(
    mission_id="fix_build_123",
    status=InteractionStatus.INTERNAL_MONOLOGUE,
    thought_process="Build failed on line 42 in test.py. ImportError: numpy. Checking requirements.txt...",
    solution_attempt="Adding numpy==1.24.0 to requirements.txt"
)
# → Armazenado em thought_logs, não mostrado ao usuário
```

### 2. ThoughtLog (Persistence Layer)

**Modelo de Dados:**

```python
class ThoughtLog(SQLModel, table=True):
    id: int
    mission_id: str              # Agrupa tentativas da mesma missão
    session_id: str              # Agrupa pensamentos na mesma sessão
    status: str                  # USER_INTERACTION ou INTERNAL_MONOLOGUE
    
    # Conteúdo
    thought_process: str         # Raciocínio técnico
    problem_description: str     # O que está sendo resolvido
    solution_attempt: str        # O que foi tentado
    
    # Tracking
    success: bool                # Sucesso/falha da tentativa
    error_message: str           # Erro se falhou
    retry_count: int             # Número da tentativa (0, 1, 2, 3...)
    
    # Escalation
    requires_human: bool         # True após 3 falhas
    escalation_reason: str       # Por que escalar
    
    # Metadata
    context_data: str            # JSON com logs, stack traces, etc.
    created_at: datetime
```

**Características:**

- **Retry Counter**: Incrementa a cada falha para a mesma `mission_id`
- **Safety Latch**: Após 3 falhas, marca `requires_human=True`
- **Consolidated Logs**: Agrupa todas as tentativas em um log único para review

### 3. Auto-Correction Loop

**Fluxo Completo:**

```python
def auto_heal_workflow(run_id: int):
    mission_id = f"ci_fix_{run_id}"
    
    # 1. Detectar falha
    ci_status = github_worker.fetch_ci_status(run_id=run_id)
    if not ci_status["failed"]:
        return "CI passou"
    
    # 2. Baixar logs
    logs = github_worker.download_ci_logs(run_id)
    
    # 3. Raciocínio interno (INTERNAL_MONOLOGUE)
    thought_log_service.create_thought(
        mission_id=mission_id,
        session_id=f"session_{run_id}",
        thought_process=f"Analyzing CI failure. Error: {parse_error(logs)}",
        problem_description="CI build failed",
        solution_attempt="Will update dependencies",
        status=InteractionStatus.INTERNAL_MONOLOGUE,
        success=False,
        error_message=logs[:500],
        context_data={"run_id": run_id, "logs": logs}
    )
    
    # 4. Verificar safety latch
    if thought_log_service.check_requires_human(mission_id):
        # Após 3 falhas, escalar
        consolidated = thought_log_service.generate_consolidated_log(mission_id)
        notify_commander(mission_id, consolidated)
        return
    
    # 5. Gerar correção (usando Gemini ou regras)
    fix = generate_fix(logs)
    
    # 6. Aplicar patch
    github_worker.file_write("requirements.txt", fix)
    
    # 7. Commit e push
    github_worker.create_feature_branch(f"auto-fix-{mission_id}")
    github_worker.submit_pull_request(
        title=f"Auto-fix: {mission_id}",
        body="Correção automática gerada pelo Jarvis"
    )
    
    # 8. Retry (novo CI run será disparado)
```

### 4. Development Arms (GitHub Worker)

**Capabilities:**

```python
class GitHubWorker:
    def create_feature_branch(branch_name: str) -> dict
    def submit_pull_request(title: str, body: str) -> dict
    def fetch_ci_status(run_id: int) -> dict
    def download_ci_logs(run_id: int) -> dict
    def file_write(path: str, content: str) -> dict
    def auto_heal_ci_failure(run_id: int, mission_id: str) -> dict
```

**Integração com GitHub CLI:**

Todos os métodos usam `gh` CLI internamente:

```bash
# Criar branch
git checkout -b feature/auto-fix
git push -u origin HEAD

# Criar PR
gh pr create --title "Auto-fix" --body "..."

# Checar CI
gh run view 12345 --json status,conclusion

# Baixar logs
gh run view 12345 --log
```

### 5. Ephemeral Execution

**TaskRunner:**

- Cria venvs temporários para cada execução
- Instala dependências on-demand
- Executa scripts Python isolados
- Suporta persistência via `keep_alive=True`

**PersistentBrowserManager:**

- Mantém instância Playwright viva
- User data dir fixo (preserva logins)
- Expõe CDP URL para conexão de scripts efêmeros
- Suporta codegen para criar novos skills

## API Response Structure

### ExecuteResponse (Atualizado)

```python
class ExecuteResponse(BaseModel):
    success: bool
    message: str
    data: Optional[Dict[str, Any]]
    error: Optional[str]
    
    # Self-Healing fields
    is_internal: bool = False              # É pensamento interno?
    thought_process: Optional[str] = None  # Raciocínio técnico
    execution_payload: Optional[ExecutionPayload] = None
```

### ExecutionPayload

```python
class ExecutionPayload(BaseModel):
    code: str                    # Python code para executar
    dependencies: List[str]      # Pacotes pip
    keep_alive: bool = False     # Persistir ambiente?
    browser_required: bool = False
```

## Safety Mechanisms

### 1. Three-Strike Rule

- **Strike 1**: Primeira falha, retry automático
- **Strike 2**: Segunda falha, retry com análise mais profunda
- **Strike 3**: Terceira falha, retry com estratégia alternativa
- **After Strike 3**: Escalate para humano com consolidated log

### 2. Human Gateway

Quando `requires_human=True`:

1. Sistema para de tentar
2. Gera consolidated log com todas as tentativas
3. Envia para `/v1/thoughts/escalations`
4. Notifica Comandante (email, Slack, etc.)
5. Aguarda intervenção manual

### 3. Consolidated Logs

Exemplo de log consolidado:

```
=== Consolidated Log for Mission: fix_ci_build_123 ===
Total Attempts: 3
Status: ESCALATED TO HUMAN

--- Attempt 1 (2024-01-01T10:00:00Z) ---
Problem: CI build failed due to ImportError
Reasoning: Checking requirements.txt for missing packages
Solution: Added numpy==1.24.0
Result: FAILED
Error: Still failing with same error

--- Attempt 2 (2024-01-01T10:15:00Z) ---
Problem: CI build failed due to ImportError
Reasoning: Version conflict detected. numpy incompatible with pandas
Solution: Updated pandas to 2.0.0
Result: FAILED
Error: Now failing with different error in scipy

--- Attempt 3 (2024-01-01T10:30:00Z) ---
Problem: CI build failed due to ImportError
Reasoning: Dependency tree is broken
Solution: Regenerated entire requirements.txt from scratch
Result: FAILED
Error: Same error persists

=== COMMANDER INTERVENTION REQUIRED ===
Reason: Auto-correction failed 3 times. Human intervention required.
```

## Use Cases

### UC1: Auto-Fix CI Failure

```python
# Webhook do GitHub Actions dispara:
POST /v1/github/ci-heal/12345?mission_id=fix_build_123

# Jarvis:
# 1. Baixa logs do run 12345
# 2. Identifica: "ImportError: No module named 'numpy'"
# 3. Cria ThoughtLog (INTERNAL_MONOLOGUE)
# 4. Adiciona numpy ao requirements.txt
# 5. Commit + Push
# 6. Se falhar novamente, retry
# 7. Se falhar 3x, escala para humano
```

### UC2: Monitoramento Contínuo

```python
# Cron job a cada 5 minutos:
GET /v1/thoughts/escalations

# Se houver escalations:
# 1. Busca consolidated log
# 2. Envia para Slack do time
# 3. Cria issue no GitHub
# 4. Aguarda resolução manual
```

### UC3: Análise Post-Mortem

```python
# Após resolver manualmente:
GET /v1/thoughts/mission/fix_build_123/consolidated

# Review:
# - O que Jarvis tentou?
# - Por que falhou?
# - Como melhorar para próxima vez?
# - Atualizar system prompt com learnings
```

## Futuras Evoluções

### 1. Learning Loop

- Armazenar soluções bem-sucedidas
- Reutilizar patterns que funcionaram
- Atualizar system prompts com conhecimento novo

### 2. Multi-Agent Collaboration

- Jarvis chama outros agents especializados
- Agent de Python, Agent de DevOps, Agent de Testes
- Colaboração via ThoughtLogs compartilhados

### 3. Proactive Monitoring

- Detectar problemas antes de falharem
- "Smell tests" em PRs
- Previsão de falhas baseada em histórico

### 4. Integration com Gemini Pro

- Análise de logs mais sofisticada
- Geração de fixes mais precisas
- Explicações melhores nos ThoughtLogs

## Conclusão

O Self-Healing Orchestrator transforma Jarvis de um simples executor de comandos em um **engenheiro autônomo** capaz de:

1. ✅ Detectar problemas
2. ✅ Analisar causas (INTERNAL_MONOLOGUE)
3. ✅ Tentar soluções
4. ✅ Aprender com falhas
5. ✅ Reconhecer limitações
6. ✅ Pedir ajuda quando necessário

É o primeiro passo para um sistema verdadeiramente auto-evolutivo.
