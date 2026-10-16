# Verificação de Entregas — propostas da documentação vs. código real

**Data:** 2026-10-16 · **Base:** commit `0559109` (branch `main`)
**Método:** cada proposta foi confrontada com evidência executável (probe, teste,
grep ou execução ponta a ponta). Nada aqui é inferido de leitura de código apenas —
quando só a leitura existia, está marcado como "sem evidência de execução".

Legenda: ✅ entregue · 🟨 parcial (funciona, mas não como a documentação descreve) ·
❌ não entregue · 📄 documento conceitual (proposta, não implementação).

---

## 1. Núcleo — Nexus DI (`docs/NEXUS.md`)

| Proposta | Status | Evidência |
|----------|--------|-----------|
| Nexus dividido em 4 módulos (nexus, exceptions, discovery, registry) | ✅ | os 4 arquivos existem em `app/core/` |
| `resolve()` resolve e instancia por ID | ✅ | probe: `evolution_sandbox → EvolutionSandbox`, `docker_sandbox → DockerSandbox` |
| Discovery em disco acha componentes fora do registry estático | ✅ | `eagle_osint_adapter`, `cost_tracker_adapter` resolvidos via discovery |
| `list_loaded_ids()`, `invalidate_component()`, `commit_memory()` | ✅ | `hasattr` = True nos três |
| Circuit breaker + `CloudMock` injetado em falha | ✅ | `tests/test_nexus_circuit_breaker.py` (19 testes) |
| `resolve(..., use_cache=False)` força re-instanciação | ✅ *(corrigido nesta rodada)* | antes o kwarg era silenciosamente ignorado; agora invalida o cache e há teste |
| Timeouts documentados (`NEXUS_TIMEOUT`, `NEXUS_IMPORT_TIMEOUT`, `NEXUS_INSTANTIATE_TIMEOUT`, `NEXUS_CIRCUIT_RESET`) | ✅ *(corrigido)* | tabela estava com 30s/300s e sem `NEXUS_IMPORT_TIMEOUT`; valores reais 30/10/5/60s |
| Registry `.jrvs` + sync com Gist | 🟨 | `nexus_registry.py` lê `GIST_PAT`; sem evidência de execução real de sync (sem credencial) |
| "Todos os componentes ativos são NexusComponent registrados" | ✅ | `tests/security/test_nexus_contract_compliance.py` (verde) |

Fonte do drift corrigido: `tests/test_nexus_docs_contract.py` (novo) compara a tabela
do doc com `app/core/nexus_exceptions.py`.

## 2. Auto-evolução e self-healing

| Proposta | Status | Evidência |
|----------|--------|-----------|
| Ciclo completo: snapshot → contexto → procedural memory → LLM → validação de sintaxe → proposta → PR | ✅ | `tests/application/test_evolution_orchestrator.py` |
| Gatekeeper aprova/rejeita ciclo | ✅ | idem + `_check_test_count`, `_check_recent_stability` |
| Sandbox de teste da proposta | ✅ | `EvolutionGatekeeper._check_sandbox` → `nexus.resolve("evolution_sandbox")`; `tests/test_evolution_sandbox.py` |
| Escalonamento para COMMANDER quando rejeitado | ✅ | teste `test_gatekeeper_rejection_escalates_to_commander` |
| Evolução em lote das capabilities pendentes | ✅ *(migrado nesta rodada)* | `scripts/evolve_all_pending.py` → `EvolutionOrchestrator` |
| Workflow de CI chama o motor real | ✅ *(corrigido)* | `auto_evolution_triggerV2.yml` chamava `scripts/evolution_mutator.py`, que não existe |
| Inventário lido corretamente | ✅ *(corrigido)* | fallback `.jrvs → .json`; antes respondia `empty_inventory` |
| "Evolução não altera arquivos protegidos (capabilities/, adapters/infrastructure/, application/security)" | ❌ | `_PROTECTED_CORE_FILES` só protege 3 arquivos do Nexus + prefixo `.frozen` (SECURITY_GUARDRAILS §7) |

## 3. JarvisDevAgent

| Proposta (README/STATUS) | Status | Evidência |
|--------------------------|--------|-----------|
| Ciclo: select capability → few-shot → prompt → LLM → proposta → gatekeeper → PR | ✅ | `app/application/services/jarvis_dev_agent/agent.py` + `tests/test_phase4_fixes.py` |
| Log de auditoria por job + timeout | ✅ | `data/dev_agent_jobs.jsonl`, testes de timeout |
| "Aprende com cada interação (ProceduralMemory/SemanticMemory)" | 🟨 | grava em `semantic_memory` (`_record_cycle`); nenhum consumo de `procedural_memory_adapter` no agente |
| "Consulta AdapterRegistry (o que existe?) → decide não criar" | ❌ | **`adapter_registry` não tem nenhum consumidor em `app/`** — o registry funciona (list/get/find_gap), mas nada o consulta |
| "Executa código existente (prioritário sobre criar)" | ❌ | `get_executable_capabilities()` filtra **apenas** dependências; **34/34 capabilities pendentes já têm arquivo** em `app/domain/capabilities/` |
| "Testa em sandbox isolado (DockerSandbox ou EvolutionSandbox)" | 🟨 | só via gatekeeper → `EvolutionSandbox` (testado). **`DockerSandbox` não tem consumidor nem teste em todo o repositório** |
| "Cria pipelines YAML reutilizáveis (PipelineBuilder)" | ❌ | nada grava `config/pipelines/*.yml`; o PipelineBuilder foi removido e o runner só consome YAML declarado |

## 4. Métrica de capabilities (o achado mais relevante)

| Proposta | Status | Evidência |
|----------|--------|-----------|
| "Capabilities implementadas: 68/102" | 🟨 | 102 arquivos em `app/domain/capabilities/`, mas **78 são stubs do CrystallizerEngine** (`def execute: return {'status': 'active'}`); as completas têm ~16 linhas |
| Capabilities exercitadas por testes | ❌ | **nenhum** teste referencia `cap_0XX`/`Cap0XX` |

Ou seja: a métrica mede *geração de stub*, não comportamento entregue. As 68
"concluídas" não têm verificação automatizada de que fazem o que descrevem.

## 5. Segurança (`SECURITY_GUARDRAILS.md`)

| Regra | Status | Evidência |
|-------|--------|-----------|
| §2 capabilities sensíveis exigem `human_confirmed` | ✅ | probe: `system_executor`/`github_worker` → `PermissionError` sem confirmação; liberado com `human_confirmed: true` |
| §3 bloqueio de injeção no payload (recursivo) | ✅ | probe: `oi; rm -rf /` e `{"nested":[{"deep":"$(whoami)"}]}` → `ValueError` |
| Allowlist (capability fora da lista rejeitada) | ✅ | probe: `desconhecido_xyz` → `PermissionError` |
| §1 "Toda execução passa pelo CapabilityAuthorizer (AssistantService → Authorizer → Executor)" | ❌ | único consumidor real é `eagle_osint_adapter`; `assistant_service`, `system_executor`, `github_worker`, `drive_uploader`, `gist_uploader` **não** passam |
| §4 nenhum módulo lê `os.environ` para **segredos** | 🟨 | nenhum lê segredo direto ✅; mas `persistent_shell_adapter` executa subprocesso com `env=os.environ` (vaza todos os segredos para o filho) |
| §5 PII redigida antes do índice vetorial + `purge_by_user`/`purge_all` | ✅ | `vector_memory_adapter` resolve `pii_redactor` antes de indexar; métodos em `pii_redactor.py`; `tests/privacy/` verde |
| §6 vision externa desligada por padrão + consentimento + auditoria | ✅ | `allow_external_vision=False`, `user_consent=False`; `tests/vision/test_external_upload_blocking.py` verde |
| §7 auto-merge proibido em `capabilities/`, `adapters/infrastructure/`, `application/security/` | ❌ | ver §2 acima |
| §8 testes de segurança obrigatórios e verdes | ✅ | `tests/security` + `tests/privacy` + `tests/vision`: **101 passed** |

## 6. Fase 4 (Soldier Mesh / Edge) e Fase 5 (Econômico)

| Proposta | Status | Evidência |
|----------|--------|-----------|
| Fase 4: Soldier Mesh em progresso | 🟨 | existem `domain/models/soldier.py`, `soldier_registry`, `soldier_telemetry_adapter`, `soldier_bridge`, `tactical_map_service`, `security_audit_adapter` (edge) e `tests/application/test_tactical_mesh.py`; não há execução ponta a ponta com dispositivo real |
| Fase 5: "Pendente (CostTracker, ResourceOptimizer)" | 🟨 | **`CostTrackerAdapter` já existe e é consumido pelo `llm_router`** (persiste em `llm_cost_log`) — a doc subestima; `ResourceOptimizer` não existe |

## 7. Autorregulação / instintos sintéticos / modelo de si

| Proposta | Status | Evidência |
|----------|--------|-----------|
| `docs/AUTORREGULACAO.md` (linha de estudo) | 📄 | documento declara-se "camada conceitual preliminar" — coerente |
| `docs/AUTORREGULACAO_ESBOCO.md` (energy, integrity, operational_stress, model_confidence, stability, motivações concorrentes, ciclo perceber→recalibrar, registro de discrepância) | ❌ | grep por `operational_stress`, `model_confidence`, `resource_availability`, `self_model`, `instinct` em `app/`: **nenhum resultado** |
| Análogos funcionais já existentes | ✅ | `curiosity_engine`, `assistant_curiosity`, `exploration_controller`, `decision_engine`, `policy_store`, `prioritizer_service`, `evaluate_risks_service`, `state_manager` |
| `docs/SOLICITAÇÃO_AO_CLAUDE.md` | 📄 | carta/pedido, não implementação |

## 8. Padrões estruturais e artefatos gerados

| Proposta | Status | Evidência |
|----------|--------|-----------|
| "Nenhum arquivo acima de 300 linhas" (CHANGELOG 2026-03-06) | ❌ | **35 arquivos** em `app/` acima de 300 linhas (maior: `ai_gateway.py`, 765) |
| `ARCHITECTURE.md` reflete o código real | ❌ | gerado por bot: lista módulos já removidos (`pipeline_builder.py`, `code_discovery.py`, `trajectory.py`, `overwatch_perimeter.py`, `jarvis_dev_agent.py`) |
| `docs/ARQUIVO_MAP.md` reflete o código real | ❌ | idem (23 referências inexistentes) |
| Documentação não cita arquivo inexistente | ✅ *(novo)* | `tests/test_docs_references.py` |

---

## Resumo executivo

**Entregue e verificado:** DI do Nexus (incl. circuit breaker/CloudMock/discovery),
pipelines YAML com resolução via Nexus, ciclo de auto-evolução com gatekeeper +
sandbox + PR, autorizador de capabilities (allowlist/sensível/injeção), PII antes do
índice vetorial, bloqueio de vision externa, log de custos de LLM, autoconsciência
via contexto consolidado, self-healing de CI (`jarvis_healer`).

**Não entregue (a doc promete, o código não faz):**
1. Métrica "68/102 capabilities" mede stubs gerados — 78/102 arquivos são placeholders e nenhum teste os exercita.
2. O ciclo de evolução não evita recriar o que já existe (34/34 capabilities pendentes já têm arquivo de código) e o `AdapterRegistry` só é exercitado por testes — nenhum consumidor de produção.
3. `CapabilityAuthorizer` não é aplicado ao fluxo principal (`AssistantService → Executor`).
4. A regra §7 de arquivos protegidos da auto-evolução não cobre as pastas listadas.
5. `DockerSandbox` não tem nenhum consumidor nem teste; o sandbox efetivo é o `EvolutionSandbox` (acionado pelo gatekeeper).
6. Nada gera pipelines YAML automaticamente (o claim "pipeline salvo para reuso" não existe mais).
7. Camada de autorregulação (estado interno/motivações/modelo de si) é só conceitual.
8. Padrão de 300 linhas violado em 35 arquivos; `ARCHITECTURE.md`/`ARQUIVO_MAP.md` desatualizados.

**Corrigido nesta verificação:** `use_cache=False` documentado e implementado; tabela
de timeouts do `NEXUS.md` alinhada ao código (com teste de contrato); docs de status
e README alinhados ao que existe.

## Como reproduzir as evidências

```bash
# Nexus (cache, circuit breaker, contrato de componentes)
python -m pytest tests/test_nexus_circuit_breaker.py tests/security/test_nexus_contract_compliance.py -q
python -m pytest tests/test_nexus_docs_contract.py -q

# Segurança / privacidade / visão
python -m pytest tests/security tests/privacy tests/vision -q

# Auto-evolução e agente
python -m pytest tests/application/test_evolution_orchestrator.py tests/test_phase4_fixes.py -q

# Stubs de capabilities
grep -l "Gerado automaticamente pelo CrystallizerEngine" app/domain/capabilities/*.py | wc -l   # 78
python -c "import json,pathlib;c=json.loads(pathlib.Path('data/capabilities.json').read_text())['capabilities'];print(sum(1 for x in c if x['status']!='complete'))"  # 34 pendentes, todos com arquivo

# Arquivos acima de 300 linhas
wc -l $(find app -name "*.py" -not -path "*__pycache__*") | awk '$1>300' | wc -l             # 35
```
