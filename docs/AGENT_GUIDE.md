# Guia de navegação do repositório para agentes

Este documento orienta agentes de código e automação que trabalham em Jarvis Xerife. Ele descreve a árvore atual em termos de responsabilidade; o código e os schemas versionados são a fonte de verdade.

## 1. Bootstrap da sessão

1. Leia AGENTS.md e as instruções específicas do diretório.
2. Descubra ferramentas, conectores e permissões realmente expostos pelo host atual. Não infira acesso a partir do catálogo.
3. Leia docs/skills-connectors/CATALOG.md e docs/skills-connectors/CONTEXT_MEMORY_PROTOCOL.md.
4. Reconcile a tarefa com o estado atual do branch, arquivos, testes e serviços relevantes.
5. Consulte Graphify antes de grep/leitura ampla: definições, callers, dependências, blast radius e testes relacionados. Verifique a data/commit do índice; se estiver atrasado, use o GitHub/checkout como fonte atual.
6. Antes de executar uma ação, confirme schema, alvo, autorização, pré-condições, efeitos colaterais, sinal de sucesso e rollback.

## 2. Mapa de diretórios

| Caminho | O que procurar |
|---|---|
| app/core | Nexus DI, configuração e composição. |
| app/domain/tools | Contratos e registry de manifests. |
| app/domain/capabilities | Modelos e gestão de capabilities. |
| app/domain/intelligence | Contratos de eventos/observações e regras de inteligência. |
| app/domain/memory e app/domain/context | Memória e contexto. |
| app/domain/missions e app/domain/orchestration | Missões, seleção e coordenação. |
| app/application/services | Casos de uso e serviços de aplicação. |
| app/application/ports | Contratos de saída/entrada da aplicação. |
| app/application/security e privacy | Políticas e proteção de dados. |
| app/adapters/api | Entradas HTTP/API. |
| app/adapters/edge | Integração com host, desktop e dispositivos. |
| app/adapters/infrastructure | Providers, persistência, integrações e serviços externos. |
| app/runtime/toolbox | Dispatcher e execução de ferramentas. |
| app/runtime/pipeline_runner.py | Execução de pipelines YAML. |
| app/multiagent | Scheduler, queue, workers, transport e execution plans. |
| app/communication | Componentes de comunicação compartilhados. |
| mobile/android | Aplicativo Android nativo e testes Kotlin. |
| desktop | Recursos e empacotamento desktop. |
| scripts | Setup, diagnóstico, manutenção e automação. |
| config | Manifests, toolchains e pipelines. |
| migrations | Evolução de schema/RPCs. |
| tests | Testes de unidade, integração, segurança e contratos. |
| skills e .agents | Skills portáteis e configuração de agentes. |

## 3. Fluxos centrais

### API e bootstrap
- serve.py delega para app.application.services.serve.
- main.py combina bootstrap cloud/edge e serviços de background conforme ambiente.
- app/bootstrap_edge.py valida configuração local e resolve assistant_service via Nexus.

### Ferramentas
1. Manifesto tipado em config/tool_registry.json.
2. Contrato/registry em app/domain/tools.
3. Pedido tipado e validação no app/runtime/toolbox.
4. Política de autorização e principal/sessão.
5. Resolução do adapter e execução.
6. Resultado tipado e evento/auditoria.

O registry é metadado; não concede autorização. Sem política de autorização válida, o dispatcher deve recusar.

### Multiagente
1. Uma rotina ou produtor publica tarefa.
2. O backend persiste prioridade, dependências, tentativas e estado.
3. Um worker autenticado envia heartbeat e reivindica tarefa elegível.
4. O worker executa apenas as ferramentas concedidas ao seu principal.
5. O resultado é concluído/liberado usando a identidade da tentativa atual.
6. Lease expirado e fencing impedem conclusão obsoleta.

Não presuma papéis fixos por modelo. Não atribua trabalho com ferramentas a workers que anunciam apenas text_reasoning.

### Inteligência
O coletor normaliza resultados de adapters e reporta falhas parciais. Diferencie consulta sob demanda, armazenamento, execução recorrente e visualização.

### Android/Host
Permissões Android, VPN ativa, consentimentos, pairing, shell opt-in e estado do serviço são condições runtime. Não trate acesso a um endpoint como autorização irrestrita ao dispositivo.

## 4. Regras para alteração

- Antes de criar código, localize a implementação e consumidores existentes.
- Prefira mudanças pequenas e aditivas; preserve compatibilidade usada.
- Faça testes primeiro para comportamento novo ou bug corrigido.
- Não altere migrations aplicadas sem estratégia compatível e revisão do schema real.
- Não reduza cobertura, não pule testes válidos e não esconda falhas.
- Não use valores de ambiente ou tokens reais em exemplos.
- Não execute operações de produção, grants, credenciais, deploy ou ações destrutivas sem autorização.
- Não afirme sucesso sem observar o estado final em fonte autoritativa.

## 5. Verificação

Use o Makefile e os workflows ativos como fonte de comandos CI. Para alterações Python, execute testes focados e a suíte exigida. Para Android, execute os testes/build Gradle definidos pelo projeto. Para Docker, deploy ou provider externo, declare pré-requisitos e resultados separadamente.

## 6. Relato de conclusão

Informe:
- arquivos alterados;
- comportamento implementado;
- testes executados e resultado;
- verificações runtime realmente realizadas;
- limitações, falhas e riscos residuais;
- estado de branch/PR/merge com SHA e checks, quando aplicável.

Não confunda código implementado com integração ativa ou produção verificada.
