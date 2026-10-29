# Jarvis Mobile — Android nativo

Cliente Android isolado do núcleo Jarvis. Não substitui o HUD, os conectores MCP nem os adaptadores de desktop.

## Incluído

- Interface nativa Jetpack Compose.
- Login por HTTPS em POST /v1/mobile/session/login; a senha não é persistida.
- Access token de 15 minutos e refresh token rotativo/revogável, cifrados com AES-GCM via Android Keystore.
- TTS local em português do Brasil.
- Presença WebSocket iniciada explicitamente pelo usuário, com notificação persistente, reconexão progressiva e renovação de sessão.
- Fila persistente de eventos no Supabase para sincronização quando o WebSocket autenticado reconecta.
- Push transporta apenas um ID opaco; o conteúdo é buscado por HTTPS autenticado.
- Ações remotas limitadas a speak, com texto limitado a 1.000 caracteres.
- Logout limpa as credenciais locais e tenta revogar sessão e registro push no servidor.

## Entrega de eventos

O APK não usa serviços de push externos. Quando o telefone está conectado, o Jarvis entrega notificações e fala pelo WebSocket autenticado. Quando está desconectado, o backend guarda o evento com TTL no Supabase; o aplicativo consulta a fila após reconectar e envia ACK após processar o evento.

A fila é entrega eventual, não notificação instantânea: se o Android encerrar ou restringir o serviço de presença, o evento aguarda até o app voltar a conectar. Não há tokens de provedor externo nem credenciais de push no build.

## Limites de presença

- WebSocket é o canal principal apenas enquanto a conexão estiver ativa.
- Se a conexão cair, o status diz que o canal do Jarvis está indisponível; isso não prova que o telefone perdeu internet.
- A fila é contingência persistente, não uma conexão contínua nem garantia de fala imediata.
- A fala em segundo plano depende de permissão de notificação, prioridade efetiva da mensagem e das regras do Android. Se o sistema negar a execução, o app preserva a notificação em vez de contornar as restrições.
- O evento é efêmero (expiração de dez minutos). O texto é armazenado somente no banco privado e entregue por API autenticada.

## Build

Requisitos: JDK 17, Android SDK Platform 35, Build Tools 35 e Gradle 8.13.

    gradle --no-daemon :app:assembleDebug

O workflow Android Mobile Build compila o APK de debug em CI. A validação final ainda requer APK instalado em telefone físico e testes de tela bloqueada, suspensão do processo, troca de rede, expiração de sessão e logout.
