# ADR-007 — World Model: identidade canônica e projeção temporal

- **Status:** Proposed — requer revisão arquitetural; não aceito nem implementado
- **Data:** 2026-11-24
- **Depende de:** ADR-002 e ADR-004
- **Pré-requisito do roadmap:** C0-CAPABILITY-MAP, C0-GAPS-RECORDED e C0-NO-NAME-BASED-COMPLETION (verified em `docs/STATUS.md`)
- **Critério-alvo:** C1-WORLD-MODEL
- **Escopo:** primeiro incremento verificável da Fase 1 do Cognitive Roadmap

## 1. Contexto e estado comprovado

O ledger de docs/STATUS.md registra os três critérios C0 como verified no commit 9ad37374465c25a40f9bf3ceb51fa9889622aae9, com os três checks correspondentes. Na main atual, C1-WORLD-MODEL é o próximo critério pendente. Este ADR propõe o contrato que falta; não declara C1 concluído.

Há componentes reutilizáveis, mas nenhum deles isoladamente satisfaz o contrato de C1:

1. IntelligenceObservation é um snapshot provider-specific com source_id, entity_type, entity_id, observed_at, posição, atributos limitados e evidências. Não contém scope_id, identidade canônica ou semântica de confiança.
2. intelligence_observation_snapshots já preserva snapshots append-only, com observed_at separado de ingested_at e chave idempotente por fonte, tipo, entidade, instante e hash. ADR-004 já define esse histórico; C1 não deve criar uma segunda cópia da evidência.
3. IntelligenceRecurringWorker coleta e persiste IntelligenceReport sob lease com fencing, mas não projeta as observações para entidades ou relações.
4. GraphStorePort é o contrato do grafo OSINT. Sua implementação é SQLite, permite exclusão de nós/arestas e usa IDs derivados de tipo, seletor e escopo. Node não preserva proveniência temporal da observação; Edge.confidence deriva de heurística do pivô, não da confiabilidade da fonte ou da resolução de identidade. Não deve ser promovido diretamente a fonte canônica do World Model.
5. Existem dois módulos com uma classe chamada SupabaseIntelligenceHistoryAdapter: supabase_intelligence_history.py implementa IntelligenceHistoryRepository e é usado pelo worker; supabase_intelligence_history_adapter.py oferece persist_batch/load_latest e é usado pelas rotas Desktop. Ambos escrevem nas tabelas de ADR-004. A implementação C1 deve reutilizar um contrato de aplicação comum e não introduzir um terceiro escritor de histórico.

A lacuna não é falta de um grafo local: é a ausência de uma fronteira explícita entre observação de fonte, identidade canônica, afirmação temporal e estado materializado.

## 2. Decisão proposta

### 2.1 Separar observação, identidade e estado

- IntelligenceObservation continua sendo a observação imutável emitida pelo provider.
- Entity representa uma entidade canônica dentro de um escopo.
- EntityIdentity representa um identificador observado ou uma chave canônica, sempre com namespace e semântica explícita.
- Observation referencia o snapshot de origem, sem copiar novamente o payload bruto.
- StateAssertion representa uma afirmação temporal sobre um atributo ou estado.
- Relationship representa uma afirmação tipada entre duas entidades.
- EvidenceReference aponta para o snapshot e sua proveniência.
- ChangeEvent registra a alteração produzida na projeção do World Model.

Esses contratos devem ser imutáveis na camada de domínio. A projeção atual pode ser reconstruída a partir das observações e afirmações append-only.

### 2.2 Identidade determinística e aliases

1. O ID canônico é determinístico dentro de scope_id e deriva de uma chave explícita (scope_id, canonical_namespace, canonical_key).
2. O par (source_id, entity_type, entity_id) é uma identidade provider-specific. Ele não autoriza, por si só, fusão com outro provider.
3. Um identificador só pode ser usado como chave compartilhada quando seu namespace estiver declarado como estável e sua semântica de unicidade for conhecida.
4. IP, MAC, nome, coordenada e outros identificadores reutilizáveis ou temporais são aliases observados, não chaves globais. Devem preservar origem e validade quando conhecida.
5. Uma colisão, cardinalidade ambígua ou conflito de escopo impede a fusão automática.
6. Correspondências probabilísticas geram IdentityCandidate com evidências, método, versão e score; permanecem candidatas até uma regra determinística ou revisão explícita. Score não é autorização para fundir.
7. Todo ID, alias, relação e consulta inclui scope_id. Nenhuma resolução atravessa escopos implicitamente.

O scope_id do grafo OSINT é atualmente orientado a casos. Sua equivalência com tenant, usuário, dispositivo ou ambiente ainda precisa ser decidida; não deve ser reutilizada sem mapeamento explícito.

### 2.3 Semântica de confiança

Não usar um único número para representar conceitos diferentes. O contrato deve preservar, quando disponíveis:

- source_reliability: confiabilidade atribuída à fonte por política versionada;
- observation_confidence: confiança declarada ou calculada sobre a observação;
- identity_match_confidence: confiança do vínculo entre o identificador observado e a entidade canônica;
- assertion_confidence: confiança da afirmação temporal.

Cada valor é finito e limitado a [0, 1], acompanhado de método e versão. Valor desconhecido permanece null; não deve virar 1.0 por conveniência. A confiança heurística de Edge/pivô do grafo OSINT não é substituta para essas dimensões.

### 2.4 Semântica temporal e contraditório

- observed_at é o instante informado pela fonte.
- ingested_at é atribuído pelo banco no recebimento.
- valid_from e valid_to são opcionais e só existem quando a fonte ou regra consegue sustentá-los.
- Observações atrasadas ou reordenadas entram no histórico, mas não podem regredir silenciosamente a projeção atual.
- Duas afirmações incompatíveis permanecem preservadas com suas evidências; o sistema não escolhe uma silenciosamente nem apaga a outra.
- Correções são novas evidências/afirmações. O histórico de origem não recebe UPDATE ou DELETE pela aplicação.

A regra de estado atual deve considerar semântica temporal e proveniência, não apenas a ordem de chegada.

## 3. Persistência proposta

PostgreSQL/Supabase permanece a primeira persistência, conforme o roadmap. Não introduzir Neo4j ou outro banco de grafos antes de medir consultas, volume e custo.

O desenho lógico inicial pode ser materializado em:

| Estrutura lógica | Responsabilidade |
|---|---|
| world_entities | projeção rebuildable de entidades canônicas por escopo |
| world_entity_identities | namespaces, aliases, validade e método de resolução |
| world_observation_links | vínculo idempotente entre entidade e snapshot existente |
| world_assertions | estado e relações tipadas, com tempo, confiança e evidência |
| world_identity_candidates | candidatos ambíguos sem fusão automática |
| world_change_events | histórico append-only das mudanças da projeção |

A divisão física final deve ser validada pelos padrões de consulta; a tabela não é autorização para criar todas as estruturas de uma vez.

Invariantes obrigatórias:

- scope_id participa das chaves únicas e das relações entre tabelas.
- world_observation_links referencia a chave natural já única de intelligence_observation_snapshots: (source_id, entity_type, entity_id, observed_at, content_hash).
- Repetir o mesmo snapshot e a mesma versão do projetor não cria uma segunda projeção.
- A tabela de entidades é uma projeção reconstruível; observações, afirmações e eventos são a trilha de evidências.
- Índices iniciais cobrem (scope_id, entity_id, observed_at DESC) e lookup de identidade por escopo/namespace/hash. Índices adicionais dependem de EXPLAIN ANALYZE com volume representativo.
- Conteúdo sensível segue SensitivityPolicy e o armazenamento sensível existente. CPF em texto claro, tokens e segredos não entram no grafo geral.
- Todas as tabelas têm RLS e grants explícitos. O cliente é server-side; não usar anon/authenticated nem fallback para cliente público. Como service_role pode ignorar RLS, os grants SQL continuam sendo a fronteira efetiva.
- Cada escrita da projeção precisa identificar `projector_id` e `projector_version` imutáveis e usar chaves de idempotência determinísticas nas relações, afirmações e eventos. A chave deve incluir escopo, snapshot de origem, versão do projetor e identidade/hash da saída conforme o tipo de registro.
- Reexecutar o mesmo snapshot com a mesma versão do projetor não pode duplicar links, afirmações nem `world_change_events`. Uma nova versão do projetor representa uma revisão distinta, que precisa ser reconstruída/validada e promovida deliberadamente; não pode sobrescrever silenciosamente a projeção ativa nem duplicar eventos visíveis.

world_entities pode ser atualizado somente pela transação/RPC controlada do adapter de projeção. A trilha de evidências permanece append-only. A projeção deve poder ser descartada e reconstruída sem perder informação.

## 4. Integração de aplicação

Criar um WorldModelRepository port e um WorldModelProjector determinístico, sem chamadas de rede ou LLM. O projetor recebe observações normalizadas, resolve apenas namespaces explicitamente permitidos e produz um delta idempotente.

A primeira composição usa o caminho existente:

1. IntelligenceRecurringWorker adquire e renova o lease existente.
2. O collector produz IntelligenceReport.
3. O IntelligenceHistoryRepository persiste os snapshots de origem.
4. O projetor aplica a projeção no mesmo scope_id e registra resultado/erro sem apagar o histórico já persistido.
5. Um replay do relatório ou snapshot pode repetir a projeção com segurança.

Não criar outra fila, scheduler ou worker para o C1. O adapter Desktop deve convergir para o mesmo contrato de aplicação antes de duplicar a projeção. A falha do projetor deve ser observável como execução parcial e recuperável por replay idempotente.

## 5. Testes de aceitação obrigatórios

Executar contra PostgreSQL descartável, sem DDL no Supabase de produção:

1. Mesmo snapshot repetido: uma projeção por escopo e versão.
2. Duas fontes com a mesma chave canônica aprovada: uma entidade e duas evidências.
3. IDs provider-specific iguais em fontes diferentes, sem namespace compartilhado: entidades separadas.
4. IP/MAC/nome/posição ambíguos ou reutilizados: nenhum merge automático.
5. Observações atrasadas e reordenadas: histórico preservado e estado atual não regredido.
6. Payloads conflitantes no mesmo instante: variantes e evidências preservadas.
7. Atributos opcionais ausentes: nenhum valor inventado.
8. Escopos diferentes: nenhuma identidade ou relação cruzada.
9. Dados sensíveis: rejeição, HMAC ou store apropriado; nunca texto claro no grafo geral.
10. Replay integral das evidências: mesma projeção e mesmos IDs.
11. Falha após persistir o histórico e antes da projeção: replay conclui sem duplicação.
12. Cliente admin ausente ou grants insuficientes: falha fechada, sem fallback público.
13. Replay do mesmo snapshot e da mesma versão do projetor mantém os mesmos links, afirmações e IDs de change event; uma versão nova gera revisão identificável sem mutar os snapshots de origem.

O critério C1-WORLD-MODEL só pode ser registrado como concluído quando o teste integrado provar consulta por escopo, replay, proveniência, confiança e reconstrução a partir das evidências.

## 6. Alternativas consideradas

- Promover SQLiteGraphStore a fonte canônica: rejeitada. É local, permite exclusão e não modela o histórico de observações, aliases temporais ou dimensões de confiança exigidas.
- Converter diretamente cada IntelligenceObservation em Node OSINT: rejeitada. Perderia a distinção entre ID provider-specific e identidade canônica, além de tratar confiança de pivô como confiança da observação.
- Criar uma segunda tabela de snapshots: rejeitada. ADR-004 já é o histórico de origem; a projeção deve referenciá-lo.
- Adicionar banco de grafos agora: adiada até existirem consultas e benchmarks que justifiquem o custo operacional.
- Fusão probabilística automática: rejeitada. Ambiguidade deve permanecer explícita.

## 7. Segurança, migração e rollout

- Nenhuma migração, segredo, flag ou serviço de produção é alterado por este ADR.
- Implementação inicial deve usar fixtures e PostgreSQL descartável.
- **Reconciliação de versões/nomes (auditoria read-only 2026-11-24):** os 31 arquivos SQL locais correspondem exatamente às 31 entradas retornadas pelo ledger remoto, incluindo `20261103184307_20261103100304_intelligence_history.sql`. A issue #732 permanece aberta: a correspondência de versão/nome não comprova comparação completa de schema, validação descartável, Supabase Preview nem plano de rollback. Nenhuma migração foi aplicada ou reparada nesta execução.
- **Auditoria read-only de privilégios (2026-11-24):** as duas tabelas ADR-004 têm RLS habilitado e nenhuma policy em `pg_policies`; `service_role` possui somente SELECT/INSERT; `anon`, `authenticated` e `PUBLIC` não possuem privilégios. `UPDATE`, `DELETE` e `TRUNCATE` estão negados para os roles verificados.
- **Evidência operacional (2026-11-24):** `intelligence_event_snapshots`, `intelligence_observation_snapshots` e `jarvis_intelligence_worker_runs` têm zero linhas; o registro singleton de lease está sem `worker_id` e `lease_expires_at`. O schema e os grants estão comprovados, mas não há evidência de ciclo recorrente ou ingestão real no momento.
- Qualquer flag C1 deve nascer desabilitada e só ser ativada após revisão, CI, teste de integração e evidência operacional.
- Não habilitar captura contínua de câmeras/RTSP como parte do C1. Câmeras entram depois como fontes de IntelligenceObservation, respeitando consentimento, origem, limites e orçamento.

## 8. Decisões que exigem revisão antes do código

1. Qual é a semântica canônica de scope_id (tenant, usuário, ambiente, dispositivo, caso) e como ela se relaciona ao escopo OSINT?
2. Quais namespaces de identidade podem ser compartilhados entre fontes e quais permanecem provider-specific?
3. Qual política versionada atribui confiabilidade às fontes e como scores probabilísticos serão calibrados?
4. A projeção atual será uma tabela rebuildable, view ou materialized view? Quais consultas precisam ser atendidas no primeiro slice?
5. Como retenção, exclusão por solicitação e dados sensíveis se aplicam à projeção sem violar a trilha de evidências?
6. Como validar em ambiente descartável/preview a reconciliação de versões já alinhada, incluindo comparação de schema, Supabase Preview e rollback?
7. Como `projector_id`, `projector_version` e as chaves de idempotência serão persistidos e como uma nova versão será reconstruída, comparada e promovida sem duplicar eventos?

8. Qual é a classificação de escopo/visibilidade do snapshot antes da projeção? Hoje `IntelligenceObservation` e `intelligence_observation_snapshots` não carregam `scope_id`, `owner_id` nem classificação de visibilidade; o worker recorrente usa lease singleton e chama o collector sem principal ou escopo. Definir explicitamente quais fontes produzem observações globais compartilháveis e quais são tenant/user/case-scoped, como o escopo é atribuído antes da persistência, e se um snapshot global pode ser ligado a múltiplos escopos. Nunca inferir escopo por `source_id`, `worker_id`, host ou nome da fonte, nem permitir que um snapshot privado seja consultado por outro escopo por meio de um link do World Model.

## 9. Próximo incremento após aceitação

Depois da revisão deste ADR, implementar primeiro os contratos de domínio e o projetor puro com testes determinísticos. Em seguida, implementar o adapter/migração PostgreSQL e só então conectá-lo ao worker existente. Nenhum desses passos deve marcar C1 como concluído antes do teste integrado e do registro de evidência em docs/STATUS.md.


## 10. Revalidação read-only — 2026-11-26

A revalidação foi feita contra `main @ 5359b02505b28751bec4da780bfd3e5951c2f687` e o projeto Supabase ativo, sem DDL/DML, alteração de migration ledger ou escrita de dados.

- **Migrações:** 31 arquivos SQL em `supabase/migrations` e 31 entradas no ledger remoto; pareamento exato `(version, name)` = **31/31**, sem itens locais ou remotos exclusivos. Isso resolve apenas a correspondência de nomes/versões; não fecha a issue #732, pois equivalência schema-a-schema, Supabase Preview e rollback continuam sem evidência suficiente.
- **Idempotência da origem:** a tabela `intelligence_observation_snapshots` possui a constraint única `(source_id, entity_type, entity_id, observed_at, content_hash)`, correspondente ao `on_conflict` usado pelo adapter atual. A chave não contém escopo, pois a tabela de origem também não tem coluna de escopo.
- **Privilégios:** RLS habilitado nas duas tabelas de snapshots; nenhuma policy aparece em `pg_policies`. `service_role` possui SELECT/INSERT; `anon`, `authenticated` e `PUBLIC` não aparecem com privilégios nessas tabelas. O owner `postgres` mantém privilégios administrativos. As cinco RPCs do worker de inteligência existem e EXECUTE está concedido a `service_role` e `postgres`.
- **Runtime:** `intelligence_event_snapshots`, `intelligence_observation_snapshots` e `jarvis_intelligence_worker_runs` continuam com zero linhas. O lease singleton está sem `worker_id` e sem `lease_expires_at`. Portanto, a infraestrutura SQL está presente, mas não há evidência de ciclo recorrente ou ingestão operacional.
- **Contrato de escopo:** a inspeção de `IntelligenceObservation`, `collect_live_intelligence` e `IntelligenceRecurringWorker` confirma que o contrato não recebe escopo/principal e que o worker executa coleta global sob lease singleton. O projetor não pode inventar `scope_id`; a política de visibilidade e a atribuição do escopo precisam ser definidas na origem ou em um vínculo de escopo explicitamente autorizado antes de habilitar projeção.

### Fonte complementar já escopada: observações de ambiente Android/Desktop

A tabela existente `jarvis_environment_observations` é uma fonte distinta do histórico da Universal Intelligence e tem um contrato de escopo mais explícito: `user_id`, `device_id`, `source_device_type`, `observation_type`, `observed_at`, `received_at` e `expires_at`. A rota de ingestão valida a identidade do JWT contra o usuário autenticado, grava o `user_id` derivado do servidor e a rota de leitura filtra pelo mesmo usuário. Localização e uso de aplicativos exigem opt-in explícito; a validação limita payloads e proíbe campos de credenciais.

Snapshot read-only em 2026-11-26: **4.840 registros**, um usuário e um dispositivo; 2.254 `presence`, 2.238 `network_snapshot`, 96 `location_snapshot` e 252 `app_usage_snapshot`. O registro mais recente foi recebido em **2026-11-16 19:37:52 UTC** e todos os 4.840 registros estão expirados segundo `expires_at`. A API os classifica como `stale`; isso não comprova exclusão física nem retenção intencional, portanto a política de retenção continua pendente.

A tabela tem RLS habilitado, sem policies; `service_role` tem SELECT/INSERT e a aplicação aplica o filtro por `user_id`. Como `service_role` ignora RLS, essa autorização no servidor é uma fronteira crítica e não pode ser omitida em novos consumidores. Esta fonte pode informar um mapeamento explícito para escopo de usuário/dispositivo, mas não define o escopo de observações globais da Universal Intelligence nem autoriza importar payload bruto de localização/uso para o World Model. O projetor deve consumir apenas fatos mínimos permitidos, preservando consentimento e validade temporal.

A pendência C1 permanece arquitetural: definir a semântica de escopo/visibilidade na origem, além das decisões já listadas na seção 8. Nenhum dado foi escrito e nenhuma capacidade foi marcada como concluída.
