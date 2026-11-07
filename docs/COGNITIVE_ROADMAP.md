# Jarvis Cognitive Architecture — Roadmap de implementação

**Status:** proposta aprovada para planejamento; implementação ainda não iniciada por este documento.  
**Data:** 2026-11-05  
**Repositório:** `TheDrack/Jarvis_Xerife`  
**Objetivo:** transformar a infraestrutura já existente em um sistema cognitivo contínuo, evidence-driven, persistente e capaz de atuar sob políticas explícitas.

## 1. Objetivo e limites

O objetivo não é reconstruir Harness, Nexus, Universal Toolbox, Multi-Agent, Universal Intelligence, Desktop, Android ou os conectores existentes. É integrar e completar suas capacidades para que o Jarvis mantenha um estado contextual do ambiente, interprete mudanças, raciocine com evidências, persiga objetivos, execute ações autorizadas e aprenda com resultados verificados.

"Jarvis igual à ficção" é uma direção aspiracional, não um critério técnico literal. O escopo verificável deste roadmap é continuidade operacional, percepção contextual, memória útil, raciocínio rastreável, planejamento, execução supervisionada, iniciativa limitada por políticas e melhoria demonstrável.

Não presumir consciência, compreensão humana ou autonomia irrestrita. Cada capacidade será avaliada por comportamento reproduzível.

## 2. Princípios arquiteturais obrigatórios

1. **Reutilizar antes de criar:** cada etapa começa mapeando módulos, contratos, migrations, workflows e testes existentes.
2. **Evidência antes de status:** nomes de classes, documentação, arquivos, PRs merged ou flags configuradas não provam comportamento operacional.
3. **Fonte e proveniência:** toda observação preserva origem, instante de coleta, instante de validade quando conhecido, método, confiança e limitações.
4. **Fato não é inferência:** observações, afirmações extraídas, hipóteses e previsões são tipos distintos.
5. **Identidade conservadora:** correlação incerta gera candidato de vínculo; não fundir entidades automaticamente sem evidência suficiente.
6. **Eventos idempotentes:** ingestão e projeções devem tolerar entrega ao menos uma vez, duplicatas, reordenação e replay.
7. **Persistência explícita:** estado atual é uma projeção reconstruível; histórico de evidências/eventos é append-only quando aplicável.
8. **Política antes de ação:** nenhuma conclusão cognitiva concede permissão. Execução continua sujeita ao principal autenticado, escopo, política, aprovação e limites existentes.
9. **Falha fechada:** perda de memória, proveniência, autorização ou verificação não deve produzir ação ativa por suposição.
10. **Privacidade e retenção:** minimizar dados pessoais, segredos e conteúdo bruto; definir acesso, retenção, expurgo e auditoria antes de produção.
11. **Provider-neutral:** modelos são substituíveis; nenhum raciocínio ou plano pode depender de um único fornecedor.
12. **Incrementos pequenos:** PRs focadas, testes de regressão e CI verde; nunca enfraquecer testes ou critérios para obter aprovação.


## 2.1 Trilha transversal permanente — manutenção e correção automática de PRs

Esta trilha é independente das fases C0–C8 e permanece ativa durante todo o ciclo de vida do projeto. O Cognitive Roadmap governa a evolução de capacidades; o sistema de correção automática de PRs governa a manutenção contínua da qualidade do código e das entregas. Uma responsabilidade não substitui a outra.

- Preservar os workflows de CI, self-healing e correção automática de PRs já existentes. Nenhuma fase cognitiva autoriza removê-los, desativá-los, enfraquecê-los ou reduzir sua cobertura.
- Ao falhar um workflow, coletar logs e contexto do job, classificar a falha (código, teste, ambiente, dependência, configuração ou serviço externo), reproduzir quando viável e identificar a causa raiz.
- Quando a correção for determinística e segura, atualizar a branch/PR que originou a falha, adicionar ou corrigir testes e reexecutar os checks. Reutilizar PR/issue equivalente; não abrir duplicatas.
- Se a falha for transitória ou externa, registrar evidência e repetir somente conforme política de retry; não mascarar falha nem alterar testes válidos para obter status verde.
- Manter publicação em branch/PR separada da execução candidata. Não conceder ao agente de correção permissão para aprovar, fazer merge, alterar secrets ou implantar. Merge/deploy continuam sujeitos aos gates, revisão humana e políticas do repositório.
- Medir taxa de falhas detectadas, causas raiz, correções aceitas, regressões, retries e tempo de recuperação. Uma correção só é concluída após confirmação dos checks aplicáveis.
- Falhas de CI que bloqueiem uma capacidade do roadmap são tratadas prioritariamente como manutenção; após restaurar a integridade da PR, a autoevolução retoma o próximo critério cognitivo pendente.

A trilha transversal não conta como marco cognitivo concluído e não altera a ordem/dependências C0–C8. É requisito operacional contínuo para todas as fases.

## 3. Estado inicial: candidatos de reutilização, não capacidades certificadas

A inspeção documental e a busca de símbolos na `main` identificaram componentes que devem ser auditados antes de qualquer implementação nova:

| Domínio | Implementações encontradas na árvore atual | Tratamento inicial |
|---|---|---|
| Roteamento cognitivo | `app/domain/gears/cognitive_router.py`, pipeline `jarvis_chat.yml` | Auditar escopo: roteamento de conversa não equivale a ciclo cognitivo contínuo |
| Memória | `memory_manager.py`, `working_memory`, `vector_memory_adapter.py`, `procedural_memory_adapter.py`, `memory_consolidation_service.py` | Verificar semântica, persistência, recuperação, consolidação, proveniência, retenção e testes comportamentais |
| Inteligência e observações | `intelligence_core.py`, contratos e adaptadores documentados em `jarvis-universal-intelligence.md` | Reutilizar ingestão e síntese; semântica de entidade/track e correlação temporal continuam incrementais |
| Raciocínio/reflexão | `thought_log_service.py`, `meta_reflection.py`, `technical_analysis_service.py` | Verificar se produzem hipóteses ligadas a evidências, contraditório e calibração, não apenas logs ou chamadas LLM |
| Planejamento | `strategist_service.py`, `app/multiagent/execution_plan.py`, `TaskRunner`, diário declarativo | Reutilizar execução declarativa; confirmar se há objetivos persistentes, dependências e replanejamento |
| Coordenação/execução | Scheduler, fila, workers, Universal Toolbox e política de execução | Completar gaps operacionais multi-runtime e verificação de efeitos |
| Iniciativa | `assistant_proactivity.py`, `assistant_curiosity.py`, `curiosity_engine.py`, workers recorrentes | Verificar gatilhos, frequência, deduplicação, utilidade e controles; não confundir sugestão em chat com iniciativa contínua |
| Aprendizado/evolução | `evolution_orchestrator.py`, `evolution_sandbox.py`, `evolution_gatekeeper.py`, serviços de learning | Reutilizar proposta/sandbox/gatekeeper; exigir avaliação comparativa, rollback e ausência de regressões |

A busca de código é um inventário preliminar. Nenhum item desta tabela está declarado operacionalmente concluído por aparecer na árvore. O levantamento detalhado deverá apontar caminho, símbolos, consumidores reais, migrations, testes e evidência de runtime.

## 4. Fase 0 — Auditoria de capacidades e contratos

**Objetivo:** estabelecer a verdade do estado atual e impedir duplicação.

### Trabalho
- Mapear módulos, símbolos, entry points, dependências, consumidores, filas, eventos, tabelas, migrations, flags, permissões e testes.
- Classificar cada capacidade como: `REUSE_VERIFIED`, `REUSE_PARTIAL`, `IMPLEMENTED_UNVERIFIED`, `MISSING`, `DUPLICATE_CANDIDATE` ou `BLOCKED`.
- Distinguir implementação, teste unitário, CI, conexão, autorização, execução agendada e verificação ponta a ponta.
- Identificar contratos duplicados entre Universal Intelligence, memória, plano declarativo e multiagente.
- Registrar riscos de privacidade, volume, custo, retenção, consistência e falha.
- Criar testes comportamentais de baseline antes de mudar módulos existentes.

### Entregáveis
- Matriz de capacidades com evidências rastreáveis.
- Diagrama de fluxo atual e mapa de dependências.
- Lista de contratos a reutilizar, estender ou substituir.
- ADR para decisões estruturais que alterem limites ou persistência.

### Aceitação
- **C0-A01:** cada capacidade crítica tem caminho de código, consumidor e teste identificados.
- **C0-A02:** lacunas e incertezas estão explicitamente registradas.
- **C0-A03:** nenhum módulo é considerado pronto apenas por nome ou documentação.

### Manifesto de missões executáveis
O selector agendado consome exclusivamente o manifesto versionado neste documento. Cada missão deve referenciar um critério C0–C8 existente, um único arquivo Python rastreado e não protegido, testes existentes, dependências, risco e resultado esperado. A fase declarada precisa estar marcada como **Em andamento** em `docs/STATUS.md`. O manifesto vazio é intencional: não existe atualmente um alvo C0 aprovado para mutação automática. A ausência de missão elegível mantém o workflow em `blocked`, antes de LLM, sandbox ou publicação.

O manifesto seleciona trabalho; ele não concede autorização. EVOLUTION_ENABLED, Gatekeeper, sandbox Docker, publisher confiável, deduplicação de PR, checks e revisão humana continuam obrigatórios.

<!-- JARVIS_EVOLUTION_MANIFEST_START -->
```json
{
  "schema_version": 1,
  "phase": "C0",
  "missions": []
}
```
<!-- JARVIS_EVOLUTION_MANIFEST_END -->

## 5. Fase 1 — World Model

**Objetivo:** manter uma representação temporal e coerente de entidades, relações, estados e observações do ambiente.

### Trabalho
- Definir contratos canônicos para `Entity`, `EntityIdentity`, `Relationship`, `Observation`, `StateAssertion`, `EvidenceReference` e `ChangeEvent`.
- Separar identidade estável de identificadores observados (IP, MAC, provider ID, nome, coordenada etc.).
- Preservar proveniência, confiança, método, `observed_at`, `valid_from/valid_to` quando conhecidos e instante de ingestão.
- Implementar resolução determinística de identidade e geração de candidatos probabilísticos; conflitos não resolvidos permanecem separados.
- Construir projeção de estado atual e histórico temporal reconstruível.
- Integrar observações da Universal Intelligence, OSINT, inventário de rede e fontes do ambiente por adaptadores, sem tornar mapas ou dashboards a fonte canônica.
- Começar com PostgreSQL/Supabase e índices relacionais/JSONB; avaliar banco de grafos somente após medir consultas e escala reais.
- Expor consultas de entidade, vizinhança, histórico, proveniência e alterações.

### Aceitação
- Observações repetidas são idempotentes.
- Duas fontes podem descrever a mesma entidade sem duplicação indevida.
- Identidade incerta não é fundida automaticamente.
- O estado atual pode ser explicado e reconstruído a partir das evidências.
- Alterações e contradições preservam origem e tempo.
- Testes cobrem dados atrasados, reordenados, duplicados, conflitantes e parcialmente ausentes.

## 6. Fase 2 — Cognitive Memory

**Objetivo:** transformar experiências em conhecimento recuperável, contextual e governado.

### Domínios
- Episódica: eventos e experiências datadas.
- Semântica: conhecimento consolidado com evidências e validade.
- Procedural: procedimentos e estratégias que funcionaram sob condições conhecidas.
- Prospectiva: objetivos, compromissos e ações futuras.

### Trabalho
- Auditar e reutilizar memória de trabalho, vetorial, procedural e consolidação já existentes.
- Definir ciclo de ingestão, classificação, consolidação, recuperação, atualização, conflito e expiração.
- Associar memórias a entidades, objetivos, tarefas e evidências do World Model.
- Implementar recuperação híbrida: filtros estruturados, full-text e vetores; ranking por relevância, recência, confiança e contexto.
- Manter versões e contradições em vez de sobrescrever fatos sem histórico.
- Implementar política de retenção, exclusão, isolamento por usuário/tenant e minimização de dados.
- Distinguir memória persistida de contexto temporário de uma sessão.

### Aceitação
- O sistema recupera experiências relevantes em um cenário novo.
- Memórias retornam fonte, data, confiança e escopo.
- Contradições são sinalizadas; não são silenciosamente resolvidas.
- Repetição não gera crescimento ilimitado de duplicatas.
- Exclusão/expiração respeita a política definida e é testada.
- Falha no armazenamento não é apresentada como memória salva.

## 7. Fase 3 — Perception Engine

**Objetivo:** converter fluxos heterogêneos em observações normalizadas que atualizam o World Model.

### Trabalho
- Reutilizar os adaptadores e coletores existentes de Universal Intelligence, OSINT, rede, dispositivos, streaming e canais móveis.
- Definir envelope versionado de evento/observação com fonte, identidade candidata, timestamps, modalidade, payload referenciado, confiança e classificação de sensibilidade.
- Implementar ingestão assíncrona, backpressure, limites de tamanho, timeout, retry seletivo, DLQ e replay.
- Deduplicar por identidade de origem e chave semântica; processar fora de ordem.
- Adicionar percepção de áudio/imagem/vídeo por tarefas acionadas e amostragem adaptativa, evitando inferência cara contínua sem necessidade.
- Separar coleta passiva de ação ativa; conectores remotos respeitam escopos e permissões.
- Medir latência, perda, taxa de duplicatas, falhas por fonte e custo.

### Aceitação
- Pelo menos duas fontes distintas atualizam a mesma entidade ou evento com proveniência preservada.
- Falha parcial de uma fonte não interrompe fontes independentes.
- Backpressure e indisponibilidade não causam perda silenciosa.
- Replay é idempotente.
- O sistema distingue ausência de dados de evidência de ausência.

## 8. Fase 4 — Reasoning Engine

**Objetivo:** produzir conclusões rastreáveis, hipóteses testáveis e previsões calibradas.

### Trabalho
- Criar contrato de `Claim`, `Hypothesis`, `EvidenceLink`, `CounterEvidence`, `Inference`, `Prediction` e `ConfidenceAssessment`.
- Construir pipeline: pergunta/objetivo → busca de evidências → geração de hipóteses → busca contraditória → avaliação → conclusão ou abstenção.
- Usar LLMs para interpretação e síntese; regras determinísticas para invariantes; estatística para detecção/previsão; planejamento simbólico para restrições.
- Exigir citações internas a observações/memórias para afirmações factuais relevantes.
- Registrar versão do modelo, prompt/estratégia, dados utilizados, custo e resultado, sem persistir segredos ou conteúdo desnecessário.
- Medir calibração, precisão, falsos positivos, abstenção e qualidade das evidências.
- Tratar saída de modelo e conteúdo externo como dados não confiáveis, nunca como autorização ou instrução privilegiada.

### Aceitação
- Toda conclusão importante aponta evidências e limitações.
- Evidência contrária é pesquisada e exibida.
- O sistema abstém quando a informação é insuficiente.
- Hipóteses não são promovidas a fatos sem confirmação.
- Benchmarks incluem casos ambíguos, contraditórios e fora de distribuição.

## 9. Fase 5 — Strategic Planner

**Objetivo:** manter objetivos persistentes e produzir planos executáveis, dependentes de contexto e revisáveis.

### Trabalho
- Auditar e estender os planos declarativos, diário e TaskRunner existentes.
- Definir `Goal`, `Subgoal`, `Plan`, `PlanStep`, `Dependency`, `Constraint`, `Milestone` e `Outcome`.
- Persistir estado do objetivo, motivação, prioridade, prazo, orçamento, risco e critério de sucesso.
- Decompor objetivos em tarefas verificáveis e selecionar capacidades por contrato.
- Planejar dependências, paralelismo, checkpoints, compensações e limites.
- Replanejar quando evidências, recursos, prazos ou resultados mudarem.
- Evitar objetivos concorrentes incompatíveis e tarefas sem proprietário/condição de encerramento.

### Aceitação
- Um objetivo sobrevive a reinício e pode ser retomado.
- Cada plano tem pré-condições, critérios de conclusão, orçamento e limites.
- Mudança de contexto invalida/revisa etapas afetadas, sem perder histórico.
- O sistema detecta impasses e solicita intervenção quando necessário.

## 10. Fase 6 — Autonomous Executive

**Objetivo:** executar planos por agentes e ferramentas existentes, com autorização, supervisão e comprovação de efeitos.

### Trabalho
- Reutilizar scheduler, fila, workers, Toolbox, TaskRunner, Gatekeeper e políticas existentes.
- Introduzir decisão explícita entre planejar e despachar: principal, ferramenta, operação, escopo, risco, reversibilidade e aprovação.
- Verificar autorização no momento da execução, não apenas no planejamento.
- Adotar entrega at-least-once com idempotência, leases, fencing, checkpoints e tratamento de resultado desconhecido.
- Verificar efeito pós-ação usando evidência independente quando possível.
- Implementar compensação apenas quando for segura e definida; não repetir automaticamente ação com resultado desconhecido.
- Separar modo observação, recomendação e execução; ativação gradual por capability e ambiente.

### Aceitação
- Um objetivo é executado ponta a ponta em ambiente de teste com pelo menos dois runtimes reais ou dois processos independentes.
- Falhas de worker, timeout, duplicação e expiração de lease são recuperadas sem ação duplicada.
- Ação sensível exige aprovação vinculada ao plano exato.
- Resultado é verificado; despacho bem-sucedido não equivale a efeito confirmado.
- Auditoria permite reconstruir decisão, autorização, execução e resultado.

## 11. Fase 7 — Initiative Engine

**Objetivo:** iniciar investigação ou trabalho útil sem depender de prompt pontual, dentro de limites definidos.

### Trabalho
- Reutilizar workers recorrentes e serviços de proatividade/curiosidade após auditoria.
- Detectar mudanças relevantes no World Model, objetivos vencidos, anomalias e oportunidades.
- Gerar candidatos de iniciativa com evidências, impacto, urgência, confiança, custo e ação sugerida.
- Deduplicar, agrupar e suprimir alertas repetidos.
- Aplicar orçamento, horário, preferência, quiet hours e política de notificação.
- Começar por observar e recomendar; ampliar execução somente por capability autorizada.
- Permitir ao usuário corrigir relevância e registrar feedback.

### Aceitação
- Um cenário relevante dispara investigação sem prompt humano.
- Eventos redundantes não geram tempestade de notificações/tarefas.
- A iniciativa explica por que foi iniciada e quais evidências a motivaram.
- O sistema respeita silêncio, orçamento, escopo e permissões.

## 12. Fase 8 — Learning & Evolution Engine

**Objetivo:** melhorar estratégias e componentes a partir de resultados medidos, sem regressão silenciosa.

### Trabalho
- Comparar previsão, decisão e resultado real.
- Registrar sucesso/falha por estratégia, modelo, ferramenta e contexto.
- Detectar limitações recorrentes e propor melhorias/skills.
- Criar datasets de avaliação com dados minimizados e consentimento/política adequados.
- Executar experimentos offline ou em sandbox, com baseline, holdout e métricas pré-definidas.
- Reutilizar Evolution Orchestrator, Sandbox e Gatekeeper; integrar revisão e rollback.
- Exigir avaliação de segurança, regressão, custo, latência e qualidade antes de promover mudança.
- Separar aprendizado de política/modelo de alteração automática do código-fonte.

### Aceitação
- Toda melhoria compara baseline e candidato com métricas reproduzíveis.
- Nenhuma mudança é promovida se houver regressão acima do limite definido.
- Há trilha de auditoria, versão e rollback testado.
- O aprendizado não altera permissões nem amplia autonomia por conta própria.

## 13. Cognitive Runtime — integração contínua

O Cognitive Runtime será a camada de coordenação do ciclo, não um nono agente monolítico e não uma duplicação do scheduler multiagente.

Responsabilidades:
- manter ciclo de avaliação acionado por eventos e objetivos;
- consultar World Model e Memory;
- solicitar Reasoning e Planning quando necessário;
- delegar execução ao Autonomous Executive;
- receber resultados e atualizar estado/memória;
- controlar budgets, checkpoints, cancelamento e backpressure;
- expor estado observável e health sem revelar dados sensíveis.

O runtime deve ser incremental, com composição por portas/adapters e contratos versionados. O primeiro protótipo deve operar em modo shadow/observe, sem ações externas, antes de qualquer execução autônoma.

## 14. Marcos de entrega e dependências

| Marco | Entrega | Dependência | Gate de saída |
|---|---|---|---|
| C0 | Auditoria e baseline comportamental | Estado atual da main | Matriz com evidências e gaps |
| C1 | Contratos + World Model mínimo | C0 | Entidades, observações, relações e histórico testados |
| C2 | Memória cognitiva ligada ao World Model | C1 | Recuperação contextual e consolidação testadas |
| C3 | Percepção integrada | C1; C2 em paralelo | Duas fontes atualizam modelo com replay idempotente |
| C4 | Raciocínio baseado em evidências | C1–C3 | Hipóteses, contraditório e abstenção avaliados |
| C5 | Objetivos e planejamento persistentes | C1–C4 | Plano retomável e replanejável |
| C6 | Execução supervisionada | C5 + controles multiagente | Cenário ponta a ponta com verificação de efeitos |
| C7 | Iniciativa controlada | C1–C6 | Gatilho autônomo útil, deduplicado e governado |
| C8 | Aprendizado e evolução validados | C4–C7 | Ganho medido, sem regressão, rollback provado |

As etapas C1–C3 podem ter trabalho paralelo apenas depois que os contratos de eventos, entidades e memória forem acordados. A ativação de iniciativa e autoevolução depende dos gates anteriores; não antecipar permissões.

## 15. Primeiro vertical slice obrigatório

Antes de ampliar o escopo, demonstrar um cenário completo, controlado e reproduzível:

1. Um dispositivo de laboratório muda de estado (ex.: fica indisponível).
2. Uma fonte de percepção emite uma observação com timestamp e proveniência.
3. O World Model atualiza o estado sem apagar o histórico.
4. A memória recupera ocorrências anteriores relacionadas.
5. O Reasoning Engine formula hipóteses e procura evidência contrária.
6. O Planner cria uma investigação com etapas e critérios de conclusão.
7. O Executive executa somente consultas passivas permitidas.
8. O sistema verifica o estado do dispositivo por uma segunda observação.
9. A memória registra o resultado e o ciclo encerra ou propõe próximo passo.
10. Um teste comprova o fluxo completo, inclusive falhas e duplicatas.

O slice não deve executar varreduras ativas, alterar dispositivos, reiniciar serviços ou realizar ações destrutivas. Ações ativas ficam fora do primeiro experimento.

## 16. Observabilidade e métricas

Medir no mínimo:
- cobertura de proveniência por observação e conclusão;
- taxa de resolução correta e falsa fusão de entidades;
- duplicatas, eventos atrasados e perdas no pipeline;
- precisão/recall e calibração de hipóteses;
- taxa de abstenção adequada;
- sucesso de recuperação de memória contextual;
- objetivos concluídos versus abandonados/expirados;
- taxa de sucesso de tarefas e efeitos confirmados;
- ações duplicadas e resultados desconhecidos;
- iniciativas úteis, redundantes e ignoradas;
- custo, latência e consumo por ciclo cognitivo;
- regressões por versão de modelo, prompt, skill e código.

Os thresholds devem ser definidos no baseline da Fase 0; não inventar metas numéricas antes de medir a situação atual.

## 17. Segurança, operação e rollout

- Começar em ambiente local/CI e modo shadow.
- Não habilitar workers recorrentes ou flags de histórico até migrations, grants, leases e persistência real estarem reconciliados e testados.
- Não aplicar migrations de produção como parte deste roadmap documental.
- Não conceder novas permissões, alterar ACL, segredos, deploy ou configuração de produção sem autorização específica.
- Usar feature flags por capacidade e manter defaults seguros.
- Exigir PR, workflows verdes e revisão de segurança para mudanças de execução, memória sensível ou autorização.
- Registrar rollback e plano de desativação antes de cada ativação.

## 18. Próximas ações imediatas

1. Executar a Fase 0 com foco em memória, Universal Intelligence, execução declarativa, proatividade e evolução.
2. Escrever contratos e ADR do World Model, incluindo semântica temporal e identidade.
3. Prototipar World Model mínimo em branch isolada, sem alterar o banco de produção.
4. Implementar testes de idempotência, proveniência, conflito e reconstrução temporal.
5. Integrar primeiro uma fonte já disponível e uma fonte local de laboratório.
6. Validar o vertical slice em modo somente leitura.
7. Atualizar este roadmap com evidências reais após cada PR/merge.

## 19. Regra de status

Cada capacidade deve usar estados separados:
- `NOT_STARTED`
- `AUDIT_REQUIRED`
- `PARTIAL`
- `IMPLEMENTED_UNVERIFIED`
- `TESTED`
- `RUNTIME_VERIFIED`
- `PRODUCTION_VERIFIED`
- `BLOCKED`

O status global de uma fase é limitado pelo critério mais fraco entre seus gates obrigatórios. Não inferir conclusão de uma fase a partir de submódulos existentes.
