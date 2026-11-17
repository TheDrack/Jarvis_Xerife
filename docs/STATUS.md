# Estado do projeto — leitura do código versionado

**Revisão documental integral anterior:** 2026-11-16  
**Base da revisão integral:** main @ 444b0b322f132802368cbbe0c9568d4409438e61  
**Delta incremental verificado:** 2026-11-17 — main @ ec2755a1a3e673971d4c1ba0ebdba5b7324ecc97  
**Escopo do delta:** PRs #859/#860, inventário Prospecto e handoff de memória; não substitui reauditoria integral dos demais subsistemas.  
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
| Universal Tool Registry | Contratos tipados/versionados e registry em app/domain/tools; catálogo em config/tool_registry.json com 12 manifests no main atual. | Registry é metadado. Não autentica, autoriza, verifica saúde ou executa. |
| Tool Dispatcher | Implementação em app/runtime/toolbox com validação, resolução, autorização e eventos. | Sem política/principal autorizados, execução deve falhar fechada. Controles locais em memória não são garantias distribuídas. |
| Prospecto | Busca CNPJ read-only e workflow outbound auditável via Android MCP; planos, aprovação, dispatch, DNC e histórico. | Sem descoberta automática de contatos; sem relay/provider real configurado ou envio externo comprovado. Não equivale a operação comercial autônoma. |
| Pipelines | Pipeline runner e definições YAML presentes. | Compatibilidade legada permanece; não declarar migração integral para tool_id/dispatcher. |
| Multiagente | Contratos, scheduler, queue, workers, transport e execution plans presentes em app/multiagent. | Opt-in e dependente de backend, credenciais, grants e configuração. Código não prova worker ativo. |
| Identidade de worker | Existe caminho autenticado com token opaco individual e grants do lado do servidor, além de um caminho legado Supabase direto. | O caminho legado service-role não oferece a mesma fronteira de identidade. Verificar migration e runtime no ambiente alvo. |
| Inteligência | Domínio e adaptadores de fontes estão presentes. | Consulta sob demanda, persistência, execução recorrente e apresentação são capacidades distintas. Fontes externas podem falhar parcialmente. |
| Android | Cliente nativo e integração com serviços Jarvis estão versionados. | VPN, acessibilidade, shell, captura e inspeção dependem de permissões, consentimento, pareamento e testes no dispositivo. |
| Desktop | Cliente Windows/WebView2, API local e scripts de build/start estão presentes. | Listener, firewall, pairing e sessão interativa dependem do host real. |
| MCP e acesso remoto | Servidores/adaptadores e runbooks de transporte estão presentes. | STDIO, HTTP local, Secure MCP Tunnel e gateways privados são rotas diferentes; não inferir conectividade atual. |
| Auto-evolução e reparo | Serviços, gatekeeper, sandbox, scripts e workflows estão presentes. | Não declarar autonomia irrestrita nem merge automático. Validar isolamento, aprovação, testes e publisher por fluxo. |
| Deploy e persistência | Manifestos, migrations e adapters estão presentes. | Só inspeção no ambiente confirma deploy, schema aplicado, RLS/grants, feature flags e saúde. |

## Delta verificado: Jarvis Prospecto (2026-11-17)

- **PR [#859](https://github.com/TheDrack/Jarvis_Xerife/pull/859)** foi integrada em `main`. A busca/lookup CNPJ read-only está registrada em `config/tool_registry.json` como `prospecting.companies.search` e `prospecting.companies.lookup`, com implementação em `app/adapters/infrastructure/prospecting/`, consumer Android MCP e UI de Prospecto. Os três workflows do head `9c3dfc9` retornaram sucesso: [44104544766](https://github.com/TheDrack/Jarvis_Xerife/actions/runs/44104544766), [44104544800](https://github.com/TheDrack/Jarvis_Xerife/actions/runs/44104544800) e [44104544626](https://github.com/TheDrack/Jarvis_Xerife/actions/runs/44104544626).
- **PR [#860](https://github.com/TheDrack/Jarvis_Xerife/pull/860)** foi integrada em 2026-11-17 15:00:45 UTC. O head `27c4dca` passou em [JARVIS PR Validation](https://github.com/TheDrack/Jarvis_Xerife/actions/runs/44108337559) e [Jarvis Task Queue Tests](https://github.com/TheDrack/Jarvis_Xerife/actions/runs/44108337555). O código registra cinco ferramentas MCP de outbound: plan, approve, dispatch, block e history; quatro canais são modelados por relays HTTPS configuráveis.
- **Limites operacionais:** planejar não envia; dispatch exige aprovação; DNC e unicidade por empresa/canal/destino/campanha são aplicados localmente. Não há descoberta automática de e-mails, telefones ou formulários institucionais. A PR declara que não foram fornecidas credenciais de providers e que nenhum envio externo ao vivo foi realizado. Relay/provider e sessão Android com a nova capability não foram validados neste delta.
- **Revisão independente:** a API do GitHub não retornou reviews para a PR #860. Os comentários de Strix e Codex registram indisponibilidade de revisão por limite de trial/uso. CI verde não substitui revisão independente. A issue [#682](https://github.com/TheDrack/Jarvis_Xerife/issues/682) de proteção da branch continua aberta; a configuração atual de proteção não foi revalidada por este conector.
- **Roadmap cognitivo:** os três critérios C0 continuam pendentes no ledger abaixo. As PRs de Prospecto não constituem evidência de conclusão C0 nem liberam C1.
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


## Ledger verificável dos critérios cognitivos

Este bloco é consumido por `RoadmapMissionSelector`. Um critério só pode ser tratado como concluído quando estiver como `verified` e trouxer referência imutável de commit, execução de Actions, implementação, consumidor e testes. A presença das referências é validada pelo selector; a autenticidade e a suficiência técnica continuam sujeitas à revisão humana.

<!-- JARVIS_COGNITIVE_EVIDENCE_START -->
```json
{
  "schema_version": 1,
  "roadmap_path": "docs/COGNITIVE_ROADMAP.md",
  "criteria": [
    {
      "criterion_id": "C0-CAPABILITY-MAP",
      "state": "pending",
      "evidence": {
        "commit_url": null,
        "check_urls": [],
        "implementation_paths": [],
        "consumer_paths": [],
        "test_paths": []
      }
    },
    {
      "criterion_id": "C0-GAPS-RECORDED",
      "state": "pending",
      "evidence": {
        "commit_url": null,
        "check_urls": [],
        "implementation_paths": [],
        "consumer_paths": [],
        "test_paths": []
      }
    },
    {
      "criterion_id": "C0-NO-NAME-BASED-COMPLETION",
      "state": "pending",
      "evidence": {
        "commit_url": null,
        "check_urls": [],
        "implementation_paths": [],
        "consumer_paths": [],
        "test_paths": []
      }
    }
  ]
}
```
<!-- JARVIS_COGNITIVE_EVIDENCE_END -->
