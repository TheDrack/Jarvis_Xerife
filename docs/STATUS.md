# JARVIS — Status do Projeto

**Versão:** 2.0.0  
**Revisão documental:** 2026-11-07
**Escopo desta revisão:** reconciliar C0 após os merges #770/#773, confirmar a migration no Supabase e o runtime Render, auditar a fronteira de autoevolução e verificar se o selector agendado consome o Cognitive Roadmap.

## Visão geral e qualidade da evidência

| Área | Estado sustentado pelas evidências disponíveis | Limite / próxima validação |
|---|---|---|
| Arquitetura hexagonal e Nexus DI | Implementados e cobertos por testes segundo a auditoria de entregas | Reexecutar CI no HEAD atual antes de usar métricas antigas como estado corrente |
| Auto-evolução e self-healing | Gatekeeper aplica protected prefixes; EvolutionSandbox substitui o alvo em snapshot e testa em Docker hardened; publisher separado valida digest/source/path e não executa candidato. PRs #756/#757 integraram a fronteira à main. | O workflow agendado usa AutoEvolutionServiceV2 + data/capabilities.json, não o Cognitive Roadmap. Os 102 registros têm 34 pendentes e 0 target_file; find_next_mission também não propaga target_file ao nível superior lido pelo workflow. Resultado determinístico: blocked/no-op antes de LLM/Docker. Não reativar nem inventar alvos. |
| JarvisDevAgent | Fluxo de desenvolvimento e registro de jobs existem | A auditoria identificou promessas não cumpridas: AdapterRegistry sem consumidor de produção, execução de código existente não priorizada de forma comprovada e geração automática de pipelines não entregue |
| PipelineRunner | Runner consome pipelines YAML; a main agora inclui etapas explícitas tool_id via dispatcher pela PR #681 | Migração de todos os passos legados e validação de produção ainda pendentes |
| Universal Toolbox | Registry versionado canônico, dispatcher fail-closed com JSON Schema, toolchains DAG, adapters Telegram/Drive/rede passiva e audit JSONL local implementados e integrados à main pela PR #681 (merge em 2026-11-02) | No HEAD da PR `8dd5cd1734a6a42a6dc208691d13a416061badee`, CI Linux/Python 3.11.17 e Windows/Python 3.12.10 aprovou a suíte completa: 2043 passed, 12 skipped em cada plataforma. Não há reviews nem threads de revisão registradas na PR #681; revisão técnica/segurança, policy host-backed, auditoria/estado distribuídos, idempotência distribuída e migração dos demais conectores permanecem pendentes. |
| Universal Intelligence | Contratos de eventos/observações, Core 0.2, adaptadores GEV MCP/OSIRIS, coleta sob demanda, histórico append-only e schema/RPCs do recurring worker estão integrados. O ledger remoto tem 28 versões e inclui a migration de identidade 20261107183000; a comparação integral local/remota 28/28 não foi refeita nesta execução. | O recurring worker segue desabilitado por feature flags no Render; logs após o deploy atual confirmam `Universal Intelligence recurring worker disabled by feature flags`. Lease sem owner e zero execuções. A ativação exige autorização operacional e prova de uma execução supervisionada com persistência/readback. GEV/OSIRIS continuam exigindo health checks live; GDELT pode responder 429 e AISSTREAM_API_KEY não está configurada. |
| Memória vetorial | PR #769 adicionou `SupabaseVectorMemoryStore`, escopo por usuário, redaction recursiva de metadata e readback após reinício; 38 testes direcionados e 16 pgTAP passaram. | A tabela de produção existe com RLS; service_role tem SELECT/INSERT/DELETE sem UPDATE e roles de cliente não têm SELECT. A tabela contém 0 linhas, portanto escrita/readback real pelo runtime ainda não foi demonstrada. Sem service-role, o adapter permanece em fallback volátil. |
| Inventário de capabilities | data/capabilities.json contém 102 registros; 34 pendentes, 34 com auto=true e nenhum target_file. O primeiro elegível pelo seletor legado é CAP-058. | Esse catálogo não representa os critérios C0–C8 e não é consumido pelo Cognitive Roadmap. Não usar status/auto como evidência comportamental; criar manifesto de missão revisado e target explícito antes de qualquer evolução. |
| Soldier Mesh / edge | Há modelos, registry, adapters e testes relacionados | Continua parcial até existir validação ponta a ponta com dispositivos reais |
| Otimização econômica | CostTrackerAdapter está descrito como integrado ao llm_router | ResourceOptimizer não foi encontrado pela auditoria; não marcar fase como completa |
| Coordenação multiagente | Contratos, scheduler, transporte, fila e workers integrados. PR #761 valida message fencing em dois processos; PR #766 valida task claim/renew/execute/complete em dois processos independentes contra Supabase isolado. PR #773 foi merged com credencial opaca por agente, rotação/revogação, autenticação dupla HTTP e grants server-side. | CI da PR #773 passou: 2.717 passed/14 skipped em Linux, 2.716 passed/15 skipped em Windows e 8 testes direcionados. A migration está aplicada; a tabela de credenciais tem RLS, ACL service_role e 0 registros. Logs Render confirmam fallback Supabase service-role e três workers com text_reasoning. Ownership de tarefas, attestation dinâmica, executores reais e ToolAuthorizationPolicy host-backed continuam pendentes. |
| Planos declarativos | Interpretador, integração no orquestrador, autorizador e adaptador de diário estão no repositório | Execução exige plano estruturado, allowlist e diário durável. Ações sensíveis permanecem bloqueadas até existir protocolo confiável de aprovação/retomada |
| Diário de planos no Supabase | Migrações e grants registrados; ledger remoto 28 versões, incluindo 20261107183000; comparação integral 28/28 não refeita nesta execução | Insert/readback pelo adaptador em runtime ainda precisa de prova; existência de tabela não comprova integração operacional |
| Catálogo comum de agentes | Catálogo de skills/connectors e protocolo de memória existem; quatro skills portáteis foram localizadas no repositório | A leitura automática no início de toda conversa depende de cada host/harness e precisa ser validada por runtime |
| Deploy Render | `Jarvis-api` está live no commit `1ad74752a6393cb8f0de3614d74be0994ece940b`; deploy concluído em 2026-11-07 19:01:33 UTC e inclui o merge da PR #773. | Logs após o deploy confirmam fallback legado Supabase service-role para os três workers e Universal Intelligence recurring worker desabilitado por feature flags. A identidade HTTP individual está no código, mas não foi ativada no runtime. Memória vetorial segue sem linhas. |
| Governança da branch main | **Proteção ausente; issue #682 aberta** | API do GitHub confirmou `protected=false`, `protection.enabled=false` e zero rulesets. Exigir PR e o check de validação sempre executado; o workflow path-filtered da fila precisa de agregador antes de ser obrigatório globalmente. |
| Segurança Supabase / RLS legado | **Mitigação aplicada em produção; issue #726 fechada** | A migration `lock_down_legacy_public_tables` removeu a policy ampla e revogou grants de tabela e coluna para `PUBLIC`, `anon` e `authenticated` nas sete tabelas. Verificação dos catálogos: zero grants de cliente, zero policies amplas e 28/28 grants CRUD preservados para `service_role`. O acesso direto de clientes permanece bloqueado até existir API com ownership explícito. |

### Evidência operacional Supabase — 2026-11-07 (estado atual)

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
| Phase 2 — Auto-evolução + self-healing | **Parcial / fronteira de execução corrigida; scheduler roadmap-driven bloqueado** | Gatekeeper, protected-path policy, Docker snapshot sem rede/secrets e publisher separado estão integrados. O workflow agendado ainda usa o inventário legado sem target_file e não lê o Cognitive Roadmap; permanece em blocked/no-op. Não considerar a autoevolução funcional nem reativar mutação até existir manifesto/selector C0 validado e execução controlada. |
| Phase 3 — JarvisDevAgent + AdapterRegistry + PipelineRunner | **Parcial em termos de entrega comportamental** | Runner existe; auditoria registrou que AdapterRegistry não era consumido em produção e geração automática de pipelines não estava implementada. Não manter um selo global de completo sem fechar esses critérios. |
| Phase 4 — Soldier Mesh / Edge Computing | **Em progresso** | Existem componentes e testes, mas não foi comprovada execução ponta a ponta com dispositivo real. |
| Phase 5 — Economia de recursos | **Parcial** | CostTrackerAdapter é consumido pelo llm_router; ResourceOptimizer permanece pendente na auditoria. |
| Trilha — Jarvis OS / provider-neutral model runtime | **Contrato, bindings nos três worker roots integrados; seleção/roteamento global pendentes** | `ModelRuntime` define mensagens, request/result, usage, erros retry-aware e cancelamento explícito. `ModelRuntimeBindings` resolve `ModelProfile` para o adaptador do provider; `create_registered_model_handler` é usado pelos workers HTTP, Supabase e supervisionado. PRs #685, #688 e #689 estão merged (a #689 em 2026-11-03). Isso não prova health/conectividade dos providers nem seleção global entre múltiplos modelos. `LLMRouter`, `AIGateway` e `ModelOrchestrator` ainda preservam rotas próprias. Próximo passo: seleção por capabilities/modalities no scheduler e integração gradual dos três roteadores após testes de compatibilidade. |
| Trilha — harness multiagente e fila compartilhada | **Implementação parcial** | Contratos, scheduler, transporte, fila e workers existem. O worker Supabase de tarefas já atualiza heartbeat e renova lease com testes unitários; ainda faltam supervisão contínua do processo, deduplicação/recovery comprovados e E2E entre dois runtimes reais. |
| Trilha — execução declarativa auditável | **Código integrado; validação de produção pendente** | PRs #610–#613 integraram TaskRunner, limites de aprovação, diário Supabase e orquestrador. Confirmar deploy atual, gravação real e comportamento runtime. |
| Trilha — descoberta universal de skills/connectors | **Documentação atualizada; adoção por host pendente** | Catálogo comum agora lista skills e famílias de capacidades; cada host deve carregar o catálogo e descobrir ferramentas vivas. Não pressupor injeção automática em todos os provedores. |
| Trilha — Universal Toolbox / Toolchains | **Implementação integrada à main; revisão de segurança e produção pendentes** | Issue #680. Registry, dispatcher fail-closed, toolchains DAG e integração inicial do PipelineRunner foram integrados pela PR #681 em 2026-11-02. O HEAD validado `8dd5cd1734a6a42a6dc208691d13a416061badee` passou a suíte completa em Linux/Python 3.11.17 e Windows/Python 3.12.10: 2043 passed, 12 skipped em cada plataforma. A PR não tem reviews nem threads registradas. Permanecem pendentes revisão técnica/segurança, policy host-backed, estado/audit distribuídos, migração gradual e validação runtime. |
| Trilha — Jarvis Universal Intelligence | **Coleta sob demanda integrada; recurring worker permanece desabilitado** | O ledger remoto contém 28 versões, incluindo a migration de identidade de worker; a reconciliação local/remota completa 28/28 não foi refeita nesta execução. As tabelas/RPCs do recurring worker estão presentes, mas Render logs confirmam feature flag desabilitada, lease sem owner e zero execuções. A memória vetorial tem schema/ACL implantados, porém zero linhas; insert/readback do runtime não foi demonstrado. Próximos gates: autorização operacional, execução supervisionada com lease/run/persistência/readback e health checks live dos providers. |

## Regra operacional permanente — correção automática de PRs

A autoevolução de capacidades segue o [Cognitive Roadmap](COGNITIVE_ROADMAP.md), mas a correção automática de PRs/CI e os workflows Self Healing são uma trilha transversal permanente. Devem continuar ativos durante todas as fases: diagnosticar falhas por logs/causa raiz, corrigir a branch/PR correspondente quando seguro, acrescentar testes e reexecutar checks. Não desativar nem enfraquecer esses mecanismos, não duplicar PRs, não reduzir testes e não permitir merge/deploy autônomo. A publicação permanece sujeita aos gates e à revisão humana. Correção de CI é manutenção; não substitui nem conclui marco cognitivo.

## Nova trilha — Jarvis Cognitive Architecture

**Estado:** C0 em andamento; C1–C8 não são declaradas concluídas. O inventário inicial está em [COGNITIVE_BASELINE.md](COGNITIVE_BASELINE.md) e não substitui os critérios de aceitação do roadmap.

O roadmap cognitivo foi formalizado em [COGNITIVE_ROADMAP.md](COGNITIVE_ROADMAP.md). A trilha não substitui nem reconstrói Harness, Nexus, Universal Toolbox, Multi-Agent ou Universal Intelligence: ela audita e integra essas bases para formar um ciclo contínuo de percepção, modelo de mundo, memória, raciocínio, planejamento, execução supervisionada, iniciativa e aprendizado validado.

| Marco | Capacidade | Estado inicial | Critério principal |
|---|---|---|---|
| C0 | Auditoria de capacidades e baseline comportamental | **Em andamento — identidade HTTP ainda não ativa; autoevolução agendada em no-op seguro** | [COGNITIVE_BASELINE.md](COGNITIVE_BASELINE.md) registra PR #773, CI verde, migration aplicada e runtime Render ainda no fallback service-role. O workflow agendado não consome o Cognitive Roadmap: usa data/capabilities.json, que tem 0 target_file, e o selector também não propaga esse campo. Permanecem manifesto/selector C0, ownership persistido, ToolAuthorizationPolicy host-backed e executores reais. |
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
1. Reexecutar o baseline comportamental C0 com evidências atuais; não usar contagens históricas como métricas correntes.
2. **Roadmap-driven autoevolution:** criar manifesto de missão C0 revisado com criterion_id, target_file confiável, testes, dependências, risco e resultado esperado; fazer o selector consumir o manifesto, não data/capabilities.json, e propagar o target_file ao workflow. Preservar blocked/no-op até o contrato estar válido. Não inferir alvo pelo LLM.
3. Persistir owner/creator nas tarefas da fila a partir do usuário autenticado e propagar o proprietário aos eventos de iniciativa; cobrir isolamento, tarefas legadas e atribuição correta de task_blocked.
4. Integrar executores reais ao ToolDispatcher e registrar ToolAuthorizationPolicy host-backed com principal, sessão, escopo e aprovação verificáveis; manter fail-closed até então.
5. Provisionar tokens individuais de worker somente por fluxo administrativo autorizado e secret store; comprovar heartbeat/claim/finish/release HTTP e retirar o fallback service-role apenas após validação e rollout aprovado.
6. Validar multiagente ponta a ponta com dois runtimes independentes no runtime de produção/teste controlado, supervisão, deduplicação e recuperação de lease; workers atuais continuam no fallback service-role.
7. Guard de provider nas RPCs Supabase de claim: implementação aplicada e verificada em 2026-11-05 nas duas definições remotas, com ACL restrita a service_role e pgTAP isolado 29/29 (PR #729). Issue #723 permanece aberta apenas pelo drift histórico, acompanhado em #732; não repetir a implementação do guard.
8. Provar insert/readback vetorial real com service_role em execução controlada; tabela permanece vazia. Não executar db push nem migration repair sem divergência nova comprovada.
9. Validar em cada harness se catálogo e skills são carregados no bootstrap de uma conversa nova.
10. Proteger main com PR obrigatório e validação CI obrigatória, conforme issue #682. Última evidência explícita, de 2026-11-05, indicava main sem proteção; o estado atual não foi reconsultado por falta de endpoint administrativo no conector.
11. Avançar a etapa global de seleção de modelos: adaptar LLMRouter/AIGateway/ModelOrchestrator ao port comum sem remover adapters existentes; introduzir seleção por capabilities/modalities e política de custo/latência no scheduler, com testes de concorrência, timeout, cancelamento, usage e falhas de provider.



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
