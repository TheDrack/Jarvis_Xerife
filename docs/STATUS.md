# JARVIS — Status do Projeto

**Versão:** 2.0.0  
**Revisão documental:** 2026-11-12
**Escopo desta revisão:** revalidação pós-merge #817 e acompanhamento da PR #818; C0, integrações, multiagente, CI, segurança e workflows. Runtime/produção só são declarados com evidência direta e datada.

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

- Achado C0 adicional (revalidado em 2026-11-10): `config/pipelines/jarvis_chat.yml` referencia `cognitive_router`, mas `data/nexus_registry.json` não contém mapeamento explícito para esse ID; o consumo de `run_pipeline("jarvis_chat")` não foi localizado fora do CLI/testes. O contexto do runner não injeta `metadata`, embora `CognitiveRouter.execute()` a acesse; runtime do pipeline permanece não verificado. `capture_curiosity_answer()` foi corrigido pela PR #796 para preservar `pending_need_id` em falha e agora possui cinco testes diretos, mas ainda envia `store_answer`, ação não suportada pelo `CuriosityEngine` (`analyze`, `explore`, `suggest`). `maybe_inject_curiosity_question()` envia `detect_gaps`, também não suportada, sem teste comportamental ou consumidor de produção localizado. `CuriosityIntake` é outro componente: está registrado e exposto por wrappers MCP, mas os testes atuais não invocam esses wrappers. Ver a seção `Delta de auditoria — 2026-11-10` para a evidência completa. C0 permanece aberto; não inferir runtime.


## Delta de auditoria — 2026-11-10 — PR #805, CI e revalidação C0

**HEAD consultado:** `main` em `956583a9fa69728b40613ceb81133e60b8da3cde`. O commit `dd7af8d06b9bc562669503dda2423939c159ac82` é o merge da PR #805 e o pai direto do HEAD atual. A comparação confirma que o commit posterior `956583a` altera somente `ARCHITECTURE.md` (atualização automática, mensagem `[skip ci]`); portanto o último código executável foi validado no pai `dd7af8d`.

### PRs, issues e CI

- Não havia PRs abertas na consulta `GET /pulls?state=open`.
- **PR #805 — merged em 2026-11-10 21:36:20 UTC:** correções do GEV/HUD, clima e persistência OSINT. Head final: `9ccc318b42b8795e211f3b5459f0751df5456546`.
- PR Validation run [42905716363](https://github.com/TheDrack/Jarvis_Xerife/actions/runs/42905716363): success no head final; **3.143 passed, 34 skipped, 8 warnings**, 64,02 s.
- Task Queue run [42905716297](https://github.com/TheDrack/Jarvis_Xerife/actions/runs/42905716297): success no head final.
- Main Task Queue run [42906674072](https://github.com/TheDrack/Jarvis_Xerife/actions/runs/42906674072): success no merge commit `dd7af8d`; **3.160 passed, 17 skipped, 181 warnings**, 114,52 s. Auto-Documentation run [42906674081](https://github.com/TheDrack/Jarvis_Xerife/actions/runs/42906674081): success.
- **Falha real corrigida dentro da PR #805:** run [42903577636](https://github.com/TheDrack/Jarvis_Xerife/actions/runs/42903577636), SHA `a53e9622942f1b1d1a4d80ceb656856a39fac47b`, falhou em `tests/test_regression_guards.py::TestNoUndefinedNames::test_pyflakes_reports_no_undefined_names_in_app`: `IntelligenceEvidence` indefinido em `app/adapters/edge/jarvis_desktop_local.py:1011`. A PR adicionou o import ausente; os checks do head final e da main passaram. Classificação: defeito determinístico de código, corrigido na mesma PR; não flakiness/infraestrutura.

### Segurança e revisão da PR #805

- O finding de descoberta cross-profile do `intelligence.env` não corresponde ao código final: a configuração usa somente caminho explicitamente indicado, `LOCALAPPDATA` e o home do usuário; não enumera `/mnt/c/Users`.
- O finding de permissão do arquivo de ambiente não considera a normalização posterior: o provisioner faz `chmod 600` depois da substituição atômica do arquivo, e `test_provisioner_enforces_environment_permissions_after_atomic_replacement` verifica essa ordem.
- Os campos meteorológicos apontados pelo finding XSS são escapados por `esc()`, que codifica `& < > " '`; `test_weather_panel_escapes_every_external_string_before_html_insertion` verifica os nove campos/expressões citados. O thread Strix permanece sem resolução no GitHub; a evidência do código final não confirma o sink descrito.
- A PR também registra como resolvidos os achados de bind da API, coordenadas não finitas e crescimento ilimitado do cache. Não foi identificado nesta revisão um finding de segurança confirmado que justifique uma nova PR corretiva.

### Autoevolução e Self Healing

- Workflow agendado [42905628673](https://github.com/TheDrack/Jarvis_Xerife/actions/runs/42905628673): gate executado com sucesso, mas `EVOLUTION_ENABLED` estava vazio. Geração/validação isolada e publicação privilegiada foram skipped.
- `data/roadmap_missions.json` continua com `missions: []` e hold reason explícito: C0 aberto, sem mapeamento revisado de critério → alvo Python → testes.
- Self Healing V3 permanece versionado e não foi alterado. Run [42905657841](https://github.com/TheDrack/Jarvis_Xerife/actions/runs/42905657841) ficou skipped. `homeostase.yml` observa somente os workflows listados, em eventos confiáveis de `main`; não lista JARVIS PR Validation nem Jarvis Task Queue Tests. Logo, não declarar que o healer corrige falhas originadas em branches de PR. A trilha de correção automática permanece preservada, sem conceder ao executor de PR credenciais de publicação.

### Governança e pendências externas

- Consulta atual da API: `main.protected=false`, `protection.enabled=false`, required checks com enforcement `off`, listas de checks vazias e `rulesets=[]`. Issue [#682](https://github.com/TheDrack/Jarvis_Xerife/issues/682) permanece aberta. O conector disponível nesta execução oferece leitura desses endpoints, mas não uma operação de escrita para branch protection/rulesets; nenhuma configuração administrativa foi alterada.
- Issues abertas: [#682](https://github.com/TheDrack/Jarvis_Xerife/issues/682), [#723](https://github.com/TheDrack/Jarvis_Xerife/issues/723) e [#732](https://github.com/TheDrack/Jarvis_Xerife/issues/732). #723 mantém o guard provider-aware já implantado; a reconciliação do histórico/Preview continua rastreada em #732. Nenhuma issue foi criada.

### Estado C0 após esta revalidação

- Os três critérios `C0-CAPABILITY-MAP`, `C0-GAPS-RECORDED` e `C0-NO-NAME-BASED-COMPLETION` continuam **pending**. C1 permanece bloqueado.
- `CognitiveRouter`: `config/pipelines/jarvis_chat.yml` referencia `cognitive_router`, mas `data/nexus_registry.json` não contém mapeamento explícito para esse ID. O Nexus pode tentar descoberta por filesystem quando não está em strict mode; isso não prova consumo. Graphify não encontrou callers estritos nem testes ligados a `CognitiveRouter.execute()`. O grafo de `run_pipeline()` mostra apenas o CLI do próprio módulo e testes, sem consumidor de aplicação identificado. Além disso, o contexto inicial de `run_pipeline` não cria `metadata`, enquanto `CognitiveRouter.execute()` acessa `context["metadata"]`; há incompatibilidade potencial se o pipeline for chamado sem `inputs.metadata`. Runtime externo permanece não verificado.
- `CuriosityIntake` é distinto de `CuriosityEngine`: está registrado no Nexus; `curiosity_capture` e `curiosity_list_recent` são funções `@mcp.tool` que resolvem `curiosity_intake` e chamam `execute()`. Os testes atuais cobrem o componente diretamente e verificam estaticamente o contrato MCP, mas não invocam os wrappers via MCP.
- `assistant_curiosity.py` ainda envia `detect_gaps` e `store_answer`; `CuriosityEngine.execute()` aceita somente `analyze`, `explore` e `suggest`. A correção da PR #796 preserva `pending_need_id` após falha e tem cinco testes diretos, mas não implementa armazenamento de respostas. Graphify encontra somente testes como callers de `capture_curiosity_answer()`; não localiza consumidor de produção para esses helpers. O impacto operacional permanece não confirmado.
- Próximo critério: fechar o mapa de composição/consumidores e o contrato de entrada do `CognitiveRouter`; adicionar teste de integração pelo consumidor real ou documentar formalmente que o pipeline é legado/não utilizado. Separadamente, testar os wrappers MCP reais e decidir se os helpers de `CuriosityEngine` devem receber ações válidas e um consumidor, sem criar outro motor. Não iniciar C1 antes da aceitação C0.

## Delta de auditoria técnica — 2026-11-11 — PR #811 e revalidação C0

**Base auditada:** `main` em `00c69fd8437f24ee3518e147a8476baf3c544e2a`. O último commit principal continua sendo a integração da captura binária CDP da PR #810.

### PRs, CI e continuidade

- PR [#811 — limpar metadados retidos dos fluxos de mídia](https://github.com/TheDrack/Jarvis_Xerife/pull/811) está aberta, mergeable e não merged. A branch `fix/portas-clear-media-state-20261111` contém a correção e seu teste de regressão. O commit de código/teste `ee7e0e21f59a339916dc9f577a05ec22704023e3` passou nos três workflows abaixo; esta atualização documental é um commit separado e terá checks próprios.
- PR Validation run [43106444703](https://github.com/TheDrack/Jarvis_Xerife/actions/runs/43106444703): success; pytest Linux/Python 3.11: **3.184 passed, 34 skipped, 8 warnings**, 80,23 s. Build do sandbox hardened também passou.
- Task Queue run [43106444689](https://github.com/TheDrack/Jarvis_Xerife/actions/runs/43106444689): success; pytest Windows/Python 3.12: **3.200 passed, 18 skipped, 181 warnings**, 136,07 s.
- Portas browser run [43106444669](https://github.com/TheDrack/Jarvis_Xerife/actions/runs/43106444669): success; testes unitários **31 passed, 1 warning** e integração Chromium/CDP **7 passed, 1 warning**. O novo teste `test_clear_removes_media_stream_metadata_and_indexes_without_stopping_capture` passou.
- Graphify review da PR #811: gate `pass`, zero findings bloqueantes e um advisory de fan-out do teste (7 chamadas); Graphify não executou testes. A validação comportamental vem dos workflows acima.
- PR #809 continua aberta, `mergeable=false`, com 37 commits à frente e 69 atrás da `main`; o head atual não tem workflow run associado. O review Graphify disponível para #809 está ligado a outro SHA (`2105870`), não ao head atual (`1a60d368`), portanto não é evidência de revisão do estado atual. Não atualizar nem integrar essa branch divergente sem reconciliação de diff e revalidação.
- PRs #807, #808 e #810 estão merged. Na #810, PR Validation [43065158699](https://github.com/TheDrack/Jarvis_Xerife/actions/runs/43065158699) passou com **3.157 passed, 34 skipped, 8 warnings**; Task Queue [43065158870](https://github.com/TheDrack/Jarvis_Xerife/actions/runs/43065158870) passou com **3.174 passed, 17 skipped, 181 warnings**; Portas browser [43065158904](https://github.com/TheDrack/Jarvis_Xerife/actions/runs/43065158904) passou com **31 unit tests e 7 integração**.

### Correção de retenção no observador Portas

- O tool MCP `portas_trafego_limpar` chama `BrowserTrafficObserver.clear()`. Na `main` anterior à PR #811, `clear()` removia `_events` e `_media_chunks`, mas mantinha `_media_streams`, `_media_request_streams`, `_media_sequences` e `_media_offsets`. Assim, após limpar, `portas_media_eventos` ainda podia expor metadados antigos de fluxo e `portas_media_chunks(stream_id)` ainda reconhecia um stream cujo buffer havia sido apagado. O achado é de retenção/consistência de estado; os valores de query das URLs já eram redigidos.
- A PR #811 limpa os metadados e índices de mídia sob o mesmo lock, informa a quantidade de streams removidos e mantém `_active`, `_capture_media` e as sessões CDP intactas. O teste confirma que eventos/chunks/metadados/índices ficam vazios, que o stream anterior retorna `stream_not_found` e que a captura continua ativa. A mudança ainda não está na `main` nem em produção.
- Achado independente ainda pendente: `_on_media_loading_finished()` define `status="finished"` incondicionalmente e pode sobrescrever `status="truncated"` quando o limite de bytes foi atingido. Isso pode reportar como completo um stream parcial. Não foi incluído na PR #811 para manter uma única melhoria por execução.
- A revisão Graphify da #810 também levantou uma possível corrida em que `_attach_media_page()` poderia registrar uma sessão após shutdown; permanece hipótese não reproduzida, não uma falha confirmada.

### C0 — estado e próximos critérios

- Os critérios `C0-CAPABILITY-MAP`, `C0-GAPS-RECORDED` e `C0-NO-NAME-BASED-COMPLETION` permanecem **pending** no ledger. `data/roadmap_missions.json` continua com `missions: []`; não há missão C0 revisada com target/testes aprovada. C1 — World Model — continua bloqueado.
- Graphify, indexado em `00c69fd`, confirma que os callers estritos de `run_pipeline()` são o próprio CLI e testes; não foi localizado consumidor de aplicação para `run_pipeline("jarvis_chat")`. `config/pipelines/jarvis_chat.yml` referencia `cognitive_router`, mas `CognitiveRouter.execute()` não tem caller estrito nem teste ligado no grafo. O runner aceita `inputs`, mas não injeta `metadata` por padrão; a execução sem esse input pode falhar no acesso `context["metadata"]`. Runtime de aplicação permanece não verificado.
- `CuriosityIntake` está registrado no Nexus e seus wrappers `curiosity_capture`/`curiosity_list_recent` são tools MCP reais que resolvem o componente e chamam `execute()`. O teste atual ainda verifica o contrato MCP estaticamente e testa o serviço isolado; não invoca os wrappers. `assistant_curiosity.py` continua enviando `detect_gaps` e `store_answer`, ações não suportadas pelo `CuriosityEngine` atual (`analyze`, `explore`, `suggest`), sem consumidor de produção identificado.
- Próximo passo C0: fechar o mapa de composition root/consumidores e provar o contrato do router pelo consumidor real, ou documentar o pipeline como legado/não utilizado; em paralelo, testar os wrappers MCP reais e reconciliar os contratos de curiosidade sem criar outro motor. Não iniciar C1 nem adicionar um segundo grafo, memória, event bus ou scheduler.

### Issues, governança e automações

- Issues abertas: [#682](https://github.com/TheDrack/Jarvis_Xerife/issues/682), [#723](https://github.com/TheDrack/Jarvis_Xerife/issues/723) e [#732](https://github.com/TheDrack/Jarvis_Xerife/issues/732). #732 ainda exige equivalência schema-aware, Preview descartável e plano de rollback; #723 mantém a reconciliação histórica/Preview pendente.
- A última evidência direta registrada para branch protection é de 2026-11-05: `main.protected=false` e rulesets vazios. Não foi reconsultada nesta execução porque o conector GitHub disponível não expõe a ação de leitura/escrita administrativa de branch protection/rulesets; não afirmar que o estado atual foi revalidado.
- `.github/workflows/homeostase.yml` e `.github/workflows/auto_evolution_triggerV2.yml` foram inspecionados e não modificados. Self Healing V3 continua restrito a workflows confiáveis originados na `main`; não observa os runs de PR Validation/Task Queue. A autoevolução é horária e fail-closed, mas o manifesto está vazio. Não habilitar flags, criar missão inferida ou entregar credenciais privilegiadas ao executor.
- Nenhum merge, deploy, migration, alteração de secrets/flags, DDL/DML, escrita em produção ou issue nova foi executado nesta auditoria.


## Delta de pesquisa técnica — 2026-11-12 — main 128ec137 e PR #818

**Base auditada:** `main` em `128ec1378569d82155a42d3c234ad61a8ea0d514`.  
**Objetivo:** atualizar evidências posteriores ao delta de 2026-11-11 sem promover critérios C0 nem inferir estado de produção. As seções históricas anteriores permanecem como snapshots de suas respectivas datas.

### PRs, issues e CI

- **PR #807 — merged em 2026-11-11:** endurece o perfil Git read-only contra configuração local que pode executar helpers, aplicando overrides também às sondagens de commit. O escopo declarado não fecha TOCTOU de filesystem nem a contenção de alternates/worktrees vinculados; esses limites permanecem fora da garantia desta PR.
- **PR #808 — merged em 2026-11-11:** integra verificação pós-condição confiável. O código atual passa o resultado bruto do executor ao verifier e usa `output_fields` somente para projetar o resultado visível às etapas seguintes. O TaskRunner canonicaliza aliases de navegação antes de autorização/dispatch e espelha o verifier confiável para os aliases. Verifiers continuam sendo configuração do host; a PR não habilita verificadores de produção por padrão.
- **PR #809 — merged em 2026-11-12:** integra persistência do grafo OSINT, provider Windy, captura de mídia do navegador, endpoints de clima/geocode e kit de provisionamento Linux. O grafo persistido continua sendo OSINT (nós/arestas de investigação), não o World Model cognitivo canônico; não há prova de reconstrução temporal de entidades.
- **PR #811 — merged em 2026-11-12:** limpa metadados e índices de streams no observador Portas sem interromper a captura. Os checks do head final constam na própria PR.
- **Disposição dos findings Strix da PR #809:** o review histórico listou sete findings (URL assinada exposta, buffering de mídia, descoberta de `intelligence.env` entre perfis, bind do API Linux, WAL/SHM sem ignore, geocode sem opt-out/throttle e permissões do env file). Inspeção do código atual da main encontra remediações para esses caminhos: URL passa por `sanitizar_url()`; captura exige `Content-Length` positivo dentro de 16 MiB, encoding identity e semáforo de duas leituras; descoberta de config não enumera perfis; o `ExecStart` válido em `[Service]` fixa `127.0.0.1`; WAL/SHM e `geoint.sqlite` estão ignorados; geocode usa `forward_place()` com opt-out/lock/cooldown; provisionamento aplica diretório 0700 e arquivo 0600 em toda execução.
  - **Limite residual da captura:** Playwright `Response.body()` ainda materializa o buffer completo antes do segundo teste de tamanho. O pre-gate reduz o domínio a respostas com comprimento declarado, identity encoding e no máximo duas leituras concorrentes; não é uma API de streaming com limite de bytes imposto durante a leitura. Os testes cobrem Content-Length declarado acima do limite e URL redigida, mas não um servidor de protocolo malformado/subdeclarante. Classificar como mitigação de código sob o framing HTTP do browser, não como prova formal de limite de memória.
  - **Limite do scanner:** o summary Strix da PR #809 registrou commits não revisados após o último review; os comentários de findings são históricos e não constituem um sign-off Strix do head final mesclado. As remediações acima foram verificadas no código da main; não afirmar que o scanner aprovou o merge final.
- **PR #815 — merged em 2026-11-12:** aplica o cooldown de 30 minutos da curiosidade antes da amostragem aleatória. Isso corrige a ordem do guard, mas não implementa o ciclo conversacional de captura de respostas.
- **PR #816 — merged em 2026-11-12:** inicializa/valida `metadata` no CognitiveRouter, declara `hint_path` explícito para `jarvis_chat` e mantém LiteLLM opcional no import. A correção resolve o contrato local do pipeline; não comprova consumidor de aplicação ou uso em produção.
- **PR #817 — merged em 2026-11-12:** faz `POST /v1/missions/execute` falhar fechado com HTTP 503 e remove a execução de Python arbitrário pelo subprocesso do host em `TaskRunner.execute_mission()`. A execução de missões permanece indisponível até existir executor dedicado em container hardened e testes de isolamento. Não reabilitar o endpoint por meio de `sandbox_mode`.
- **PR #818 — aberta, head `d3072fcbcbf30bd6e3a1d31008335e8ae3875c0e`:** adiciona um teste de round-trip MCP (arquivo presente na branch da PR, ainda ausente em `main`), usando o transporte in-memory oficial, Nexus e JSONL temporário para invocar `curiosity_capture` e `curiosity_list_recent`.
  - PR Validation run [43242697022](https://github.com/TheDrack/Jarvis_Xerife/actions/runs/43242697022): success; **3.204 passed, 36 skipped, 8 warnings** (Linux/Python 3.11).
  - Task Queue run [43242697156](https://github.com/TheDrack/Jarvis_Xerife/actions/runs/43242697156): success; **3.221 passed, 19 skipped, 181 warnings** (Windows/Python 3.12); os testes direcionados da fila também passaram (**15 passed**).
  - O workflow Linux instala `requirements.txt`, que não inclui o SDK MCP; como o teste usa `pytest.importorskip("mcp")`, esse workflow não é evidência da execução específica do round-trip. O workflow Windows instala `requirements/edge.txt`, que declara `mcp>=1.30,<2`, e executa a suíte completa; esse é o caminho de CI que disponibiliza o SDK necessário. O log agregado não lista individualmente o node ID do teste.
  - A revisão Graphify publicada está ancorada no SHA anterior `086c185102f5e3c5dbaa4148aacb7f0c9f52f9fa`; a comparação confirma que o head atual está um commit à frente. Portanto, o gate Graphify não é revisão do head atual. Codex e Strix não produziram revisão atual nesta execução por indisponibilidade/limites dos serviços. Não considerar a PR revisada no head atual nem fazer merge com base apenas nos checks verdes.
- A consulta de PRs recentes retornou #818 como aberta. Issues #682, #723 e #732 continuam abertas na consulta atual; #682 ainda registra evidência de `protected=false` obtida em 2026-11-05, mas a proteção de branch não foi reconsultada nesta execução. #723 permanece aberta embora o próprio histórico da issue registre a integração dos guards provider-aware pela PR #729; #732 continua exigindo reconciliação schema-aware, Preview descartável e plano de rollback. Nenhuma operação de banco foi executada.

### Cognitive Roadmap — C0

O ledger estruturado abaixo permanece inalterado: `C0-CAPABILITY-MAP`, `C0-GAPS-RECORDED` e `C0-NO-NAME-BASED-COMPLETION` continuam **pending**. C1 — World Model — continua bloqueada.

`docs/COGNITIVE_BASELINE.md` continua sendo snapshot de 2026-11-07 no commit `82ca2ac70f67e8418f62079f7d94e3fc8b4d1230`; suas linhas de CognitiveRouter, Curiosity, worker e Toolbox não foram reconciliadas integralmente com os merges #815–#817 e a PR #818. Não usar esse snapshot como mapa corrente. A conclusão de C0 exige reconciliar a matriz detalhada com a main atual e então preencher o ledger com commit, checks, implementation paths, consumer paths e test paths reais.

- A PR #816 elimina a falha de contexto conhecida do CognitiveRouter. Graphify ainda não encontra consumidor de aplicação para `run_pipeline("jarvis_chat")`; o uso identificado permanece no CLI/testes. A capacidade deve ser classificada como implementação corrigida, mas consumo de aplicação/runtime não verificado.
- A PR #818 acrescenta evidência comportamental real para os wrappers MCP de `CuriosityIntake`. O teste usa armazenamento temporário e comprova o caminho cliente/servidor → wrapper → Nexus → componente → JSONL. Não comprova persistência de produção, nem o ciclo separado de resposta conversacional.
- `CuriosityIntake` continua sendo um intake observacional de cartões de descoberta. Não deve ser confundido com `CuriosityEngine` ou com respostas vinculadas a usuário.
- `assistant_curiosity.py` ainda envia `detect_gaps` e `store_answer`; `CuriosityEngine.execute()` aceita `analyze`, `explore` e `suggest`. Os helpers de curiosidade não têm consumidor de aplicação estrito identificado no grafo. Não implementar `store_answer` por alias superficial: faltam contrato de ownership por usuário, persistência, idempotência, retenção e política de privacidade.
- `data/roadmap_missions.json` continua com `missions: []` e hold reason explícito: C0 permanece aberto e não há mapeamento revisado de critério → alvo Python existente → testes para geração autônoma.
- Próximo critério efetivamente pendente: completar `C0-CAPABILITY-MAP` com composition roots, consumidores reais, contratos, testes e nível de verificação de cada capacidade crítica. O mapa precisa separar `CuriosityIntake` do ciclo conversacional e o CognitiveRouter corrigido do pipeline efetivamente consumido. Não iniciar C1 nem promover qualquer critério por presença de classe, PR ou CI isolado.

### Integrações e Universal Intelligence

- **Câmeras públicas:** `app/adapters/edge/jarvis_open_cameras.py` na main contém TfL, Datumfeed e Windy. Windy exige `JARVIS_WINDY_API_KEY`, coordenadas e usa cache de 300 segundos para renovar URLs de imagem. A implementação existe, mas não foi feita chamada live nem verificada a presença da chave. Os testes localizados cobrem TfL/Datumfeed; não foi localizado teste específico de Windy nesta suíte.
- **ONVIF/SSDP:** a rota autenticada `POST /v1/network/cameras/discover` envia uma requisição multicast de cada protocolo, limitada ao enlace local e timeout entre 0,2 e 5 segundos. Faz descoberta de metadados; não autentica câmeras nem abre streams.
- **RTSP:** a inspeção ativa aceita um único IPv4 RFC1918 explicitamente informado e envia somente `OPTIONS` para portas RTSP selecionadas. Não executa SETUP/PLAY nem captura vídeo.
- **MQTT:** a rota aceita somente um host privado e portas 1883/8883. O probe abre conexão MQTT 3.1.1 sem autenticação, lê CONNACK e desconecta; não publica nem assina tópicos.
- **Universal Intelligence:** `IntelligenceEvent`, `IntelligenceObservation`, proveniência, deduplicação e correlações candidatas estão implementados e cobertos por testes. O schema de snapshots possui chaves de idempotência e timestamps de observação/ingestão. A última evidência operacional registrada em STATUS (2026-11-09) ainda apontava zero snapshots e zero runs do worker; não houve consulta nova ao banco/Render nesta execução. Portanto não declarar persistência ou recorrência operacional.
- A fundação de observações e eventos ainda não satisfaz C1: não há evidência completa de identidade estável de entidade, resolução conservadora entre fontes, projeção de estado atual e reconstrução histórica explicável.

### Multiagente, Toolbox, desempenho e confiabilidade

- **Multiagente:** o código atual contém autenticação HTTP de worker por token, store com hash SHA-256, expiração, rotação por reemissão e revogação por agente, além do script explícito de provisionamento. Isso comprova implementação local; a última consulta operacional registrada (2026-11-09) indicava zero credenciais ativas e não foi revalidada nesta execução. Não provisionar tokens nem alterar secrets.
- **Universal Toolbox:** `ToolDispatcher`, `HostToolAuthorizationPolicy`, approval store e toolchains permanecem componentes distintos. O TaskRunner fail-closed exige journal durável e capability authorizer. Não foi feita nova consulta ao composition root/produção nem ao banco de approvals; manter a afirmação de ativação operacional como não comprovada.
- **Desempenho/custo:** `ModelRegistry`, `ModelOrchestrator`, `AIGateway`, `LLMRouter` e `CostTrackerAdapter` permanecem abstrações distintas. O ModelOrchestrator tem rota local Ollama com fallback cloud; não há baseline atual de custo por ciclo, latência, taxa de fallback ou qualidade que justifique consolidar/remover caminhos nesta etapa.
- **Self Healing:** `.github/workflows/homeostase.yml` permanece versionado e não foi alterado. Seu gatilho `workflow_run` está restrito a workflows confiáveis originados em `main`; não inclui diretamente PR Validation nem Task Queue Tests. A proteção não deve ser removida nem ampliada com secrets para executar código não confiável de PR.
- **Autoevolução:** `.github/workflows/auto_evolution_triggerV2.yml` mantém o gate `EVOLUTION_ENABLED` e o selector roadmap-driven. O manifesto atual vazio mantém o fluxo em no-op; não houve geração, sandbox de candidato ou publicação nesta execução.

### Decisão desta execução

Nenhum novo componente cognitivo foi criado e nenhum critério C0 foi promovido. A atualização documental registra os merges e a evidência nova da PR #818, sem alterar o ledger. A próxima implementação de código continua sendo a conclusão do mapa C0; a correção conversacional de curiosidade deve aguardar contrato de usuário/persistência e consumidor real. Não foram executados probes de rede, operações de banco, deploy, alterações de secrets/flags, mudanças administrativas, merge ou deploy manual.
