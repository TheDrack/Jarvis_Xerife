# ADR-006 — Fronteiras entre capacidade, implementação, host e política

- **Status:** Aceito; C1 e C2 implementados e testados localmente (ver [Estado de implementação](#estado-de-implementação-2026-11-21)). R1 parcial, R2/R4/R5 e C3–C5 pendentes.
- **Data:** 2026-11-21
- **Depende de:** [ADR-001](ADR-001-universal-tool-registry.md) (Universal Tool Registry, dispatcher fail-closed)
- **Insumo:** [Jarvis OS — auditoria de capacidades](JARVIS_OS_CAPABILITY_AUDIT.md) §4, §8 e §9
- **Escopo:** define vocabulário, fronteiras e ordem de execução. Não altera código, registro, política de produção nem o ledger de [STATUS.md](../STATUS.md).

## Contexto

A auditoria mostrou que o repositório já possui o núcleo difícil — contrato de ferramenta versionado, dispatcher com autorização fail-closed, porta de host somente leitura, perfis de operação — mas não possui a distinção que a arquitetura alvo exige: **capacidade, implementação, host e política são hoje a mesma coisa em vários pontos do código**.

Evidências que motivam esta decisão:

- `screen.capture` não existe como identificador. Existem `observe_screen`, `android_observe_screen`, `take_screenshot` e endpoints de acessibilidade — o **nome da tool é a implementação**, e o chamador precisa saber o host.
- `ToolManifest` amarra `capabilities` a um `adapter_id` fixo; o dispatcher resolve exatamente um adapter via `nexus.resolve(manifest.adapter_id)`. Não há alternativas por host nem resposta explícita de indisponibilidade.
- A política é resolvida por nome de tool e vinculada a principal/sessão/tool/versão/capability/escopo, mas ainda não existe dimensão de host na decisão.
- Cinco registros de "capacidade" concorrentes (§4 da auditoria) usam o mesmo vocabulário para coisas diferentes: objetivos de roadmap, catálogo de adapters, mapeamento capability→adapter, aliases e tools executáveis.
- `app/application/services/adapter_registry.py` já é um mapeamento capability exata → instâncias de adapter, e é a semente correta para a dimensão host — não um motivo para criar um sexto registro.

Sem uma fronteira explícita, cada incremento futuro tende a recriar o problema: um novo módulo de capacidade que não estenda `adapter_registry` + `ToolManifest`.

## Decisão

### 1. Cinco registros conceituais distintos

Toda contribuição ao caminho de execução deve distinguir explicitamente:

| Registro | Pergunta que responde | Identidade | Onde vive hoje (alvo) |
|---|---|---|---|
| **Capacidade** | *O que* o sistema sabe fazer | `capability:screen.capture` (namespace `capability:`) | `ToolManifest.capabilities` + `adapter_registry` (aplicação) |
| **Implementação** | *Como* a capacidade é realizada | `adapter_id` estável (ex.: `psutil_host_adapter`) | `ToolManifest.adapter_id`, adapters Nexus |
| **Host** | *Onde* a implementação roda | `host_ref` estável (ex.: `host:windows-workstation`, `host:android-pixel`) | dimensão nova em `adapter_registry`, origem em `HostPort`/dispositivos |
| **Política** | *Quem* pode, com qual escopo e aprovação | `policy_class` + decisão vinculada a principal/sessão/tool/versão/capability/escopo/expiração | `ToolAuthorizationPolicy`, `TrustedToolPrincipal`, `VerifiedToolApproval` |
| **Resultado** | *O que efetivamente aconteceu* | `ToolResult` + `ToolExecutionEvent`/`EvidenceRecord` | dispatcher, `runtime/toolbox/audit.py` |

Regras de vocabulário:

- Identificadores de capacidade usam namespace explícito e ponto: `capability:screen.capture`. IDs de objetivo usam `objective:CAP-001`.
- Objetivos de auto-evolução (`data/capabilities.json`, `cap_*.py`) **não** são capacidades executáveis e não compartilham namespace com elas.
- Um nome de tool MCP não é um ID de capacidade. `android_observe_screen` é uma implementação; a capacidade é `capability:screen.capture` no host Android.
- Nenhum registro novo é criado por este ADR; a fonte de verdade de execução continua sendo `config/tool_registry.json` + `ToolManifest`.

### 2. Invariantes de fronteira

1. **Capacidade não conhece host nem implementação.** O chamador pede `(capability, host solicitado | qualquer)`; nunca escolhe `adapter_id` diretamente para contornar a resolução.
2. **Implementação declara o que realiza e onde.** Uma implementação que não declara `capability` e `host_ref` não é elegível para roteamento; permanece dívida explícita.
3. **Host não amplia política.** A escolha de host/implementação é posterior e subordinada à decisão de autorização; ela não pode relaxar escopo, classe de operação, aprovação ou expiração.
4. **Ausência é resposta de primeira classe.** Se nenhuma implementação atende `(capability, host)`, o resultado é `CapabilityGap`/`unavailable` com motivo declarado. Proibido fallback silencioso para outra implementação, outro host ou outro caminho de execução.
5. **Política é fail-closed e independente do registro.** Pertencer ao catálogo, a uma allowlist ou a um host não autoriza execução (ADR-001).
6. **Resultado é observável e atribuível.** Todo resultado de execução registra qual capacidade foi pedida, qual implementação e host executaram, qual decisão de política se aplicou e qual evidência foi produzida — sem segredos.
7. **Disponibilidade, limitação e teste são estados separados.** `availability`, `limitations`, perfil de operação e evidência de teste não se substituem mutuamente, e nenhum deles é autorização.
8. **Observação e ação são portas distintas.** `HostPort` permanece somente leitura; operações privilegiadas de escrita exigem porta separada com broker, allowlist e aprovação verificada.
9. **Paridade não é presumida.** Um host pode declarar limitações ou não implementar a capacidade. Android via app nativo/Termux não é apresentado como acesso equivalente ao kernel de um host Linux.

### 3. Contrato de resolução (forma, não implementação)

A resolução capability → host retorna uma de duas coisas:

- **candidatos ordenados**, cada um com `capability_id`, `host_ref`, `adapter_id`, `availability`, `limitations`, `policy_class`;
- **gap explícito**, com `capability_id`, host consultado e motivo (`no_implementation`, `host_offline`, `capability_not_declared`, `policy_denied`).

A ordem dos candidatos é determinística e declarada; o dispatcher só executa depois da decisão de política. Este ADR fixa a forma do contrato e as invariantes, **não** o schema final, os campos obrigatórios em código, nem a estratégia de ordenação — isso pertence a C1.

## Pré-requisitos de refatoração (R1–R7)

Executar antes de qualquer incremento de construção, na ordem abaixo. Cada item tem critério de aceite verificável; nenhum autoriza código paralelo.

| ID | Refatoração | Aceite |
|---|---|---|
| **R1** | Um catálogo, três namespaces: `config/tool_registry.json` permanece catálogo de execução; `data/capabilities.json` passa a ser explicitamente roadmap/objetivos com IDs `objective:`. Não apagar histórico. | Nenhum consumidor compara os dois namespaces; `RoadmapMissionSelector` continua funcionando; os 68 `complete` heurísticos passam a exigir evidência de execução. |
| **R2** | Um registro de adapters: aposentar `app/domain/models/adapter_registry.py` (substring, `can_execute() == True`); manter o de aplicação. | Nenhuma chamada a `find_gap` por substring; teste de gap exato cobre `required`/`optional`. |
| **R3** | Fim da duplicação de blueprint entre `CapabilityManager`, `CapabilityBlueprintService` e `CapabilityGapReporter`; um único gerador; remover ou implementar explicitamente o `execute()` stub. | Um único gerador de blueprint; `test_capability_manager.py` mantido e verde. |
| **R4** | Integrar o alias registry na normalização intenção → capacidade canônica, não como camada decorativa. | Um caminho real resolve alias e registra audit com alias + ID canônico. |
| **R5** | Normalizar a superfície MCP: mapa `tool MCP → capability_id → host`, primeiro **somente leitura** (relatório de cobertura), sem reescrever adapters. | Relatório mostra capabilities com 0, 1 ou N implementações por host e lista as tools sem capacidade como dívida explícita. |
| **R6** | Remover código morto: `capabilities/classification.py` (raiz), com `print()` em nível de módulo. | Nenhuma importação; nenhum efeito colateral em import. |
| **R7** | Corrigir documentação divergente: `docs/skills-connectors/CATALOG.md` ("dez ferramentas") vs 12 manifests reais; apontar a auditoria como insumo, não como estado. | Catálogo e inventário concordam com o registry; auditoria citada como evidência datada. |

## Incrementos de construção (C1–C5)

Somente depois dos pré-requisitos aplicáveis. Cada incremento é independente, testável e não pressupõe o seguinte.

| ID | Incremento | Aceite |
|---|---|---|
| **C1** | Contrato de vínculo capacidade × host × implementação, como **extensão** de `adapter_registry`: `CapabilityBinding { capability_id, host_ref, adapter_id, availability, limitations, policy_class }` e resolvedor `(capability, host \| qualquer)` com candidatos ordenados ou gap explícito. | Dois hosts fictícios, um sem `screen.capture` → `unavailable` com motivo; nenhuma mudança de comportamento no dispatcher antes do teste de paridade. |
| **C2** | Dimensão host no caminho de execução: `ToolManifest` declara alternativas por host e o dispatcher escolhe uma, mantendo idêntica a decisão de autorização. | Dois adapters coexistem; política nega por host quando o escopo não cobre; o resultado registra qual implementação executou. |
| **C3** | Host privilegiado tipado: `HostPort` permanece somente leitura; escrita (serviços, pacotes, armazenamento) em porta separada com broker, allowlist e aprovação — nunca shell arbitrário vindo do modelo. | Operação crítica exige aprovação verificada e produz journal. |
| **C4** | Journal de execução durável: idempotência, rate limit, circuit breaker e audit deixam de ser apenas locais ao processo. | Reinício não perde evidência; idempotência sobrevive a restart. |
| **C5** | Camada de SO real: imagem reproduzível, boot, instalador, canal de atualização e recuperação. `linux/` permanece provisionamento de runtime, não distribuição. | Validado primeiro em VM descartável; nenhum disco físico sobrescrito durante o protótipo. |

## Ordem e não-objetivos

Ordem obrigatória: **R1–R7 → C1 → C2 → C3/C4 → C5**. C3 e C4 são independentes entre si, mas ambos pressupõem C1.

Não faz parte desta decisão:

- escrever código, schema final, migration ou teste;
- criar um "capability system" como sexto registro;
- ativar `jarvis-os` a partir de configuração ou tratar relatório de perfil como autorização;
- migrar os 115 tools MCP de uma vez, ou reescrever adapters funcionais;
- declarar paridade Android/Linux, ou empacotar userland como equivalente de kernel;
- alterar o ledger de `docs/STATUS.md`, que exige commit, execução de Actions, implementação, consumidor e testes como evidência.

## Consequências

### Positivas

- O critério de sucesso do conjunto deixa de ser "o Jarvis OS existe" e passa a ser verificável: **`screen.capture` resolve para implementações diferentes em hosts diferentes, com disponibilidade, limitação, política e resultado observáveis separadamente.**
- Reaproveita o que já está correto (manifest versionado, dispatcher fail-closed, `HostPort` read-only, `adapter_registry` de aplicação) em vez de duplicar.
- Torna indisponibilidade e dívida de catálogo explícitas, em vez de escondidas em fallback.
- Impede que autorização seja inferida de catálogo, host ou nome de tool.

### Trade-offs e decisões adiadas

- Enquanto R5 não produzir o mapa de cobertura, a maior parte da superfície MCP permanece fora do contrato e sem autorização do dispatcher.
- Um `CapabilityGap` explícito pode reduzir funcionalidade aparente: chamadas que hoje "funcionam" por acoplamento direto passarão a falhar de forma declarada quando o host não implementar a capacidade.
- O schema definitivo de `CapabilityBinding`, a estratégia de ordenação de candidatos, a durabilidade do journal e o desenho da porta privilegiada ficam para C1–C4.
- Nenhuma execução foi validada por este documento: ele é decisão arquitetural baseada em auditoria source-only.

## Estado de implementação (2026-11-21)

Os incrementos abaixo foram implementados **depois** desta decisão, na ordem obrigatória. Cada linha declara apenas o que foi realmente testado; nada aqui é inferido de leitura de código.

### Entregue e testado

| ID | Entrega | Evidência de teste | Não verificado |
|---|---|---|---|
| **C1** | `app/application/services/capability_binding_registry.py`: `CapabilityBinding`, `HostRecord`, `CapabilityResolution`, `CapabilityResolutionGap` e `CapabilityBindingRegistry` como **extensão** de `AdapterRegistry` (não um sexto registro). Namespace `capability:` canônico; `objective:` recusado com `NamespaceViolation`. | `tests/application/test_capability_binding_registry.py` (20 testes): dois hosts fictícios, um sem `screen.capture` → gap `capability_not_declared`; host desconhecido, host offline, implementação indisponível com a limitação preservada; ordenação determinística entre consultas; `find_gap` herdado continua funcionando. | Nenhum adapter real foi executado e nenhum host real foi sondado. |
| **C1 (catálogo Ubuntu)** | `app/application/services/reference_host_catalog.py`: `host:ubuntu-server` e `host:ubuntu-desktop` com telemetria (`psutil_host_adapter`), descoberta de rede, mensageria e `screen.capture`. | `screen.capture` resolve de forma diferente nos dois hosts Ubuntu: disponível no desktop com limitação `captures-only-the-current-x11-session`; no server, `implementation_unavailable` com `requires-graphical-display-session`. | `host:android-*` e `host:windows-*` não foram declarados porque não foram verificados nesta sessão; não há alegação de paridade. |
| **C2** | `ToolManifest.host_implementations` + `HostImplementation`; `ToolRequest.host_ref` como preferência não confiável; `ToolDispatcher._select_implementation` escolhe **depois** da autorização e falha com `capability_unavailable` em vez de fallback; `ToolResult`/`ToolExecutionEvent` registram `capability`, `adapter_id` e `host_ref`. | `tests/runtime/test_toolbox_host_implementations.py` (8 testes): dois adapters coexistem; host indisponível é rejeitado sem resolver adapter; host que não declara a tool é rejeitado; política negada continua negando antes da seleção; manifesto rejeita host duplicado, host inválido e capability `objective:`. | Nenhuma tool de `config/tool_registry.json` declara `host_implementations` ainda, e nenhum adapter real foi executado por host. |
| **C1+C2 (vocabulário único)** | `app/domain/tools/host_selection.py` passa a ser a única definição de `Availability`, `GapReason` e da ordenação (`implementation_order_key`). O catálogo de vínculos e o dispatcher importam o mesmo vocabulário; `HostImplementation.availability` deixa de ser um `Literal` paralelo e passa a usar o enum compartilhado. | `tests/domain/test_host_catalog_manifest_consistency.py` (6 testes): o manifesto derivado do catálogo preserva a mesma disponibilidade e a mesma ordem, o dispatcher escolhe o mesmo `adapter_id`/`host_ref`/limitações que `resolve_capability` em cada host Ubuntu, e o `config/tool_registry.json` real não contradiz o catálogo (host declarado inexistente ou disponibilidade divergente falham). | As duas camadas continuam sendo avaliadas com hosts e adapters de teste; nenhum host real foi sondado. |
| **R3** | Um único gerador: `generate_capability_blueprint()`; `CapabilityManager`, `CapabilityGapReporter` e `CapabilityBlueprintService` delegam a ele. | `tests/test_capability_manager.py` mantido e verde. | Os `execute()` de componente Nexus continuam stub; não foram alterados. |
| **R6** | `capabilities/classification.py` removido. | Nenhuma importação restante; o pacote não tem mais efeito colateral em import. | — |
| **R7** | `docs/skills-connectors/CATALOG.md`: "dez" → "doze" (10 `read_only`, 2 `active_bounded`), apontando o registry versionado e a auditoria como insumo datado. | Contagem verificada em `config/tool_registry.json` (12 manifests, 10 `read_only` / 2 `active_bounded`). | — |

### Pendente, declarado

- **R1 parcial.** O namespace é imposto no código (`normalize_capability_id` e `ToolManifest.capabilities` recusam `objective:`), mas `data/capabilities.json` continua com IDs `CAP-###` e os 68 `complete` heurísticos **não** foram migrados para exigir evidência de execução.
- **R2.** `app/domain/models/adapter_registry.py` segue registrado em `data/nexus_registry.json` e coberto por `tests/test_nexus_registry_sync.py`; aposentá-lo exige migrar o componente Nexus, não apagar o arquivo.
- **R4.** O alias registry continua sem consumidor de produção.
- **R5.** `coverage_report()` cobre o registry de vínculos, **não** as ~115 tools MCP.
- **C3, C4, C5.** Porta privilegiada tipada, journal durável e camada de SO não foram iniciados; `linux/` continua apenas provisionamento de runtime.

### Verificação executada

```
python -m pytest tests/runtime tests/application tests/domain \
  tests/test_capability_manager.py tests/test_nexus_registry_sync.py \
  tests/test_regression_guards.py tests/test_docs_references.py
→ 1168 passed, 1 skipped
```

Ambiente local com as dependências de `requirements/core.txt` em `venv`, Python 3.12.3. Os testes usam adapters e hosts de teste; nenhum adapter real foi invocado. CI da PR, build Android/Desktop, execução em dispositivo e boot de VM **não** foram executados nesta sessão e permanecem não verificados, como declarado em [JARVIS_OS_CAPABILITY_AUDIT.md](JARVIS_OS_CAPABILITY_AUDIT.md) §11.

## Verificação

O critério de implementação do ADR continua sendo o teste decisivo: **`screen.capture` resolve para implementações diferentes em hosts diferentes, com disponibilidade, limitação, política e resultado observáveis separadamente.** C1 cobre descoberta e catálogo; C2 cobre seleção e resultado no caminho de execução. Ambos têm teste automatizado; falta a execução real por host e a CI da mudança.

## Referências

- [Jarvis OS — auditoria de capacidades](JARVIS_OS_CAPABILITY_AUDIT.md)
- [ADR-001 — Universal Tool Registry](ADR-001-universal-tool-registry.md)
- [Jarvis OS Foundation](../JARVIS_OS_FOUNDATION.md)
- [Arquitetura](../ARCHITECTURE.md) e [Status](../STATUS.md)
