# JARVIS — Status do Projeto

**Versão:** 2.0.0  
**Revisão documental:** 2026-11-04
**Escopo desta revisão:** alinhar catálogo de habilidades/capacidades e roadmap ao que está documentado. Não equivale a uma auditoria completa do runtime nem a uma confirmação de deploy.

## Visão geral e qualidade da evidência

| Área | Estado sustentado pelas evidências disponíveis | Limite / próxima validação |
|---|---|---|
| Arquitetura hexagonal e Nexus DI | Implementados e cobertos por testes segundo a auditoria de entregas | Reexecutar CI no HEAD atual antes de usar métricas antigas como estado corrente |
| Auto-evolução e self-healing | Há motor, gatekeeper, sandbox local de evolução e workflows de recuperação | Manter mutação automática sob opt-in; revisar proteção de arquivos críticos e resultado de cada workflow |
| JarvisDevAgent | Fluxo de desenvolvimento e registro de jobs existem | A auditoria identificou promessas não cumpridas: AdapterRegistry sem consumidor de produção, execução de código existente não priorizada de forma comprovada e geração automática de pipelines não entregue |
| PipelineRunner | Runner consome pipelines YAML; a main agora inclui etapas explícitas tool_id via dispatcher pela PR #681 | Migração de todos os passos legados e validação de produção ainda pendentes |
| Universal Toolbox | Registry versionado canônico, dispatcher fail-closed com JSON Schema, toolchains DAG, adapters Telegram/Drive/rede passiva e audit JSONL local implementados e integrados à main pela PR #681 (merge em 2026-11-02) | No HEAD da PR `8dd5cd1734a6a42a6dc208691d13a416061badee`, CI Linux/Python 3.11.17 e Windows/Python 3.12.10 aprovou a suíte completa: 2043 passed, 12 skipped em cada plataforma. Não há reviews nem threads de revisão registradas na PR #681; revisão técnica/segurança, policy host-backed, auditoria/estado distribuídos, idempotência distribuída e migração dos demais conectores permanecem pendentes. |
| Universal Intelligence | Contratos de eventos/observações, Core 0.2, adaptadores GEV MCP e OSIRIS REST e coleta sob demanda integrados à main pela PR #702; persistência append-only conectada ao endpoint autenticado pela PR #715, protegida por JARVIS_INTELLIGENCE_HISTORY_ENABLED (default false). Esta branch adiciona OSIRIS público como padrão configurável e carregamento local allowlisted da configuração GEV. | Validação local nesta branch: OSIRIS 4/4 rotas saudáveis; GEV MCP retornou 50 observações (aeronaves/satélites) com PartialFailure porque AISSTREAM_API_KEY não está configurada; GDELT retornou HTTP 429. O histórico continua indisponível e não foi habilitado: o ledger remoto registra 20261103184307 com nome 20261103100304_intelligence_history, mas o arquivo local começa por 20261103100304; o check Supabase Preview falha por versão remota ausente no diretório local. Grants exatos e insert/read real não foram verificados. PR #716 continua bloqueada até reconciliação da migration e validação read-only. |
| Inventário de capabilities | data/capabilities.json existe | Contagens anteriores são históricas: auditoria de 2026-10-16 encontrou 78 de 102 arquivos como stubs e nenhum teste exercitando os IDs cap_0XX/Cap0XX. Recontar e validar comportamento antes de alterar o estado de cada capability |
| Soldier Mesh / edge | Há modelos, registry, adapters e testes relacionados | Continua parcial até existir validação ponta a ponta com dispositivos reais |
| Otimização econômica | CostTrackerAdapter está descrito como integrado ao llm_router | ResourceOptimizer não foi encontrado pela auditoria; não marcar fase como completa |
| Coordenação multiagente | Contratos, scheduler determinístico, protocolo de transporte, fila/worker e arquitetura estão no repositório | A arquitetura registra como pendentes a supervisão contínua, heartbeat, renovação de lease e teste ponta a ponta entre dois runtimes reais |
| Planos declarativos | Interpretador, integração no orquestrador, autorizador e adaptador de diário estão no repositório | Execução exige plano estruturado, allowlist e diário durável. Ações sensíveis permanecem bloqueadas até existir protocolo confiável de aprovação/retomada |
| Diário de planos no Supabase | Migrações e adaptador estão no repositório; migrações de tabela e grants foram registradas no projeto Supabase nesta rodada de trabalho | Ainda é necessário confirmar insert real via adaptador no deploy atual; existência da tabela não prova integração operacional |
| Catálogo comum de agentes | Catálogo de skills/connectors e protocolo de memória existem; quatro skills portáteis foram localizadas no repositório | A leitura automática no início de toda conversa depende de cada host/harness e precisa ser validada por runtime |
| Deploy Render | Serviço configurado para deploy por novo commit após checks; deploy pode ser sujeito a cooldown externo configurado pelo operador | Confirmar SHA do deploy e health check após a janela de cooldown; merge não é prova de deploy |
| Governança da branch main | **Proteção ausente; issue #682 aberta** | API do GitHub confirmou `protected=false`, `protection.enabled=false` e zero rulesets. Exigir PR e o check de validação sempre executado; o workflow path-filtered da fila precisa de agregador antes de ser obrigatório globalmente. |

### Evidência operacional Supabase — 2026-11-04

- Projeto consultado em modo somente leitura: `saibtpdehhprttqlgqdt`, estado `ACTIVE_HEALTHY`.
- O ledger remoto retornou 16 registros; o repositório contém 20 arquivos SQL em `supabase/migrations`. Há divergências entre timestamps remotos e prefixos locais; o histórico de inteligência aparece como versão remota `20261103184307`, com nome `20261103100304_intelligence_history`.
- As tabelas `public.intelligence_event_snapshots` e `public.intelligence_observation_snapshots` existem e têm RLS habilitado. As tabelas/RPCs do worker da PR #716 não foram encontradas no projeto.
- O check `Supabase Preview` do commit `fafdd5bd50e07ad7605b60aea685e56936287d3b` falhou com `Remote migration versions not found in local migrations directory.`
- O advisor aponta `public.rls_auto_enable()` como `SECURITY DEFINER` com EXECUTE para `PUBLIC`, `anon`, `authenticated` e `service_role`. A introspecção de 2026-11-04 confirmou que retorna `event_trigger`, está vinculada a `ensure_rls` (`ddl_command_end`), usa `search_path=pg_catalog` e executa apenas ao final de DDL compatível. `anon` e `authenticated` não possuem CREATE em `public`; não foi demonstrada invocação direta por PostgREST. O achado foi reclassificado como revisão de least privilege/ACL, issue #718; nenhum grant foi alterado.
- A introspecção read-only de 2026-11-04 confirmou que as RPCs remotas `claim_jarvis_agent_task` e `claim_next_jarvis_agent_task` continuam sem predicado `model_provider`/regra Venice, embora a migration local `202610260001_red_blue_venice_routing.sql` contenha essa defesa. As RPCs remotas são `SECURITY DEFINER`, com ACL apenas para `postgres` e `service_role`; o risco é integridade do roteamento no worker confiável, não exposição a `anon`. Issue #723 acompanha a correção.
- Grants exatos das tabelas de histórico, conectividade do service role e insert/reload real continuam não verificados. Nenhuma migration, repair, DDL ou escrita de dados foi executada nesta auditoria.

## Roadmap — estado conservador

| Fase / trilha | Estado | Evidência e critério para avançar |
|---|---|---|
| Phase 1 — Arquitetura hexagonal + Nexus DI | **Implementada; testes documentados** | Auditoria anterior registrou resolução por ID, discovery e testes de contrato/circuit breaker. Revalidar no HEAD atual para atualizar métricas. |
| Phase 2 — Auto-evolução + self-healing | **Parcial / requer controles** | Motor e workflows existem; auditoria apontou falhas em proteção de caminhos críticos e gaps no ciclo de evolução. Não considerar concluída a segurança de mutação automática sem testes atuais. |
| Phase 3 — JarvisDevAgent + AdapterRegistry + PipelineRunner | **Parcial em termos de entrega comportamental** | Runner existe; auditoria registrou que AdapterRegistry não era consumido em produção e geração automática de pipelines não estava implementada. Não manter um selo global de completo sem fechar esses critérios. |
| Phase 4 — Soldier Mesh / Edge Computing | **Em progresso** | Existem componentes e testes, mas não foi comprovada execução ponta a ponta com dispositivo real. |
| Phase 5 — Economia de recursos | **Parcial** | CostTrackerAdapter é consumido pelo llm_router; ResourceOptimizer permanece pendente na auditoria. |
| Trilha — Jarvis OS / provider-neutral model runtime | **Contrato, bindings nos três worker roots integrados; seleção/roteamento global pendentes** | `ModelRuntime` define mensagens, request/result, usage, erros retry-aware e cancelamento explícito. `ModelRuntimeBindings` resolve `ModelProfile` para o adaptador do provider; `create_registered_model_handler` é usado pelos workers HTTP, Supabase e supervisionado. PRs #685, #688 e #689 estão merged (a #689 em 2026-11-03). Isso não prova health/conectividade dos providers nem seleção global entre múltiplos modelos. `LLMRouter`, `AIGateway` e `ModelOrchestrator` ainda preservam rotas próprias. Próximo passo: seleção por capabilities/modalities no scheduler e integração gradual dos três roteadores após testes de compatibilidade. |
| Trilha — harness multiagente e fila compartilhada | **Implementação parcial** | Contratos, scheduler, transporte, fila e worker existem; faltam os critérios operacionais listados em docs/architecture/jarvis-multi-agent-platform.md. |
| Trilha — execução declarativa auditável | **Código integrado; validação de produção pendente** | PRs #610–#613 integraram TaskRunner, limites de aprovação, diário Supabase e orquestrador. Confirmar deploy atual, gravação real e comportamento runtime. |
| Trilha — descoberta universal de skills/connectors | **Documentação atualizada; adoção por host pendente** | Catálogo comum agora lista skills e famílias de capacidades; cada host deve carregar o catálogo e descobrir ferramentas vivas. Não pressupor injeção automática em todos os provedores. |
| Trilha — Universal Toolbox / Toolchains | **Implementação integrada à main; revisão de segurança e produção pendentes** | Issue #680. Registry, dispatcher fail-closed, toolchains DAG e integração inicial do PipelineRunner foram integrados pela PR #681 em 2026-11-02. O HEAD validado `8dd5cd1734a6a42a6dc208691d13a416061badee` passou a suíte completa em Linux/Python 3.11.17 e Windows/Python 3.12.10: 2043 passed, 12 skipped em cada plataforma. A PR não tem reviews nem threads registradas. Permanecem pendentes revisão técnica/segurança, policy host-backed, estado/audit distribuídos, migração gradual e validação runtime. |
| Trilha — Jarvis Universal Intelligence | **Coleta sob demanda e adapter append-only conectados atrás de feature flag; worker recorrente em PR** | PR #702 integrou o endpoint autenticado e PR #715 conectou a persistência append-only ao endpoint. O `.env.example` mantém `JARVIS_INTELLIGENCE_HISTORY_ENABLED=false`. O projeto Supabase ativo contém as duas tabelas de histórico com RLS habilitado; o ledger remoto registra a migration de histórico na versão `20261103184307`, divergente do prefixo local `20261103100304`, e o check `Supabase Preview` falha por versões remotas ausentes no diretório local. Grants por role e insert/read real permanecem não verificados. PR #716 propõe worker recorrente, mas sua migration/tabelas não estão no banco remoto e a execução permanece opt-in. Próximos critérios: reconciliar o ledger sem reaplicar DDL, confirmar grants e persistência em ambiente controlado, validar o worker/lease, depois briefing, entrega e mapa. |

## Pendências prioritárias sustentadas pela auditoria

1. Reexecutar auditoria de capabilities e testes comportamentais; não usar os números históricos como métricas atuais.
2. Corrigir e testar os limites de auto-evolução para pastas de infraestrutura e segurança antes de reativar mutação automática irrestrita.
3. Integrar AdapterRegistry ao fluxo de produção e provar que o Jarvis procura implementação existente antes de gerar outra.
4. Manter o status de DockerSandbox como não comprovado em produção até haver consumidor e teste que demonstrem isolamento real.
5. Confirmar cobertura de CapabilityAuthorizer no caminho principal de execução; a auditoria anterior encontrou lacunas.
6. Validar multiagente ponta a ponta: dois runtimes reais, heartbeat, supervisão, renovação de lease, deduplicação e recuperação de mensagens expiradas.
7. Fechar o guard de provider nas RPCs Supabase de claim antes de tratar o roteamento Red/Blue como garantido. A migration local `202610260001_red_blue_venice_routing.sql` contém a regra Venice, mas as definições remotas ainda não; seguir issue #723 e validar migration forward-only em preview descartável, preservando EXECUTE apenas para `service_role`.
7. Reconciliar o ledger local/remoto do Supabase sem reaplicar DDL; verificar grants de `anon`, `authenticated` e `service_role` e testar insert/reload em ambiente controlado antes de habilitar a flag de histórico. Depois confirmar deploy, `/health` e persistência real sem executar capacidades com efeitos externos.
8. Validar em cada harness se o catálogo e as skills são carregados no bootstrap de uma conversa nova.
9. Proteger `main` com PR obrigatório e validação CI obrigatória, conforme issue #682; o estado atual não bloqueia push direto nem exige checks.
10. Após integrar o binding incremental de `ModelRegistry` → `ModelRuntimeBindings` nos três workers, avançar para a etapa global: adaptar `LLMRouter`/`AIGateway`/`ModelOrchestrator` ao port comum sem remover adapters existentes; introduzir seleção por capabilities/modalities e política de custo/latência no scheduler, com testes de concorrência, timeout, cancelamento, usage e falhas de provider.

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
