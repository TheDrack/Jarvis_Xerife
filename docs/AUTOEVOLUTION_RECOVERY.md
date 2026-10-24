# Recuperação controlada da autoevolução

## Objetivo

Retomar a evolução do Jarvis a partir de uma base coerente, sem repetir o antigo ciclo de mutação parcialmente implementado. Este procedimento não apaga histórico nem redefine capacidades para "completo" ou "pendente" por suposição.

## Estado conhecido no repositório

A auditoria existente em docs/VERIFICACAO_ENTREGAS.md encontrou diferenças importantes entre promessa e comportamento:
- O workflow .github/workflows/auto_evolution_triggerV2.yml tem agendamento diário e gate de repositório EVOLUTION_ENABLED; a variável efetiva de produção não é visível pela leitura do código.
- AutoEvolutionServiceV2 aceita ações evolve_next/evolve_cap e encaminha para EvolutionOrchestrator.
- scripts/evolve_all_pending.py chama o orquestrador diretamente, portanto o gate do workflow não protege por si só execuções manuais/externas desse script.
- EvolutionOrchestrator valida sintaxe e pode criar PRs, mas isso não comprova que o comportamento proposto atende à capability.
- data/context.json continha métricas de saúde (CPU 99%, RAM 10%, status critical) sem timestamp ou fonte de coleta; esses valores não devem ser tratados como telemetria atual.
- O inventário data/capabilities.json contém afirmações de conclusão que a auditoria anterior identificou como não necessariamente respaldadas por testes comportamentais.

## Procedimento seguro

1. Manter EVOLUTION_ENABLED diferente de true enquanto a auditoria estiver em curso.
2. Confirmar no GitHub Actions que não há execução em andamento do workflow de autoevolução e revisar o valor real da variável de repositório/ambiente; não inferir esse valor apenas pelo YAML.
3. Inventariar proposals, branches/PRs automáticas, logs de ThoughtLog, registros de rollback e estado de capabilities. Arquivar ou marcar itens obsoletos; não apagar evidências.
4. Separar estado operacional transitório de histórico: reiniciar apenas contadores/leases temporários depois de provar que nenhum worker os está usando.
5. Reclassificar capabilities com base em testes representativos; não redefinir todo o inventário nem confiar em stubs como implementação.
6. Validar em branch isolada: testes unitários, integração, regressão e, quando pertinente, execução ponta a ponta.
7. Reativar somente em modo de proposta/PR, com limite de tentativas, branch isolada, gatekeeper e CI obrigatório. Aplicação direta de patches fica desabilitada.
8. Observar um ciclo manual de baixo risco; avaliar o PR e o resultado real antes de qualquer reativação agendada.

## Definição de "reset"

O reset seguro significa voltar a um estado operacional conhecido, pausado e auditável — não apagar a memória, histórico, inventário ou propostas. A telemetria sem origem/tempo passa para unknown. O estado de autoevolução passa para paused. A reativação é uma decisão separada após critérios de aceite.

## Critérios mínimos para reativar

- Todos os pontos de entrada de mutação estão protegidos pelo mesmo opt-in explícito.
- Autoevolução desativada por padrão quando a variável não existe.
- Nenhum caminho altera arquivos de produção diretamente; propostas em branch/PR.
- Gatekeeper verifica arquivos protegidos, testes e sandbox; nenhum teste válido é desabilitado.
- Capabilities só são marcadas completas após testes que validam seu comportamento.
- Execução falha fechada quando inventário, memória, gatekeeper, sandbox ou testes necessários estão indisponíveis.
- Curiosidade pode capturar e investigar ideias enquanto a autoevolução está pausada, mas não pode alterar código nem produção.
- Métricas do piloto: taxa de PR aprovado, regressões, rollback, duplicação de oportunidades, custo e benefício confirmado.

## Limites desta mudança

Este runbook e a baseline versionada não alteram, por si só, variáveis secretas/de repositório no GitHub nem estado de serviços externos. A confirmação de que a autoevolução está efetivamente pausada exige inspeção autorizada desses ambientes.
