# Jarvis Prospecto — arquitetura inicial

**Status:** domínio e qualificação determinística implementados; persistência, API e discovery pendentes  
**Escopo:** prospecção comercial B2B para a operação própria e, futuramente, tenants clientes.  
**Princípio:** extensão do Jarvis_Xerife; não criar uma segunda plataforma de agentes, fila ou identidade.

## 1. Objetivo do produto

Jarvis Prospecto transforma pesquisa empresarial em oportunidades comerciais rastreáveis. O produto não vende listas estáticas nem classifica uma empresa como compradora apenas por pertencer a determinado setor.

O pipeline distingue:

1. **Discovery:** identificar empresas compatíveis em fontes públicas ou provedores autorizados.
2. **Enrichment:** completar atributos empresariais, preservando a origem de cada dado.
3. **Qualification:** avaliar aderência ao perfil de cliente ideal e sinais explícitos de intenção, com justificativa.
4. **Prospecting:** registrar abordagens autorizadas, respostas, recusas e próximos passos.
5. **Analytics:** medir qualidade da carteira, conversões, reuniões, propostas e receita.

Empresa encontrada, empresa qualificada e empresa com intenção demonstrada são estados diferentes.

## 2. Primeira carteira

A operação própria será o primeiro tenant e o primeiro usuário do produto. MultMetal (São José/SC) e M&B Menegaz e Boger são prospects potenciais da operação Jarvis Prospecto, não tenants nem clientes confirmados.

- **Operação própria:** usar o sistema para encontrar empresas que possam contratar os serviços de inteligência comercial e automação.
- **MultMetal:** prospect de relacionamento profissional. Os segmentos compradores devem ser definidos a partir do catálogo, capacidade produtiva, território e histórico comercial confirmados.
- **M&B Menegaz e Boger:** prospect de relacionamento profissional. Mercados, mercearias, padarias e food service são hipóteses de segmentos compradores a validar com catálogo e cobertura logística.

Não criar contas de clientes, importar listas privadas ou conectar sistemas dessas empresas sem autorização e relação comercial estabelecida.

## 3. Arquitetura lógica

```text
Android / Desktop / Web / API
            |
      FastAPI routers
            |
   Authenticated application services
            |
       Prospecting domain
       |       |       |
    Company  Evidence  Pipeline
       |       |       |
       +--- Qualification policy
            |
    Tenant-scoped repositories
            |
 PostgreSQL / Supabase (future persistence)
            |
 Discovery / Enrichment provider adapters
            |
 Public registries / official websites / licensed providers

Existing Jarvis Multi-agent Queue
            |
 Optional asynchronous jobs after deterministic MVP
```

O domínio de prospecção não deve depender do Android nem do PC da MultMetal. O PC da empresa é infraestrutura de terceiro e não é requisito de execução, armazenamento ou disponibilidade do produto.

## 4. Limites de domínio

### Empresa e prospect

- `ProspectCompany`: identidade empresarial, CNPJ, website, setor/segmento e localização.
- `ProspectRecord`: vínculo entre a empresa e a carteira comercial de um tenant.
- `ProspectEvidence`: fonte, URL, tipo de fonte, termos aplicáveis, timestamps e lista explícita dos atributos empresariais sustentados por aquela evidência.
- `ProspectStageChange`: evento auditável de mudança de etapa.

A primeira versão não armazena contatos pessoais. A inclusão futura de nome, telefone, e-mail pessoal ou perfil profissional exigirá finalidade específica, base legal documentada, minimização, retenção, controle de acesso e mecanismo de oposição/opt-out.

### Pipeline

```text
DISCOVERED
   -> ENRICHED
      -> QUALIFIED
         -> CONTACTED
            -> ENGAGED
               -> MEETING_SCHEDULED
               -> PROPOSAL_SENT
                  -> CUSTOMER

Qualquer etapa aberta -> DO_NOT_CONTACT
Etapas não convertidas -> DISQUALIFIED
```

Transições inválidas são rejeitadas. `DO_NOT_CONTACT` é terminal para impedir reativação acidental. Toda transição exige ator e justificativa; a persistência futura deve manter o histórico append-only.

## 5. Multi-tenancy e autorização

- Cada prospect e cada dado comercial pertencem a um `tenant_id` obrigatório.
- O tenant ativo deve ser resolvido no servidor a partir da identidade autenticada e de uma associação/membership verificada.
- Nunca confiar em `tenant_id` enviado pelo cliente como prova de autorização.
- Nunca usar `user_id` como se fosse automaticamente `tenant_id`.
- Consultas, atualizações, exports, tarefas assíncronas e eventos devem aplicar o mesmo escopo do tenant.
- Usar chaves estrangeiras compostas ou constraints equivalentes para impedir referências cruzadas entre tenants.
- RLS no banco será defesa adicional, alinhada ao modelo de autenticação real; não aplicar uma policy genérica antes de verificar como a identidade JWT atual se relaciona com o Supabase.
- Não compartilhar evidências, contatos, scores, notas ou histórico comercial entre tenants por deduplicação global implícita.

A API atual do Jarvis injeta usuário autenticado, mas isso não comprova associação a uma organização. Por isso a camada de persistência multi-tenant e os endpoints de cliente ficam bloqueados até existir um contrato de membership verificável.

## 6. Contrato de qualidade dos dados

Cada atributo obtido externamente deve permitir responder:

- Qual fonte o forneceu?
- Qual URL ou referência permite verificá-lo?
- Quando foi coletado e quando foi verificado pela última vez?
- Quais termos/licenças se aplicam?
- Qual tenant e qual finalidade justificam o armazenamento?
- O dado está confirmado, inferido ou ainda não verificado?

Conteúdo de páginas, diretórios e APIs externas é dado não confiável. Não pode ser interpretado como instrução para agentes nem como autorização para contatar uma pessoa.

## 7. Qualificação e scoring

O score é explicável e separado em dimensões:

- **Fit:** aderência ao ICP (setor, segmento, território e porte/capacidade), calculado por `evaluate_fit` em `app/domain/prospecting/icp.py`.
- **Intent:** apenas sinais explícitos, datados e com evidência, avaliados por `assess_intent`.
- **Confidence:** qualidade, atualidade e independência das evidências, avaliada por `assess_confidence`.

Não converter fit em intent. Segmento compatível, tamanho da empresa ou presença na web não provam intenção de compra: uma empresa com fit máximo e nenhum sinal fica em `outbound` (lista fria), nunca em `priority`.

Os pesos de fit são **dados do perfil**, não constantes do código: `IcpProfile` exige um peso positivo para cada critério configurado e não aceita perfil sem critério. O score é a fração do peso avaliável que casou. Atributo ausente na empresa vira `unknown` — não penaliza o score, não conta como incompatibilidade e marca o prospect para verificação. Os pesos ainda não foram calibrados com resultados comerciais; até lá o score ordena listas, não decide sozinho.

A confiança usa uma rubrica determinística documentada (fontes distintas, atualidade e diversidade de tipos de fonte), não uma probabilidade calibrada.

## 7b. Fontes de dados

A base durável de discovery é o conjunto público do CNPJ da Receita Federal (CC-BY, mensal): não há custo por consulta e a atribuição é obrigatória na entrega. Google Places não pode ser armazenado (os termos permitem apenas `place_id`), então não é base de dados. Comparativo de fontes, custos, limites e regras de armazenamento em [JARVIS_PROSPECTO_SOURCES.md](JARVIS_PROSPECTO_SOURCES.md).

## 8. Integração com o Jarvis existente

Reutilizar:
- FastAPI e dependência de autenticação já existentes.
- Nexus DI para composição de serviços.
- Pydantic v2 e contratos imutáveis usados no domínio de inteligência.
- PostgreSQL/Supabase depois de definir membership, RLS e migrations.
- Fila multiagente existente para discovery/enrichment assíncronos quando houver critérios, idempotência, orçamento, limites de fonte e auditoria.

Não criar nova fila, scheduler, worker, sistema de identidade ou memória comercial paralelos.

## 9. API planejada

Depois de implementar membership e repositórios tenant-scoped:

- `GET /v1/prospects` — lista paginada e filtrada.
- `POST /v1/prospects` — cria prospect com evidência.
- `GET /v1/prospects/{prospect_id}` — consulta no tenant ativo.
- `PATCH /v1/prospects/{prospect_id}` — atualiza atributos permitidos.
- `POST /v1/prospects/{prospect_id}/transitions` — registra mudança de etapa.
- `POST /v1/discovery-runs` — agenda uma execução de descoberta com parâmetros explícitos e idempotência. **(contrato de discovery já existe: `DiscoveryQuery`/`DiscoveryProvider`/`DiscoveryResult`)**
- `GET /v1/discovery-runs/{run_id}` — acompanha estado, fontes e falhas parciais.

Listagens serão paginadas; erros seguirão envelope consistente; criação e execução assíncrona terão idempotency key durável.

## 10. Fases de implementação

### Fase 1 — domínio (implementada)
- Contratos de empresa, evidência e prospect tenant-scoped.
- Pipeline determinístico e histórico de transições.
- Testes unitários de validação, isolamento conceitual e transições.
- `employee_count` opcional em `ProspectCompany` para o critério de porte, sempre sustentado por evidência.

### Fase 2 — persistência segura
- Resolver modelo de tenants e memberships.
- Migration de tabelas e índices, RLS e constraints anti-cross-tenant.
- Repositório com tenant_id sempre explícito e testes de isolamento entre dois tenants.
- Sem aplicar migrations em produção durante a implementação da PR.

### Fase 3 — API e interface
- Endpoints autenticados, paginação, filtros e respostas tipadas.
- Interface inicial de carteira e pipeline.
- Testes de autorização, IDOR/BOLA e contratos.

### Fase 4 — discovery e qualification
- Adaptadores de fontes permitidas, rate limit, termos e proveniência. **(parcial: adaptador de dados abertos do CNPJ implementado em `app/adapters/infrastructure/prospecting/cnpj_open_data.py`; fontes e termos em [JARVIS_PROSPECTO_SOURCES.md](JARVIS_PROSPECTO_SOURCES.md))**
- ICPs configuráveis por oferta/tenant. **(implementado: `IcpProfile` + `IcpWeights`)**
- Scores separados e explicáveis de fit, intent e confidence. **(implementado, sem calibração de pesos)**
- Sem scraping indiscriminado ou disparo automático. **(respeitado: nenhuma coleta ou envio existe no domínio)**

### Fase 4b — entregável
- `build_deliverable_csv` gera o banco de prospects entregue ao cliente, com score, tier, critérios, fontes e flag de verificação.
- `app/application/prospecting/campaign.py` + `scripts/prospecto_run.py` executam uma campanha (ICP + consulta) de forma repetível, com manifesto por execução (passo a passo em [JARVIS_PROSPECTO_RUNBOOK.md](JARVIS_PROSPECTO_RUNBOOK.md)).
- `app/adapters/infrastructure/prospecting/cnpj_store.py` + `scripts/prospecto_ingest.py` materializam a base por UF num store DuckDB retomável, tirando a varredura de ~30 GB do caminho de cada campanha ([metodologia e medições](JARVIS_PROSPECTO_DATA_PIPELINE.md)).
- Sem dados de contato pessoal; valores vindos de fontes externas são neutralizados contra injeção de fórmula em planilha.
- `outbound` = lista fria por aderência; `priority` = aderência com sinal explícito; `not_fit` fica fora do CSV por padrão.

### Fase 5 — outreach e analytics
- Integrações de canais permitidos, inicialmente com aprovação humana.
- Opt-out/supressão, idempotência, limites e auditoria.
- Métricas de conversão e receita atribuível.

## 11. Critérios de aceite do MVP

- Nenhum prospect pode ser lido ou alterado fora do tenant autenticado.
- Todo prospect tem pelo menos uma evidência de origem.
- Toda mudança de etapa tem ator, motivo e timestamp.
- `DO_NOT_CONTACT` não pode ser revertido por fluxo comum.
- Scores distinguem fit, intent e confiança e mostram as evidências.
- Nenhum contato é enviado sem autorização e política de canal.
- Jobs são idempotentes, limitados e auditáveis.
- Testes unitários, integração, segurança e suíte completa passam sem desabilitar testes ou reduzir cobertura.
