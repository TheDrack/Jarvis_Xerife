# FreeLLMAPI como motor de miniagentes

## Papel na arquitetura

FreeLLMAPI será um gateway de inferência econômico e opcional para tarefas textuais delimitadas. Ele não substitui ChatGPT/Claude, não amplia a inteligência de um modelo por si só e não recebe permissão implícita para executar ferramentas.

- **ChatGPT / Claude:** podem continuar como agentes de maior capacidade e disparadores de rotinas nativas.
- **Fila Jarvis no PostgreSQL/Supabase:** mantém prioridade, leases, idempotência, dependências, tentativas e resultados.
- **Harness Jarvis:** fornece contratos, mensagens, contexto e ferramentas autorizadas por separado.
- **FreeLLMAPI:** roteia a inferência dos miniagentes para provedores gratuitos ou endpoints locais compatíveis.
- **Worker local:** deve executar perto do gateway FreeLLMAPI no PC, usando `127.0.0.1:3001`; não exponha o gateway na internet para que Render consiga acessá-lo.

## Configuração local

Instale e configure FreeLLMAPI separadamente conforme sua documentação oficial. Adicione as chaves dos provedores gratuitos no próprio gateway e crie uma chave unificada. Depois configure no ambiente do worker Jarvis:

- `FREELLMAPI_BASE_URL=http://127.0.0.1:3001/v1`
- `FREELLMAPI_API_KEY=<chave unificada local>`
- `FREELLMAPI_MODEL=auto`
- `FREELLMAPI_PROVIDER=unknown` (use `venice` only when this worker calls Venice directly)
- `FREELLMAPI_TIMEOUT_SECONDS=45`

Não coloque chaves em código, commits, payloads de tarefas ou logs. Sem `FREELLMAPI_API_KEY`, o cliente permanece desativado e falha explicitamente.

## Protocolo do miniagente

`FreeLLMAgentHandler` implementa o handler de `AgentWorker`. Ele recebe uma mensagem `request` com `objective`, `task_type`, `constraints`, `acceptance_criteria` e contexto opcional. Publica texto e telemetria de roteamento como resultado; o worker só reconhece a mensagem depois de publicar a resposta.

O handler é **text-only**: não executa shell, browser, arquivos ou ações externas. Ferramentas necessárias precisam ser autorizadas e executadas por um runtime Jarvis separado. O modelo não pode afirmar que usou ferramentas sem evidência fornecida.

## Limites de custo e qualidade

FreeLLMAPI agrega camadas gratuitas, mas quotas, modelos, limites de requisição e termos de cada provedor podem mudar. O roteador pode falhar quando as cotas acabam. Configure tarefas de baixo risco, limites de tokens, timeout e critérios de aceitação; escalone para um agente mais capaz quando o miniagente não satisfizer os critérios.

## Referências

- Repositório: https://github.com/tashfeenahmed/freellmapi
- API compatível com OpenAI: https://github.com/tashfeenahmed/freellmapi/blob/main/docs/en/api/01-rest-api.md
- O projeto declara ser destinado a experimentação pessoal, não uma base de inferência com SLA de produção.

## Worker conectado à fila de prioridades

Configuração completa, execução de vários slots e diagnóstico: [MULTI_AGENT_USAGE.md](MULTI_AGENT_USAGE.md).

Configure o worker local com as variáveis listadas acima e com um token autorizado para a API Jarvis:

- `JARVIS_TASK_QUEUE_API_URL=https://<host-jarvis>`
- `JARVIS_TASK_QUEUE_API_TOKEN=<token de API autorizado>`
- `JARVIS_AGENT_ID=mini-freellmapi-1`
- `JARVIS_TASK_QUEUE_LEASE_SECONDS=90`

Uso de um ciclo:

```python
from app.multiagent import PriorityQueueMiniAgent

worker = PriorityQueueMiniAgent.from_env()
outcome = worker.run_once()  # None quando não há tarefa elegível
```

O processo hospedeiro deve repetir o ciclo com backoff, shutdown limpo e heartbeat. O worker anuncia somente `text_reasoning`, reivindica a maior prioridade elegível pela API compartilhada e envia o resultado ligado ao `attempt_id`. Se a inferência falhar, não marca a tarefa como concluída: a tentativa é liberada na hora (RPC `release_jarvis_agent_task` no backend nativo ou `POST /v1/agent-tasks/{task_id}/release` no HTTP) e volta a `ready` com `attempts` incrementado; o lease de 90 s é apenas a rede de segurança quando o release não pode ser registrado. Ao esgotar `max_attempts`, a tarefa termina em `failed`. Passo a passo em [MULTI_AGENT_USAGE.md](MULTI_AGENT_USAGE.md).

O gateway FreeLLMAPI continua em loopback no PC. Não execute este worker no Render esperando que ele consiga acessar `127.0.0.1:3001` do computador local.

Para autenticação do worker, prefira configurar `JARVIS_TASK_QUEUE_USERNAME` e `JARVIS_TASK_QUEUE_PASSWORD` por um gerenciador seguro de segredos: o worker obtém o JWT no endpoint `/token` e renova após HTTP 401. Alternativamente, `JARVIS_TASK_QUEUE_API_TOKEN` pode ser usado enquanto válido, mas um token JWT expira e precisa ser rotacionado externamente.

## Venice Uncensored 1.2

O Venice é um provedor opcional do `AIGateway`; a configuração padrão continua sendo Groq. Para o roteador principal:

- `VENICE_API_KEY`: chave da API Venice (não versionar).
- `VENICE_MODEL=venice-uncensored-1-2`
- `VENICE_BASE_URL=https://api.venice.ai/api/v1`

Para usar Venice diretamente no worker FreeLLMAPI, configure `FREELLMAPI_BASE_URL=https://api.venice.ai/api/v1`, `FREELLMAPI_API_KEY` com o valor da chave Venice e `FREELLMAPI_MODEL=venice-uncensored-1-2`. Essa configuração é independente da chave do roteador principal.

## Delegação por papel de segurança

A liderança continua decidindo dinamicamente qual agente recebe cada tarefa. Não existem agentes permanentemente fixos como Red Team ou Blue Team. Para tarefas com `task_type` igual a `red_team` ou `blue_team` (aceita variação de maiúsculas, espaços e hífens), o scheduler só considera perfis cujo `model_provider` anunciado seja `venice`.

O envelope de atribuição inclui `required_model_provider: "venice"`. Se nenhum agente Venice estiver disponível, elegível em capacidade, ferramentas e orçamento, a atribuição falha explicitamente com `NoEligibleAgentError`; não há fallback para Groq, Gemini ou outro provedor. Para todos os demais tipos de tarefa, a seleção de agente/provedor permanece como antes.

O valor `model_provider` do perfil/heartbeat deve refletir o provedor realmente configurado no runtime do agente, e não apenas uma preferência declarada pelo líder. Para o worker FreeLLMAPI apontado diretamente à API Venice, configure `FREELLMAPI_PROVIDER=venice`; mantenha `unknown` se o endpoint usar um roteador que não garante Venice. O schema de fila armazena esse campo e as funções SQL de claim recusam Red/Blue Team para agentes não-Venice, inclusive em tentativas de claim direto. O runtime que executa o agente também deve impedir fallback interno para outro provedor durante a tarefa protegida.
