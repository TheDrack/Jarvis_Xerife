# Jarvis Prospecto — arquitetura inicial

**Status:** domínio, discovery por CNPJ, qualificação, campanhas, entregáveis e store DuckDB implementados. Esta branch acrescenta uma capability interna read-only via Nexus, Tool Registry, Android MCP com sessão autorizada e HUD Global local. API de carteira multi-tenant, cobrança e marketplace não pertencem ao núcleo de inteligência.  
**Escopo:** mecanismo interno de descoberta e qualificação empresarial reutilizável pelo Jarvis, por seus agentes e por aplicações autorizadas. A operação própria é o primeiro operador; a entrega comercial manual é um uso do mecanismo, não um SaaS embutido no Jarvis.  
**Princípio:** extensão do Jarvis_Xerife; não criar uma segunda plataforma de agentes, fila ou identidade. Vitrines, catálogos, relacionamento comprador-fornecedor, pedidos e recorrência pertencem a outro produto e outro repositório.

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

A operação própria será o primeiro operador e usuário do mecanismo. O `tenant_id` presente em arquivos de campanha é apenas um rótulo local de execução, não cadastro de cliente, membership ou isolamento SaaS. MultMetal (São José/SC) e M&B Menegaz e Boger são prospects potenciais da operação, não clientes confirmados.

- **Operação própria:** usar o sistema para encontrar empresas que possam contratar os serviços de inteligência comercial e automação.
- **MultMetal:** prospect de relacionamento profissional. Os segmentos compradores devem ser definidos a partir do catálogo, capacidade produtiva, território e histórico comercial confirmados.
- **M&B Menegaz e Boger:** prospect de relacionamento profissional. Mercados, mercearias, padarias e food service são hipóteses de segmentos compradores a validar com catálogo e cobertura logística.

Não criar contas de clientes, importar listas privadas ou conectar sistemas dessas empresas sem autorização e relação comercial estabelecida.

## 3. Arquitetura lógica

```text
Jarvis Agent / HUD Global / MCP Android
                         |
                Tool Registry + Dispatcher
                         |
                 ProspectingAdapter
                         |
              DiscoveryQuery / Provider
                         |
               CnpjStoreProvider
                         |
                 DuckDB (read-only)
                         |
        Receita Federal — Dados Abertos CNPJ

Produto comercial independente
          |
   contrato privado versionado
          |
   capability de discovery do Jarvis
```

O mecanismo de discovery não depende do HUD, de uma sessão de agente específica nem do computador da MultMetal. O HUD e os agentes são consumidores; o DuckDB precisa estar disponível no host configurado. A integração com o produto comercial será serviço-a-serviço, nunca importação direta de módulos Python.

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

A capability interna usa os componentes já existentes:

- `ProspectingAdapter` resolve `CnpjStoreProvider` e o contrato `DiscoveryQuery`.
- `data/nexus_registry.json` registra o adaptador no Nexus.
- `config/tool_registry.json` declara `prospecting.companies.search` e `prospecting.companies.lookup`, com schemas, capability, permissão, escopo, rate limit e classificação.
- `app/adapters/edge/prospecting_mcp_tools.py` expõe as duas operações no Android MCP; cada chamada passa pelo `ToolDispatcher`, que valida schemas, aplica rate limit, exige a capability `prospecting.cnpj.read`, resolve o Nexus e registra auditoria.
- O Android MCP exige pareamento com o perfil `termux_jarvis`; o perfil reúne `android.shell.exec`, `communication.chatgpt.prompt` e `prospecting.cnpj.read`. Sessões criadas antes da inclusão da capability não são atualizadas automaticamente.
- O HUD Global Desktop usa endpoints locais autenticados pelo token do próprio HUD. O endpoint não é publicado na API SaaS e não abre DuckDB no navegador.

O adaptador só abre o store em modo de leitura. O caminho é definido por `JARVIS_PROSPECTO_STORE_PATH`; sem arquivo presente, a capability falha fechada e informa que o store está indisponível. O banco não é versionado nem sincronizado automaticamente entre dispositivos.

A busca devolve um registro por raiz de CNPJ (`cnpj_basico`, 8 dígitos). O CNPJ completo exibido identifica o estabelecimento representativo retornado; a operação `lookup` exata, por sua vez, consulta um estabelecimento pelo CNPJ completo. Não confundir essas duas granularidades.

Não criar nova fila, scheduler, worker, sistema de identidade ou memória comercial paralelos.

## 9. API da carteira comercial — fora do núcleo

Os endpoints de carteira abaixo descrevem um CRM/serviço comercial multi-tenant. Eles não devem ser implementados no Jarvis_Xerife como parte da capability de discovery. Se forem necessários, pertencem ao novo produto comercial e ao seu próprio modelo de identidade e persistência.

Depois de implementar membership e repositórios tenant-scoped no produto comercial:

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

### Fase 2 — carteira comercial (fora do Jarvis_Xerife)
- Tenants, memberships, carteira comercial e histórico de relacionamento pertencem ao repositório do novo produto.
- O núcleo Jarvis não recebe tabelas de marketplace, pedidos, recorrência, pagamentos ou assinatura.
- O `tenant_id` de campanha permanece um rótulo local até que exista um consumidor comercial com contrato próprio.

### Fase 3 — integração interna e HUD (implementada nesta branch)
- Consumir a capability pelo MCP/Tool Registry e apresentar resultados no HUD Global sem duplicar o motor de busca. **(Android MCP via dispatcher + janela Prospecto no HUD Global Desktop)**
- O HUD usa `/api/prospecting/search` e `/api/prospecting/lookup`, autenticados pelo token local e limitados a leitura.
- Paginação por `after_cnpj_basico`, limite de 100 por chamada, estado explícito quando o store não existe e proveniência exibida na interface.
- A rota é do servidor local do Desktop, não uma API pública de clientes.

### Fase 4 — discovery e qualification
- Adaptadores de fontes permitidas, rate limit, termos e proveniência. **(implementado para a base oficial de CNPJ: adaptadores CSV e DuckDB, com proveniência CC-BY; fontes e termos em [JARVIS_PROSPECTO_SOURCES.md](JARVIS_PROSPECTO_SOURCES.md))**
- ICPs configuráveis por oferta/tenant. **(implementado: `IcpProfile` + `IcpWeights`)**
- Scores separados e explicáveis de fit, intent e confidence. **(implementado, sem calibração de pesos)**
- Sem scraping indiscriminado ou disparo automático. **(respeitado: nenhuma coleta ou envio existe no domínio)**

### Fase 4b — entregável e operação manual (implementada)
- `build_deliverable_csv` gera o banco de prospects entregue ao cliente, com score, tier, critérios, fontes e flag de verificação.
- `app/application/prospecting/campaign.py` + `scripts/prospecto_run.py` executam uma campanha (ICP + consulta) de forma repetível, com manifesto por execução (passo a passo em [JARVIS_PROSPECTO_RUNBOOK.md](JARVIS_PROSPECTO_RUNBOOK.md)).
- `app/adapters/infrastructure/prospecting/cnpj_store.py` + `scripts/prospecto_ingest.py` materializam a base por UF num store DuckDB retomável, tirando a varredura de ~30 GB do caminho de cada campanha ([metodologia e medições](JARVIS_PROSPECTO_DATA_PIPELINE.md)).
- Sem dados de contato pessoal; valores vindos de fontes externas são neutralizados contra injeção de fórmula em planilha.
- `outbound` = lista fria por aderência; `priority` = aderência com sinal explícito; `not_fit` fica fora do CSV por padrão.

### Fase 5 — outreach e analytics (fora do núcleo de discovery)
- Gestão de relacionamento, opt-out, campanhas de contato e métricas comerciais pertencem ao novo produto comercial.
- O Jarvis pode fornecer automação de canais como infraestrutura, mas não deve acoplar esse fluxo ao mecanismo público de CNPJ.
- Nenhum outreach é executado por esta capability.

## 11. Critérios de aceite da capability interna

- As chamadas do HUD local exigem o token local; os MCPs expõem apenas operações de leitura.
- O store é aberto em modo read-only e não é criado automaticamente pelo adaptador.
- Toda empresa devolvida tem pelo menos uma evidência de origem.
- A busca declara a granularidade por raiz CNPJ; lookup declara a granularidade por estabelecimento.
- Paginação é limitada e explicita `truncated` e `next_cursor`.
- Ausência do store ou falha de consulta não produz resultados fictícios.
- Nenhum telefone/e-mail é coletado e nenhum contato é enviado.
- Cobrança, membership, carteira comercial e marketplace permanecem fora deste núcleo.
- Testes unitários, integração, segurança e suíte completa passam sem desabilitar testes ou reduzir cobertura.

### Fase 4c — capability interna (esta implementação)
- Expor pesquisa por UF, município e prefixos CNAE via `ProspectingAdapter`.
- Expor consulta exata de CNPJ completo por estabelecimento.
- Registrar os manifests no Tool Registry e o adaptador no Nexus.
- Disponibilizar os tools nos MCPs Desktop e Android, com paginação e limite de 100 resultados por chamada.
- Não executar outreach, não ler telefone/e-mail e não cobrar automaticamente.
