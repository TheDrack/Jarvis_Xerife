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
Android Jarvis Mobile ◄── FCM push ─────┘             │
                                                      └── memória, agentes e ferramentas
```

O núcleo continua responsável por raciocínio, ferramentas, rotinas e memória. O aplicativo móvel fornece canais de interação, voz local, notificações e contexto do dispositivo, sempre com permissões explícitas.

## Decisões técnicas

1. **Cliente Android nativo (Kotlin + Jetpack Compose).** Não depender de uma WebView aberta para receber eventos ou reproduzir voz.
2. **Push para acordar a atenção, não para transportar memória sensível.** Usar Firebase Cloud Messaging (FCM) para notificações/eventos breves quando o processo estiver suspenso. Buscar detalhes por uma API autenticada. Não incluir tokens, localização precisa ou conteúdo privado no payload de push.
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
- FCM com token de instalação registrado por endpoint autenticado; atualização e revogação do token.
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

A aplicação não pode garantir execução ininterrupta nem inicializar arbitrariamente microfone/serviços quando o sistema restringe o background. FCM, notificações, WorkManager e foreground service têm papéis diferentes. A implementação deve obedecer às regras vigentes do Android e às otimizações de bateria do fabricante; “sempre presente” significa recuperação robusta e canais disponíveis, não execução irrestrita.

## Critérios de aceitação

- Nenhum WebSocket pessoal aceita conexão sem autenticação e autorização verificadas.
- O cliente pode registrar-se, autenticar-se, desconectar-se e revogar a própria sessão.
- Um evento PC de retorno produz no máximo uma saudação por janela de cooldown; eventos repetidos não duplicam a fala.
- Notificações funcionam com o app em foreground e background; os resultados são testados separadamente para tela bloqueada, rede indisponível, processo encerrado e reinicialização.
- Nenhum teste válido é removido ou enfraquecido para obter CI verde.
- HUD, Telegram, rotinas e navegação Android existentes continuam funcionando.
- Produção e credenciais Firebase só são configuradas depois de revisar o fluxo em ambiente de teste; nenhum segredo entra no repositório.

## Fontes técnicas

- Android: restrições para iniciar foreground services em background — https://developer.android.com/develop/background-work/services/fgs/restrictions-bg-start
- Android: visão geral de foreground services — https://developer.android.com/develop/background-work/services/fgs
- Firebase: receber mensagens em apps Android — https://firebase.google.com/docs/cloud-messaging/android/receive-messages

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

- O endpoint legado `/token` continua usando o prazo OAuth2 padrão de 30 minutos. O aplicativo nativo passa a usar os endpoints de sessão móvel renovável descritos no incremento 2; para produção, ainda é necessário configurar a chave administrativa e aplicar a migration.
- FCM não está configurado; isso exige um projeto Firebase e configuração de servidor que não devem ser inventados. Sem FCM, o canal depende de o serviço em primeiro plano continuar permitido pelo Android.
- O Android impõe limite de seis horas por janela de 24 horas a serviços foreground do tipo `dataSync` em apps que miram API 35. O serviço encerra no callback de timeout; não tenta contornar a regra.
- A saudação PC→telefone ainda não está ponta a ponta: o watcher Windows não publica evento autenticado ao núcleo e não há push FCM. Não foi instalado APK no telefone nem alterada a produção.

## Estado desta proposta

A base nativa e a sessão móvel renovável/revogável estão implementadas em código, mas ainda dependem da migration e da chave administrativa no ambiente de servidor. O canal de eventos ainda não é uma solução conclusiva de presença persistente. Não marcar a integração PC→telefone como concluída até configurar FCM, ligar o watcher ao fluxo autenticado e testar em dispositivo Android real.
## Incremento 2 — sessão móvel renovável e revogável

- Adiciona `POST /v1/mobile/session/login`, `POST /v1/mobile/session/refresh` e `POST /v1/mobile/session/revoke`.
- Access tokens móveis duram 15 minutos; refresh tokens opacos duram até 30 dias e são rotacionados a cada renovação.
- O banco guarda apenas SHA-256 do refresh token, nunca o token bruto. A função SQL de rotação usa bloqueio de linha, invalida o token anterior e revoga a família em caso de replay ou expiração.
- O token de acesso inclui identidade, família da sessão e ID do dispositivo; o WebSocket exige que o `device_id` solicitado corresponda ao dispositivo do token.
- Android cifra access + refresh token com Android Keystore. Ao receber rejeição de sessão, tenta renovação antes de interromper a presença; logout tenta revogar no servidor e sempre limpa o material local.
- A migration `20261024200302_mobile_device_sessions.sql` ativa RLS, não concede acesso às roles públicas/autenticadas e limita tabela/função ao `service_role`.
- O backend requer `SUPABASE_SERVICE_ROLE_KEY` no ambiente de servidor. Não foi configurada nenhuma chave, aplicada migration em produção ou feito deploy nesta etapa.
- Testes locais específicos: `test_mobile_sessions.py` e `test_mobile_bridge_auth.py`.

### Próximos bloqueios

1. Configurar `SUPABASE_SERVICE_ROLE_KEY` no ambiente de servidor usando o gerenciador de segredos, sem expor o valor.
2. Aplicar a migration somente após revisão e confirmar tabela/função e RLS no projeto correto.
3. Configurar FCM com um projeto e credenciais reais.
4. Integrar o watcher de retorno do Windows ao fluxo autenticado e validar PC → núcleo → Android.
5. Compilar APK, instalar e validar em telefone real, incluindo tela bloqueada, rede interrompida, expiração, replay e logout.

### Atenção ao histórico de migrations do projeto remoto

Na inspeção somente leitura do projeto Supabase `saibtpdehhprttqlgqdt`, as quatro migrations existentes aparecem com versões remotas `20261024142633`, `20261024142635`, `20261024142637` e `20261024142639`, enquanto os prefixos dos arquivos no repositório são `202610230001` a `202610230004`. Antes de aplicar a nova migration, reconciliar esse histórico e a ordem com a ferramenta de migração escolhida; não executar um `db push` às cegas. Nenhuma alteração foi aplicada ao banco durante esta etapa.
