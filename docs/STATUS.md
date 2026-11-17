# Estado do projeto — leitura do código versionado

**Data da revisão documental:** 2026-11-16  
**Branch de referência:** main  
**Commit de referência:** 444b0b322f132802368cbbe0c9568d4409438e61  
**Escopo:** árvore de código e documentação versionada. Não foi realizada nesta página uma inspeção autenticada do deploy, banco, dispositivos ou serviços externos.

## Como interpretar este documento

| Estado | Significado |
|---|---|
| Presente no código | Há implementação versionada no branch de referência. |
| Coberto por teste | Existe teste relevante; é necessário consultar o resultado do CI/execução para afirmar que passou. |
| Integrado no fluxo | Há ligação entre os componentes no código; não prova que o ambiente esteja configurado. |
| Runtime verificado | Foi exercitado no ambiente real, com evidência datada e identificável. |
| Produção verificada | Foi confirmado no serviço implantado, banco ou dispositivo de destino. |
| Parcial / condicionado | A implementação depende de política, credenciais, feature flag, serviço externo, permissão ou integração ainda não comprovada. |
| Planejado | Existe como objetivo/documento, mas não deve ser apresentado como comportamento entregue. |

A presença de arquivo, migration, manifest, skill ou variável de ambiente não é prova de integração ativa. Um teste existente não é prova de que ele passou no commit atual.

## Inventário por subsistema

| Subsistema | Estado sustentado pela árvore de código | Limite que deve ser preservado na comunicação |
|---|---|---|
| Nexus DI e composição | Presente no código; usado pelos entrypoints e wrappers de compatibilidade. | Não confundir wrapper app/container.py com um segundo container independente. |
| Domínio e aplicação | Presentes: tools, capabilities, intelligence, memory, context, graph, missions, orchestration, services, ports e security. | A separação é incremental; existem módulos históricos e compatibilidade. |
| Universal Tool Registry | Contratos tipados/versionados e registry em app/domain/tools; catálogo em config/tool_registry.json. | Registry é metadado. Não autentica, autoriza, verifica saúde ou executa. |
| Tool Dispatcher | Implementação em app/runtime/toolbox com validação, resolução, autorização e eventos. | Sem política/principal autorizados, execução deve falhar fechada. Controles locais em memória não são garantias distribuídas. |
| Pipelines | Pipeline runner e definições YAML presentes. | Compatibilidade legada permanece; não declarar migração integral para tool_id/dispatcher. |
| Multiagente | Contratos, scheduler, queue, workers, transport e execution plans presentes em app/multiagent. | Opt-in e dependente de backend, credenciais, grants e configuração. Código não prova worker ativo. |
| Identidade de worker | Existe caminho autenticado com token opaco individual e grants do lado do servidor, além de um caminho legado Supabase direto. | O caminho legado service-role não oferece a mesma fronteira de identidade. Verificar migration e runtime no ambiente alvo. |
| Inteligência | Domínio e adaptadores de fontes estão presentes. | Consulta sob demanda, persistência, execução recorrente e apresentação são capacidades distintas. Fontes externas podem falhar parcialmente. |
| Android | Cliente nativo e integração com serviços Jarvis estão versionados. | VPN, acessibilidade, shell, captura e inspeção dependem de permissões, consentimento, pareamento e testes no dispositivo. |
| Desktop | Cliente Windows/WebView2, API local e scripts de build/start estão presentes. | Listener, firewall, pairing e sessão interativa dependem do host real. |
| MCP e acesso remoto | Servidores/adaptadores e runbooks de transporte estão presentes. | STDIO, HTTP local, Secure MCP Tunnel e gateways privados são rotas diferentes; não inferir conectividade atual. |
| Auto-evolução e reparo | Serviços, gatekeeper, sandbox, scripts e workflows estão presentes. | Não declarar autonomia irrestrita nem merge automático. Validar isolamento, aprovação, testes e publisher por fluxo. |
| Deploy e persistência | Manifestos, migrations e adapters estão presentes. | Só inspeção no ambiente confirma deploy, schema aplicado, RLS/grants, feature flags e saúde. |

## Entrypoints

- main.py — bootstrap principal cloud/edge.
- serve.py — entrada headless/API.
- app/bootstrap_edge.py — bootstrap local/edge.
- scripts/start_jarvis_desktop.ps1 — inicialização desktop Windows.
- app/adapters/edge/jarvis_desktop_mcp.py — servidor MCP desktop.
- scripts/run_multiagent_worker.py — worker multiagente opt-in.
- mobile/android — cliente Android nativo.

## Evidência necessária para atualizar estados operacionais

Para declarar um componente runtime-verified ou production-verified, registre:
1. ambiente/serviço/dispositivo exato;
2. commit ou versão implantada;
3. data/hora e comando ou operação executada;
4. resultado bruto relevante, sanitizado;
5. feature flags, grants e pré-requisitos relevantes;
6. falhas parciais e limitações.

Para Supabase, verifique migrations remotas, schema, RLS, grants e uma operação de leitura/escrita controlada quando autorizada. Para Render, confirme serviço, commit implantado, health e logs. Para Android/Desktop, confirme build e teste real no dispositivo/host.

## Atualização

Esta página substitui snapshots antigos como descrição geral de estado. Resultados históricos continuam úteis como histórico, mas devem permanecer datados e não ser copiados para uma afirmação de estado atual sem revalidação.
