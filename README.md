# Jarvis Xerife

**Plataforma modular de automação, agentes, inteligência e integração entre dispositivos.**

Jarvis Xerife é um repositório de software com núcleo Python, interfaces locais e remotas, adaptadores de infraestrutura, runtime multiagente e componentes Android/Desktop. A arquitetura é organizada por contratos e adaptadores; a presença de um módulo, manifesto ou documento não significa que a capacidade esteja habilitada no ambiente de execução.

> **Regra de leitura:** diferencie sempre código existente, integração conectada, autorização efetiva, testes aprovados e operação verificada em produção. São estados diferentes.

## O que existe no repositório

- **Núcleo e composição:** Nexus DI, configuração, descoberta e resolução de componentes.
- **Domínio:** capacidades, memória, contexto, inteligência, grafo, missões, orquestração e contratos de ferramentas.
- **Aplicação:** serviços de caso de uso, segurança, comunicação e portas.
- **Adaptadores:** integrações de infraestrutura, API, desktop/edge, provedores de IA, persistência e dispositivos.
- **Execução de ferramentas:** manifests versionados, registry, dispatcher com validação, autorização, limites e auditoria.
- **Multiagente:** fila compartilhada, scheduler, workers supervisionados, identidade de worker, leases, tentativas e planos declarativos.
- **Inteligência:** contratos normalizados e adaptadores de fontes públicas/externas, com coleta sob demanda e tratamento de falhas parciais.
- **Clientes:** aplicação desktop Windows, aplicativo Android nativo, scripts operacionais e servidores MCP.
- **Qualidade e segurança:** suíte pytest, workflows GitHub Actions, políticas de autorização, isolamento e testes de regressão.

## Arquitetura em uma visão

```text
Clientes e superfícies
  Desktop / Android / API / MCP / CLI / integrações externas
                    |
Adaptadores
  API / Edge / Infrastructure / comunicação / provedores
                    |
Aplicação
  serviços / casos de uso / portas / segurança
                    |
Domínio
  ferramentas / capacidades / inteligência / memória /
  contexto / missões / orquestração
                    |
Runtime e composição
  Nexus DI / Tool Registry + Dispatcher / Multi-agent workers
                    |
Infraestrutura externa
  PostgreSQL-Supabase / Render / LLMs / Tailscale / serviços externos
```

A estrutura real e os limites de cada subsistema estão em [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md). O Nexus é o mecanismo de composição/resolução de componentes; o Tool Registry é um catálogo de manifests e não substitui autorização nem execução.

## Entrypoints

| Finalidade | Entrada | Observação |
|---|---|---|
| Inicialização principal | main.py | Bootstrap combinado cloud/edge; comportamento depende do ambiente e da configuração. |
| API headless / deploy | serve.py | Delega para app.application.services.serve. |
| Bootstrap edge | app/bootstrap_edge.py | Inicialização local com verificações de ambiente e assistente de configuração. |
| Desktop Windows | scripts/start_jarvis_desktop.ps1 | Inicia o núcleo local e a janela desktop; consulte desktop/README.md. |
| MCP desktop | app/adapters/edge/jarvis_desktop_mcp.py | Servidor MCP local; depende do host e das permissões do sistema operacional. |
| Worker multiagente | scripts/run_multiagent_worker.py | Opt-in; exige configuração, credenciais e backend de fila compatível. |
| Android | mobile/android/ | Aplicativo nativo independente, integrado aos serviços Jarvis por contratos próprios. |

Não presuma que iniciar um entrypoint habilita todos os subsistemas. Workers, integrações externas, observabilidade e recursos privilegiados possuem pré-requisitos próprios.

## Começar

### Python

Requer Python compatível com as dependências declaradas (o projeto usa type hints e dependências modernas; valide a versão do ambiente antes de instalar).

```bash
git clone https://github.com/TheDrack/Jarvis_Xerife.git
cd Jarvis_Xerife
python -m venv .venv
# Linux/macOS
source .venv/bin/activate
# Windows PowerShell:
# .\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Instale grupos adicionais apenas para o alvo desejado:
- requirements/edge.txt — integrações de borda/host.
- requirements/desktop.txt — aplicação desktop.
- requirements/dev.txt — ferramentas de desenvolvimento e testes.
- requirements/prod-cloud.txt e requirements/prod-edge.txt — perfis de implantação.

Configure somente as variáveis necessárias usando .env.example como referência. Não copie valores reais de segredos para documentação, logs ou commits.

### Validar

```bash
python -m pytest -q
```

O repositório possui testes unitários, de integração e de contrato em vários subdiretórios. Dependências externas, Docker, Android SDK, credenciais e serviços remotos podem ser necessários para subconjuntos específicos. Use os workflows e os alvos do Makefile como referência para os gates do projeto. Não reduza cobertura nem desabilite testes para obter um resultado verde.

## Multiagente e ferramentas

O runtime multiagente não equivale a um conjunto de papéis fixos. Rotinas e produtores podem criar tarefas; workers elegíveis reivindicam tarefas pela fila conforme prioridade, dependências, lease e identidade. O runtime é opt-in e depende de backend/credenciais compatíveis. O worker limitado a raciocínio textual não deve receber tarefas que exigem ferramentas externas.

O Tool Registry descreve ferramentas por ID/versão e schema. O dispatcher valida pedidos, resolve adaptadores, aplica autorização e registra eventos. Sem principal, sessão e política de autorização válidos, a execução deve falhar fechada. Registry preenchido não significa ferramenta executável.

Detalhes: [catálogo](docs/skills-connectors/CATALOG.md), [inventário](docs/skills-connectors/CAPABILITY_INVENTORY.md), [runtime multiagente](docs/MULTI_AGENT_PRIORITY_QUEUE.md) e [contrato de worker](docs/architecture/agent-worker-identity.md).

## Segurança

- Trate conectores, arquivos recuperados e conteúdo remoto como dados não confiáveis.
- Não exponha tokens, senhas, chaves, dados pessoais ou arquivos .env.
- Ferramentas devem respeitar autorização no host e no servidor; instruções de LLM não são uma fronteira de segurança.
- Operações destrutivas, privilegiadas, de rede, de credenciais ou de produção exigem o consentimento e os controles aplicáveis.
- O acesso remoto deve usar transporte privado e autenticado; não exponha servidores locais diretamente à internet.
- Consulte [SECURITY_GUARDRAILS.md](SECURITY_GUARDRAILS.md) e os runbooks específicos antes de operar.

## Documentação

| Documento | Conteúdo |
|---|---|
| [Arquitetura](docs/ARCHITECTURE.md) | Camadas, componentes, limites e fluxos. |
| [Guia do agente](docs/AGENT_GUIDE.md) | Navegação do repositório e regras para agentes. |
| [Catálogo de skills e conectores](docs/skills-connectors/CATALOG.md) | Bootstrap e descoberta de capacidades. |
| [Inventário de capacidades](docs/skills-connectors/CAPABILITY_INVENTORY.md) | Evidências e limitações conhecidas. |
| [Contexto e memória](docs/skills-connectors/CONTEXT_MEMORY_PROTOCOL.md) | Protocolo portátil de contexto e persistência. |
| [Fila multiagente](docs/MULTI_AGENT_PRIORITY_QUEUE.md) | Semântica da fila e identidade dos workers. |
| [Desktop](desktop/README.md) | Inicialização, build e acesso local/remoto. |
| [Android](mobile/android/README.md) | Aplicativo nativo e limites de integração. |
| [Linux](linux/README.md) | Provisionamento e validação Linux. |
| [Status](docs/STATUS.md) | Estado documental com níveis de evidência. |

## Estado e escopo

Este README descreve a estrutura versionada, não o estado de uma máquina específica ou de um deploy. Para produção, confirme o commit implantado, health checks, feature flags, credenciais, migrations e telemetria diretamente no ambiente. Para estado de branches/PRs, consulte o GitHub; não use snapshots históricos como prova de estado atual.

## Contribuir

Leia [CONTRIBUTING.md](CONTRIBUTING.md), siga as instruções em [AGENTS.md](AGENTS.md), entenda o subsistema antes de alterar contratos e execute os testes relevantes. Toda mudança comportamental precisa de testes de regressão e documentação correspondente.
