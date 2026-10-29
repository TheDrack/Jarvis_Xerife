# Jarvis Mobile — arquitetura e plano de entrega

## Objetivo

Evoluir o HUD web para um cliente Android nativo que mantenha uma presença útil do Jarvis no telefone mesmo quando a interface não estiver aberta. O aplicativo é um cliente do mesmo núcleo Jarvis, não um segundo agente nem uma nova fonte de memória.

## Estado verificado antes da implementação

- O repositório já possui um HUD web/PWA em `app/static/index.html`.
- Há APIs autenticadas para login OAuth2 (`POST /token`) e cadastro/heartbeat de dispositivos (`/v1/devices/*`).
- Há navegação Android por ADB documentada em `docs/ANDROID_AUTONOMOUS_NAVIGATION.md`; ela cobre controle de UI, não presença pessoal contínua.
- O endpoint `/v1/local-bridge` aceita WebSocket sem validar a identidade do cliente. O endpoint `/ws/{user_id}` também confia no identificador da URL. Nenhum deles deve ser usado como canal de eventos pessoais do aplicativo antes de corrigir a autenticação e a autorização.
- O monitor Windows de retorno de atividade está em uma PR separada (#582) e atualmente tenta falar pelo áudio padrão do PC. Esta proposta não altera nem mistura essa PR.

## Arquitetura alvo

```text
Windows watcher ── evento autenticado ──┐
HUD web ────────────────────────────────┼── Jarvis Core / event router
Android Jarvis Mobile ◄── WebSocket autenticado + fila persistente ──┘             │
                                                      └── memória, agentes e ferramentas
```

O núcleo continua responsável por raciocínio, ferramentas, rotinas e memória. O aplicativo móvel fornece canais de interação, voz local, notificações e contexto do dispositivo, sempre com permissões explícitas.

## Decisões técnicas

1. **Cliente Android nativo (Kotlin + Jetpack Compose).** Não depender de uma WebView aberta para receber eventos ou reproduzir voz.
2. **Canal próprio de eventos.** O WebSocket autenticado entrega tarefas enquanto a presença móvel está conectada. Eventos offline ficam na fila Supabase com TTL e são sincronizados após reconexão; não há entrega imediata enquanto o telefone estiver desconectado.
3. **Conexão em tempo real apenas quando permitida.** WebSocket autenticado pode servir enquanto o processo está ativo e conectado, mas não é garantia de presença permanente.
4. **Trabalho adiado com WorkManager.** Sincronizações recuperáveis e não urgentes usam trabalho agendado, em vez de loops permanentes.
5. **Foreground service apenas para uma sessão contínua perceptível pelo usuário.** Exibir notificação persistente e permitir que a pessoa pare a sessão. Não manter microfone sempre ligado como comportamento padrão.
6. **Identidade e autorização de dispositivo.** Reutilizar a autenticação OAuth2 existente como ponto de entrada, mas introduzir credenciais/sessões de dispositivo revogáveis para a conexão móvel. Não colocar senha, JWT de longa duração ou segredo de servidor no APK.
7. **Canal de eventos dedicado.** Corrigir ou contornar explicitamente os WebSockets sem autenticação. Validar a identidade do usuário e a associação do dispositivo em cada conexão e ação; validar payloads e aplicar limites.
8. **Rotas de contingência.** O HUD e Telegram permanecem disponíveis; a falha do aplicativo não pode bloquear o núcleo Jarvis nem as rotas atuais.
9. **Contexto com proveniência.** Diferenciar fatos observados de inferências; registrar apenas os sinais autorizados, com controles de revogação e retenção.

## Entregas incrementais

### Fase 0 — segurança e contratos (obrigatória antes de conectar o app)

- Definir o contrato de eventos: identificador, tipo permitido, origem, timestamp, idempotency key e política de expiração.
- Adicionar testes de autenticação/autorização para WebSocket e rotas de evento; garantir rejeição de token ausente/inválido e de usuário/dispositivo incompatível.
- Definir registro, revogação e rotação de credencial de dispositivo sem armazenar segredos em logs.
- Criar testes de contrato para eventos duplicados, payload inválido, replay e desconexão.

### Fase 1 — aplicativo mínimo

- Projeto Android nativo, estado de conexão visível e teste de síntese de voz `pt-BR`.
- Login pelo fluxo existente sem persistir senha.
- Armazenamento protegido de credenciais curtas/revogáveis, logout e revogação.
- Build automatizado de APK de debug e testes de lógica.

### Fase 2 — presença e notificações

- Registro do telefone como dispositivo Jarvis.
- Registro autenticado do dispositivo e fila de eventos com TTL, expiração e ACK.
- Notificações de eventos enquanto o HUD estiver fechado.
- Confirmação de recebimento e deduplicação; recuperação após ficar offline.

### Fase 3 — saudação PC → telefone

- O watcher do Windows publica um evento de retorno por um cliente autorizado, sem embutir credenciais no script.
- O núcleo valida a origem, associa o evento ao usuário e entrega uma notificação ao telefone.
- O Android decide se fala por TTS, considerando preferências de silêncio, volume, estado do aparelho e janela de cooldown.
- Se o telefone estiver offline, registrar estado de entrega e manter a contingência configurada; não afirmar que a fala foi reproduzida sem confirmação do cliente.

### Fase 4 — contexto e capacidades adicionais

- Presença, rede/localização opcional, voz interativa e automação Android por APIs apropriadas.
- Permissões granulares, indicação visível de captura, controles de pausa e exclusão.
- Avaliar ARTEMIS como ferramenta de automação/teste Android, não como substituto do aplicativo de presença.

## Limites do Android

A aplicação não pode garantir execução ininterrupta nem inicializar arbitrariamente microfone/serviços quando o sistema restringe o background. WebSocket, fila persistente, WorkManager e foreground service têm papéis diferentes.

## Critérios de aceitação

- Nenhum WebSocket pessoal aceita conexão sem autenticação e autorização verificadas.
- O cliente pode registrar-se, autenticar-se, desconectar-se e revogar a própria sessão.
- Um evento PC de retorno produz no máximo uma saudação por janela de cooldown; eventos repetidos não duplicam a fala.
- Notificações funcionam com o app em foreground e background; os resultados são testados separadamente para tela bloqueada, rede indisponível, processo encerrado e reinicialização.
- Nenhum teste válido é removido ou enfraquecido para obter CI verde.
- HUD, Telegram, rotinas e navegação Android existentes continuam funcionando.
- Nenhum segredo de servidor entra no APK, logs ou repositório.

## Fontes técnicas

- Android: restrições para iniciar foreground services em background — https://developer.android.com/develop/background-work/services/fgs/restrictions-bg-start
- Android: visão geral de foreground services — https://developer.android.com/develop/background-work/services/fgs


## Implementação em andamento — 2026-10-24

O primeiro incremento foi implementado nesta branch:

- Projeto Android nativo isolado em `mobile/android`, Kotlin + Jetpack Compose.
- Login OAuth2 por HTTPS, senha não persistida e token cifrado com AES-GCM usando chave do Android Keystore.
- TTS local em português e serviço de conexão WebSocket opcional, iniciado pelo usuário com notificação persistente.
- O serviço aceita apenas a ação de fala, limita o texto a 1.000 caracteres e retorna o resultado da tarefa.
- Conexões WebSocket com `device_type=mobile` agora exigem JWT Bearer válido; o identificador é namespaceado com a identidade autenticada.
- Os endpoints HTTP de listagem e despacho do bridge também exigem JWT. Testes locais específicos: 6 passaram.
- CI Android configurado para compilar o APK de debug. A primeira execução revelou que `setup-android@v3` tenta instalar o pacote SDK removido `tools`; foi corrigida para `setup-android@v4` com `platform-tools` explícito. A compilação após essa correção ainda precisa terminar.

### Limitações ainda abertas

- O endpoint legado `/token` continua usando o prazo OAuth2 padrão de 30 minutos. O aplicativo nativo usa os endpoints de sessão móvel renovável do incremento 2; as migrations já estão aplicadas, mas o backend precisa ser implantado e a chave administrativa confirmada no Render.
- A entrega depende do serviço de presença e da fila de eventos; eventos offline só são processados quando o Android reconecta. Isso não foi validado em telefone físico.
- O Android impõe limite de seis horas por janela de 24 horas a serviços foreground do tipo `dataSync` em apps que miram API 35. O serviço encerra no callback de timeout; não tenta contornar a regra.
- A entrega depende do serviço de presença e da fila de eventos; eventos offline só são processados quando o Android reconecta. Isso não foi validado em telefone físico.

## Estado desta proposta

A base nativa e a sessão móvel renovável/revogável estão implementadas; as migrations já estão aplicadas no Supabase. O login ainda depende do deploy do backend e da chave administrativa no ambiente de servidor. O canal de eventos ainda não é uma solução conclusiva de presença persistente. Não marcar a integração PC→telefone como concluída até configurar a chave do watcher e testar em dispositivo Android real.
## Incremento 2 — sessão móvel renovável e revogável

- Adiciona `POST /v1/mobile/session/login`, `POST /v1/mobile/session/refresh` e `POST /v1/mobile/session/revoke`.
- Access tokens móveis duram 15 minutos; refresh tokens opacos duram até 30 dias e são rotacionados a cada renovação.
- O banco guarda apenas SHA-256 do refresh token, nunca o token bruto. A função SQL de rotação usa bloqueio de linha, invalida o token anterior e revoga a família em caso de replay ou expiração.
- O token de acesso inclui identidade, família da sessão e ID do dispositivo; o WebSocket exige que o `device_id` solicitado corresponda ao dispositivo do token.
- Android cifra access + refresh token com Android Keystore. Ao receber rejeição de sessão, tenta renovação antes de interromper a presença; logout tenta revogar no servidor e sempre limpa o material local.
- A migration `20261024200302_mobile_device_sessions.sql` ativa RLS, não concede acesso às roles públicas/autenticadas e limita tabela/função ao `service_role`.
- O backend requer `SUPABASE_SERVICE_ROLE_KEY` no ambiente de servidor; o valor não foi lido nem alterado nesta etapa. As migrations móveis já estão aplicadas no Supabase, mas o backend do Render ainda não foi atualizado.
- Testes locais específicos: `test_mobile_sessions.py` e `test_mobile_bridge_auth.py`.

### Próximos bloqueios

1. Confirmar se `SUPABASE_SERVICE_ROLE_KEY` está configurada no Render; se faltar, adicioná-la pelo gerenciador de segredos sem expor o valor.
2. As migrations móveis já estão aplicadas; não reaplicá-las. Confirmar tabelas e RLS antes de futuras alterações.
3. Configurar e aplicar a migração da fila nativa de eventos.
4. A PR #587 integra o watcher; após CI verde, revisão e merge, configurar a chave dedicada e validar PC → núcleo → Android.
5. Validar em telefone real, incluindo tela bloqueada, rede interrompida, expiração, replay e logout.

### Atenção ao histórico de migrations do projeto remoto

Na inspeção somente leitura do projeto Supabase `saibtpdehhprttqlgqdt`, as quatro migrations existentes aparecem com versões remotas `20261024142633`, `20261024142635`, `20261024142637` e `20261024142639`, enquanto os prefixos dos arquivos no repositório são `202610230001` a `202610230004`. Depois dessa inspeção, as duas migrations móveis foram aplicadas pelo conector sob as versões remotas `20261024213541` e `20261024213552`. Os prefixos dos arquivos locais ainda diferem das versões remotas; não executar `db push` às cegas nem reaplicar essas migrations. Reconciliar o histórico antes de qualquer migração futura.

## Incremento 3 — fila nativa de eventos quando o WebSocket está offline

- O backend mantém registro do dispositivo e eventos com expiração; o texto permanece no banco privado e só é recuperado pela API autenticada.
- Se o telefone estiver desconectado do WebSocket, `/v1/local-bridge/send-task` enfileira tarefas de fala e notificação para o próximo reconnect; com o dispositivo conectado, o bridge entrega imediatamente.
- Ao reconectar, o Android consulta a fila autenticada, exibe notificações permitidas e reproduz voz `pt-BR`; o sistema Android ainda pode restringir o serviço em segundo plano.
- O APK não depende de credenciais de provedor externo; a entrega offline é eventual e exige que o app volte a conectar ao Jarvis.

- A migration `20261024213552_mobile_push_delivery.sql` cria o registro de dispositivos sem tokens de provedores e a fila privada de eventos, com RLS e acesso apenas a `service_role`; a migração de transição remove o registro legado em instalações existentes.
- A validação local específica da segunda etapa foi: `test_mobile_push.py`, `test_mobile_sessions.py` e `test_mobile_bridge_auth.py` — **23 passed**; depois, a suíte completa passou com **1504 passed, 4 skipped**. O CI da PR #587 está em execução.
- Ainda é obrigatório implantar o backend, aplicar a migração e validar o fluxo em telefone físico.

## Diagnóstico de login após o merge — 2026-10-24

A verificação real do serviço de produção após os merges encontrou dois bloqueios independentes:

1. O serviço Render ainda estava servindo um commit anterior aos merges do cliente móvel. A verificação HTTP confirmou /health = 200, mas /v1/mobile/session/login = 404 e as rotas de eventos móveis não estavam no OpenAPI. A notificação de canal indisponível no Android era o estado do serviço WebSocket, não prova de que o fila nativa estivesse ativo.
2. O projeto Supabase contém a tabela histórica public.user (singular), sem registros de conta, enquanto o adaptador de autenticação consultava public.users (plural). O adaptador foi ajustado para compatibilidade com os dois nomes, consulta somente pelo cliente administrativo e grava contas somente com privilégios de servidor.

A correção de autenticação foi mesclada na main. As migrations de sessões móveis e entrega push já foram aplicadas ao projeto Supabase saibtpdehhprttqlgqdt na ordem registrada no histórico remoto (versões 20261024213541 e 20261024213552); as tabelas existem e ainda não têm registros móveis. O backend do Render continua num commit anterior e não expõe as rotas móveis. Antes de validar o login, confirmar/configurar SUPABASE_SERVICE_ROLE_KEY no Render; essa chave não pode ser colocada no APK nem em código. Nenhuma conta móvel foi criada nesta etapa.


## Incremento 4 — saudação autenticada do Windows ao telefone

- O watcher de retorno do Windows tenta o endpoint HTTPS POST /v1/mobile/push/return-activity antes de usar a saída de áudio local.
- O endpoint usa uma credencial dedicada JARVIS_RETURN_ACTIVITY_KEY, comparada em tempo constante; não reutiliza nem envia API_KEY_LOCAL ao telefone.
- A rota aceita apenas a saudação fixa, sem texto, usuário ou ID de dispositivo arbitrário no corpo. Ela falha de forma fechada se não houver telefone ativo ou se houver mais de um telefone registrado.
- Se o telefone estiver conectado ao WebSocket autenticado, a saudação segue por esse canal; se estiver desconectado, o evento é enfileirado e aguarda reconexão. Não envia a mesma saudação pelos dois caminhos.
- O watcher lê a chave de JARVIS_RETURN_ACTIVITY_KEY no ambiente do usuário ou de %LOCALAPPDATA%\\Jarvis_Xerife\\config\\return_activity\\return_activity.key. O instalador cria a pasta de configuração sem criar nem exibir segredo.
- Para habilitar, configurar o mesmo segredo aleatório em `JARVIS_RETURN_ACTIVITY_KEY` no serviço Render e no Windows (variável do usuário ou arquivo protegido).
- Se o telefone estiver desconectado, a fala fica na fila e só é processada após reconexão; o sistema não afirma entrega antes do ACK.
- Testes cobrem credencial ausente/incorreta, fila offline, ACK de evento, escolha de dispositivo e requisição do watcher sem registrar o segredo.


## Incremento 5 — notificações arbitrárias autenticadas de agentes

O endpoint `POST /v1/mobile/push/notify` permite que um agente autorizado envie uma notificação visível ou uma mensagem de voz sem obter o Bearer token do app móvel.

- A autenticação usa uma chave de serviço dedicada `JARVIS_MOBILE_NOTIFY_KEY` no servidor Render e no cliente autorizado; ela não reutiliza `API_KEY_LOCAL` nem `JARVIS_RETURN_ACTIVITY_KEY`.
- O agente pode consultar `GET /v1/mobile/push/agent/devices`, que retorna apenas IDs, estado de conexão e estado de registro — nenhum token de provedor externo é armazenado.
- O corpo aceita `text` (1–1000 caracteres), `title` (1–80), `mode` (`notification` ou `speak`) e, quando houver mais de um aparelho, `device_id` e `user_id` explícitos.
- Com WebSocket ativo, o servidor aguarda o `task_result` do app. Sem WebSocket, armazena o evento e devolve `event_id`; consulte `GET /v1/mobile/push/agent/events/{event_id}` para verificar `queued`, `acknowledged` ou `expired`.
- Nenhum segredo de servidor entra no APK, logs ou repositório.
- No Windows, `scripts/send_mobile_notification.ps1` lê a chave do ambiente do usuário ou de `%LOCALAPPDATA%\\Jarvis_Xerife\\config\\mobile_notify\\mobile_notify.key`. Não imprima nem registre a chave.
