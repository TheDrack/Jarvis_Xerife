# Jarvis Mobile (Android)

O transporte de presença e comandos remotos é exclusivamente WebSocket autenticado (`wss://.../v1/local-bridge`). O app mantém uma conexão em primeiro plano enquanto a presença estiver ativada; o servidor envia tarefas `speak` pelo socket e recebe `task_result` no mesmo canal.

## Fluxo de voz

1. O usuário entra no app e ativa **Presença**.
2. `BridgeService` abre o WebSocket com Bearer token, `device_id` persistente e capacidades `tts,notifications`.
3. O servidor envia `{type: task, action: speak, task_id, parameters: {text}}`.
4. O Android executa TTS em português do Brasil e envia `{type: task_result, task_id, success, result}`.
5. O servidor só confirma a tarefa quando recebe o resultado; não há fallback de Firebase/FCM nem fila push offline.

## Restrições operacionais

- O aparelho precisa estar online e com **Presença** ativa para receber comandos imediatamente.
- O Android pode suspender ou encerrar serviços por política de bateria; mantenha a notificação persistente do serviço e confira o estado de conexão.
- Tokens são mantidos no `TokenVault`; não registrar credenciais em logs.
- Build local: `gradle --no-daemon :app:testDebugUnitTest :app:assembleDebug` a partir de `mobile/android`.
