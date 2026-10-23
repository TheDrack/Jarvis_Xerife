# Auditoria e plano de recuperação distribuída do JARVIS

**Inspeção:** 2026-10-23. **Escopo:** repositório TheDrack/Jarvis_Xerife na branch main, Blueprint Render versionado e projeto Supabase associado visível pela integração. Não houve acesso confirmado ao dashboard Render, deploys ativos, logs de produção ou variáveis secretas.

## Resumo

O JARVIS já tem autocorreção de código e logs por job, mas não há protocolo comum de checkpoint, restauração e verificação para ações de agentes em múltiplos ambientes. O healer grava a correção no arquivo antes de validar o comportamento; validação sintática não garante que a mudança seja segura.

Esta primeira entrega acrescenta uma primitiva local conservadora e um esquema versionado para futuro histórico central. Ela não habilita rollback cloud nem altera o banco Supabase automaticamente.

## Matriz de achados

| Área | Evidência | Lacuna / risco | Ação | Prioridade |
|---|---|---|---|---|
| CI self-healing | .github/workflows/homeostase.yml roda pytest, chama scripts/jarvis_healer.py, roda pytest novamente e pode enviar alterações para branch/PR | Não existe checkpoint por arquivo; healer modifica antes da validação comportamental | Checkpoint antes da escrita, teste, restauração condicional e verificação final | P0 |
| Healer | scripts/jarvis_healer.py usa write_text para aplicar resposta do modelo e compile() como validação sintática | Correção sintaticamente válida pode piorar comportamento; escrita pode ser interrompida | Escrita atômica, snapshot e testes antes de declarar cura | P0 |
| Agente | JarvisDevAgent mantém data/dev_agent_jobs.jsonl; EvolutionOrchestrator gera propostas e usa gatekeeper | Log por job não desfaz efeitos colaterais de ferramentas | Propagar run_id/operation_id e usar adaptadores de recuperação | P0 |
| Sandbox | docs/VERIFICACAO_ENTREGAS.md relata DockerSandbox sem consumidor/testes e sandbox de evolução local | Isolamento de execução arbitrária não é garantido | Testar falhas e conectar sandbox depois de verificar seu comportamento | P1 |
| Local | Não foi identificado contrato comum de checkpoint/restore nos arquivos auditados | Arquivos alterados, removidos ou criados podem não ser recuperáveis | Snapshots por conteúdo, detecção de conflito, journal encadeado | P0 |
| Render | render.yaml define /health, python serve.py, disco /app/data e banco Render jarvis-db | Health check não prova rollback de execução; DATABASE_URL do Blueprint aponta ao banco Render, não ao projeto Supabase consultado | Confirmar serviço e banco em uso; rollback de deploy separado e verificado | P0 |
| Supabase | Projeto ativo; tabelas existentes incluem interactions, devices, command_results, thought_logs, capabilities e evolution_rewards; API de migrações retornou lista vazia e nenhuma Edge Function | Não há histórico de recovery nas tabelas listadas; lista vazia não prova ausência de DDL manual | Versionar migration, testar fora de produção e depois conectar writer idempotente | P0 |
| Supabase security | Advisors reportam tabelas expostas no schema GraphQL a anon/authenticated, função public.rls_auto_enable() executável por anon e evolution_rewards com RLS sem policy | Exposição e privilégios merecem revisão independente | Revisar grants, SECURITY DEFINER, RLS e policies sem mudar consumidores às cegas | P0 |
| Segredos | .env.example tem DATABASE_URL não comentada com aparência de conexão real | Credencial pode ter sido versionada | Usar placeholder; se válida, rotacionar fora do GitHub e revisar histórico | P0 |
| Aprovação | Gatekeeper protege alguns arquivos do núcleo, mas docs/VERIFICACAO_ENTREGAS.md registra lacunas na proteção de arquivos críticos | A política não cobre uniformemente todas as ações de agentes | Centralizar risco, aprovação, idempotência e auditoria | P0 |

## Referências open source

| Projeto | Conceito útil | Uso potencial | Limite |
|---|---|---|---|
| [Hermes Agent](https://github.com/NousResearch/hermes-agent) | Snapshots e restauração seletiva antes de operações | Referência para checkpoints por operação de arquivo | Verificar licença, dependências e adaptação antes de copiar código |
| [agent-rollback](https://github.com/superops-team/agent-rollback) | Snapshots locais, hashes, undo granular | Inspiração para snapshots por conteúdo | Não reverte APIs externas nem estado de navegador/banco |
| [Crab](https://github.com/open-agent-infra/crab) | Checkpoint/restore de sandbox | Avaliar para sandbox Linux isolada | Não desfaz efeitos externos; validar plataformas e manutenção |
| [LangGraph](https://github.com/langchain-ai/langgraph) | Checkpoints de estado de workflow | Retomada de fluxo lógico do agente | Não desfaz ações externas |
| [Temporal](https://github.com/temporalio/temporal) | Execução durável e retries | Workflows distribuídos longos | Infraestrutura adicional; não substitui snapshot nem compensação |

Não tornar nenhum projeto dependência obrigatória antes de comparar licença, manutenção, Windows/Linux, isolamento e custo.

## Contrato de recuperação

1. Criar run_id e operation_id estáveis antes da ação.
2. Registrar intenção, recurso, ambiente e risco.
3. Criar checkpoint antes da mutação.
4. Executar dentro do escopo autorizado.
5. Selar o checkpoint com o estado posterior.
6. Verificar o resultado com teste ou health check independente.
7. Restaurar apenas se o estado atual corresponder ao estado selado; em caso de conflito, não sobrescrever.
8. Nunca excluir automaticamente arquivos criados durante a operação. Retornar requires_authorization.
9. Registrar tentativas e resultados no journal local e, quando configurado, sincronizar metadados com Supabase.
10. Se a recuperação falhar, interromper mutações subsequentes, preservar evidências e escalar.

## Plano por fases

- **Fase 1 — Local (esta PR):** snapshots, detecção de conflito, journal hash-chained, testes, migration SQL versionada e documentação.
- **Fase 2 — Healer:** checkpoint antes da escrita, restauração condicional e teste completo; remoção de arquivo novo requer aprovação.
- **Fase 3 — Supabase:** autenticação server-side de privilégio mínimo, sincronização idempotente, fila offline e testes RLS. Não aplicar migration em produção sem validar destino e backup.
- **Fase 4 — Render:** verificar dashboard, deploys, health check, banco usado e rollback; separar rollback de código e schema.
- **Fase 5 — Ferramentas:** adaptadores para filesystem, Git, browser, APIs, deploys e Postgres; efeitos irreversíveis protegidos por aprovação.
- **Fase 6 — Testes de falha:** interrupção entre checkpoint/seal, objeto corrompido, mudança posterior, evento duplicado, Supabase offline, health check falho e interrupção da recuperação.

## Critérios de aceitação

- Arquivo existente retorna exatamente aos bytes anteriores.
- Mudança externa posterior ao seal nunca é sobrescrita silenciosamente.
- Arquivo criado pela operação não é removido automaticamente.
- Journal detecta alteração e quebra de encadeamento.
- Caminhos fora da raiz e symlinks são rejeitados.
- Migration habilita RLS e não dá acesso direto a anon/authenticated.
- Integração cloud só é considerada ativa depois de teste ponta a ponta no ambiente de destino.
