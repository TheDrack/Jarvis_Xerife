# Arquitetura do Jarvis Xerife

**Escopo:** arquitetura presente no código versionado de main, não uma promessa de roadmap nem uma declaração de disponibilidade de produção.

## 1. Modelo arquitetural

O sistema combina separação por camadas, portas/adaptadores e composição via Nexus. A estrutura não é uma implementação hexagonal pura: existem módulos históricos e wrappers de compatibilidade, além de runtimes especializados. Ao alterar um subsistema, siga seus contratos locais e não presuma que toda a árvore obedece a uma única abstração.

```text
Interfaces / clientes
  ├─ Desktop Windows (WebView2 + API local)
  ├─ Android nativo
  ├─ API HTTP / WebSocket
  ├─ MCP / CLI
  └─ integrações externas
          |
Adaptadores de entrada e infraestrutura
  ├─ app/adapters/api
  ├─ app/adapters/edge
  └─ app/adapters/infrastructure
          |
Aplicação
  ├─ serviços e casos de uso
  ├─ portas
  ├─ comunicação
  └─ segurança / privacidade
          |
Domínio
  ├─ capabilities, tools, missions
  ├─ intelligence, graph, analysis
  ├─ memory, context
  └─ orchestration, models, services
          |
Composição e execução
  ├─ Nexus DI
  ├─ Tool Registry + Dispatcher
  ├─ Pipeline Runner
  └─ Multi-agent runtime
          |
Dependências externas
  PostgreSQL/Supabase, Render, LLMs, APIs públicas,
  rede privada, Android OS e Windows host
```

## 2. Estrutura real do código

| Diretório | Papel | Observações |
|---|---|---|
| app/core | Composição e configuração | Nexus e configuração compartilhada. |
| app/domain | Núcleo de domínio | Inclui ai, analysis, capabilities, context, graph, intelligence, memory, missions, orchestration, tools e modelos/serviços. |
| app/application | Casos de uso e políticas | Inclui ports, services, communication, privacy e security. |
| app/adapters/api | Adaptadores de API | Entradas HTTP e integração com a aplicação. |
| app/adapters/edge | Host e edge | Desktop, Android bridge e recursos dependentes do sistema operacional. |
| app/adapters/infrastructure | Infraestrutura | Persistência, LLM, mensageria, provedores, auditoria e integrações. |
| app/runtime | Execução declarativa | Pipeline runner e toolbox. |
| app/multiagent | Execução multiagente | Worker, scheduler, queue, transport, contracts e execution plan. |
| app/communication | Comunicação compartilhada | Contratos/implementações usados por mais de uma superfície. |
| config | Catálogos declarativos | tool_registry.json, toolchains e pipelines. |
| migrations | Schema e funções de banco | Migrations precisam ser aplicadas e verificadas separadamente. |
| mobile/android | App Android | Código Kotlin/Gradle e testes Android. |
| desktop | App desktop | Recursos de UI e empacotamento Windows. |
| scripts | Operação | Instalação, diagnóstico, automação e manutenção. |
| skills e .agents | Instruções para agentes | A descoberta depende do host/harness. |
| tests | Qualidade | Testes distribuídos por subsistema e tipo. |

## 3. Composição: Nexus

O Nexus é o mecanismo de resolução de componentes. app/container.py é um wrapper de compatibilidade apoiado no singleton Nexus, não um segundo container independente. O bootstrap edge resolve assistant_service pelo Nexus. A inicialização principal e a entrada headless têm responsabilidades diferentes:

- main.py: bootstrap combinado cloud/edge, serviços de background e comportamento de interface conforme ambiente.
- serve.py: delega para app.application.services.serve e é o entrypoint headless documentado para deploy.
- app/bootstrap_edge.py: valida ambiente, executa setup wizard quando necessário e inicia o assistant_service.

Não trate main.py, serve.py e o bootstrap edge como processos equivalentes.

## 4. Registry e execução de ferramentas

O contrato de ToolManifest é tipado e versionado. O registry canônico está em app/domain/tools/registry.py e lê config/tool_registry.json. O catálogo de runtime possui adaptadores/compatibilidade em app/runtime/toolbox.

O registry:
- valida manifests e schemas;
- protege duplicidade de ID/versão;
- resolve versão exata (ou versão única durante migração);
- não resolve credenciais, não autoriza e não executa.

O dispatcher:
- valida o envelope e argumentos;
- verifica autorização com a política fornecida;
- resolve o adaptador via Nexus;
- aplica controles de execução implementados no processo;
- valida resultado e emite eventos/auditoria.

**Segurança:** ausência de política/principal/autorização deve falhar fechada. Idempotência e limites em memória do processo não equivalem a garantias distribuídas ou duráveis. Catálogo presente não significa adapter saudável, provider conectado ou chamada autorizada.

## 5. Multiagente e fila

O pacote app/multiagent contém contratos, transporte, líder, scheduler, store, fila Supabase e workers. Rotinas/serviços podem publicar tarefas; workers elegíveis reivindicam trabalho conforme prioridade, dependências e disponibilidade. A persistência e a semântica de concorrência dependem do backend e das migrations correspondentes.

O caminho HTTP autenticado separa o JWT do principal chamador do token opaco do worker. O servidor associa a credencial ao agent_id e aos grants armazenados no servidor. Credenciais são individuais, expiram e podem ser revogadas. O caminho direto com SUPABASE_SERVICE_ROLE_KEY permanece legado e não deve ser descrito como equivalente em isolamento de identidade.

O worker é opt-in. A presença do código, migration ou variáveis de exemplo não prova que o worker esteja habilitado, provisionado ou ativo no deploy.

## 6. Inteligência e observabilidade

app/domain/intelligence define contratos normalizados; adaptadores em app/adapters/infrastructure/intelligence e os serviços de coleta integram fontes. As respostas devem preservar fonte, timestamp, proveniência e falhas parciais.

Distinguir:
- parser/adaptador implementado;
- coleta acionada sob demanda;
- persistência histórica;
- worker recorrente;
- dashboard/briefing;
- disponibilidade real da fonte externa.

Nenhum destes estados prova automaticamente os demais. Credenciais de fontes, limites, disponibilidade e termos de uso são externos ao código.

## 7. Clientes e comunicação

### Desktop
O desktop Windows inicia um núcleo local e uma interface WebView2. O listener, autenticação/pairing, firewall e transporte devem ser avaliados pelo runbook desktop. Não exponha portas locais à internet.

### Android
mobile/android é um aplicativo nativo separado. Serviços VPN, acessibilidade, observabilidade, shell e MCP dependem de permissões do Android, consentimento explícito, pareamento e estado do processo. O backend não pode presumir que a permissão foi concedida ou que o dispositivo está conectado.

### MCP
MCP é uma superfície de ferramentas. STDIO, HTTP local, túnel seguro e gateway privado são transportes distintos, com requisitos de host e autorização diferentes. Consulte os runbooks de navegação visual, acesso remoto e Secure MCP Tunnel.

## 8. Pipelines declarativos

app/runtime/pipeline_runner.py executa pipelines YAML. O formato legado continua presente; etapas com tool_id podem integrar o dispatcher. Não declarar migração total nem equivalência entre o runner legado e o toolbox novo sem validação específica.

## 9. Infraestrutura e dados

- PostgreSQL/Supabase: migrations, RLS, grants, RPCs e credenciais precisam ser verificados no projeto de destino.
- Render: o manifesto de deploy não comprova que o serviço esteja saudável ou implantado no commit atual.
- LLMs: adapters e roteadores não comprovam disponibilidade de credenciais, quota ou provider.
- Windows/Linux/Android: permissões do host e serviços externos são pré-requisitos operacionais.

## 10. Procedimento para manter a arquitetura

1. Antes de editar, consulte Graphify para localizar definições, callers, dependências e testes; se o índice estiver atrasado, confirme no branch alvo.
2. Mapeie o fluxo real desde o entrypoint até o adapter e o efeito persistido.
3. Preserve contratos e caminhos de compatibilidade ainda utilizados.
4. Adicione testes para comportamento, autorização, falha e regressão.
5. Atualize o documento do subsistema, o guia do agente e o README quando a mudança alterar arquitetura/uso.
6. Registre claramente o que foi implementado, testado e verificado em runtime.
