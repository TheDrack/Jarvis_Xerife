# JARVIS — Status do Projeto

**Versão:** 2.0.0  
**Revisão documental:** 2026-11-09
**Escopo desta revisão:** revalidação pós-merge #792–#794; CI, autoevolução agendada, baseline C0, Supabase read-only e Render. Runtime/produção só são declarados com evidência direta.

## Visão geral e qualidade da evidência

| Área | Estado sustentado pelas evidências disponíveis | Limite / próxima validação |
|---|---|---|
| Arquitetura hexagonal e Nexus DI | Implementados e cobertos por testes segundo a auditoria de entregas | Reexecutar CI no HEAD atual antes de usar métricas antigas como estado corrente |
| Auto-evolução e self-healing | Gatekeeper, snapshot descartável em Docker hardened e publisher privilegiado separado estão integrados. PR #775 foi merged em 2026-11-08: o workflow usa RoadmapMissionSelector e data/roadmap_missions.json, não o selector legado. | O manifesto está vazio; o selector retorna no-op antes de LLM/Docker. Nenhuma missão C0 tem target/testes revisados para geração. Self Healing V3 e PR Validation continuam presentes e inalterados. Não declarar autoevolução funcional enquanto não houver missão aprovada e validação supervisionada. |
| JarvisDevAgent | Fluxo de desenvolvimento e registro de jobs existem | A auditoria identificou promessas não cumpridas: AdapterRegistry sem consumidor de produção, execução de código existente não priorizada de forma comprovada e geração automática de pipelines não entregue |
| PipelineRunner | Runner consome pipelines YAML; a main agora inclui etapas explícitas tool_id via dispatcher pela PR #681 | Migração de todos os passos legados e validação de produção ainda pendentes |
| Universal Toolbox | Registry, dispatcher fail-closed, toolchains DAG e audit JSONL estão integrados. PR #779 adicionou HostToolAuthorizationPolicy; PR #787 adicionou o store de approvals e a migration foi aplicada em produção. | A tabela `jarvis_tool_approvals` existe, com RLS e ACL service-role-only, mas contém 0 linhas. Não há API de aprovação, resolver de sessão nem registro da policy no Nexus; ToolDispatcher permanece fail-closed. |
| Universal Intelligence | Contratos de eventos/observações, Core 0.2, adaptadores GEV MCP/OSIRIS, coleta sob demanda e schema/RPCs do worker estão integrados. Ledger Supabase: 30 migrations locais e 30 remotas, com correspondência exata version/name 30/30; última 20261108193000 durable_tool_approvals. | Snapshot read-only 2026-11-09: event snapshots 0, observation snapshots 0 e worker runs 0. Render foi reconsultado em 2026-11-09: os logs registram o worker recorrente desabilitado por feature flags; lease sem proprietário/expiração e zero execuções. Não habilitar sem autorização operacional. GEV/OSIRIS ainda exigem health checks live; GDELT pode responder 429 e AISSTREAM_API_KEY não foi verificada nesta execução. |
| Memória vetorial | SupabaseVectorMemoryStore, escopo por usuário e redaction recursiva estão integrados; RLS está habilitado. | Consulta read-only em 2026-11-09 confirmou 0 linhas em jarvis_vector_memories. Os grants observados são service_role-only, sem grants anon/authenticated; insert/readback real do runtime continua não comprovado. |
| Inventário de capabilities | data/capabilities.json mantém 102 registros legados; 34 pendentes, 34 com auto=true e nenhum target_file no snapshot anterior. | O catálogo legado não seleciona missões cognitivas; serve apenas para validar o CAP de compatibilidade quando uma missão do manifesto existe. A seleção agendada usa data/roadmap_missions.json, atualmente vazio. |
| Soldier Mesh / edge | Há modelos, registry, adapters e testes relacionados | Continua parcial até existir validação ponta a ponta com dispositivos reais |
| Otimização econômica | CostTrackerAdapter está descrito como integrado ao llm_router | ResourceOptimizer não foi encontrado pela auditoria; não marcar fase como completa |
| Coordenação multiagente | PR #776 persiste created_by/owner_id a partir da identidade autenticada para novos enqueues e usa owner persistido no sinal task_blocked. PR #773 implementa credenciais opacas por agente; PR #779 implementa HostToolAuthorizationPolicy. | Snapshot Supabase 2026-11-09: 5 agentes, 13 tarefas e **0/13 tarefas com owner_id ou created_by**; 0 credenciais individuais ativas. A migration de ownership está aplicada, mas os registros existentes continuam sem owner. A policy host-backed ainda não tem composition root de produção localizado; workers não têm identidade individual runtime-verified. |
| Planos declarativos | Interpretador, integração no orquestrador, autorizador e adaptador de diário estão no repositório | Execução exige plano estruturado, allowlist e diário durável. Ações sensíveis permanecem bloqueadas até existir protocolo confiável de aprovação/retomada |
| Diário de planos no Supabase | Migrations e grants registrados; ledger local/remoto tem 29/29 versões/names correspondentes em 2026-11-08. | Insert/readback pelo adaptador em runtime ainda precisa de prova; existência de tabela/migration não comprova integração operacional. |
| Catálogo comum de agentes | Catálogo de skills/connectors e protocolo de memória existem; quatro skills portáteis foram localizadas no repositório | A leitura automática no início de toda conversa depende de cada host/harness e precisa ser validada por runtime |
| Deploy Render | `Jarvis-api` está live no commit `1ad74752a6393cb8f0de3614d74be0994ece940b`; deploy concluído em 2026-11-07 19:01:33 UTC e inclui o merge da PR #773. | Logs após o deploy confirmam fallback legado Supabase service-role para os três workers e Universal Intelligence recurring worker desabilitado por feature flags. A identidade HTTP individual está no código, mas não foi ativada no runtime. Memória vetorial segue sem linhas. |
| Governança da branch main | **Proteção ausente — confirmado em 2026-11-09** | API da branch main retornou protected=false e a consulta de rulesets retornou lista vazia. Issue #682 permanece aberta; a API de proteção administrativa não está acessível ao conector. |
| Segurança Supabase / RLS legado | Mitigação legacy aplicada em produção; issue #726 fechada. | Advisor de 2026-11-09 reportou 31 tabelas com RLS habilitado sem policy (INFO), incluindo `jarvis_tool_approvals`. Nesta tabela, anon/authenticated não têm SELECT/INSERT/UPDATE/DELETE e service_role tem os quatro privilégios; não extrapolar essa verificação às demais tabelas. Manter revisão de ACL e não criar policies de cliente sem modelo de ownership. |

### Evidência operacional Supabase — 2026-11-07 (snapshot histórico)

- Projeto `saibtpdehhprttqlgqdt`: `ACTIVE_HEALTHY`; branch `main`: `FUNCTIONS_DEPLOYED`; preview `ACTIVE_HEALTHY`.
- Ledger remoto: **28 migrations**; a última é `20261107183000 / agent_worker_credentials`, aplicada após o merge da PR #773. A comparação local/remota 28/28 não foi refeita integralmente nesta execução; o snapshot anterior de 27/27 permanece válido para as 27 versões anteriores.
- A migration `20261107183000_agent_worker_credentials.sql` foi integrada à main pela PR #773 e aplicada pela integração GitHub–Supabase. A consulta read-only confirmou a versão remota 20261107183000. Nenhuma aplicação manual foi feita.
- Após o merge do PR #767, a integração GitHub–Supabase aplicou as seis migrations forward-only; após o PR #769, aplicou a migration da memória vetorial. Nenhum `db push`, `migration repair` ou DDL/DML manual foi executado nesta sessão.
- A introspecção read-only de jarvis_agent_credentials confirmou RLS habilitado, service_role com SELECT/INSERT/UPDATE, anon e authenticated sem SELECT e **0 credenciais provisionadas**. O advisor retorna rls_enabled_no_policy como INFO para essa tabela; isso é compatível com a estratégia service-role-only observada, mas deve continuar sob monitoramento.
- A tabela jarvis_vector_memories continua com 0 linhas e 0 scopes; o schema/ACL não substituem prova de insert/readback pelo runtime.
- Fencing de mensagens ativo: `claim_token` presente e ACK de três argumentos disponível para `service_role`. O overload legado de dois argumentos permanece no catálogo, mas não possui EXECUTE para `service_role`, `anon` ou `authenticated`.
- RPCs de claim direto/provider-aware, renovação NULL-safe de lease, release de tentativa e recurring intelligence worker presentes. Os cinco índices de attempts/events/parent/routine estão presentes.
- Três agentes `mini-freellmapi` online, provider `groq`, capabilities `text_reasoning` apenas (heartbeats observados às 21:47:53–21:47:54 UTC). A tabela `jarvis_agent_credentials` contém 0 linhas; portanto ainda não há credenciais individuais provisionadas. O caminho HTTP novo não está comprovado em runtime; não inferir o backend efetivo apenas pelo heartbeat. Não adicionar capabilities sem executor e policy reais.
- Logs do Render em 2026-11-07 às 21:45:18 UTC registram `Mini-agent runtime using legacy Supabase service-role queue access; per-agent worker identity is not enforced on this path` e a inicialização dos três workers. Às 21:45:19 UTC, o recurring intelligence worker informa que permanece desabilitado por feature flags.
- A lease do recurring intelligence worker está livre (`worker_id=NULL`) e o histórico de runs contém zero execuções. Logs do Render após o deploy atual confirmam que o worker é desabilitado por feature flags. O código é iniciado em thread supervisionada pelo `main.py` quando ambas as flags estão habilitadas; nenhuma flag foi alterada.
- Render `Jarvis-api` está `live` no commit `1ad74752a6393cb8f0de3614d74be0994ece940b`, deploy concluído às 19:01:33 UTC em 2026-11-07; esse deploy contém o merge da PR #773.
- A próxima entrega prioritária de C0 é conectar a autoevolução ao Cognitive Roadmap por um manifesto de missão C0 revisado: criterion_id, target_file confiável, testes, dependências, risco e resultado esperado. O selector deve ler esse manifesto e preservar target_file; o workflow deve permanecer blocked/no-op quando o mapeamento não existir. Depois, persistir owner/creator da tarefa a partir do usuário autenticado e propagar esse vínculo aos eventos de conclusão/bloqueio. Em seguida, integrar executores reais ao heartbeat/ToolDispatcher e registrar ToolAuthorizationPolicy host-backed. A migration de identidade já está aplicada; provisionamento de tokens individuais exige autorização operacional e secret store aprovado. A memória vetorial ainda precisa de insert/readback real; o worker recorrente exige autorização operacional separada.

### Evidência histórica Supabase — 2026-11-05 (superseded)

- Projeto consultado em modo somente leitura: `saibtpdehhprttqlgqdt`, estado `ACTIVE_HEALTHY`.
- O ledger remoto retornou 20 registros; a branch `main` contém 24 arquivos SQL em `supabase/migrations`. A diferença de contagem é de quatro entradas; o mapeamento exato entre versões e nomes locais/remotos ainda precisa ser reconciliado. A migration `lock_down_legacy_public_tables` está registrada na versão `20261104223338`; a migration `provider_aware_remote_task_claims` aparece na versão remota `20261105023946`; a divergência histórica do timestamp da migration de inteligência (`20261103184307` remoto versus prefixo local `20261103100304`) permanece pendente.
- As tabelas `public.intelligence_event_snapshots` e `public.intelligence_observation_snapshots` existem e têm RLS habilitado. As tabelas/RPCs do worker da PR #716 não foram encontradas no projeto.
- O check `Supabase Preview` do commit `fafdd5bd50e07ad7605b60aea685e56936287d3b` falhou com `Remote migration versions not found in local migrations directory.`
- O advisor aponta `public.rls_auto_enable()` como `SECURITY DEFINER` com EXECUTE para `PUBLIC`, `anon`, `authenticated` e `service_role`. A introspecção de 2026-11-04 confirmou que retorna `event_trigger`, está vinculada a `ensure_rls` (`ddl_command_end`), usa `search_path=pg_catalog` e executa apenas ao final de DDL compatível. `anon` e `authenticated` não possuem CREATE em `public`; não foi demonstrada invocação direta por PostgREST. O achado foi reclassificado como revisão de least privilege/ACL, issue #718; nenhum grant foi alterado.
- A introspecção read-only de 2026-11-05 confirmou que as RPCs remotas `claim_jarvis_agent_task` e `claim_next_jarvis_agent_task` agora incluem o guard de `model_provider`/Venice e as verificações de heartbeat. ACL observada nas duas: `anon EXECUTE=false`, `authenticated EXECUTE=false`, `service_role EXECUTE=true`. O ledger registra `20261105023946 / provider_aware_remote_task_claims`; a implementação do guard está aplicada e verificada. Issue #723 permanece aberta exclusivamente para acompanhar a divergência histórica do ledger/Preview, rastreada em #732. A consulta foi somente leitura; nenhum claim, DDL ou migration foi executado no projeto ativo.
- Grants exatos das tabelas de histórico, conectividade do service role e insert/reload real continuam não verificados. Nenhuma migration, repair, DDL ou escrita de dados foi executada nesta auditoria.
- A auditoria read-only identificou sete tabelas com policy `ALL` baseada apenas em `auth.role() = 'authenticated'`, grants amplos e exposição de colunas sensíveis. A mitigação foi aplicada em produção pela migration `lock_down_legacy_public_tables` e verificada nos catálogos: `client_table_privileges_remaining=0`, `client_column_grants_remaining=0`, `broad_policies_remaining=0` e `service_role_crud_grants_remaining=28/28`. Issue #726 fechada após a integração da PR #727. Nenhum conteúdo de linha foi lido, alterado ou apagado.

## Roadmap — estado conservador

| Fase / trilha | Estado | Evidência e critério para avançar |
|---|---|---|
| Phase 1 — Arquitetura hexagonal + Nexus DI | **Implementada; testes documentados** | Auditoria anterior registrou resolução por ID, discovery e testes de contrato/circuit breaker. Revalidar no HEAD atual para atualizar métricas. |
| Phase 2 — Auto-evolução + self-healing | **Parcial / selector roadmap-driven integrado; geração permanece em idle seguro** | PR #775 integrou RoadmapMissionSelector e manifesto vazio. O workflow consome o Cognitive Roadmap e não usa o catálogo legado para escolher missões; sem mapeamento revisado, não invoca LLM/Docker/publicador. Preservar Self Healing e PR Validation como trilha transversal. |
| Phase 3 — JarvisDevAgent + AdapterRegistry + PipelineRunner | **Parcial em termos de entrega comportamental** | Runner existe; auditoria registrou que AdapterRegistry não era consumido em produção e geração automática de pipelines não estava implementada. Não manter um selo global de completo sem fechar esses critérios. |
| Phase 4 — Soldier Mesh / Edge Computing | **Em progresso** | Existem componentes e testes, mas não foi comprovada execução ponta a ponta com dispositivo real. |
| Phase 5 — Economia de recursos | **Parcial** | CostTrackerAdapter é consumido pelo llm_router; ResourceOptimizer permanece pendente na auditoria. |
| Trilha — Jarvis OS / provider-neutral model runtime | **Contrato, bindings nos três worker roots integrados; seleção/roteamento global pendentes** | `ModelRuntime` define mensagens, request/result, usage, erros retry-aware e cancelamento explícito. `ModelRuntimeBindings` resolve `ModelProfile` para o adaptador do provider; `create_registered_model_handler` é usado pelos workers HTTP, Supabase e supervisionado. PRs #685, #688 e #689 estão merged (a #689 em 2026-11-03). Isso não prova health/conectividade dos providers nem seleção global entre múltiplos modelos. `LLMRouter`, `AIGateway` e `ModelOrchestrator` ainda preservam rotas próprias. Próximo passo: seleção por capabilities/modalities no scheduler e integração gradual dos três roteadores após testes de compatibilidade. |
| Trilha — harness multiagente e fila compartilhada | **Implementação parcial** | Contratos, scheduler, transporte, fila e workers existem. O worker Supabase de tarefas já atualiza heartbeat e renova lease com testes unitários; ainda faltam supervisão contínua do processo, deduplicação/recovery comprovados e E2E entre dois runtimes reais. |
| Trilha — execução declarativa auditável | **Código integrado; validação de produção pendente** | PRs #610–#613 integraram TaskRunner, limites de aprovação, diário Supabase e orquestrador. Confirmar deploy atual, gravação real e comportamento runtime. |
| Trilha — descoberta universal de skills/connectors | **Documentação atualizada; adoção por host pendente** | Catálogo comum agora lista skills e famílias de capacidades; cada host deve carregar o catálogo e descobrir ferramentas vivas. Não pressupor injeção automática em todos os provedores. |
| Trilha — Universal Toolbox / Toolchains | **Registry/dispatcher integrados; policy host-backed implementada, integração de produção pendente** | PR #681 integrou registry/dispatcher/toolchains; PR #779 adicionou HostToolAuthorizationPolicy e testes. Não foi localizado consumidor em composition root; faltam resolvers host confiáveis, executores invocáveis, estado/audit distribuídos e validação runtime. |
| Trilha — Jarvis Universal Intelligence | **Coleta sob demanda integrada; recorrência sem execução observada** | Ledger local/remoto 29/29 exato em 2026-11-08. Banco: 0 runs, lease sem worker/expiração, 0 snapshots de evento/observação. A flag de runtime não foi consultada nesta execução; não ativar sem autorização e prova supervisionada. |

## Regra operacional permanente — correção automática de PRs

A autoevolução de capacidades segue o [Cognitive Roadmap](COGNITIVE_ROADMAP.md), mas a correção automática de PRs/CI e os workflows Self Healing são uma trilha transversal permanente. Devem continuar ativos durante todas as fases: diagnosticar falhas por logs/causa raiz, corrigir a branch/PR correspondente quando seguro, acrescentar testes e reexecutar checks. Não desativar nem enfraquecer esses mecanismos, não duplicar PRs, não reduzir testes e não permitir merge/deploy autônomo. A publicação permanece sujeita aos gates e à revisão humana. Correção de CI é manutenção; não substitui nem conclui marco cognitivo.

## Nova trilha — Jarvis Cognitive Architecture

**Estado:** C0 em andamento; C1–C8 não são declaradas concluídas. O inventário inicial está em [COGNITIVE_BASELINE.md](COGNITIVE_BASELINE.md) e não substitui os critérios de aceitação do roadmap.

O roadmap cognitivo foi formalizado em [COGNITIVE_ROADMAP.md](COGNITIVE_ROADMAP.md). A trilha não substitui nem reconstrói Harness, Nexus, Universal Toolbox, Multi-Agent ou Universal Intelligence: ela audita e integra essas bases para formar um ciclo contínuo de percepção, modelo de mundo, memória, raciocínio, planejamento, execução supervisionada, iniciativa e aprendizado validado.

| Marco | Capacidade | Estado inicial | Critério principal |
|---|---|---|---|
| C0 | Auditoria de capacidades e baseline comportamental | **Em andamento — selector roadmap-driven integrado; manifesto vazio; ownership ausente nos 13 registros atuais; approvals duráveis aplicadas mas sem consumidor; policy host-backed sem composition root de produção** | PR #775 integra seleção por manifesto fail-closed; PR #776 grava owner em novos enqueues, mas o snapshot atual tem 0/13 tarefas com owner/creator; PR #779 implementa/testa a policy, ainda sem composition root. Permanecem baseline comportamental, mapa completo de consumers/runtime, identidade HTTP ativa, executores autorizados e persistência cognitiva comprovada. C1 não inicia até fechar C0. |
| C1 | World Model | **Auditoria necessária** | Entidades, relações, observações, proveniência, identidade conservadora e histórico temporal reconstruível |
| C2 | Cognitive Memory | **Parcial / auditoria necessária** | Consolidar memórias episódica, semântica, procedural e prospectiva com recuperação contextual, conflitos e retenção |
| C3 | Perception Engine | **Parcial / auditoria necessária** | Integrar fontes existentes em pipeline normalizado, resiliente, idempotente e observável |
| C4 | Reasoning Engine | **Auditoria necessária** | Hipóteses e conclusões ligadas a evidências, contraditório, calibração e abstenção |
| C5 | Strategic Planner | **Parcial / auditoria necessária** | Objetivos persistentes, decomposição, dependências e replanejamento |
| C6 | Autonomous Executive | **Parcial / auditoria necessária** | Execução multiagente autorizada, supervisionada, idempotente e com efeito verificado |
| C7 | Initiative Engine | **Parcial / auditoria necessária** | Iniciativas úteis disparadas por mudanças, com deduplicação, orçamento e política |
| C8 | Learning & Evolution Engine | **Parcial / auditoria necessária** | Melhorias avaliadas contra baseline, sem regressões, com auditoria e rollback |

**Primeiro vertical slice:** mudança de estado de um dispositivo de laboratório → observação com proveniência → atualização do World Model → recuperação de memória → hipóteses com evidências → plano de investigação → consultas passivas autorizadas → verificação independente → registro do resultado. O primeiro slice não executará varreduras ativas nem ações destrutivas.

**Próximo passo:** concluir C0 e especificar os contratos do World Model. Não criar um segundo sistema de memória, event bus, scheduler ou grafo antes de comprovar que os existentes não atendem ao contrato. Migrations e flags de produção permanecem fora desta atualização documental.

## Pendências prioritárias sustentadas pela auditoria
1. **Concluir C0 — capability map e baseline comportamental:** para cada capacidade crítica, registrar caminho, consumidor real, testes e nível de verificação. Reexecutar percepção → collector → IntelligenceCore → endpoint com falha parcial, duplicatas, reordenação e proveniência; distinguir CI de runtime.
2. **Integrar autorização host-backed no composition root:** PR #779 adicionou HostToolAuthorizationPolicy; PR #787 aplicou a tabela durável, mas ela tem 0 linhas e não há API de aprovação, sessão confiável ou policy registrada no Nexus. O JWT atual não expõe `sid`/`jti` ao `get_current_user`. Implementar contexto autenticado, resolvers host-owned de owner/executor e consumo atômico; manter fail-closed.
3. **Revisar o primeiro mapeamento de missão C0:** PR #775 integrou selector/manifesto; data/roadmap_missions.json continua vazio. Só adicionar missão ready após revisão humana de criterion, target Python existente e não protegido, testes, dependências, risco baixo e resultado esperado. Não inferir target por LLM.
4. **Validar ownership ponta a ponta:** PR #776 grava owner/creator para novos enqueues e usa o owner persistido em task_blocked. O snapshot atual tem 13 tarefas legadas, 0/13 com owner_id/created_by, incluindo 2 ready; provar isolamento e definir compatibilidade/backfill antes de usá-las em execução autorizada.
5. **Ativar identidade individual de workers somente após autorização operacional:** migration aplicada; a consulta read-only de 2026-11-09 confirma 0 credenciais ativas. Provisionar via fluxo aprovado/secret store e validar heartbeat/claim/finish/release HTTP; não alterar secrets nesta trilha.
6. **Validar multiagente E2E:** dois runtimes independentes, ownership, fencing, recuperação de lease, executor real e autorização vinculada à tentativa.
7. **Provar memória vetorial em runtime:** insert/readback real, idempotência, retenção/erasure e isolamento; a tabela permanece com 0 linhas.
8. **Manter Universal Intelligence recurring worker sem ativação** até autorização operacional e execução supervisionada com lease/run/persistência/readback/liberação. Snapshot atual: 0 runs e lease sem owner/expiração; flag Render não reconsultada.
9. **Manter treinamento desabilitado:** PR #780 endureceu elegibilidade, mas consentimento, redaction completa, retenção, isolamento multi-tenant e ground truth não foram demonstrados.
10. **Proteger main:** API confirmou protected=false e nenhum required check em 2026-11-08; issue #682 permanece aberta.
11. **Fechar a reconciliação do ledger com validação completa:** inventário read-only de 2026-11-09 encontrou 30 migrations locais e 30 remotas com correspondência exata version/name. Issue #732 permanece aberta até validar equivalência de schema, Supabase Preview e rollback; sem repair/reset/db push ou reescrita de histórico.
12. **Validar bootstrap e roteamento de modelos:** confirmar carregamento de skills/connectors em cada harness e integrar LLMRouter/AIGateway/ModelOrchestrator ao port comum sem remover adapters, com testes de concorrência, timeout, cancelamento, usage e falhas de provider.

### Estado da seleção de autoevolução — 2026-11-07

- O catálogo alternativo no formato JRVS não está versionado; AutoEvolutionServiceV2 usa o fallback JSON em `data/capabilities.json`.
- O inventário contém 102 registros, 34 pendentes, 34 auto=true e 0 target_file. A primeira missão elegível é CAP-058, Adapt plans during execution, prioridade 5 — catálogo legado, não critério C0.
- find_next_mission() retorna target metadata dentro de mission e não a propaga ao nível superior; auto_evolution_triggerV2.yml lê next_mission.target_file.
- Resultado previsto pelo código: action=blocked antes do LLM e do sandbox. O workflow não lê docs/COGNITIVE_ROADMAP.md nem docs/STATUS.md.
- O conector GitHub usado nesta execução não expõe a listagem de runs schedule; a conclusão de no-op deriva do código e do inventário observados, não de uma execução schedule observada.

### Evidência de CI — identidade individual de workers (PR #773)

- PR #773 merged em 2026-11-07 no commit 4f35eac4a425bd508f0e156637f35a9f9e0f01b3.
- Task Queue Tests run 42403685896 (#777): success; testes direcionados 8 passed; suíte completa Windows/Python 3.12.10: 2.716 passed, 15 skipped, 80 warnings.
- JARVIS PR Validation run 42403685897 (#434): success; teste frontend geospatial e build Docker do sandbox passaram; suíte completa Linux/Python 3.11.18: 2.717 passed, 14 skipped, 8 warnings.
- O bot de revisão Codex não concluiu a revisão por limite de uso; não há review formal registrada. Os checks de CI verdes não substituem revisão independente.
- O commit de documentação mais recente consultado é 1ad74752a6393cb8f0de3614d74be0994ece940b e contém [skip ci]; não há run associado a esse commit, sem indicação de falha.

## Documentos de referência

- [Catálogo de skills, capacidades e conectores](skills-connectors/CATALOG.md)
- [Inventário de capacidades para agentes](skills-connectors/CAPABILITY_INVENTORY.md)
- [Protocolo de contexto e memória](skills-connectors/CONTEXT_MEMORY_PROTOCOL.md)
- [Arquitetura multiagente](architecture/jarvis-multi-agent-platform.md)
- [Planos declarativos de execução](architecture/declarative-execution-plans.md)
- [Auditoria de entregas](VERIFICACAO_ENTREGAS.md)
- [Guia de uso](GUIA_DE_USO.md)

## Regra de atualização do roadmap

Só marcar como concluído quando os critérios de aceitação correspondentes tiverem evidência verificável. Para funcionalidades de produção, exigir também confirmação de deploy, saúde e conectividade reais. Um arquivo, skill, migração, PR merged ou campo status=complete no inventário, isoladamente, não comprova comportamento funcional.


## Revalidação técnica — 2026-11-08 21:54 UTC

**Base consultada:** main em 6f2222a24b829c13db96c561c0691e50c070e494. PRs abertas observadas: #783 (recuperação do MCP Tunnel em disco cheio), #782 (refresh C0), #777 (Laya shadow mode) e #781 (referência DeepSeek). Issues abertas observadas: #708 (fronteira de autoevolução), #732 (ledger Supabase), #682 (proteção de main) e #723 (RPCs/ledger provider-aware). Não foram criadas issues nem PR duplicadas.

**Roadmap e código**
- PR #775 merged: RoadmapMissionSelector é consumido pelo workflow agendado; manifesto vazio e testes confirmam no-op seguro. O inventário data/capabilities.json deixou de ser fonte de seleção.
- PR #776 merged: enqueue deriva owner da identidade autenticada e persiste created_by/owner_id; sinal task_blocked usa o owner consultado da tarefa.
- PR #779 merged: HostToolAuthorizationPolicy está implementada, exportada e testada; não foi localizada instanciação em composition root de produção. Não declarar autorização de ferramentas operacional.
- PRs #778/#780: arquitetura Wake/Sleep é documental; filtro de dataset foi endurecido, mas treinamento permanece desabilitado e gates de privacidade não comprovados.
- docs/COGNITIVE_ROADMAP.md não foi alterado. C0 permanece aberto; C1 não iniciado.

**Actions/CI**
- Main commit #779: Task Queue Tests run 42526509992 — success; Auto-Documentation run 42526509993 — success.
- PR #777: runs 42523333002 e 42523333055 — success.
- PR #781: run 42523339700 — success.
- PR #783: runs 42524233623 e 42524233622 — success no head consultado.
- PR #782: run 42523443734 executou frontend, build Docker e pytest completo com success no head anterior; a atualização documental desta PR precisa de novos checks.
- Não foi executado pytest local nesta sessão. Não usar os checks antigos como evidência do novo commit da PR #782.
- Comentários do Codex em #777/#779/#781/#783 reportaram limite de uso; não há revisão automatizada independente concluída para esses heads.

**Limites e segurança**
- API da branch main: protected=false, protection.enabled=false; não há required checks. Issue #682 continua aberta.
- homeostase.yml e jarvis-pr-validation.yml continuam versionados na main e não foram alterados.
- Nenhum merge, deploy, migration, alteração de secrets, feature flag ou ação destrutiva foi executado.
- Não foi possível confirmar o valor atual de EVOLUTION_ENABLED, uma execução schedule específica, composição de produção da policy host-backed, credenciais individuais de worker ou insert/readback vetorial em runtime.


## Snapshot Supabase read-only — 2026-11-08 22:10 UTC

- Projeto saibtpdehhprttqlgqdt: ACTIVE_HEALTHY; PostgreSQL 17.6.1.063. A lista de branches retornou somente main (FUNCTIONS_DEPLOYED; preview_project_status ACTIVE_HEALTHY).
- Ledger remoto e arquivos locais: **29/29 correspondências exatas de version + name**; última migration 20261108120000_agent_task_ownership.sql. Issue #732 continua aberta para schema/Preview/rollback; não houve migration, repair ou DDL/DML nesta auditoria.
- Tarefas: 13 linhas — 8 completed, 3 cancelled, 2 ready — e 0 com owner_id/created_by. Credenciais de worker: 0. Agentes: 3 available, 2 offline. Rotinas persistidas: 0.
- Memória vetorial: 0 linhas. Intelligence event/observation snapshots: 0. Worker runs: 0. Lease: uma linha com worker_id e lease_expires_at NULL.
- RLS está habilitado sem policies nas seis tabelas C0 consultadas; grants observados apenas para service_role, sem grants anon/authenticated. Advisor global reportou 30 tabelas com RLS/no policy (INFO), mas não foram auditados grants de todas as 30.
- Advisor de performance reportou 42 índices unused (INFO). Não remover sem medir workload. A consulta de logs Supabase não encontrou mensagens “recurring worker” na janela de 24h; isso não prova estado da feature flag Render.


## Delta da auditoria recorrente — 2026-11-08 22:27 UTC

- Main revalidada em `6f2222a24b829c13db96c561c0691e50c070e494`; branch protection segue ausente (`protected=false`, sem required checks). Issue #682 permanece aberta por depender de configuração administrativa.
- Issue #708 fechada após validação em código, testes de regressão, teste real Docker no CI e separação de permissões/credenciais. A fronteira de sandbox/publicação está coberta; isso não declara a autoevolução funcional.
- CI atual das PRs: #782 full pytest **2.786 passed, 14 skipped, 8 warnings** (run 42529184685); #783 PowerShell parser e PR validation success nos runs 42524233622/42524233623; #777 PR Validation e Task Queue success; #781 PR Validation success. Falhas antigas do parser PowerShell em #783 foram corrigidas em commits posteriores; não há falha atual pendente.
- PRs abertas: #782, #783, #777 e #781. Nenhuma foi merged nesta auditoria.
- Issues abertas: #682, #732 e #723. A #732 continua exigindo validação schema-aware/Preview; a #723 permanece vinculada a esse histórico.
- `data/roadmap_missions.json` continua vazio; a evolução agendada permanece em no-op seguro. C0 segue aberto; C1 não iniciado. Não criar missão nem atribuir target sem mapeamento revisado de critério, código e teste.
- Self Healing V3 e PR Validation foram preservados sem alteração. Nenhuma migration, deploy, alteração de secrets/flags ou escrita em produção foi executada.


## Atualização pós-merge — 2026-11-08 22:39 UTC

- PR #784 foi merged pelo usuário às 22:38:28 UTC, commit `c0ceefcc6c2986499f5b1cf0e1a4757282f4242f`. O merge não foi executado por esta auditoria.
- A mudança expõe `PsutilHostAdapter` por ferramenta MCP de diagnóstico somente leitura: identidade do host, CPU/RAM, volumes e até 50 processos, sem command lines, variáveis de ambiente ou conteúdo de arquivos.
- A correção do teste de observabilidade WebSocket sincroniza o evento recebido do Chromium/CDP antes de consultar o buffer; mantém asserções para abertura e frames enviados/recebidos.
- CI do head da PR #784: Portas de navegador success; JARVIS PR Validation **2.794 passed, 14 skipped, 8 warnings**; Task Queue Tests **2.793 passed, 15 skipped, 80 warnings** e foco da fila 15/15. O teste de navegador que falhou no primeiro run passou após a sincronização; nenhuma cobertura foi removida.
- Validação pós-merge na main (runs 42531241885 e 42531241814) ainda estava em execução no momento deste registro. A execução de Auto-Documentation 42531241847 terminou com success.
- A integração MCP de diagnóstico está comprovada em código e CI, mas ainda não foi executada no Windows do usuário; depende da restauração do Secure MCP Tunnel. Não inferir diagnóstico atual de disco/RAM a partir dos testes.


### C0 blocker — selector completion status versus proven STATUS

- Confirmed from `app/application/services/roadmap_mission_selector.py`: the selector validates criterion IDs against the roadmap, but reads no `docs/STATUS.md`. A dependency is treated as complete when its manifest entry says `status: complete`; no evidence pointer or STATUS corroboration is required.
- `data/roadmap_missions.json` is currently empty, so the scheduled workflow remains a safe no-op. No LLM generation, Docker candidate execution or publication occurs.
- Before a reviewed mission is marked ready, define and test a fail-closed evidence contract binding each completed criterion to the proven state in STATUS. Also add an integration test using the actual C0 criterion IDs from the production roadmap; the selector's current dependency tests use synthetic IDs in a fixture.
- This is the next C0 hardening task. Do not populate the manifest or begin C1 until C0's capability map, behavioral baseline, evidence provenance and completion-state consistency are verified.




## Auditoria recorrente — 2026-11-08 — revalidação da main

**Snapshot:** `main` em `ccaea37134f0c73012fda436dcf151212000dc55` (merge da PR #785).

- PR #785 foi merged pelo usuário. O head da PR passou no pytest completo (run 42531527379) e na validação PowerShell (42531527338). PR #784 também foi merged; seus checks de Chromium/CDP, pytest completo e Task Queue concluíram com success (runs 42530829407, 42530829424 e 42530829368).
- PRs abertas observadas: #782, #786, #777 e #781. CI dos heads consultados: #786 full pytest e Task Queue success (42531696010/42531695981); #777 PR Validation e Task Queue success (42523333002/42523333055); #781 full pytest success (42523339700). PR #782 teve sucesso no head anterior (42531878759), mas os novos commits de selector/testes precisam de validação própria.
- No commit atual de main, a API retornou apenas o check `Supabase Preview: skipped`; não foi localizado full pytest associado exatamente ao SHA `ccaea371...`. O sucesso dos heads de PR anteriores não substitui validação do merge atual.
- Issues abertas: #682 (proteção de main), #732 (reconciliação schema-aware/Preview do ledger) e #723 (RPCs provider-aware).
- A consulta atual de branch protection retornou 403 (`Resource not accessible by integration`). A última evidência administrativa registrada em 2026-11-08 22:27 UTC indicava `protected=false` e nenhum required check; o estado atual não pôde ser revalidado nesta passagem.
- `homeostase.yml` (Self Healing V3) e `jarvis-pr-validation.yml` continuam presentes na main. A PR #782 não altera esses workflows nem suas permissões.
- Percepção: `collect_live_intelligence` é consumido pelo dashboard autenticado e pelo desktop local; o worker recorrente também usa o coletor, mas depende de duas flags separadas. Testes existentes cobrem falha parcial de fonte, falha de observações OSIRIS sem descartar eventos, deduplicação determinística de eventos, deduplicação de snapshots de observação, proveniência e lease/persistência isoladas. Os testes do worker usam collector/history fakes; não foi localizado nesta passagem um teste ponta a ponta do coletor real até persistência e consumidor. O último log Render documentado (07/11) dizia que o worker estava desabilitado; não foi reconsultado nesta execução.
- A PR #782 adiciona gate de evidência em STATUS e ordem entre fases: o ledger deve cobrir todos os IDs de aceitação do roadmap; toda missão marcada complete exige evidência estruturada; C1 exige dependência explícita de todos os critérios C0. O ledger atual mantém os três critérios C0 como pending. `data/roadmap_missions.json` permanece vazio, portanto a evolução agendada continua em no-op seguro.
- C0 permanece aberto. Próximo critério: consolidar um teste comportamental integrado que ligue coleta real, falha parcial, síntese/deduplicação/proveniência, persistência e consumidor; comprovar runtime/persistência sem habilitar o worker ou alterar produção. C1 continua bloqueado.
- Nenhum merge, deploy, migration, alteração de secrets/flags, escrita em produção ou alteração dos workflows de self-healing foi executado por esta auditoria.

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


## Revalidação read-only — 2026-11-09

**Base consultada:** `main` em `00143238801ccac38c7ed82596af46db49f67f75`. PRs abertas: **0**. Issues abertas: #682, #723 e #732. Esta revalidação não executou DDL/DML, migration repair, `db push`, deploy, alteração de secrets/flags, permissões ou workflows.

### Merges e evidência de CI

- PR #782 (refresh C0) merged em `de181704`; a versão final passou no full pytest Linux e na suíte Windows. Os primeiros runs falharam em dois testes do selector que esperavam `RoadmapManifestError`, mas o cenário não lançava a exceção. A correção ficou na PR correspondente; não houve redução de testes ou cobertura.
- PR #787 (approvals duráveis) merged em `d86db76c`; a migration `20261108193000_durable_tool_approvals` aparece no ledger de produção.
- PR #788 (PowerShell restrito pelo MCP Tunnel) merged em `00143238`; os checks de integração, pytest e build do head final passaram. A revisão Strix identificou inicialmente o risco de `-ComputerName`/RPC-NTLM; commits posteriores adicionaram allowlist de parâmetros por cmdlet e testes para `-ComputerName`, `-CimSession` e `-OutVariable`. O thread de revisão continua aberto e não há re-review Strix do commit final; registrar a correção de código não equivale a aprovação independente.
- No commit atual, `Jarvis Task Queue Tests` e `Auto-Documentation JARVIS` passaram (runs 42619019715 e 42619019669). O run 42616056149 falhou apenas no `git push` do Auto-Documentation: o commit gerado ficou atrás de uma atualização concorrente de `main` (non-fast-forward). Um run posterior passou; a condição de corrida no workflow ainda existe.
- `JARVIS Self Healing V3` permanece ativo. Seu gatilho atual aceita falhas de workflows executados em `main`, mas não inclui `JARVIS PR Validation` nem `Jarvis Task Queue Tests` como fontes de falha de PR; portanto, não é evidência de auto-correção de branches de PR.

### Supabase — snapshot somente leitura

- `list_migrations`: **30 entradas remotas**; `supabase/migrations`: **30 arquivos locais**; comparação por versão e nome: **30/30 exatos**. A migration mais recente é `20261108193000 / durable_tool_approvals`. Isso elimina a divergência de version/name observada anteriormente, mas não fecha #732: equivalência de schema, Supabase Preview e rollback ainda não foram comprovados.
- `public.jarvis_tool_approvals`: tabela presente, owner `postgres`, RLS habilitado (não FORCE), **0 linhas**. `anon` e `authenticated` não possuem SELECT/INSERT/UPDATE/DELETE; `service_role` possui os quatro privilégios. O advisor classifica RLS sem policy como INFO; para esta tabela, a ausência de policy é coerente com a ACL server-only observada, não prova de exposição pública.
- Fila: **5 agentes**, **13 tarefas**, **0/13** com `owner_id`, **0/13** com `created_by`, **0 credenciais de worker ativas**. A migration de ownership está presente, mas os registros legados continuam sem proprietário; não fazer backfill presumido.
- Universal Intelligence: **0** snapshots de eventos, **0** snapshots de observações e **0** runs do worker recorrente. Isso não prova ausência de coleta local sob demanda, mas não comprova persistência/recorrência de produção.
- Advisors: **31** tabelas com RLS sem policy (INFO), incluindo a tabela de approvals; **43** índices reportados como unused (INFO). Não remover índices sem medir workload; a tabela de approvals tem zero linhas e seus índices ainda não têm uso operacional.

### Autorização e C0

- `ToolApprovalStore` existe e sua migration está aplicada, mas não há API de criação/confirmação de approval, resolver de sessão autenticada, composição dos resolvers owner/executor nem registro `tool_authorization_policy` no Nexus. O JWT atual não carrega `sid`/session claim e `get_current_user` não fornece session_id. `ToolDispatcher` continua fail-closed; não declarar dispatch operacional.
- O ledger de evidência cognitiva continua com os três critérios C0 em `pending`; `data/roadmap_missions.json` permanece vazio. Nenhum critério foi promovido por presença de migration, PR merged ou CI isolado.
- C0 continua aberto. C1 — World Model — permanece bloqueado até a aceitação C0 e não deve começar nesta etapa.


### Perception ambiental — snapshot read-only 2026-11-09

- Consulta SQL somente leitura em `public.jarvis_environment_observations`: **1.755 registros** (878 `presence`, 877 `network_snapshot`); **0 não expirados e 1.755 expirados**. Último `received_at`: `2026-11-03 15:11:28 UTC`; maior `expires_at`: `2026-11-03 15:16:27 UTC`. O router define TTL de 2 minutos para presença e 5 minutos para network snapshot. A consulta não leu payloads nem identificadores.
- Isso comprova ingestão histórica da trilha de observação ambiental, mas não telemetria atual nem recorrência em 2026-11-09. Não confundir esta tabela com `intelligence_observation_snapshots`, que continua com 0 linhas. Portanto Perception permanece parcial e sem evidência de frescor operacional.


## Revalidação pós-merge — 2026-11-09 — PRs #789–#791

- GitHub confirma PRs #789, #790 e #791 como merged. #789 atualiza evidência C0; #790 adiciona teste integrado do coletor/core/worker/history adapter com dependências simuladas; #791 serializa escritas do Auto-Documentation e faz checkout do main atual antes da geração.
- Checks associados aos heads finais: #789 PR Validation run 42641532396 success; #790 PR Validation 42641924299 success e Task Queue 42641924074 success; #791 PR Validation 42642600559 success. Esses checks comprovam os respectivos commits/ambientes de CI, não execução recorrente ou persistência atual em produção.
- A revisão do código em main confirma que RoadmapMissionSelector lê o ledger estruturado de docs/STATUS.md por _load_status_evidence. Uma missão marcada complete exige o mesmo criterion_id como verified, commit URL, Actions run URL, paths existentes de implementação/consumidor/testes e correspondência do target/testes. O parser valida formato e existência local; não autentica o commit ou o resultado do Actions remotamente.
- A nota histórica anterior que afirmava que o selector não lia STATUS foi supersedida pela implementação da PR #782, já merged. A limitação restante é que o teste real do repositório para manifesto vazio retorna antes de exercitar o parser do ledger.
- PR #790 fecha o teste integrado de percepção local, mas não prova worker ativo nem snapshots persistidos em produção. PR #792 foi merged: `tests/application/test_roadmap_mission_selector.py` exercita `_load_status_evidence` contra o STATUS real e confirma os três critérios C0 como `pending`; PR Validation run 42647241982 e Task Queue run 42647241960 passaram. O teste do manifesto vazio continua sendo um no-op e não substitui essa cobertura dedicada.
- data/roadmap_missions.json permanece com missions vazio. C0-CAPABILITY-MAP, C0-GAPS-RECORDED e C0-NO-NAME-BASED-COMPLETION permanecem pending. C1 — World Model — continua bloqueado.
- Issues abertas verificadas: #682 (proteção da main), #723 (histórico/Preview relacionado às RPCs provider-aware) e #732 (reconciliação schema-aware, Preview e rollback). Nenhuma issue nova foi criada.
- Self Healing V3 e JARVIS PR Validation permanecem presentes. A documentação do repositório confirma que Self Healing atua em falhas/timouts/cancelamentos originados na main; não processa runs de PR. Não desabilitar nem reduzir essa proteção. Extensão segura para PRs exige separar execução de código não confiável e credenciais privilegiadas.
- Nenhum merge, deploy, migration, alteração de secrets/flags, DDL/DML ou alteração de produção foi executado nesta revalidação.


## Revalidação recorrente — 2026-11-09 — main #794

**Base consultada:** `main` em `1ac9186eedb6ab0825d6254aaa8c3204582f4a11`. O commit #794 foi implantado automaticamente no Render; o deploy `dep-dbp301favr4c73e6comg` terminou `live` em 2026-11-09 20:43:42 UTC. Esta auditoria não acionou deploy.

### PRs, issues e governança

- No início da auditoria: PRs abertas **0**. A PR #757, que separou geração de candidato e publicação privilegiada, já está merged; PRs #792, #793 e #794 também estão merged. Esta revalidação abriu a PR documental #795.
- Issues abertas: #682 (proteção de `main`), #723 (reconciliação das RPCs provider-aware/Preview) e #732 (histórico de migrations/Preview/rollback).
- A API da branch retorna `protected=false`, `protection.enabled=false`, required checks `off` e nenhum contexto obrigatório; a API de repository rulesets retorna `[]`. O endpoint administrativo de branch protection não está acessível ao conector. A issue #682 continua bloqueada por acesso administrativo.
- Nenhuma issue foi criada ou fechada nesta auditoria.

### CI e correção contínua

- PR #792: PR Validation run [42647241982](https://github.com/TheDrack/Jarvis_Xerife/actions/runs/42647241982) e Task Queue run [42647241960](https://github.com/TheDrack/Jarvis_Xerife/actions/runs/42647241960) passaram. O teste real do ledger C0 está em `tests/application/test_roadmap_mission_selector.py`.
- PR #793: PR Validation [42677389755](https://github.com/TheDrack/Jarvis_Xerife/actions/runs/42677389755) e Task Queue [42677389547](https://github.com/TheDrack/Jarvis_Xerife/actions/runs/42677389547) passaram.
- PR #794: PR Validation [42693842123](https://github.com/TheDrack/Jarvis_Xerife/actions/runs/42693842123), Task Queue [42693842031](https://github.com/TheDrack/Jarvis_Xerife/actions/runs/42693842031) e Browser Tests [42693842090](https://github.com/TheDrack/Jarvis_Xerife/actions/runs/42693842090) passaram. No pytest Linux/Python 3.11.18: **2.888 passed, 15 skipped, 8 warnings**.
- Após o merge, Task Queue run [42694784471](https://github.com/TheDrack/Jarvis_Xerife/actions/runs/42694784471) passou no HEAD #794; pytest Windows/Python 3.12.10: **2.888 passed, 15 skipped, 181 warnings**. Auto-Documentation run [42694785391](https://github.com/TheDrack/Jarvis_Xerife/actions/runs/42694785391) também passou.
- O run main [42646055614](https://github.com/TheDrack/Jarvis_Xerife/actions/runs/42646055614), no SHA anterior `601f7c4`, falhou somente em `test_windows_runner_executes_an_allowlisted_command_end_to_end`: `Get-Date` excedeu o timeout de 10 s. O teste direcionado passou 15/15 e o restante da suíte passou; a suíte completa em HEAD posterior #794 passou sem alteração desse teste. Classificação: timeout transitório do runner/ambiente Windows, provável flakiness de inicialização do PowerShell; não há evidência de defeito determinístico no código. Nenhum teste foi removido, afrouxado ou reexecutado artificialmente.
- Os runs cancelados de heads intermediários da PR #793 ocorreram quando a branch avançou; o head final passou. Não são falhas de teste.
- `homeostase.yml` (Self Healing V3) permanece ativo e inalterado. Seu gatilho aceita workflows selecionados originados em `main`; não inclui JARVIS PR Validation nem Jarvis Task Queue Tests. Portanto, o workflow preservado não é um auto-healer de falhas de branches de PR. Não foi feita extensão privilegiada nesta auditoria: ela exigiria uma fronteira explícita entre código de PR não confiável e publicação com credenciais.

### Autoevolução agendada

- O run agendado mais recente localizado foi [42669010758](https://github.com/TheDrack/Jarvis_Xerife/actions/runs/42669010758), no SHA anterior `36d47cb`. O job Gate registrou `EVOLUTION_ENABLED` vazio e a mensagem `Auto-evolução pausada (EVOLUTION_ENABLED != true)`; geração/sandbox e publicação foram `skipped`.
- `data/roadmap_missions.json` permanece com `missions: []`. São dois bloqueios independentes: a variável de ativação não está em `true` e não há missão revisada aprovada. Nenhum LLM, Docker candidato ou publisher foi executado. Não alterar flags/secrets nesta auditoria.

### Supabase e runtime — consultas somente leitura

- Projeto `saibtpdehhprttqlgqdt`: `ACTIVE_HEALTHY`, PostgreSQL 17.6.1.063.
- Ledger remoto: **30 migrations**; diretório local: **30 arquivos SQL**, correspondência exata de versão e nome **30/30**. Última entrada: `20261108193000 / durable_tool_approvals`. Isso resolve a divergência de nomes/versões do inventário anterior, mas **não fecha #732**: comparação schema-aware, Preview descartável e plano de rollback continuam sem validação. A lista de branches Supabase retornou apenas `main`; não foi criada branch paga.
- `jarvis_agent_tasks`: 13 linhas, 0 com `owner_id`, 0 com `created_by`. `jarvis_agents`: 5 (3 available, 2 offline). Credenciais ativas de agentes: 0. `jarvis_tool_approvals`: 0. `jarvis_vector_memories`: 0.
- `intelligence_event_snapshots`: 0; `intelligence_observation_snapshots`: 0; `jarvis_intelligence_worker_runs`: 0. A única linha da lease tem `worker_id=NULL` e `lease_expires_at=NULL`.
- `jarvis_environment_observations`: 1.755 registros, 0 não expirados; último `received_at` em 2026-11-03 15:11:28 UTC e maior `expires_at` em 15:16:27 UTC. Há ingestão histórica, não telemetria fresca.
- Logs do Render `Jarvis-api` registraram `Universal Intelligence recurring worker disabled by feature flags` até 2026-11-09 20:43:31 UTC, inclusive após o deploy #794. O deploy está live, mas o worker recorrente continua desabilitado.
- Advisor de segurança: 31 tabelas com RLS habilitado e sem policies (INFO). Consulta de privilégios confirmou zero grants de SELECT/INSERT/UPDATE/DELETE para `anon` e `authenticated` nessas 31 tabelas; `service_role` possui ao menos um desses privilégios em 30/31. O aviso não equivale a exposição pública. Advisor de health: nenhum finding.
- Advisor de performance: 43 índices marcados como unused (INFO). Não remover: tabelas vazias, baixo tráfego e janela de observação curta podem explicar o resultado; medir workload antes de qualquer alteração.

### Estado cognitivo

- PR #790 já comprova em CI a composição local do coletor, Core, worker e adaptador de histórico com doubles determinísticos; PR #792 acrescenta teste do ledger real de STATUS. Isso não prova worker ativo, persistência real ou consumer autenticado ponta a ponta.
- Os três critérios `C0-CAPABILITY-MAP`, `C0-GAPS-RECORDED` e `C0-NO-NAME-BASED-COMPLETION` permanecem `pending`; o ledger não foi alterado. `docs/COGNITIVE_BASELINE.md` precisa distinguir o mapa local/testado dos consumidores e runtime ainda não verificados.
- C0 permanece aberto; C1 — World Model — permanece bloqueado. Não criar contratos, banco de grafos, event bus, memória ou scheduler paralelo.

**Operações de ambiente:** consultas somente leitura no Supabase e Render; nenhum DDL/DML, migration, deploy manual, alteração de secret/flag, mudança de permissão ou alteração de produção foi executado. **Mutação GitHub:** somente branch isolada e atualização destes dois documentos; sem alteração de código/workflows, commit na main ou merge.

- Achado C0 adicional: `CognitiveRouter` aparece no registro Nexus e em `config/pipelines/jarvis_chat.yml`, mas a busca não encontrou teste de `execute()` nem prova de execução ponta a ponta do pipeline. `assistant_curiosity.py` chama `CuriosityEngine.execute()` com ações `detect_gaps` e `store_answer`, enquanto o engine só aceita `analyze`, `explore` e `suggest`; a captura de resposta também retorna `(False, None)` em falha, descartando o `pending_need_id`. Não foram encontrados callsites dos helpers nem testes comportamentais dedicados. É defeito de contrato confirmado no código, mas impacto em runtime permanece provável/não confirmado porque o consumidor não foi localizado. Não corrigir por adivinhação antes de identificar a composição pretendida.
