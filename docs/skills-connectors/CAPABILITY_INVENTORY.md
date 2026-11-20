# Inventário de capacidades — Jarvis Xerife

**Revisão de código:** 2026-11-19  
**Base de código auditada:** main @ 2bf151052f1a25f088030bfafec5d31d58f18e11  
**Escopo:** inventário do código e contratos versionados. Não é um health check de deploy nem de conectores do host.

## Semântica dos estados

- **No código:** existe implementação versionada.
- **Testado:** existe teste relevante; consulte o resultado do CI para saber se passou no commit atual.
- **Integrado:** há consumidor/caminho de chamada identificável.
- **Disponível no host:** o runtime atual expõe a ferramenta.
- **Autorizado:** principal, sessão e política permitem a operação.
- **Runtime/produção verificados:** houve teste direto no ambiente alvo com evidência datada.

Esses estados são independentes. Manifest, skill, migration ou adapter não provam disponibilidade, autorização ou funcionamento remoto.

## Capacidades e fronteiras

| Área | Código / entrada principal | Limite operacional |
|---|---|---|
| Composição Nexus | app/core/ | Resolve componentes; não autoriza ações. |
| Tool manifests | app/domain/tools/, config/tool_registry.json | Catálogo versionado e schemas; não executa por si só. |
| Tool dispatcher | app/runtime/toolbox/ | Valida, autoriza, resolve adapter e registra resultado; depende de política/principal válidos e deve falhar fechada. |
| Toolchains | config/toolchains/ | DAGs declarativos; limites e execução dependem do dispatcher/runtime. |
| Pipelines YAML | app/runtime/pipeline_runner.py, config/pipelines/ | Mantém compatibilidade legada; nem todo passo usa o dispatcher. |
| Multiagente | app/multiagent/ | Queue, scheduler, workers e contratos; depende de banco, migrations, credenciais e worker ativo. |
| Identidade de worker | app/adapters/infrastructure/agent_worker_credentials.py e rotas de tasks | Token opaco por agente, expiração/revogação e grants server-side no caminho autenticado. O caminho legado service-role não é equivalente. |
| Planos declarativos | app/multiagent/execution_plan.py e serviços associados | Plano estruturado, allowlist e diário são requisitos; ações sensíveis dependem de aprovação confiável. |
| Inteligência | app/domain/intelligence/, app/application/services/intelligence_collector.py | Adaptadores e coleta não implicam persistência recorrente ou fonte externa disponível. |
| OSINT / observações | app/adapters/infrastructure/intelligence/ e app/adapters/infrastructure/osint/ | Respeitar proveniência, limites geográficos, permissões e termos de uso de cada fonte. |
| Desktop | desktop/, app/adapters/edge/ | Requer host Windows, sessão interativa e configuração local. |
| Android | mobile/android/, app/adapters/edge/ | Requer pareamento, permissões Android, consentimentos e validação no dispositivo. |
| MCP | app/adapters/edge/ e app/adapters/infrastructure/ | STDIO, HTTP e túneis são transportes diferentes; conexão não concede autorização. |
| Prospecto | `app/domain/prospecting/`, `app/application/prospecting/`, `app/adapters/infrastructure/prospecting/`, `app/adapters/edge/prospecting_mcp_tools.py`, `app/adapters/edge/prospecting_demand_mcp_tools.py` | Discovery B2B por CNPJ, outreach multicanal e demandas B2B/B2C/C2B estão no código e cobertos por CI; relays externos, provedores de vagas/catálogos, runtime Android e isolamento multi-tenant hospedado não estão comprovados. |
| Auto-evolução | app/application/services/ e scripts de evolução | Gatekeeper, sandbox, revisão e publicação são etapas distintas; não assumir autonomia irrestrita. |
| Segurança | app/application/security/, app/runtime/toolbox/ e testes de segurança | A política efetiva depende do composition root e da identidade runtime. |

## Tool manifest catalog

O arquivo config/tool_registry.json declara 12 manifests na versão de schema 1.0.0 em `main @ d087d11`:

- telegram.get_updates
- telegram.send_message
- network.get_interfaces
- network.discover_devices
- drive.upload_backup
- intelligence.news.search
- intelligence.events.eonet
- intelligence.events.earthquakes
- intelligence.snapshot.collect
- communication.chatgpt_plan.send_prompt
- prospecting.companies.search
- prospecting.companies.lookup

A listagem descreve manifests versionados, não disponibilidade real de adapters, credenciais ou grants. Consulte o arquivo JSON para schemas, permissões, escopos e metadados atualizados.

### Prospecto — consumers MCP e limites operacionais

**Discovery empresarial**
- Tool Registry: `prospecting.companies.search` e `prospecting.companies.lookup`, ambos `read_only`, capability `prospecting.cnpj.read`.
- Adapter: `ProspectingAdapter` sobre `CnpjStoreProvider` e store DuckDB local.
- Consumidores: Android MCP e endpoints autenticados do HUD Global local.
- Granularidade: busca retorna um estabelecimento representativo por raiz CNPJ de 8 dígitos; lookup exato usa CNPJ completo de 14 dígitos.

**Outreach**
- MCP tools: `prospecting.outreach.plan`, `prospecting.outreach.approve`, `prospecting.outreach.dispatch`, `prospecting.outreach.history` e `prospecting.outreach.block`.
- Canais: WhatsApp, e-mail, telefone e formulário institucional, por relays HTTPS configurados separadamente.
- Planejamento não envia. Dispatch exige aprovação explícita da sessão autenticada, base de contato revisada, evidência, idempotência e ausência de bloqueio DO_NOT_CONTACT.
- O estado e o histórico ficam em SQLite local. Sem relay/credenciais de provedor configurados, não há envio externo; nenhum envio real foi comprovado.

**Demand matching**
- MCP tools: `prospecting.demands.create`, `prospecting.demands.get`, `prospecting.demands.list`, `prospecting.demands.history` e `prospecting.demands.withdraw_profile_consent`.
- Domínio suporta direções B2B, B2C e C2B; o serviço de discovery valida proveniência, deduplica, ranqueia e sinaliza falha parcial de fontes.
- CV/perfil permanece privado por padrão; compartilhamento exige consentimento explícito, timestamp e escopo por solicitação, com retirada auditada.
- Não há provider externo de vagas nem catálogo de produtos/serviços conectado. CNPJ não é evidência de vaga aberta nem de oferta atual.
- O tenant atual é um limite local single-owner, não isolamento SaaS multiusuário.

**Testes e evidência**
- Testes: `tests/domain/test_prospecting_domain.py`, `tests/adapters/infrastructure/test_prospecting_adapter.py`, `tests/runtime/test_toolbox_prospecting_integration.py`, `tests/adapters/edge/test_prospecting_mcp_tools.py`, `tests/application/test_prospecting_outreach.py`, `tests/adapters/edge/test_prospecting_demand_mcp_tools.py`, `tests/adapters/infrastructure/test_prospecting_demand_store.py`, `tests/application/test_prospecting_demand_discovery.py` e `tests/domain/test_prospecting_demand.py`.
- PRs #858–#861 foram integradas; PR Validation e Task Queue passaram nos heads das PRs #859, #860 e #861. Isso comprova CI dos commits, não execução Android, disponibilidade de relays, providers externos ou produção.

### ACATE — código presente, consumer não comprovado

- `AcateDirectoryAdapter`: importa CSV fornecido pelo operador e exige confirmação explícita de permissão de reutilização. Há teste isolado, mas não foi localizada instanciação em serviço, registro Nexus, manifest ou ferramenta MCP.
- O adapter aplica UF/município/limite, mas não aplica `cnae_prefixes`, `only_active` ou `include_secondary_cnae` do contrato `DiscoveryQuery`. O teste atual não verifica esses filtros. Não conectá-lo a campanhas genéricas até que o contrato seja implementado ou as limitações sejam explicitamente modeladas.
- `AcateObservatoryAdapter`: importa snapshot JSON local em `MarketIndicatorDataset`; não há collector ou consumer operacional identificado. Indicadores agregados não são prospects.
- **Estado:** adapters presentes e testados isoladamente; integração/runtime não verificados. Não contam como fontes ativas do Prospecto.

### TechnicalAnalysisService — não é um Reasoning Engine

- `execute()` retorna `not_implemented`; `analyze()` usa classificação por substrings.
- Não há entrada correspondente no `data/nexus_registry.json`, consumer de produção ou teste específico localizado. Manter como gap legado; não duplicar nem promover por nome.

### Self-healing — cobertura de PR não demonstrada

- `homeostase.yml` é restrito a workflows confiáveis de `main` e não recebe eventos de PR Validation/Task Queue.
- O endpoint `/v1/github/ci-heal/{run_id}` apenas baixa logs e registra tentativas; não corrige código nem publica PR.
- O fluxo trusted-main com `scripts/jarvis_healer.py` continua preservado. Não afirmar que PRs abertas são autocorrigidas automaticamente.

## Skills portáteis

A árvore skills/ contém:
- jarvis-android-navigation
- jarvis-context-memory
- jarvis-host-ops
- jarvis-mobile-notifications
- jarvis-multi-agent-coordination
- jarvis-portas-browser
- jarvis-visual-navigation
- jarvis-viv

A pasta .agents/skills/ contém uma seleção destinada a hosts que fazem descoberta por projeto. Não são duas fontes independentes de autorização. A descoberta depende do host e deve ser verificada em uma sessão nova.

## Seleção de worker

Antes de atribuir uma tarefa, confronte as ferramentas exigidas pela tarefa com os grants efetivos do worker. Workers que anunciam somente text_reasoning não devem receber tarefas que dependam de GitHub, browser, shell, desktop ou serviços externos.

## Atualização do inventário

Ao adicionar/remover manifests, skills, adapters, consumers ou grants:
1. atualize o inventário;
2. identifique testes de contrato e regressão;
3. atualize os estados somente com evidência;
4. registre o commit e a data;
5. nunca copie snapshots de produção sem revalidá-los.
