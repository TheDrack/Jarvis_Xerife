# Estado do projeto — leitura do código versionado

**Data da revisão documental:** 2026-11-20
**Base de código auditada:** main @ fdc51057c84cef8a0949ca59ccba6bcafe71da8a  
**Escopo:** árvore de código e documentação versionada. Não foi realizada nesta página uma inspeção autenticada do deploy, banco, dispositivos ou serviços externos.

## Como interpretar este documento

| Estado | Significado |
|---|---|
| Presente no código | Há implementação versionada no branch de referência. |
| Coberto por teste | Existe teste relevante; é necessário consultar o resultado do CI/execução para afirmar que passou. |
| Integrado no fluxo | Há ligação entre os componentes no código; não prova que o ambiente esteja configurado. |
| Runtime verificado | Foi exercitado no ambiente real, com evidência datada e identificável. |
| Produção verificada | Foi confirmado no serviço implantado, banco ou dispositivo de destino. |
| Parcial / condicionado | A implementação depende de política, credenciais, feature flag, serviço externo, permissão ou integração ainda não comprovada. |
| Planejado | Existe como objetivo/documento, mas não deve ser apresentado como comportamento entregue. |

A presença de arquivo, migration, manifest, skill ou variável de ambiente não é prova de integração ativa. Um teste existente não é prova de que ele passou no commit atual.

## Inventário por subsistema

| Subsistema | Estado sustentado pela árvore de código | Limite que deve ser preservado na comunicação |
|---|---|---|
| Nexus DI e composição | Presente no código; usado pelos entrypoints e wrappers de compatibilidade. | Não confundir wrapper app/container.py com um segundo container independente. |
| Domínio e aplicação | Presentes: tools, capabilities, intelligence, memory, context, graph, missions, orchestration, services, ports e security. | A separação é incremental; existem módulos históricos e compatibilidade. |
| Universal Tool Registry | Contratos tipados/versionados e registry em app/domain/tools; catálogo em config/tool_registry.json. | Registry é metadado. Não autentica, autoriza, verifica saúde ou executa. |
| Tool Dispatcher | Implementação em app/runtime/toolbox com validação, resolução, autorização e eventos. | Sem política/principal autorizados, execução deve falhar fechada. Controles locais em memória não são garantias distribuídas. |
| Pipelines | Pipeline runner e definições YAML presentes. | Compatibilidade legada permanece; não declarar migração integral para tool_id/dispatcher. |
| Multiagente | Contratos, scheduler, queue, workers, transport e execution plans presentes em app/multiagent. | Opt-in e dependente de backend, credenciais, grants e configuração. Código não prova worker ativo. |
| Identidade de worker | Existe caminho autenticado com token opaco individual e grants do lado do servidor, além de um caminho legado Supabase direto. | O caminho legado service-role não oferece a mesma fronteira de identidade. Verificar migration e runtime no ambiente alvo. |
| Inteligência | Domínio e adaptadores de fontes estão presentes. | Consulta sob demanda, persistência, execução recorrente e apresentação são capacidades distintas. Fontes externas podem falhar parcialmente. |
| Android | Cliente nativo e integração com serviços Jarvis estão versionados. | VPN, acessibilidade, shell, captura e inspeção dependem de permissões, consentimento, pareamento e testes no dispositivo. |
| Desktop | Cliente Windows/WebView2, API local e scripts de build/start estão presentes. | Listener, firewall, pairing e sessão interativa dependem do host real. |
| MCP e acesso remoto | Servidores/adaptadores e runbooks de transporte estão presentes. | STDIO, HTTP local, Secure MCP Tunnel e gateways privados são rotas diferentes; não inferir conectividade atual. |
| Prospecto | Discovery por CNPJ, outreach multicanal, demand matching B2B/B2C/C2B, extração de endereço, contratos geoespaciais, cache DuckDB, integração opcional GeocodeBR/CNEFE ao CLI e mapa empresarial Desktop estão no código. | A geocodificação é opt-in; execução real CNEFE e benchmark de volume não foram comprovados. O mapa empresarial lê apenas o cache existente, sem geocodificar durante a consulta; smoke test Desktop Windows/Android ainda pendente. Runtime Android, relays externos, providers de vagas/catálogos e isolamento multi-tenant hospedado seguem não verificados; ACATE continua sem consumer operacional e com filtros incompletos. |
| Auto-evolução e reparo | Serviços, gatekeeper, sandbox, scripts e workflows estão presentes; `homeostase.yml` usa código confiável de `main` e `scripts/jarvis_healer.py` para falhas elegíveis. | `homeostase.yml` não dispara para PR Validation/Task Queue; o endpoint protegido `/v1/github/ci-heal/{run_id}` baixa logs e registra pensamento, mas não produz patch/PR. Não declarar autocorreção automática de PRs ponta a ponta. |
| Deploy e persistência | Manifestos, migrations e adapters estão presentes. | Só inspeção no ambiente confirma deploy, schema aplicado, RLS/grants, feature flags e saúde. |

## Entrypoints

- main.py — bootstrap principal cloud/edge.
- serve.py — entrada headless/API.
- app/bootstrap_edge.py — bootstrap local/edge.
- scripts/start_jarvis_desktop.ps1 — inicialização desktop Windows.
- app/adapters/edge/jarvis_desktop_mcp.py — servidor MCP desktop.
- scripts/run_multiagent_worker.py — worker multiagente opt-in.
- mobile/android — cliente Android nativo.

## Evidência necessária para atualizar estados operacionais

Para declarar um componente runtime-verified ou production-verified, registre:
1. ambiente/serviço/dispositivo exato;
2. commit ou versão implantada;
3. data/hora e comando ou operação executada;
4. resultado bruto relevante, sanitizado;
5. feature flags, grants e pré-requisitos relevantes;
6. falhas parciais e limitações.

Para Supabase, verifique migrations remotas, schema, RLS, grants e uma operação de leitura/escrita controlada quando autorizada. Para Render, confirme serviço, commit implantado, health e logs. Para Android/Desktop, confirme build e teste real no dispositivo/host.

## Atualização

Esta página substitui snapshots antigos como descrição geral de estado. Resultados históricos continuam úteis como histórico, mas devem permanecer datados e não ser copiados para uma afirmação de estado atual sem revalidação.
- Revalidação source-only em 2026-11-18 contra `main @ 17c52c4`: `homeostase.yml` continua como recuperação de falhas elegíveis de `main`, sem gatilho para PR Validation/Task Queue; `GitHubWorker.auto_heal_ci_failure()` apenas baixa logs e registra pensamento. O caminho legado C2 chama `AutoFixer.attempt_repair()`, método ausente da classe `AutoFixer`, e captura a exceção. Além disso, `scripts/pr_manager.py::attempt_repair()` executa `pytest tests/` no checkout original antes de aplicar o candidato; o código temporário gerado não é executado pela suíte e não há pytest pós-aplicação antes do commit/PR. Portanto, não há evidência de correção automática de PR CI ponta a ponta. Nenhum reparo foi executado; não conectar esse caminho a PRs até validar o candidato em worktree/container isolado, preservar testes e separar publisher privilegiado.


## Revalidação de CI — 2026-11-19

- `main` @ `2bf151052f1a25f088030bfafec5d31d58f18e11`: `JARVIS Hourly Curiosity Audit` run [44619680908](https://github.com/TheDrack/Jarvis_Xerife/actions/runs/44619680908) — success; pytest **3.626 passed, 39 skipped, 8 warnings**, coverage **69%**.
- Mesma SHA: `Jarvis Task Queue Tests` run [44552097344](https://github.com/TheDrack/Jarvis_Xerife/actions/runs/44552097344) — success; pytest **3.649 passed, 21 skipped, 181 warnings**, coverage **70%**.
- CI verde não altera o estado dos critérios cognitivos. O ledger abaixo mantém os três critérios C0 como `pending`; C1 continua bloqueado.


## Revalidação técnica — 2026-11-20

### Base, CI e PRs
- `main` está em `32cf7e94ed54d577c85cc503b1480ef1c765399d`. O último commit funcional da linha principal é `fc30d6ab215ea428e77e794bbd9f9c99fbdd53e7`; os commits posteriores `290010f` e `32cf7e9` atualizam documentação gerada e baseline.
- `Jarvis Task Queue Tests`, run [44819128465](https://github.com/TheDrack/Jarvis_Xerife/actions/runs/44819128465), executou no commit funcional `fc30d6a`: **3.672 passed, 21 skipped, 181 warnings**; job concluído com sucesso em Windows/Python 3.12.10. `Auto-Documentation JARVIS`, run [44819127851](https://github.com/TheDrack/Jarvis_Xerife/actions/runs/44819127851), também concluiu com sucesso.
- No snapshot anterior à integração (main `32cf7e9`), a PR [#867](https://github.com/TheDrack/Jarvis_Xerife/pull/867) estava aberta, head `f52e68d7352809e372f235b18710254ffafea8d5`, base `32cf7e9`, **12 commits ahead / 0 behind**. No head exato: PR Validation run [44822315142](https://github.com/TheDrack/Jarvis_Xerife/actions/runs/44822315142) passou com **3.661 passed, 38 skipped, 8 warnings** (Linux/Python 3.11.18); Task Queue run [44822314948](https://github.com/TheDrack/Jarvis_Xerife/actions/runs/44822314948) passou com **3.683 passed, 21 skipped, 181 warnings** e teste específico da fila **15/15** (Windows/Python 3.12.10). Supabase Preview foi `skipped`, sem branch de preview. Não há review formal; a PR não foi mesclada.
- Esses resultados comprovam CI dos respectivos SHAs, não download/execução real do CNEFE, benchmark, runtime Android ou mapa. A situação da PR #867 neste parágrafo é histórica; ela foi mesclada posteriormente.

### C0 e ordem do roadmap
- Naquela revalidação, Graphify estava indexado em `main @ 32cf7e94ed54d577c85cc503b1480ef1c765399d`; o índice antecede as PRs #867 e #869. `CognitiveRouter.execute()` tem como único caller estrito o teste `test_execute_initializes_missing_metadata()`. `run_pipeline()` tem callers estritos no CLI do próprio módulo e em testes; não foi localizado consumer de aplicação. `AssistantService.process_command()` não alcança o router nem o runner no grafo de chamadas.
- `config/pipelines/jarvis_chat.yml` aparece em configuração/documentação/teste, mas não foi comprovado um caminho de aplicação nem um teste integrado input → CognitiveRouter → LlmEngine. O runner CLI não recebe `inputs`; sem `inputs.metadata.user_input`, o router observa texto vazio. O roteador atual é uma heurística de marcha com fallback, não um Reasoning Engine.
- `data/roadmap_missions.json` continua com `missions: []`. O run [44753845068](https://github.com/TheDrack/Jarvis_Xerife/actions/runs/44753845068) concluiu o gate, mas `EVOLUTION_ENABLED` estava vazio e os jobs de geração/validação e publicação foram `skipped`. Não houve candidato nem publicação.
- O ledger permanece com `C0-CAPABILITY-MAP`, `C0-GAPS-RECORDED` e `C0-NO-NAME-BASED-COMPLETION` em `pending`; **C1 — World Model — continua bloqueado**. Esta atualização não altera esses estados.

### Governança e self-healing
- A API da branch reporta `main.protected=false`; a consulta de rulesets retorna `[]`. A leitura do endpoint de branch protection retorna 403 para a integração; nenhuma configuração foi alterada. Issue [#682](https://github.com/TheDrack/Jarvis_Xerife/issues/682) continua aberta.
- Self Healing V3 run [44753874490](https://github.com/TheDrack/Jarvis_Xerife/actions/runs/44753874490) foi `skipped`; não houve reparo nessa execução. `homeostase.yml` continua limitado a workflows confiáveis originados em `main` e não observa PR Validation/Task Queue. O fluxo trusted-main permanece preservado; autocorreção automática de PRs continua não comprovada.

## Ledger verificável dos critérios cognitivos

Este bloco é consumido por `RoadmapMissionSelector`. Um critério só pode ser tratado como concluído quando estiver como `verified` e trouxer referência imutável de commit, execução de Actions, implementação, consumidor e testes. A presença das referências é validada pelo selector; a autenticidade e a suficiência técnica continuam sujeitas à revisão humana.

<!-- JARVIS_COGNITIVE_EVIDENCE_START -->
```json
{
  "schema_version": 1,
  "roadmap_path": "docs/COGNITIVE_ROADMAP.md",
  "criteria": [
    {
      "criterion_id": "C0-CAPABILITY-MAP",
      "state": "pending",
      "evidence": {
        "commit_url": null,
        "check_urls": [],
        "implementation_paths": [],
        "consumer_paths": [],
        "test_paths": []
      }
    },
    {
      "criterion_id": "C0-GAPS-RECORDED",
      "state": "pending",
      "evidence": {
        "commit_url": null,
        "check_urls": [],
        "implementation_paths": [],
        "consumer_paths": [],
        "test_paths": []
      }
    },
    {
      "criterion_id": "C0-NO-NAME-BASED-COMPLETION",
      "state": "pending",
      "evidence": {
        "commit_url": null,
        "check_urls": [],
        "implementation_paths": [],
        "consumer_paths": [],
        "test_paths": []
      }
    }
  ]
}
```
<!-- JARVIS_COGNITIVE_EVIDENCE_END -->


### Atualização Prospecto geoespacial — 2026-11-20
- PR #867 mesclada: adapter opcional GeocodeBR/CNEFE e cache batch.
- PR #869 mesclada: campanhas e CLI aceitam geocodificação opt-in; CSV/manifesto recebem coordenadas e metadados.
- PR #871 mesclada em `a9a80816aa1155af8f8ef4153c7efb985d25a104`: mapa empresarial no Desktop, enriquecimento autenticado a partir do cache existente, rota local do asset, clusters selecionáveis e leitura DuckDB estritamente read-only.
- CI da PR #871: suíte Python completa, testes frontend geoespaciais e testes da fila de tarefas passaram. Revisão Codex concluída sem findings no SHA `e973016f5e83ec4606b7cac0cd8fa7b2d229347a`.
- O fluxo padrão continua offline sem `--geocode`. Não há comprovação de download real CNEFE, benchmark de produção ou smoke test Desktop/Android.
- A tela Desktop de descoberta empresarial já oferece alternância LISTA/MAPA e anexa coordenadas existentes do cache à busca autenticada; não geocodifica sob demanda. A geração de coordenadas em campanhas continua opt-in via CLI `--geocode`; o mapa de dispositivos permanece separado.
