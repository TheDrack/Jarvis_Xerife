# Jarvis OS — auditoria de capacidades contra a arquitetura alvo

**Status:** auditoria source-only, insumo para C0-CAPABILITY-MAP
**Data:** 2026-11-21
**Base auditada:** `main @ a9a80816aa1155af8f8ef4153c7efb985d25a104` (2026-11-20 20:48 -0300)
**Escopo:** árvore versionada (1.369 arquivos rastreados; 951 `.py`, 150 `.md`, 47 `.kt`, 326 arquivos `test_*.py`). Não houve inspeção autenticada de deploy, banco, dispositivos ou conectores externos, nem execução da suíte.

Este documento responde a uma pergunta específica: **o que já existe no `Jarvis_Xerife` que serve à arquitetura de um sistema operacional orientado a capacidades, o que precisa ser refatorado e o que ainda não existe** — sem iniciar uma segunda implementação.

---

## 1. Veredito

A hipótese arquitetural está correta, e o repositório **não precisa de um segundo sistema**: ele já contém o núcleo mais difícil (registro versionado de ferramentas, dispatcher com autorização fail-closed, portas de host, perfis de operação, runtime multiagente). O que falta não é código de execução — é **a camada que hoje não existe em nenhum lugar: a separação explícita entre capacidade, implementação, host, política e resultado, com resolução capability → host**.

Concretamente:

| Pergunta | Resposta sustentada pelo código |
|---|---|
| Existe contrato de capacidade? | Parcial, e em **cinco lugares incompatíveis** (§4). O único contrato tipado e executável é o `ToolManifest`, que amarra `capabilities` a um `adapter_id` fixo. |
| Existe abstração de host? | Sim, mas **somente leitura**: `HostPort` (`get_identity`, `get_resources`, `list_processes`) com um único implementador, `PsutilHostAdapter`. |
| Existe resolução capability → host? | **Não.** Nenhum caminho de execução escolhe host. O dispatcher resolve exatamente um `adapter_id` via Nexus. |
| Existe política? | Sim, a parte mais madura: `ToolAuthorizationPolicy`, `TrustedToolPrincipal`, `VerifiedToolApproval`, decisão vinculada a principal/sessão/tool/versão/capability/escopo/expiração, fail-closed. Cobertura real ainda estreita (§3, camada 4). |
| Existe execução observável (resultado/proveniência)? | Sim para o caminho do dispatcher (`ToolResult`, `ToolExecutionEvent`, `EvidenceRecord`). Não para os ~115 tools MCP, que não passam pelo dispatcher. |
| O sistema é host-independent? | **Não na prática.** O caminho de automação é Windows/pyautogui e Android/loopback; a inteligência é independente, a execução não. |
| O sistema é local-first? | **Parcial.** `requirements/core.txt` separa o núcleo de `host.txt` (só `psutil`), mas a coordenação multiagente só tem backend Supabase, e o núcleo carrega drivers de persistência. |

**Conclusão operacional:** não construir "Jarvis OS" como projeto novo. O trabalho é (a) unificar os cinco registros de capacidade em um só catálogo com namespaces distintos, (b) adicionar a dimensão `host` ao contrato que já existe, (c) normalizar a superfície de ~115 tools MCP em IDs canônicos de capacidade, e só então (d) extensão de host privilegiado e (e) imagem de SO.

---

## 2. Método

1. Leitura dos documentos canônicos: `ARCHITECTURE.md`, `docs/ARCHITECTURE.md`, `docs/STATUS.md`, `docs/JARVIS_OS_FOUNDATION.md`, `docs/architecture/JARVIS_OS_HARNESS.md`, `docs/architecture/ADR-001-universal-tool-registry.md`, `docs/skills-connectors/CAPABILITY_INVENTORY.md`.
2. Verificação no código de cada afirmação estrutural (assinaturas, campos de contrato, composition roots, implementadores, consumidores).
3. Contagem e classificação dos registros concorrentes de "capacidade".
4. Teste de mesa do caso `screen.capture` (§3), que é o critério decisivo da arquitetura proposta.
5. Comparação com os dez domínios exigidos (§5) e com os três princípios (§6).

Cada item recebeu um tratamento: **reaproveitar**, **estender**, **refatorar**, **aposentar** ou **construir**. Nenhum item foi alterado nesta auditoria.

---

## 3. O teste decisivo: `screen.capture`

A arquitetura proposta exige que o Jarvis peça `screen.capture` e o sistema escolha host, implementação e política. O que existe hoje:

| Superfície | Nome exposto | Implementação | Host |
|---|---|---|---|
| `app/adapters/edge/jarvis_desktop_mcp.py` | `observe_screen` | captura local + observe-after-action | Windows, sessão interativa |
| `app/adapters/edge/jarvis_desktop_mcp.py` | `android_observe_screen` | bridge de acessibilidade Android | Android, pareado |
| `app/adapters/edge/portas_visualizacao.py` | tools de visualização/CDP | Playwright/CDP | browser no host |
| `app/adapters/edge/hardware_controller.py` | `take_screenshot` | `pyautogui.screenshot()` | Windows/Linux com display |
| `mobile/android/.../JarvisAccessibilityService.kt` | endpoint loopback | AccessibilityService nativo | Android |

Nenhuma dessas superfícies declara "eu implemento a capacidade `screen.capture` no host X". O nome **é** a implementação (`android_observe_screen`), e o chamador precisa saber em qual host está. Isso é o oposto do princípio capability-first, e é a lacuna central do repositório.

O embrião mais próximo de roteamento por capacidade existe, mas **fora do caminho de execução**: `app/application/services/device_capability_service.py` faz `Capability.name == capability_name` sobre a tabela `devices`, filtrando `status == "online"` e usando proximidade (`network_id`, `lat`, `lon`). Ou seja: há um registro de dispositivos com capacidades em **texto livre** (`'camera'`, `'bluetooth_scan'`, `'local_http_request'` em `app/domain/models/device.py`), sem contrato tipado, sem política associada e sem ligação com `ToolRegistry`/`ToolDispatcher`.

---

## 4. Os cinco registros de capacidade (o problema estrutural)

| # | Registro | Onde | Volume | O que realmente é | Tratamento |
|---|---|---|---|---|---|
| 1 | Objetivos de auto-evolução | `data/capabilities.json`, `cap_001.py`…`cap_102.py`, `CapabilityManager`, `CapabilityIndexService`, `RoadmapMissionSelector` | 102 objetivos (68 `complete`, 21 `pending`, 13 `partial`) + 102 stubs de 11–24 linhas | Roadmap cognitivo, não capacidade executável. Os arquivos `cap_*.py` são componentes gerados sem semântica de operação (ex.: `cap_010.py` retorna `{'status': 'active'}`). | **Renomear/separar** (namespace `objective:`) |
| 2 | Catálogo de adapters (domínio) | `app/domain/models/adapter_registry.py` | 8 adapters fixos + descoberta em `data/nexus_registry.jrvs` | Lista curada à mão, `find_gap` por **substring**, `can_execute()` sempre `True` | **Aposentar** |
| 3 | Registro capability→adapter (aplicação) | `app/application/services/adapter_registry.py` | contrato exato, `required`/`optional`, `create_if_missing` | O mais próximo do alvo: capability ID exato → instâncias de adapter | **Estender** (é a base da dimensão host) |
| 4 | Aliases semânticos | `app/domain/models/capability_alias_registry.py` | capability canônica + alias + handler + permissão + confirmação + audit | Bom contrato de autorização/nomeação, **usado apenas em teste e exemplo de doc** | **Integrar** |
| 5 | Universal Tool Registry | `app/domain/tools/`, `config/tool_registry.json`, `app/runtime/toolbox/` | 12 manifests (10 `read_only`, 2 `active_bounded`) | Único contrato versionado e executável: schema JSON 2020-12, permissões, escopos, `credential_refs` (só referências), timeout, idempotência, política de saúde declarativa | **Reaproveitar** (fonte de verdade de execução) |

Observações que precisam entrar no plano de refatoração:

- **Duplicação ativa.** `CapabilityManager`, `CapabilityBlueprintService` e `CapabilityGapReporter` repetem a mesma geração de blueprint por regra (`if "memory" in name_lower: …`). O `CapabilityManager` ainda define `execute()` retornando `not_implemented` antes do `__init__` e é instanciado em `routers/utility.py`, `routers/evolution.py` e `core/llm_config.py` — ou seja, o caminho Nexus desses serviços entrega stub.
- **Escala desconectada.** 12 manifests no registry contra **115 tools MCP** (102 decoradores `@mcp.tool` em `app/adapters/edge`, 13 em `app/adapters/infrastructure`). A imensa maioria da superfície real de capacidades não está catalogada nem passa por autorização do dispatcher.
- **Dispatcher com cobertura estreita.** `ToolDispatcher` é instanciado em apenas três pontos: `app/adapters/edge/prospecting_mcp_tools.py`, `app/communication/dispatcher.py` e `app/runtime/pipeline_runner.py`. A política é resolvida por nome (`tool_authorization_policy`, `dispatcher.py:562`) e o adapter por `nexus.resolve(manifest.adapter_id)` (`dispatcher.py:342`) — **um único adapter, sem alternativa por host**.
- **Código morto executável.** `capabilities/classification.py` (raiz) tem `print()` e exemplo `JARVIS/SARA/ALEXA` no nível de módulo, duplicando o conceito de classificação.
- **Documentação divergente.** `docs/skills-connectors/CATALOG.md` diz "dez ferramentas"; `CAPABILITY_INVENTORY.md` diz 12 (correto hoje: 12).

---

## 5. Cobertura dos dez domínios

| Domínio exigido | O que existe hoje | Lacuna para o alvo |
|---|---|---|
| **Computação** (CPU, GPU, RAM, processos) | `HostPort` + `PsutilHostAdapter` (identidade, recursos, discos, swap, processos ordenados por memória) | Sem GPU, sem ações (prioridade, cgroup, encerrar processo), sem host remoto |
| **Sistema** (arquivos, usuários, permissões, serviços, boot, recuperação) | `linux/provision-jarvis-os.sh`, units systemd de usuário (`jarvis-api`, `jarvis-mcp`), `run_shell_command`, `host_ops_mcp_tools.py` | Sem gerenciamento de serviço tipado, sem boot/recuperação, sem portas de usuário/permissão |
| **Rede** (Wi-Fi, BT, VPN, SSH, protocolos) | `network_discovery_adapter`, `mdns/udp` discovery, `network_protocol_inspector`, ETW (Windows), Android VPN/SOCKS5/flow attribution | Sem contrato de capacidade de rede; implementações por plataforma sem seleção por host |
| **Interface** (HUD, desktop, terminal, voz, câmera, tela, acessibilidade) | MCP desktop (observação, clique, teclado, acessibilidade UIA), Android Accessibility, HUD Kotlin, TTS/voz, Portas/CDP | Cada superfície nomeada por implementação; nenhuma declara capacidade/host |
| **Automação** (mouse, teclado, apps, browser) | `automation_adapter`, `keyboard_adapter`, `visual_navigation_adapter`, `portas_*`, receitas visuais | Acoplamento direto a `pyautogui` (10 módulos mencionam, inclusive `app/application/services/soldier_registry.py` e `app/core/config.py`) |
| **Inteligência** (LLM, agentes, memória, planejamento) | `ModelProfile`/`ModelRegistry` (multiagente), `ModelRuntime` port + adapter FreeLLMAPI, `AIGateway`/`LLMRouter`, memória working/semantic/prospective, `multiagent/` (scheduler, queue, transport, worker, execution_plan) | `AIGateway`/`LLMRouter` ainda com defaults por provider (documentado em `JARVIS_OS_HARNESS.md` §4); seleção por capability é só elegibilidade |
| **Desenvolvimento** (Python, compiladores, testes, Git, deploy) | `pipeline_runner`, pipelines YAML, GitHub worker, shell persistente, scripts de evolução | Sem toolchain como capacidade de host; pipeline legado não migrado integralmente |
| **Segurança** (identidade, autorização, isolamento, auditoria, política) | `ToolAuthorizationPolicy` fail-closed, `TrustedToolPrincipal`, `VerifiedToolApproval`, `CapabilityAuthorizer` legado, audit de execução | Política de produção não registrada (ADR-001); MCP não passa pelo dispatcher; `CapabilityAuthorizer` booleano ainda presente |
| **Dispositivos** (sensores, áudio, localização, notificações) | App Android nativo (47 arquivos `.kt`): Accessibility, VPN, SOCKS5, localização, HUD, `TokenVault`; `device.py`/`DeviceCapabilityService`; MQTT | Capacidades do dispositivo em texto livre, sem contrato, sem política por operação |
| **Distribuição** (instalação, update, sync, recuperação) | Provisionador Linux + verificação + units; instalador Windows/PyInstaller | Sem imagem, bootloader, canal de atualização, recuperação; provisionador declara explicitamente não particionar disco |

O que existe, portanto, cobre **execução** em quase todos os domínios e **administração de capacidade** em praticamente nenhum.

---

## 6. Os três princípios, avaliados

**Capability-first — parcial.** Existe o lugar correto (`app/domain/tools/contracts.py`) e ele é bom: identidade estável, versão semântica, capabilities como tuplas de IDs, políticas declarativas, `credential_refs` apenas por referência. Mas a capacidade é atributo de uma ferramenta com implementação fixa, e a superfície MCP (115 tools) não usa esse contrato. O sistema é, hoje, *tool-first com metadado de capability*.

**Host-independent — não.** A inteligência e a orquestração são portáveis (Nexus, registry, scheduler, `ModelRuntime`), mas a execução não: captura, clique, teclado e shell são Windows/pyautogui ou Android/loopback. `HostPort` só observa. Não há noção de "capacidade disponível no host A, indisponível no host B, com limitação declarada".

**Local-first — parcial.** A separação `requirements/core.txt` × `requirements/host.txt` (apenas `psutil`) é real e o provisionador roda sem root. Mas: (a) `core.txt` ainda arrasta `psycopg2-binary` e `duckdb`; (b) o pacote multiagente só tem `supabase_queue.py`/`supabase_store.py`, sem backend de fila local; (c) os perfis (`app/core/operating_profiles.py`, 4 perfis com flags independentes `requested/available/enabled/authorized/tested`, só stdlib) são **relatório**, não ativação — o que é correto, mas significa que "local-first" ainda não foi exercitado como caminho de execução.

---

## 7. O que aproveitar (sem tocar)

1. `app/domain/tools/contracts.py` + `app/domain/tools/registry.py` — contrato de manifest versionado, resolução por `(tool_id, version)` exata, cópias defensivas, rejeição de duplicata.
2. `app/runtime/toolbox/` — dispatcher, `host_authorization.py`, `audit.py`, `toolchains.py`. É a fronteira de execução correta e já falha fechada.
3. `app/application/services/adapter_registry.py` — capability exata → adapter, gap `required`/`optional`, `create_if_missing`. É a semente da resolução capability → implementação.
4. `app/core/operating_profiles.py` — modelo de evidência separada por perfil (`harness`, `autonomy`, `host`, `jarvis-os`). Não confundir com autorização; já está correto nesse ponto.
5. `app/domain/ports/host_port.py` + `PsutilHostAdapter` — contrato de host somente leitura, testado (`tests/domain/test_host_port.py`).
6. `app/domain/models/capability_alias_registry.py` — alias → capability canônica com permissão e confirmação preservadas no audit.
7. `linux/` — provisionamento idempotente, units de usuário, loopback + bearer token.
8. `mobile/android/` — cliente nativo com permissões e consentimentos reais; é o modelo correto de "host Android", não um userland Ubuntu fingindo acesso ao kernel.

---

## 8. O que refatorar (ordem obrigatória, sem implementação paralela) — [ADR-006](ADR-006-capability-implementation-host-policy-boundaries.md)

**R1 — Um catálogo, três namespaces.** Manter `config/tool_registry.json` como catálogo de execução; renomear `data/capabilities.json` para o que ele é (objetivos/roadmap) e prefixar IDs (`objective:CAP-001`) para impedir colisão com `capability:screen.capture`. Não apagar histórico; corrigir os 68 `complete` heurísticos para um estado que exija evidência de execução. *Aceite:* nenhum consumidor compara os dois namespaces; `RoadmapMissionSelector` continua funcionando.

**R2 — Um registro de adapters.** Aposentar `app/domain/models/adapter_registry.py` (substring, `can_execute() == True`) e manter o de aplicação. *Aceite:* nenhuma chamada a `find_gap` por substring; teste de gap exato cobre `required`/`optional`.

**R3 — Fim da duplicação de blueprint.** `CapabilityManager`, `CapabilityBlueprintService` e `CapabilityGapReporter` passam a delegar a uma implementação única; remover `execute()` stub dos serviços que são casos de uso reais ou implementá-lo de forma explícita. *Aceite:* um único gerador de blueprint; testes existentes de `test_capability_manager.py` mantidos e verdes.

**R4 — Integrar o alias registry.** Usá-lo na normalização de intenção → capability canônica, não como camada decorativa. *Aceite:* um caminho real resolve alias e registra audit com alias + ID canônico.

**R5 — Normalizar a superfície MCP.** Gerar, a partir dos 115 tools, um mapa `tool MCP → capability_id canônica → host`. Primeiro **somente leitura** (relatório de cobertura), sem reescrever os adapters. *Aceite:* relatório mostra quais capabilities têm 0, 1 ou N implementações por host, e quais tools ficam sem capability (dívida explícita).

**R6 — Remover código morto.** `capabilities/classification.py` (raiz). *Aceite:* nenhuma importação; nenhum efeito colateral em import.

**R7 — Corrigir documentação divergente.** `CATALOG.md` ("dez ferramentas") vs 12 manifests reais; e o `AGENTS.md`/catálogo devem apontar para esta auditoria como insumo, não como estado.

---

## 9. O que construir (e só isto) — [ADR-006](ADR-006-capability-implementation-host-policy-boundaries.md)

**C1 — Contrato de vínculo capacidade × host × implementação.** Extensão de `adapter_registry` (não um novo registro): `CapabilityBinding { capability_id, host_ref, adapter_id, availability, limitations, policy_class }` e um resolvedor que recebe `(capability, host solicitado | qualquer)` e devolve candidatos ordenados **ou** um `CapabilityGap` explícito com motivo. Regra dura: ausência de implementação no host é resposta de primeira classe, nunca fallback silencioso. *Aceite:* dois hosts fictícios, um sem `screen.capture` → `unavailable` com motivo; nenhuma mudança de comportamento no dispatcher até teste de paridade.

**C2 — Dimensão host no caminho de execução.** Só depois de C1: permitir que um `ToolManifest` declare alternativas por host e que o dispatcher escolha uma, mantendo exatamente a mesma decisão de autorização (host não pode ampliar escopo). *Aceite:* dois adapters coexistem; política nega por host quando o escopo não cobre; resultado registra qual implementação executou.

**C3 — Host privilegiado tipado.** `HostPort` permanece read-only. Operações de escrita (serviços, pacotes, armazenamento) entram em porta separada com broker, allowlist e aprovação — nunca shell arbitrário vindo do modelo (já é a regra do `JARVIS_OS_HARNESS.md` §6). *Aceite:* operação crítica exige aprovação verificada e produz journal.

**C4 — Journal de execução durável.** Hoje idempotência, rate limit, circuit breaker e audit JSONL são locais ao processo. Para "resultado: o que foi efetivamente executado" com valor de SO, precisa ser durável/compartilhado. *Aceite:* reinício não perde evidência; idempotência sobrevive a restart.

**C5 — Camada de SO real.** `linux/` é provisionamento de runtime, não distribuição: falta imagem reproduzível, boot, instalador, canal de atualização e recuperação. É o último item, e o `JARVIS_OS_FOUNDATION.md` já o condiciona a testes em VM descartável.

---

## 10. Riscos de executar fora de ordem

- **Criar o "capability system" como sexto registro.** É o risco mais provável, porque os cinco existentes parecem incompletos. Qualquer novo módulo de capacidade que não estenda `adapter_registry` + `ToolManifest` reproduz o problema.
- **Confundir relatório de perfil com autorização.** `operating_profiles.py` é correto justamente porque não ativa nada. Ativar `jarvis-os` a partir de configuração seria regressão de segurança.
- **Declarar paridade Android/Linux.** Termux/APK não dá acesso ao kernel Android; o repositório não tem `proot` e não deve apresentar userland como equivalência.
- **Fechar C0 no ledger sem evidência imutável.** `docs/STATUS.md` exige commit, execução de Actions, implementação, consumidor e testes. Esta auditoria é insumo; não altera o ledger e não desbloqueia C1.

---

## 11. Evidência coletada

- Contagem de arquivos, extensões e testes: `git ls-files`, `find tests -name "test_*.py"`.
- `config/tool_registry.json`: 12 manifests, 10 `read_only` / 2 `active_bounded`; adapters `public_intelligence_adapter` (4), `telegram_adapter` (2), `network_discovery_adapter` (2), `prospecting_adapter` (2), `drive_uploader` (1), `openai.chatgpt_plan` (1).
- `data/capabilities.json`: 102 objetivos, 68 `complete` / 21 `pending` / 13 `partial`, campos `id,title,description,status,auto,priority,depends_on,notes`.
- `app/domain/capabilities/cap_*.py`: 102 arquivos, 11–24 linhas, `NexusComponent` sem operação.
- `@mcp.tool`: 102 em `app/adapters/edge`, 13 em `app/adapters/infrastructure`.
- `ToolDispatcher(`: 3 instanciações (`prospecting_mcp_tools.py:45`, `communication/dispatcher.py:52`, `runtime/pipeline_runner.py:142`).
- `HostPort`: 1 implementador (`PsutilHostAdapter`), 2 testes.
- `pyautogui`: referências em 10 módulos, incluindo fora de `app/adapters`.
- `proot`: nenhuma ocorrência no repositório.
- Perfis: `app/core/operating_profiles.py`, 4 perfis, flags independentes, apenas stdlib.

**Não verificado nesta auditoria:** execução da suíte, CI atual, deploy Render, schema/RLS Supabase, worker multiagente ativo, conectores externos, builds Android/Desktop, comportamento real de permissões em dispositivo, disponibilidade de qualquer provider LLM. Nada foi alterado em código; nenhum teste foi executado.

---

## 12. Próximo passo recomendado

§8 e §9 estão registrados como decisão em [ADR-006 — fronteiras entre capacidade, implementação, host e política](ADR-006-capability-implementation-host-policy-boundaries.md), com R1–R7 como pré-requisitos e C1–C5 como incrementos independentes e testáveis. Nenhum código de implementação foi escrito. O critério de sucesso do conjunto não é "o Jarvis OS existe", e sim: **`screen.capture` resolve para implementações diferentes em hosts diferentes, com disponibilidade, limitação, política e resultado observáveis separadamente.**
