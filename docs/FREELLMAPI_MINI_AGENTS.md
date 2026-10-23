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

O processo hospedeiro deve repetir o ciclo com backoff, shutdown limpo e heartbeat. O worker anuncia somente `text_reasoning`, reivindica a maior prioridade elegível pela API compartilhada e envia o resultado ligado ao `attempt_id`. Se a inferência falhar, não marca a tarefa como concluída; a lease expira para permitir recuperação/reexecução.

O gateway FreeLLMAPI continua em loopback no PC. Não execute este worker no Render esperando que ele consiga acessar `127.0.0.1:3001` do computador local.

Para autenticação do worker, prefira configurar `JARVIS_TASK_QUEUE_USERNAME` e `JARVIS_TASK_QUEUE_PASSWORD` por um gerenciador seguro de segredos: o worker obtém o JWT no endpoint `/token` e renova após HTTP 401. Alternativamente, `JARVIS_TASK_QUEUE_API_TOKEN` pode ser usado enquanto válido, mas um token JWT expira e precisa ser rotacionado externamente.
