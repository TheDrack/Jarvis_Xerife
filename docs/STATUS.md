# JARVIS — Status do Projeto

**Versão:** 2.0.0  
**Revisão documental:** 2026-10-26  
**Escopo desta revisão:** alinhar catálogo de habilidades/capacidades e roadmap ao que está documentado. Não equivale a uma auditoria completa do runtime nem a uma confirmação de deploy.

## Visão geral e qualidade da evidência

| Área | Estado sustentado pelas evidências disponíveis | Limite / próxima validação |
|---|---|---|
| Arquitetura hexagonal e Nexus DI | Implementados e cobertos por testes segundo a auditoria de entregas | Reexecutar CI no HEAD atual antes de usar métricas antigas como estado corrente |
| Auto-evolução e self-healing | Há motor, gatekeeper, sandbox local de evolução e workflows de recuperação | Manter mutação automática sob opt-in; revisar proteção de arquivos críticos e resultado de cada workflow |
| JarvisDevAgent | Fluxo de desenvolvimento e registro de jobs existem | A auditoria identificou promessas não cumpridas: AdapterRegistry sem consumidor de produção, execução de código existente não priorizada de forma comprovada e geração automática de pipelines não entregue |
| PipelineRunner | Runner consome pipelines YAML e resolve passos pelo Nexus | Não declarar que o Jarvis gera automaticamente pipelines reutilizáveis |
| Inventário de capabilities | data/capabilities.json existe | Contagens anteriores são históricas: auditoria de 2026-10-16 encontrou 78 de 102 arquivos como stubs e nenhum teste exercitando os IDs cap_0XX/Cap0XX. Recontar e validar comportamento antes de alterar o estado de cada capability |
| Soldier Mesh / edge | Há modelos, registry, adapters e testes relacionados | Continua parcial até existir validação ponta a ponta com dispositivos reais |
| Otimização econômica | CostTrackerAdapter está descrito como integrado ao llm_router | ResourceOptimizer não foi encontrado pela auditoria; não marcar fase como completa |
| Coordenação multiagente | Contratos, scheduler determinístico, protocolo de transporte, fila/worker e arquitetura estão no repositório | A arquitetura registra como pendentes a supervisão contínua, heartbeat, renovação de lease e teste ponta a ponta entre dois runtimes reais |
| Planos declarativos | Interpretador, integração no orquestrador, autorizador e adaptador de diário estão no repositório | Execução exige plano estruturado, allowlist e diário durável. Ações sensíveis permanecem bloqueadas até existir protocolo confiável de aprovação/retomada |
| Diário de planos no Supabase | Migrações e adaptador estão no repositório; migrações de tabela e grants foram registradas no projeto Supabase nesta rodada de trabalho | Ainda é necessário confirmar insert real via adaptador no deploy atual; existência da tabela não prova integração operacional |
| Catálogo comum de agentes | Catálogo de skills/connectors e protocolo de memória existem; quatro skills portáteis foram localizadas no repositório | A leitura automática no início de toda conversa depende de cada host/harness e precisa ser validada por runtime |
| Deploy Render | Serviço configurado para deploy por novo commit após checks; deploy pode ser sujeito a cooldown externo configurado pelo operador | Confirmar SHA do deploy e health check após a janela de cooldown; merge não é prova de deploy |

## Roadmap — estado conservador

| Fase / trilha | Estado | Evidência e critério para avançar |
|---|---|---|
| Phase 1 — Arquitetura hexagonal + Nexus DI | **Implementada; testes documentados** | Auditoria anterior registrou resolução por ID, discovery e testes de contrato/circuit breaker. Revalidar no HEAD atual para atualizar métricas. |
| Phase 2 — Auto-evolução + self-healing | **Parcial / requer controles** | Motor e workflows existem; auditoria apontou falhas em proteção de caminhos críticos e gaps no ciclo de evolução. Não considerar concluída a segurança de mutação automática sem testes atuais. |
| Phase 3 — JarvisDevAgent + AdapterRegistry + PipelineRunner | **Parcial em termos de entrega comportamental** | Runner existe; auditoria registrou que AdapterRegistry não era consumido em produção e geração automática de pipelines não estava implementada. Não manter um selo global de completo sem fechar esses critérios. |
| Phase 4 — Soldier Mesh / Edge Computing | **Em progresso** | Existem componentes e testes, mas não foi comprovada execução ponta a ponta com dispositivo real. |
| Phase 5 — Economia de recursos | **Parcial** | CostTrackerAdapter é consumido pelo llm_router; ResourceOptimizer permanece pendente na auditoria. |
| Trilha — harness multiagente e fila compartilhada | **Implementação parcial** | Contratos, scheduler, transporte, fila e worker existem; faltam os critérios operacionais listados em docs/architecture/jarvis-multi-agent-platform.md. |
| Trilha — execução declarativa auditável | **Código integrado; validação de produção pendente** | PRs #610–#613 integraram TaskRunner, limites de aprovação, diário Supabase e orquestrador. Confirmar deploy atual, gravação real e comportamento runtime. |
| Trilha — descoberta universal de skills/connectors | **Documentação atualizada; adoção por host pendente** | Catálogo comum agora lista skills e famílias de capacidades; cada host deve carregar o catálogo e descobrir ferramentas vivas. Não pressupor injeção automática em todos os provedores. |

## Pendências prioritárias sustentadas pela auditoria

1. Reexecutar auditoria de capabilities e testes comportamentais; não usar os números históricos como métricas atuais.
2. Corrigir e testar os limites de auto-evolução para pastas de infraestrutura e segurança antes de reativar mutação automática irrestrita.
3. Integrar AdapterRegistry ao fluxo de produção e provar que o Jarvis procura implementação existente antes de gerar outra.
4. Manter o status de DockerSandbox como não comprovado em produção até haver consumidor e teste que demonstrem isolamento real.
5. Confirmar cobertura de CapabilityAuthorizer no caminho principal de execução; a auditoria anterior encontrou lacunas.
6. Validar multiagente ponta a ponta: dois runtimes reais, heartbeat, supervisão, renovação de lease, deduplicação e recuperação de mensagens expiradas.
7. Verificar o deploy do commit integrado, endpoint /health e gravação de evento via adaptador Supabase, sem executar capacidades com efeitos externos.
8. Validar em cada harness se o catálogo e as skills são carregados no bootstrap de uma conversa nova.

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
