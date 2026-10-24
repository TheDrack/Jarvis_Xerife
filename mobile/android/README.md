# Jarvis Mobile — Android nativo

Cliente Android isolado do núcleo Jarvis. Não substitui o HUD, os conectores MCP nem os adaptadores de desktop.

## Incluído

- Interface nativa Jetpack Compose.
- Login por HTTPS em POST /v1/mobile/session/login; a senha não é persistida.
- Access token de 15 minutos e refresh token rotativo/revogável, cifrados com AES-GCM via Android Keystore.
- TTS local em português do Brasil.
- Presença WebSocket iniciada explicitamente pelo usuário, com notificação persistente, reconexão progressiva e renovação de sessão.
- Firebase Cloud Messaging opcional para sinalizar eventos de voz quando o WebSocket não está conectado.
- Push transporta apenas um ID opaco; o conteúdo é buscado por HTTPS autenticado.
- Ações remotas limitadas a speak, com texto limitado a 1.000 caracteres.
- Logout limpa as credenciais locais e tenta revogar sessão e registro push no servidor.

## Firebase opcional

Sem a configuração abaixo, o APK compila, mas FCM não é ativado.

Configurar no ambiente de build Android:

- JARVIS_FCM_API_KEY
- JARVIS_FCM_APP_ID
- JARVIS_FCM_PROJECT_ID
- JARVIS_FCM_SENDER_ID

São os campos de configuração do aplicativo cliente Firebase, não a chave privada da conta de serviço. Não commitar esses valores em arquivos versionados; injetá-los pelo ambiente de CI/build.

No servidor, configurar como segredos FIREBASE_PROJECT_ID e FIREBASE_SERVICE_ACCOUNT_JSON (ou GOOGLE_APPLICATION_CREDENTIALS apontando para um arquivo protegido). A conta de serviço precisa de permissão para enviar FCM HTTP v1.

Aplicar antes as migrations de sessão móvel e de push no projeto Supabase correto. O histórico remoto de migrations do Jarvis precisa ser reconciliado com os prefixos locais antes de executar a migração; não fazer db push às cegas.

## Limites de presença

- WebSocket é o canal principal apenas enquanto a conexão estiver ativa.
- Se a conexão cair, o status diz que o canal do Jarvis está indisponível; isso não prova que o telefone perdeu internet.
- FCM é contingência de notificação, não uma conexão contínua nem garantia de fala imediata.
- A fala em segundo plano depende de permissão de notificação, prioridade efetiva da mensagem e das regras do Android. Se o sistema negar a execução, o app preserva a notificação em vez de contornar as restrições.
- O evento é efêmero (expiração de cinco minutos). Não enviar texto privado, tokens ou localização no payload FCM.

## Build

Requisitos: JDK 17, Android SDK Platform 35, Build Tools 35 e Gradle 8.13.

    gradle --no-daemon :app:assembleDebug

O workflow Android Mobile Build compila o APK de debug em CI. A validação final ainda requer APK instalado em telefone físico e testes de tela bloqueada, suspensão do processo, troca de rede, expiração de sessão e logout.
