# Jarvis Mobile — Android nativo

Cliente Android isolado do núcleo Jarvis. Não substitui o HUD, os conectores MCP nem os adaptadores de desktop.

## Incluído

- Interface nativa Jetpack Compose.
- Aba **HUD** com a mesma página do HUD do app desktop (`app/static/jarvis-desktop.html`) em um WebView: briefing, globo com zoom e dispositivos, câmeras e Universal Intelligence. O endereço do núcleo local (LAN ou Tailscale, porta 8777) é informado pelo operador, fica salvo no dispositivo e o pareamento acontece no próprio HUD com o código de seis dígitos. O token vive no `sessionStorage` do WebView, não no armazenamento do app.
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

## HUD no WebView e cleartext

O núcleo Jarvis Desktop não expõe listener TLS: o HUD é servido em HTTP simples
na LAN/Tailscale. Por isso o manifesto declara
`android:networkSecurityConfig="@xml/network_security_config"` com
`cleartextTrafficPermitted="true"` e `usesCleartextTraffic="true"`. Essa
configuração apenas libera HTTP; as âncoras de confiança continuam sendo as do
sistema e nenhuma validação de certificado é desativada. Se o núcleo for
publicado atrás de um reverse proxy TLS, volte `usesCleartextTraffic` para
`false` e remova o arquivo.

O HUD é a mesma página do desktop, portanto não há segunda implementação de
globo, briefing ou Universal Intelligence para manter em sincronia. O WebView
depende de `javaScriptEnabled` e `domStorageEnabled` (token de sessão); não há
ponte JavaScript exposta ao conteúdo remoto.

A página pede `navigator.geolocation` para ancorar clima e manchetes regionais
nas coordenadas do telefone. O WebView habilita a API via
`WebSettings.setGeolocationEnabled(true)`, mas concede permissão apenas quando
`onGeolocationPermissionsShowPrompt` recebe esquema, host e porta efetiva
exatamente iguais aos da origem configurada do HUD. A comparação não usa
prefixos. A aba também pede a permissão Android ao abrir; se você negar, o HUD
cai para a região configurada no núcleo e informa isso na tela.

## Testes Android

`HudTargetTest` cobre a normalização do endereço do HUD (esquema ausente, HTTPS,
caminho/consulta descartados e entradas inválidas), além da comparação exata de origem usada pela permissão de geolocalização. A compilação e a execução
desses testes exigem Gradle e o Android SDK, que não estão disponíveis neste
ambiente de trabalho; o workflow de CI compila o APK de debug.

## Build

Requisitos: JDK 17, Android SDK Platform 35, Build Tools 35 e Gradle 8.13.

    gradle --no-daemon :app:assembleDebug

O workflow Android Mobile Build compila o APK de debug em CI. A validação final ainda requer APK instalado em telefone físico e testes de tela bloqueada, suspensão do processo, troca de rede, expiração de sessão e logout.
