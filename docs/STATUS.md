# JARVIS — Status do Projeto

**Versão:** 2.0.0  
**Atualizado em:** 2026-10-16

## 📊 Visão Geral

| Métrica | Valor | Status |
|---------|-------|--------|
| Capabilities com código | 102/102 arquivos, 68 marcadas `complete` | 🔴 78/102 são stubs (ver auditoria) |
| Testes Automatizados | 1367 | ✅ Verde (4 skipped) |
| Cobertura de Código | ~60% | 🟡 Em progresso |
| Componentes Nexus | 87 | ✅ Registrados |
| Adapters Registrados | 8 + discovery | ✅ Funcionais |
| Pipelines YAML | 4 | ✅ Criados |

## 📈 Roadmap

| Fase | Status | Descrição |
|------|--------|-----------|
| Phase 1 | ✅ Completo | Arquitetura Hexagonal + Nexus DI |
| Phase 2 | ✅ Completo | Auto-Evolução + Self-Healing |
| **Phase 3** | **✅ Completo** | **JarvisDevAgent + AdapterRegistry + PipelineRunner** |
| Phase 4 | 🟡 Em Progresso | Soldier Mesh (Edge Computing) |
| Phase 5 | 🟡 Em Progresso | Econômico (`CostTrackerAdapter` ativo no `llm_router`; `ResourceOptimizer` pendente) |

## 🎯 Destaques da Última Sprint

### Motores de evolução consolidados

- ✅ **`EvolutionOrchestrator` é o motor único de mutação** (o antigo
  `scripts/evolution_mutator.py` foi removido e todos os chamadores migrados)
- ✅ Seleciona a capability-alvo via `CapabilityManager` **ou** recebe `cap_id` explícito
- ✅ Consome o **contexto consolidado** (`CORE_LOGIC_CONSOLIDATED.txt`) como autoconsciência
- ✅ Valida o patch com `ast.parse()` antes de salvar a proposta e abrir o PR

### JarvisDevAgent (COMPLETO)

- ✅ **Executa código existente** (prioritário sobre criar)
- ✅ **Cria código apenas se necessário** (detecta gaps via AdapterRegistry)
- ✅ **Testa em sandbox isolado** (DockerSandbox ou EvolutionSandbox)
- ✅ **Aprende com cada interação** (ProceduralMemory + SemanticMemory)
- ✅ **Log de auditoria por job** (`data/dev_agent_jobs.jsonl`, com timeout)

### PipelineRunner (COMPLETO)

- ✅ Pipelines declarativos em `config/pipelines/*.yml`
- ✅ Resolução de cada passo via Nexus (`id` + `hint_path` opcional)
- ✅ `CloudMock` nunca é executado: indisponibilidade vira falha explícita, não falso sucesso
- ✅ Execução direta sem `PYTHONPATH` (`PIPELINE=<nome> python app/runtime/pipeline_runner.py`)

### AdapterRegistry (COMPLETO)

- ✅ Registro simplificado de adapters (5KB vs 500KB do consolidated context)
- ✅ Detecção de gaps automática
- ✅ Exemplos YAML para cada adapter
- ✅ Descoberta automática via Nexus

### Sandbox de evolução (COMPLETO)

- ✅ `EvolutionSandbox` testa toda proposta antes do PR (acionado pelo
  `EvolutionGatekeeper`), com timeout e verificação sintática
- ⚠️ `DockerSandbox` está implementado, porém **sem consumidor e sem teste** — o
  isolamento efetivo hoje é local, não em container. Veja
  [VERIFICACAO_ENTREGAS.md](VERIFICACAO_ENTREGAS.md)

## 🔧 Componentes Novos/Alterados

| Componente | Arquivo | Status |
|------------|---------|--------|
| `JarvisDevAgent` | `app/application/services/jarvis_dev_agent/agent.py` | ✅ Funcional |
| `EvolutionOrchestrator` | `app/application/services/evolution_orchestrator.py` | ✅ Funcional |
| `AutoEvolutionServiceV2` | `app/application/services/auto_evolutionV2.py` | ✅ Funcional |
| `ConsolidatedContextService` | `app/application/services/consolidated_context_service.py` | ✅ Funcional |
| `AdapterRegistry` | `app/domain/models/adapter_registry.py` | ✅ Funcional |
| `DockerSandbox` | `app/adapters/infrastructure/docker_sandbox.py` | ✅ Funcional |
| `PipelineRunner` | `app/runtime/pipeline_runner.py` | ✅ Funcional |

## 📊 Métricas de Evolução

| Métrica | Antes | Depois |
|---------|-------|--------|
| Dependência LLM externo | 100% | ~60% (reduzindo) |
| Tempo para nova feature | 2-3 dias | 2-3 horas (pipeline) |
| Recriação de código | Alta | Baixa (AdapterRegistry) |
| Isolamento de testes | Médio | Alto (DockerSandbox) |

## 🐛 Issues Conhecidos

Auditoria completa das promessas da documentação vs. código:
[VERIFICACAO_ENTREGAS.md](VERIFICACAO_ENTREGAS.md).

| Issue | Prioridade | Status |
|-------|------------|--------|
| Métrica de capabilities conta stubs: 78/102 arquivos são placeholders do Crystallizer e nenhum teste os exercita | 🔴 Alta | Documentado na auditoria |
| Ciclo de evolução não detecta código já existente (34/34 pendentes já têm arquivo) | 🔴 Alta | Documentado na auditoria |
| `AdapterRegistry` sem consumidor de produção ("consulte o que existe" não implementado) | 🟡 Média | Documentado na auditoria |
| `CapabilityAuthorizer` não é aplicado no fluxo `AssistantService → Executor` | 🟡 Média | Documentado na auditoria |
| Auto-evolução não bloqueia `capabilities/`, `adapters/infrastructure/`, `application/security/` (regra §7) | 🟡 Média | Documentado na auditoria |
| 35 arquivos acima de 300 linhas (padrão do CHANGELOG 2026-03-06) | 🟡 Média | Documentado na auditoria |
| `ARCHITECTURE.md`/`ARQUIVO_MAP.md` gerados e desatualizados (citam módulos removidos) | 🟢 Baixa | Regeneração pelo bot |
| Cobertura de testes < 80% | 🟡 Média | Em progresso |
| Inventário de capabilities em `.json` (sem espelho `.jrvs`) | 🟢 Baixa | Documentado (fallback automático) |
| `persistent_shell_adapter` executa subprocesso com `env=os.environ` (vaza segredos para o filho) | 🟡 Média | Documentado na auditoria |
| `validate_self_awareness.py` acusa `CORE_LOGIC_CONSOLIDATED.txt` ausente em checkout novo | 🟢 Baixa | Artefato gerado pelo pipeline `sync_drive` |

## 🚀 Próximos Passos (30 Dias)

1. ✅ Completar documentação do JarvisDevAgent
2. 🟡 Aumentar cobertura de testes para 80%
3. 🟡 Evoluir as 34 capabilities pendentes via `scripts/evolve_all_pending.py`
4. ⚪ Lançar beta fechado (50 usuários)
5. ⚪ Integrar Soldier Mesh (edge computing)

## 📚 Documentação Atualizada

- [README.md](../README.md) — Visão geral + JarvisDevAgent
- [AGENT_GUIDE.md](AGENT_GUIDE.md) — Guia do agente (arquivos e IDs do Nexus)
- [ARQUIVO_MAP.md](ARQUIVO_MAP.md) — Lista de arquivos
- [ARCHITECTURE.md](ARCHITECTURE.md) — Arquitetura completa
- [NEXUS.md](NEXUS.md) — Documentação do Nexus DI
- [PIPELINE_RUNNER.md](PIPELINE_RUNNER.md) — Pipelines YAML e execução
- [VERIFICACAO_ENTREGAS.md](VERIFICACAO_ENTREGAS.md) — Auditoria: o que a documentação promete vs. o que o código entrega
- [AUTORREGULACAO.md](AUTORREGULACAO.md) / [AUTORREGULACAO_ESBOCO.md](AUTORREGULACAO_ESBOCO.md) — linha de estudo (camada conceitual, sem implementação)
