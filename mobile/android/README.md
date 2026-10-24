# Jarvis Mobile — Android nativo

Primeiro incremento funcional e isolado do cliente Android, sem substituir o HUD, o adaptador Android/ADB ou os conectores MCP existentes.

## Incluído

- Interface nativa Jetpack Compose.
- Teste de voz local `pt-BR` via Android Text-to-Speech.
- Login via `POST /token` com HTTPS e OAuth2 form-urlencoded.
- Token de acesso cifrado com AES-GCM e chave mantida pelo Android Keystore.
- A senha existe apenas em memória durante o login e é limpa após a resposta.
- Logout local e rejeição de endpoints HTTP sem TLS.

## Ainda não incluído

- Canal de eventos/presença em segundo plano, FCM ou saudação PC→telefone.
- Registro do dispositivo no backend (a API existente não demonstra ainda isolamento de propriedade por usuário).
- Microfone sempre ativo, localização ou automação de UI.

Não se deve anunciar presença persistente até a autenticação do dispositivo, canal de eventos e testes de ciclo de vida estarem concluídos.

## Build local

Requisitos: JDK 17, Android SDK Platform 35, Build Tools 35 e Gradle 8.13.

    gradle :app:assembleDebug

O workflow `Android Mobile Build` compila o APK de debug em CI.
