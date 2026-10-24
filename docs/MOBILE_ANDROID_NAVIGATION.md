# Navegação Android — variante mobile do Jarvis

Escopo: **somente Android**, controlado a partir do host Windows. Referências de estudo: Minitap mobile-use (https://github.com/minitap-ai/mobile-use) e Google Artemis (https://github.com/google/artemis), ambos Apache 2.0. Nenhum código, prompt ou nome de arquivo deles é copiado.

## Camadas independentes

| Camada | Estado | Onde |
|---|---|---|
| MCP | Existente; ganha o grupo `mobile_*` | `app/adapters/edge/jarvis_desktop_mcp.py` chama `register_mobile_tools` |
| Ferramentas mobile | **Novo** | `app/adapters/edge/mobile_mcp_tools.py` |
| Tunelamento | Existente, sem alteração | Tailscale + Aperture (`scripts/start_jarvis_tailscale.ps1`) |
| Conexão ADB | **Novo** | `app/adapters/connection/adb_connection.py` |
| Navegação | **Novo**, usa a conexão | `app/adapters/edge/android_navigation_adapter.py` |
| Banco de dados | Existente; ganha capacidades | `Device` e `Capability`, via `app/application/services/mobile_capability_service.py` |

Fluxo: `modelo → MCP (mobile_*) → AndroidNavigationAdapter → AdbConnection → adb → aparelho`. O túnel só transporta a chamada MCP. O banco guarda quais aparelhos existem e o que cada um sabe fazer.

O grupo mobile não importa dependências de desktop (pyautogui/opencv), então é testável isoladamente.

## Ferramentas MCP

- `mobile_observe(device_id)`: PNG da tela como bloco de imagem MCP, mais elementos da hierarquia.
- `mobile_find_element(device_id, resource_id|text)`: informa se há exatamente um alvo. Não toca.
- `mobile_tap(device_id, resource_id|text, user_confirmed)`: toca em um alvo único.
- `mobile_type(device_id, text, user_confirmed)`: digita texto ASCII no campo focado.
- `mobile_press_key(device_id, keycode)`: apenas teclas permitidas (3, 4, 24, 25, 66, 67, 187, 223, 224).
- `mobile_launch_app(device_id, package)`: abre app pelo nome do pacote.
- `mobile_run_recipe(device_id, steps, user_confirmed)`: até 20 passos com pós-condição.

Após ações concluídas ou falhas que deixam a tela incerta, a resposta traz uma captura nova.

## Conexão ADB (`AdbConnection`)

Executa `adb -s <serial>`. Não sabe de MCP, túnel ou banco.

- `is_connected()`: `adb get-state` deve retornar `device`.
- `screencap_png()`: `exec-out screencap -p`, validando a assinatura PNG.
- `dump_hierarchy()`: `uiautomator dump /dev/tty`, sem instalar APK próprio.
- `tap`, `swipe`, `type_text`, `key_event`, `launch_app`, `force_stop`.

Validações: serial, coordenadas não negativas, nome de pacote, texto ASCII imprimível (espaços viram `%s`, metacaracteres do shell são escapados) e keycodes de lista fechada.

## Navegação (`AndroidNavigationAdapter`)

- `observe(serial)`: captura PNG e elementos (resource-id, texto, descrição, centro de toque).
- `find(serial, resource_id|text)`: `found`, `not_found` ou `ambiguous`.
- `run_recipe(serial, steps, user_confirmed)`: valida todos os passos antes de executar; para no primeiro que não se confirma.

Passo: `{target, action, value?, verify?, wait_ms?, sensitive?}`. Ações: `tap`, `type`, `key`, `launch`, `stop`, `swipe`.

Ordem de alvo, igual à do desktop: resource-id ou texto. Sem fallback para coordenadas nesta versão.

Vocabulário de status (igual ao da navegação visual): `observed`, `completed`, `found`, `not_found`, `ambiguous`, `postcondition_failed`, `invalid_recipe`, `unavailable`, `confirmation_required`.

## Confirmação para ações sensíveis

Um passo é sensível se tiver `sensitive: true` ou se alvo, texto ou valor contiverem termos de efeito externo: enviar, send, pagar, pay, comprar, buy, transferir, transfer, excluir, apagar, delete, remove, publicar, publish, confirmar, confirm, sair, logout, sign out.

- Sem `user_confirmed=true`, a receita inteira é recusada com `confirmation_required` antes de qualquer passo. Nenhuma ação parcial acontece.
- A checagem usa o texto do alvo, não só o resource-id. Por isso `com.app:id/send` também exige confirmação.
- Termos são uma primeira barreira, não uma garantia. A decisão final é do usuário, que autoriza cada chamada.

## Capacidades no banco

`ensure_mobile_capabilities(session, device)` cria, para um `Device` do tipo `mobile`, as capacidades `mobile.observe`, `mobile.tap`, `mobile.type`, `mobile.key` e `mobile.launch_app`. É idempotente e rejeita dispositivos de outro tipo ou não persistidos.

Capacidades são descritivas. Cada chamada ainda passa pela confirmação acima.

## Testes

- `tests/adapters/connection/test_adb_connection.py`: 10 testes com executor simulado.
- `tests/adapters/edge/test_android_navigation_adapter.py`: 14 testes com conexão falsa.
- `tests/adapters/edge/test_mobile_mcp_tools.py`: 9 testes do servidor MCP real (FastMCP) com a conexão falsa.
- `tests/application/test_mobile_capability_service.py`: 3 testes em SQLite.
- Suíte de adaptadores, aplicação e verificação de documentação: 750 passam, 4 pulados.
- Integração: o servidor desktop, com dependências Windows simuladas, publica 20 ferramentas, sendo 7 `mobile_*`.

Não foi testado em aparelho real: o ambiente não tem aparelho conectado.

## Pendências

1. Testar em um aparelho Android real, por USB e depois por Wi-Fi.
2. Chamar `ensure_mobile_capabilities` no fluxo de registro de dispositivos (`DeviceService.register_device`) quando o tipo for `mobile`.
3. Ampliar a lista de termos sensíveis conforme o uso real.
4. Se houver necessidade de reconhecimento visual no Android, reaproveitar o módulo de templates do desktop.

## Requisito de ambiente

O pacote `mcp` precisa ser `<2` (API FastMCP v1). A versão 2 renomeou `FastMCP` para `MCPServer`.
