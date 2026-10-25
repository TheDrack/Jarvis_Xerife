# Paridade HUD ↔ App Android

## Papel de cada cliente

- HUD (`app/static/index.html`): interface web/PWA na nuvem. É o protótipo inicial e continua existindo; não é descartado. Funciona enquanto a aba estiver aberta.
- App Android (`mobile/android`): cliente com maior capacidade de execução e presença. Funciona com o app fechado, via notificações FCM e serviço em primeiro plano, quando permitido pelo Android.
- Núcleo Jarvis: fonte única de verdade. HUD e App consomem os mesmos contratos HTTP autenticados. Nenhum dos dois guarda memória própria.

Resultado esperado: tudo o que o HUD faz, o App também faz; o App acrescenta presença, notificações e execução no aparelho, com permissões explícitas.

## Matriz de capacidades (estado verificado no código)

| Capacidade | HUD | App Android | Endpoint/recurso |
|---|---|---|---|
| Login e logout | Sim (`/token`, expira em 30 min) | Sim (sessão renovável de 15 min, revogação no logout) | `/token`; `/v1/mobile/session/*` |
| Chat com o Jarvis (texto) | Sim | **Não** | `POST /v1/message` |
| Entrada de voz (reconhecimento) | Sim | **Não** | cliente (SpeechRecognizer) |
| Saída de voz (TTS pt-BR) | Sim | Sim | cliente (TTS) |
| Wake word | Sim (via `/v1/status`) | **Não** | `GET /v1/status` |
| Status do sistema | Parcial | **Não** | `GET /v1/status` |
| Telemetria de bateria | Sim | **Não** | `POST /v1/telemetry` |
| Localização e mapa | Sim (Leaflet + Nominatim) | **Não** | `POST /v1/telemetry`; Nominatim |
| Progresso do roadmap | Sim | **Não** | `GET /v1/roadmap/progress` |
| Presença com app fechado | Não | Sim (FCM + serviço em primeiro plano) | `/v1/mobile/push/*`; `/v1/local-bridge` |
| Ações remotas | Chat | Somente `speak` | `/v1/local-bridge/send-task` |

## Princípios

1. Paridade antes de expansão: cada capacidade do HUD ganha equivalente no App antes de qualquer ação nova no aparelho.
2. Mesmos contratos: o App não cria endpoints próprios para funções que o HUD já usa.
3. Permissão sob demanda: microfone, localização e notificações só são pedidos quando a função é ativada pelo usuário.
4. Dados mínimos: telemetria e localização seguem a política do HUD (30 s, deslocamento de 100 m) e nunca vão para payload de push.
5. Ações de execução exigem allowlist: qualquer ação nova no telefone passa por contrato com tipo, origem, idempotência, expiração e revogação, conforme a Fase 0 de `docs/JARVIS_MOBILE_COMPANION.md`.

## Fases propostas

**P1 — Conversa e voz.** Tela de chat com `POST /v1/message`, entrada de voz com reconhecimento pt-BR, wake word e status via `GET /v1/status`. Permissão extra: microfone, pedida só ao ativar a voz.

**P2 — Contexto do aparelho.** Telemetria de bateria (BatteryManager) e localização opcional (com permissão de localização aproximada por padrão) enviadas para `POST /v1/telemetry`, com throttle de 30 s e filtro de deslocamento de 100 m. Indicador visível e botão de desligar.

**P3 — Roadmap e mapa.** Painel de progresso via `GET /v1/roadmap/progress` com cache local, e mapa com geocodificação reversa respeitando 1 req/s e cache por coordenada.

**P4 — Execução ampliada.** Só depois de P1 a P3 e da Fase 0 do documento de companion: lista explícita de ações permitidas no aparelho, com decisão do dono do projeto sobre cada uma.

## Critérios de aceitação por fase

- Cada função tem teste de contrato contra o endpoint real e teste de UI em telefone físico.
- Telefone bloqueado, sem rede, após expiração de sessão e após logout: a função falha de forma explícita e não repete ações.
- Nenhuma capacidade nova conecta sem autenticação verificada no servidor.
- O HUD continua funcionando sem alterações de contrato.

## Decisões pendentes do dono do projeto

1. Quais ações de execução o telefone pode fazer em P4 (exemplos: abrir apps, automação de tela, enviar mensagens).
2. Retenção de telemetria e localização no servidor.
3. Biblioteca de mapa no Android: osmdroid (OpenStreetMap) ou MapLibre.

## Bloqueios externos já conhecidos

- Configuração do projeto Firebase e das credenciais FCM (cliente e servidor).
- Deploy do backend com `SUPABASE_SERVICE_ROLE_KEY` confirmada no ambiente.
- Reconciliação do histórico de migrations Supabase, citada em `docs/JARVIS_MOBILE_COMPANION.md`.
