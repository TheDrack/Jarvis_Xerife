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

## Shell Termux remoto (opt-in)

O MCP Android também pode expor execução Bash geral no contexto **não-root do aplicativo Termux**. Isso é separado do AccessibilityService e não usa ADB.

### Ativação local

1. Atualize o checkout Termux para uma revisão que contenha esta integração.
2. Execute `bash scripts/android/configure_termux_shell.sh enable`. O script grava `JARVIS_ANDROID_SHELL_ENABLED=1` em `~/.config/jarvis/android-mcp/server.env` com modo 600 e reinicia o serviço MCP.
3. Se uma sessão anterior ainda estiver ativa, revogue-a primeiro:
   `python -m app.adapters.infrastructure.session_authorization revoke`
4. Em cada sessão, emita um código de pareamento local:
   `python -m app.adapters.infrastructure.session_authorization create --profile termux_developer --ttl-minutes 30`
5. Use a ferramenta MCP `android_shell_session_authenticate` uma única vez com o código. O código é consumido; a sessão expira no prazo indicado.
6. Execute comandos com `android_shell_exec`. Para encerrar antes do prazo, use `android_shell_session_revoke`.

Para desativar a ferramenta e reiniciar o serviço:
`bash scripts/android/configure_termux_shell.sh disable`

### Contrato e limites

- O shell executa Bash arbitrário como o UID normal do Termux; não solicita root nem chama `su`/`sudo` por conta própria.
- O perfil `termux_developer` recebe somente `android.shell.exec`; não herda capacidades do host Windows.
- Pareamento de uso único, no máximo cinco tentativas, sessão revogável e TTL de 5 a 120 minutos.
- Um comando por vez; timeout máximo de 120 segundos; stdout limitado a 32 KiB e stderr a 16 KiB.
- O log local `~/.local/state/jarvis/android_shell_audit.jsonl` registra sessão, hashes do comando/diretório, duração e resultado, sem armazenar comando ou saída. Arquivo modo 600 e diretório modo 700.
- O shell tem acesso a tudo que o usuário Termux consegue acessar. Isso inclui arquivos privados e credenciais armazenadas no sandbox Termux. Não use esta ferramenta para imprimir chaves, tokens ou arquivos de credenciais no chat. O código de pareamento também é um segredo bearer: é de uso único e curto prazo, mas pode aparecer no histórico de ferramentas do cliente.
- A ferramenta permanece desabilitada por padrão e só aparece no catálogo MCP quando o opt-in local estiver ativo.

A sessão autenticada é uma autorização temporária para comandos com efeitos colaterais. Antes de comandos destrutivos, alterações de credenciais, remoção de arquivos ou mudanças de serviços, confirme o alvo e o impacto. O executor não oferece isolamento por diretório: o limite de segurança é o sandbox Android/Termux e o UID do aplicativo.
