# Guia de uso dos multiagentes

Como colocar a fila e os workers para rodar: migrações, variáveis, execução, concorrência,
falhas e diagnóstico. O desenho da fila está em
[MULTI_AGENT_PRIORITY_QUEUE.md](MULTI_AGENT_PRIORITY_QUEUE.md); a supervisão do worker em
[multiagent-runtime.md](multiagent-runtime.md); o motor de inferência em
[FREELLMAPI_MINI_AGENTS.md](FREELLMAPI_MINI_AGENTS.md).

## Como as peças se encaixam

- **API Jarvis** (`main.py`) expõe `/v1/agents/heartbeat`, `/v1/agent-tasks`,
  `/v1/agent-tasks/claim-next`, `/v1/agent-tasks/{task_id}/finish`,
  `/v1/agent-tasks/{task_id}/release` e `/v1/routines`.
- **Fila no PostgreSQL**: as funções SQL são a fonte de verdade da atribuição
  (`FOR UPDATE SKIP LOCKED`, lease/fencing e limite de tentativas).
- **Workers**: o processo da API inicia N threads supervisionadas quando
  `JARVIS_MINI_AGENT_ENABLED=true`. Cada thread tem identidade própria, anuncia apenas
  `text_reasoning`, reivindica uma tarefa por vez e devolve o resultado ligado ao
  `attempt_id`.
- **Dois backends de fila**, escolhidos automaticamente:
  1. **Supabase nativo** quando `SUPABASE_URL` e `SUPABASE_SERVICE_ROLE_KEY` existem —
     chama as RPCs diretamente, sem senha extra de worker.
  2. **HTTP autenticado** caso contrário — usa a API com token ou usuário/senha.

## Pré-requisitos

- PostgreSQL (Supabase ou compatível). SQLite **não** serve: a API responde `503` em vez de
  fingir uma fila compartilhada.
- Migrações aplicadas no mesmo banco que a API usa.
- Uma credencial de inferência para o worker padrão (FreeLLMAPI, Groq ou Venice).
- Nenhum segredo em código: chaves e tokens ficam no ambiente do serviço.

## 1. Aplicar as migrações

Aplique nesta ordem, no banco compartilhado. Nada é aplicado automaticamente pelo app.

| Migração | O que cria |
|---|---|
| `202610230002_multi_agent_control_plane.sql` | tabelas `jarvis_agents`, `jarvis_agent_tasks`, `jarvis_agent_attempts`, `jarvis_agent_events`; `claim_jarvis_agent_task`, `finish_jarvis_agent_task` |
| `202610230003_multi_agent_message_queue.sql` | `jarvis_agent_messages` e RPCs de mensagem (usado pelo transporte entre agentes) |
| `202610230004_priority_routine_scheduler.sql` | `jarvis_routine_definitions`; `claim_next_jarvis_agent_task`, `recover_expired_jarvis_agent_tasks` |
| `20261027120000_agent_model_provider.sql` | coluna `jarvis_agents.model_provider` (heartbeat/roteamento Red/Blue) |
| `20261028090000_release_failed_task_attempt.sql` | `release_jarvis_agent_task` (devolve a tentativa falha sem esperar o lease) |

```bash
supabase link --project-ref <ref>
supabase db push
```

## 2. Variáveis de ambiente

Nomes e presença; nunca valores em log, commit ou chat.

**Opt-in (obrigatório)**

| Variável | Efeito |
|---|---|
| `JARVIS_MINI_AGENT_ENABLED=true` | sem ela o worker não inicia e a API continua normalmente |

**Backend Supabase nativo (preferido)**

| Variável | Uso |
|---|---|
| `SUPABASE_URL` | projeto da fila |
| `SUPABASE_SERVICE_ROLE_KEY` | acesso server-side; nunca no cliente |

**Backend HTTP (alternativa)**

| Variável | Uso |
|---|---|
| `JARVIS_TASK_QUEUE_API_URL` | base da API, por exemplo `https://jarvis-api-c47i.onrender.com` |
| `JARVIS_TASK_QUEUE_API_TOKEN` **ou** `JARVIS_TASK_QUEUE_USERNAME` + `JARVIS_TASK_QUEUE_PASSWORD` | autenticação; com usuário/senha o worker obtém o JWT em `/token` e renova após `401` |

**Inferência**

| Variável | Uso |
|---|---|
| `FREELLMAPI_API_KEY`, `GROQ_API_KEY` ou `VENICE_API_KEY` | uma delas; a ordem de fallback prefere Groq antes de Venice |
| `FREELLMAPI_BASE_URL`, `FREELLMAPI_MODEL`, `FREELLMAPI_TIMEOUT_SECONDS`, `FREELLMAPI_PROVIDER` | endpoint, modelo, timeout e provedor anunciado no heartbeat |

**Identidade e ritmo**

| Variável | Padrão | Limite |
|---|---|---|
| `JARVIS_AGENT_ID` | `mini-freellmapi-1` | base das identidades |
| `JARVIS_MINI_AGENT_WORKERS` | `1` | 1–8; valores inválidos são limitados e registrados |
| `JARVIS_TASK_QUEUE_LEASE_SECONDS` | `90` | 10–3600 |

## 3. Subir API e workers

```bash
python main.py
```

O processo sobe o servidor HTTP primeiro (o `/health` responde mesmo com configuração de
worker incompleta) e depois inicia as threads. Uma exceção ao iniciar o worker é registrada
e **não derruba a API**. No desligamento, o mesmo sinal para todas as threads.

Logs que confirmam o caminho escolhido:

```text
Mini-agent runtime using configured Supabase queue backend
Supervised mini-agent runtime started with 3 worker(s): mini-freellmapi-1, mini-freellmapi-2, mini-freellmapi-3
```

Se faltar configuração no caminho HTTP, o log lista **nomes** de variáveis ausentes, sem
valores.

Para rodar somente o worker (sem API), no mesmo ambiente:

```python
from app.multiagent.agent_worker_runtime import start_configured_worker

runtime = start_configured_worker()   # None quando o opt-in está desligado
if runtime is not None:
    group, stop = runtime
    try:
        group.join()
    finally:
        stop.set()
```

## 4. Enfileirar trabalho

```bash
TOKEN="<jwt>"
curl -s -X POST "$JARVIS_TASK_QUEUE_API_URL/v1/agent-tasks" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{
    "task_id": "resumo-2026-10-28",
    "objective": "Resumir o contexto fornecido em 5 tópicos",
    "priority": 60,
    "task_type": "research",
    "required_tools": ["text_reasoning"],
    "acceptance_criteria": ["cinco tópicos", "sem fontes inventadas"],
    "max_attempts": 3,
    "idempotency_key": "resumo-2026-10-28"
  }'
```

- `required_tools` precisa ser subconjunto do que o agente anuncia (`text_reasoning`).
  Tarefas com shell, navegador, repositório ou diagnóstico **não** são reivindicáveis por
  este worker — elas exigem outro runtime registrado.
- `idempotency_key` evita duplicar a mesma demanda em disparos repetidos.
- Tarefa filha só fica elegível quando a mãe termina em `completed`.

## 5. Acompanhar

Consultas somente leitura no banco da fila:

```sql
-- distribuição atual da fila
select status, count(*) from public.jarvis_agent_tasks group by status order by 2 desc;

-- quem está vivo e qual provedor anuncia
select agent_id, status, active_tasks, concurrency_limit, model_provider, last_seen_at
from public.jarvis_agents order by last_seen_at desc;

-- últimas tentativas e por que falharam
select task_id, attempt_no, agent_id, status, left(coalesce(error_summary,''), 120) as erro, finished_at
from public.jarvis_agent_attempts order by started_at desc limit 20;

-- trilha de auditoria da tarefa
select event_type, actor_id, created_at from public.jarvis_agent_events
where task_id = '<task_id>' order by created_at;
```

## 6. Falhas, release e lease

1. O handler levanta exceção (provedor caiu, timeout, resposta inválida).
2. O worker chama o **release** imediatamente: RPC `release_jarvis_agent_task` no backend
   nativo, `POST /v1/agent-tasks/{task_id}/release` no HTTP.
3. O banco marca a tentativa como `failed`, incrementa `attempts` e devolve a tarefa a
   `ready`; se `attempts >= max_attempts`, encerra em `failed`.
4. O worker relança a exceção original e o loop aplica backoff exponencial (1 s → 30 s).

O release só aceita a tentativa dona atual (tarefa + agente + `attempt_id`). Tentativa
obsoleta ou de outro agente retorna recusa — no HTTP, `409`; nesse caso quem resolve é o
lease. Se o próprio release não puder ser registrado, o worker registra um alerta e segue:
o lease de 90 s continua como rede de segurança.

Conclusão nunca é fabricada: a tarefa só vira `completed` quando o modelo devolve
`success` e o `finish` aceita o `attempt_id` corrente.

## 7. Concorrência

`JARVIS_MINI_AGENT_WORKERS=3` abre três slots **com identidades distintas**
(`mini-freellmapi-1..3`). Identidades iguais serializariam, porque cada agente mantém uma
tarefa em voo com `concurrency_limit = 1`. A reivindicação é atômica no banco: a mesma
tarefa não é entregue a dois workers, e um worker antigo não consegue concluir depois que o
lease foi recuperado. Os slots são threads do mesmo processo — não há autoscaling.

## 8. Diagnóstico

```powershell
# presença de variáveis, grupos satisfeitos e (com --probe) saúde da API
.\.venv\Scripts\python.exe scripts\check_multiagent_env.py --probe --api-url https://<api>

# suíte do runtime, da fila e da API
.\.venv\Scripts\python.exe -m pytest tests/multiagent tests/application/test_agent_task_queue_service.py -q
```

| Sintoma | Causa provável | Ação |
|---|---|---|
| `503` em qualquer rota da fila | `DATABASE_URL`/`JARVIS_TASK_QUEUE_DATABASE_URL` não aponta para PostgreSQL | configurar o banco compartilhado |
| `401`/`403` | token expirado, usuário/senha inválidos ou service role ausente | renovar credencial no ambiente |
| Tarefa nunca é reivindicada | `required_tools` fora de `text_reasoning`, agente offline, mãe não concluída ou tentativas esgotadas | conferir `jarvis_agent_tasks` e `jarvis_agents` |
| Tarefa presa em `in_progress` | worker morreu antes do release | o lease recupera; não edite o status à mão |
| `409` no release | tentativa obsoleta, já recuperada pelo lease | tratar como esperado e não reenviar |
| Worker não sobe | opt-in desligado ou configuração incompleta | ver o log de inicialização |

## 9. Limites e segurança

- O worker padrão é **text-only**: não executa shell, navegador, arquivos nem ações
  externas, e não pode afirmar que usou ferramentas sem evidência no payload.
- Tarefas de auditoria, otimização ou produção exigem um runtime com as ferramentas
  correspondentes e credenciais de menor privilégio.
- `SUPABASE_SERVICE_ROLE_KEY` e chaves de provedor ficam apenas no servidor; tokens JWT de
  worker expiram e devem ser renovados pelo fluxo usuário/senha.
- A fila não instala cron: `schedule` em `/v1/routines` é metadado declarativo; a demanda só
  nasce quando o endpoint de trigger é chamado com um `run_key` estável.
