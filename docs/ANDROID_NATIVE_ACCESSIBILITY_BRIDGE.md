# Ponte nativa de acessibilidade Android

## Arquitetura

`Secure MCP Tunnel → Termux Streamable HTTP MCP → 127.0.0.1:18766 → JarvisAccessibilityService`

O APK contém o executor Android. Termux só encaminha chamadas MCP para o loopback; não usa ADB e não controla a própria UI via shell.

## Ativação e pareamento

1. Instale/atualize o APK Jarvis Mobile compilado com esta integração.
2. Abra a aba **Acessibilidade** no aplicativo.
3. Toque em **Parear Termux e configurar acesso** e copie o segredo gerado no aparelho.
4. Volte e abra **Configurações de Acessibilidade**.
5. Ative manualmente **Jarvis Accessibility**. O Android exige esta concessão explícita.
6. No Termux, execute `bash scripts/android/configure_accessibility_bridge.sh` no checkout do repositório e cole o segredo quando solicitado.
7. Reinicie `jarvis-android-mcp` e valide `android_accessibility_status`.

O segredo é aleatório por instalação, armazenado nas preferências privadas do APK e em `~/.config/jarvis/accessibility/token` com permissão 600 no Termux. Não é enviado ao backend, ao Tunnel Control Plane ou aos logs. Para revogar, desative o serviço nas configurações Android e remova o arquivo de token do Termux; para rotacionar, limpe os dados do app ou implemente novo pareamento.

## Ferramentas MCP

- `android_accessibility_status`: estado do listener local e suporte a screenshot.
- `android_accessibility_snapshot`: árvore limitada a 300 nós e profundidade 12.
- `android_accessibility_screenshot`: JPEG base64, Android 11 ou superior.
- `android_accessibility_action`: `tap`, `swipe`, `click_text`, `click_view_id`, `set_text`, `back`, `home`, `recents`.

Ações são limitadas por schema, tamanho e timeout. Não há execução de shell, abertura arbitrária de apps, leitura de clipboard, captura de áudio ou extração de credenciais. O serviço pode ficar indisponível se o Android o encerrar ou se a permissão for revogada.

## Transporte e segurança

- Servidor TCP ligado exclusivamente a `127.0.0.1:18766`.
- Todas as rotas exigem Bearer token pareado.
- Corpo HTTP limitado a 32 KiB; timeout de leitura de socket de 5 s.
- Árvore da UI truncada; textos e descrições limitados.
- Gestos limitados a coordenadas positivas e duração de 80–1500 ms.
- O token nunca é retornado por ferramentas MCP nem escrito nos logs.
- O MCP lê o token do ambiente `JARVIS_ANDROID_ACCESSIBILITY_TOKEN` ou do arquivo privado Termux.

A autorização de Acessibilidade é poderosa: ela pode ler o conteúdo exibido em janelas e executar ações em nome do usuário. Mantenha-a desligada quando não estiver usando automação.
