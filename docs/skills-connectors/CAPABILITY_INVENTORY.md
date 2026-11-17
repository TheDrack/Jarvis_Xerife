# Inventário de capacidades — Jarvis Xerife

**Revisão de código:** 2026-11-16  
**Branch de referência:** main, commit 444b0b322f132802368cbbe0c9568d4409438e61  
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
| Auto-evolução | app/application/services/ e scripts de evolução | Gatekeeper, sandbox, revisão e publicação são etapas distintas; não assumir autonomia irrestrita. |
| Segurança | app/application/security/, app/runtime/toolbox/ e testes de segurança | A política efetiva depende do composition root e da identidade runtime. |

## Tool manifest catalog

O arquivo config/tool_registry.json declara 10 manifests na versão de schema 1.0.0 no commit de referência:

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

A listagem descreve manifests versionados, não disponibilidade real de adapters, credenciais ou grants. Consulte o arquivo JSON para schemas, permissões, escopos e metadados atualizados.

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
