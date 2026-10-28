# Fila dinâmica de tarefas multiagente

## Objetivo

Rotinas liberam demandas no banco; agentes elegíveis reivindicam a tarefa pendente de maior prioridade disponível. Não existe mapeamento fixo de função por IA.

## Componentes

- `jarvis_routine_definitions`: agenda declarativa, prioridade padrão e template da tarefa.
- `jarvis_agent_tasks`: fila de trabalho, prioridade (0–1000), dependência, ferramentas necessárias, chave de idempotência e limite de tentativas.
- `jarvis_agents`: heartbeat, ferramentas, disponibilidade, concorrência e estimativa de custo.
- `jarvis_agent_attempts` / `jarvis_agent_events`: tentativas e trilha de auditoria.
- `claim_next_jarvis_agent_task`: reivindicação atômica com ordenação por prioridade, antiguidade e ID; usa `FOR UPDATE SKIP LOCKED`.
- `recover_expired_jarvis_agent_tasks`: recupera leases vencidos e encerra tarefas que esgotaram as tentativas.
- `release_jarvis_agent_task`: devolve a tarefa ao `ready` assim que o worker atual falha, sem esperar o lease; encerra em `failed` quando as tentativas acabam e recusa tentativas obsoletas ou de outro agente.

## API autenticada

- `POST /v1/agents/heartbeat`
- `POST /v1/agent-tasks`
- `POST /v1/agent-tasks/claim-next`
- `POST /v1/agent-tasks/{task_id}/finish`
- `POST /v1/routines` (cria/atualiza definição; não executa agendador por si só)

Todas as rotas usam a dependência de autenticação existente. A fila requer PostgreSQL; SQLite retorna HTTP 503 em vez de fingir que a fila compartilhada está disponível.

## Semântica e limites

- A reivindicação é serializada no banco; duas IAs não recebem a mesma tarefa simultaneamente.
- O lease/fencing token protege contra conclusão tardia de um worker antigo.
- A chave de idempotência impede que um disparo repetido crie a mesma tarefa novamente.
- Tarefas filhas só ficam elegíveis quando a tarefa-pai termina em `completed`.
- Agendamentos nativos de ChatGPT/Claude continuam independentes; esta API não cria nem controla esses agendamentos.
- A migração não é aplicada automaticamente. Revise o SQL e confirme o projeto Supabase antes de aplicá-la.
- A API usa a conexão PostgreSQL configurada no serviço. Para que ela acesse a mesma fila compartilhada, `DATABASE_URL` deve apontar para o banco que recebeu as migrações.

## Pesquisa aplicada

O desenho reutiliza o padrão PostgreSQL `FOR UPDATE SKIP LOCKED` recomendado para múltiplos consumidores e os conceitos de leases/visibilidade do PGMQ. PGMQ pode ser uma evolução para entrega de mensagens; para esta primeira versão, as tabelas de tarefas existentes no control plane já oferecem histórico de tentativas, dependências e resultados sem manter duas filas concorrentes.

## Fluxo para agendamentos nativos

1. Cadastre/atualize uma rotina com `POST /v1/routines`, incluindo `schedule` e `task_template.objective`.
2. Quando o agendamento nativo de ChatGPT, Claude ou outro agente disparar, ele chama `POST /v1/routines/{routine_key}/trigger` com um `run_key` estável para aquela ocorrência (por exemplo, `2026-10-24-am`). Repetir a mesma chamada não duplica a demanda.
3. Agentes ativos enviam heartbeat com suas ferramentas e consultam `POST /v1/agent-tasks/claim-next`.
4. O banco escolhe a maior prioridade elegível; o agente executa e envia o resultado para `POST /v1/agent-tasks/{task_id}/finish`.

Exemplo de template de rotina:

```json
{
  "routine_key": "morning-research",
  "name": "Curadoria matinal",
  "priority": 60,
  "schedule": {"timezone": "America/Sao_Paulo", "local_time": "05:30"},
  "task_template": {
    "objective": "Preparar a curadoria matinal de IA e física",
    "task_type": "research",
    "required_tools": ["web_search"],
    "acceptance_criteria": ["fontes citadas", "implicações e limitações"],
    "max_attempts": 3
  }
}
```

O campo `schedule` é metadado declarativo: esta PR não instala um cron nem altera os agendamentos nativos das plataformas. A rotina só gera uma demanda quando o endpoint `trigger` é chamado.
