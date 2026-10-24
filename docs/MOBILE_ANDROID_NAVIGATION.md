# Navegação Android — variante mobile do Jarvis

Escopo: **somente Android**, controlado a partir do host Windows. Referências de estudo: Minitap mobile-use (https://github.com/minitap-ai/mobile-use) e Google Artemis (https://github.com/google/artemis), ambos Apache 2.0. Nenhum código, prompt ou nome de arquivo deles é copiado.

## Camadas independentes

As camadas não se conhecem diretamente. Cada uma conversa só com a vizinha, por contrato.

| Camada | Estado | Onde |
|---|---|---|
| MCP | Existente (padrão), ganha grupo `mobile_*` | `app/adapters/edge/jarvis_desktop_mcp.py` (registro) |
| Tunelamento | Existente, sem alteração | Tailscale + Aperture (`scripts/start_jarvis_tailscale.ps1`) |
| Conexão ADB | **Novo** | `app/adapters/connection/adb_connection.py` |
| Navegação | **Novo**, usa a conexão | `app/adapters/edge/android_navigation_adapter.py` |
| Banco de dados | Existente, sem alteração | `Device` e `Capability` (`app/domain/models/device.py`) |

Fluxo: `modelo → MCP (mobile_*) → AndroidNavigationAdapter → AdbConnection → adb → aparelho`. O túnel só transporta a chamada MCP. O banco guarda quais aparelhos existem e o que cada um sabe fazer.

## Conexão ADB (`AdbConnection`)

Responsabilidades: executar comandos `adb -s <serial>` e devolver dados. Não sabe de MCP, túnel ou banco.

- `is_connected()`: `adb get-state` deve retornar `device`.
- `screencap_png()`: `exec-out screencap -p`, validando a assinatura PNG.
- `dump_hierarchy()`: `uiautomator dump /dev/tty`, sem instalar APK próprio.
- `tap`, `swipe`, `type_text`, `key_event`, `launch_app`, `force_stop`.

Validações: serial, coordenadas não negativas, nome de pacote, texto ASCII imprimível (espaços viram `%s`, metacaracteres do shell são escapados), e keycodes apenas de uma lista fechada.

O executor de comandos é injetável. Em produção usa `subprocess`; nos testes, um executor simulado.

## Navegação (`AndroidNavigationAdapter`)

Responsabilidades: transformar intenções de navegação em chamadas à conexão e devolver um status.

- `observe(serial)`: captura PNG e lista de elementos (resource-id, texto, descrição, centro de toque).
- `find(serial, resource_id|text)`: `found`, `not_found` ou `ambiguous`.
- `run_recipe(serial, steps)`: até 20 passos em ordem. Para no primeiro que não se confirma.

Passo: `{target, action, value?, verify?, wait_ms?}`, com ações `tap`, `type`, `key`, `launch`, `stop` e `swipe`. `verify` é a pós-condição: texto ou resource-id que deve existir depois da ação.

Ordem de alvo, igual à do desktop: resource-id ou texto primeiro. Não há fallback para coordenadas nesta versão. Templates visuais no Android ficam para uma fase posterior.

Vocabulário de status (igual ao da navegação visual): `observed`, `completed`, `found`, `not_found`, `ambiguous`, `postcondition_failed`, `invalid_recipe`, `unavailable`.

## Segurança

- Ações que enviam mensagens, pagam ou apagam dados exigem `user_confirmed`, no mesmo padrão de `click_at`. Ainda não implementado no adaptador; é o próximo passo antes de expor `mobile_tap` no MCP.
- Só aparelhos já registrados em `devices` podem ser controlados.
- Pareamento ADB Wi-Fi é manual.
- Nenhuma credencial no repositório.

## Testes

- `tests/adapters/connection/test_adb_connection.py`: 10 testes com executor simulado.
- `tests/adapters/edge/test_android_navigation_adapter.py`: 12 testes com conexão falsa.
- Suíte de adaptadores e `test_docs_references.py`: 389 passam, 4 pulados, sem regressões.

Teste em aparelho real não foi feito: o ambiente de desenvolvimento não tem aparelho conectado.

## Pendências

1. Registrar as ferramentas `mobile_observe`, `mobile_run_recipe`, `mobile_tap`, `mobile_type`, `mobile_press_key` e `mobile_launch_app` no servidor MCP existente.
2. Registrar as capacidades `mobile.observe` e `mobile.tap` na tabela `Capability`, vinculadas a cada `Device(type="mobile")`.
3. Exigir `user_confirmed` em ações sensíveis.
4. Validar em um aparelho real via USB e depois via Wi-Fi.
5. Se houver necessidade de reconhecimento visual no Android, reaproveitar o módulo de templates do desktop.
