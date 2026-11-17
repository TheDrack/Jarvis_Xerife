# Jarvis Xerife — guia de uso

Este guia apresenta as superfícies disponíveis no repositório e aponta para os runbooks específicos. A presença de código, skill ou manifest não significa que o recurso esteja configurado, conectado, autorizado ou ativo no ambiente atual.

## 1. Escolha a superfície

| Objetivo | Entrada / superfície | Referência |
|---|---|---|
| Inicialização combinada cloud/edge | main.py | README principal e docs/ARCHITECTURE.md |
| API headless | serve.py | app/application/services/serve.py |
| Execução local edge | app/bootstrap_edge.py | Configuração e permissões do host |
| Desktop Windows | scripts/start_jarvis_desktop.ps1 | desktop/README.md |
| MCP desktop local | app/adapters/edge/jarvis_desktop_mcp.py | Navegação visual e desktop README |
| Ponte JSONL para clientes remotos | jarvis_desktop_cli.py | desktop/README.md |
| Cliente Android | mobile/android/ | mobile/android/README.md |
| Worker multiagente | scripts/run_multiagent_worker.py | docs/MULTI_AGENT_USAGE.md |

Não trate API, desktop, Android, MCP e worker como um único processo. Cada superfície tem entrypoint, identidade, permissões e pré-requisitos próprios.

## 2. Preparar o ambiente Python

Use os grupos de dependências adequados ao alvo. O pacote base e os grupos edge/desktop/dev são separados para evitar instalar dependências de hardware em ambientes que não precisam delas.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip install -r requirements\edge.txt
```

No Linux, use o provisionador documentado em [linux/README.md](../linux/README.md). O provisionador Linux exige Python 3.10+ e systemd.

Use .env.example como referência e preencha somente as variáveis necessárias ao perfil. Não coloque segredos em prompts, documentação, logs ou commits.

## 3. Desktop Windows

O desktop requer Windows, sessão interativa do usuário e dependências de borda. Captura de tela, automação visual e UI Automation não funcionam necessariamente em um serviço headless ou na Session 0.

- Inicialização e build: [desktop/README.md](../desktop/README.md).
- Navegação visual: [NAVEGACAO_VISUAL.md](NAVEGACAO_VISUAL.md).
- CLI/bridge, MCP, autenticação e firewall: consulte o runbook desktop antes de expor qualquer listener.

Observe a tela/árvore de acessibilidade antes de interagir. Depois de cada ação, verifique a pós-condição. Não use coordenadas antigas sem recalibrar a janela, DPI, escala e viewport.

## 4. Android

O aplicativo Android é um cliente nativo. VPN, Accessibility Service, shell, notificações, captura e integração MCP dependem das permissões concedidas no próprio dispositivo, do pareamento e do estado dos serviços.

Consulte [mobile/android/README.md](../mobile/android/README.md) e os documentos Android em [docs/README.md](README.md). Não trate um dispositivo listado como conectado como prova de que shell ou acessibilidade estejam autorizados.

## 5. Acesso remoto e MCP

Transportes diferentes possuem fronteiras diferentes:

- MCP STDIO: processo local iniciado pelo cliente.
- Streamable HTTP em loopback: servidor local acessível apenas no host.
- Tailscale Serve: publicação privada dentro da tailnet.
- Aperture ou gateway: camada adicional de exposição e grants.
- Secure MCP Tunnel: rota oficial separada, com identidade e configuração próprias.

A rota RDC/Aperture/Tailscale e os scripts de boot são descritos em [docs/INSTALACAO_WINDOWS.md](INSTALACAO_WINDOWS.md) e [ACESSO_REMOTO_RDC_APERTURE_TAILSCALE.md](ACESSO_REMOTO_RDC_APERTURE_TAILSCALE.md). O Secure MCP Tunnel tem runbook próprio em [SECURE_MCP_TUNNEL.md](SECURE_MCP_TUNNEL.md).

Não exponha API/MCP em 0.0.0.0 ou na internet pública para contornar falhas de conexão. Verifique autenticação, allowlists Host/Origin, grants e ACLs da rede privada.

## 6. Ferramentas e conectores

O catálogo de manifests está em config/tool_registry.json. Os contratos ficam em app/domain/tools; o dispatcher em app/runtime/toolbox.

O manifest descreve ID, versão, schema, escopo e metadados. Não concede permissão. A execução exige principal, sessão e ToolAuthorizationPolicy confiável; sem essa política, o dispatcher deve falhar fechada.

Consulte:
- [Catálogo de skills e conectores](skills-connectors/CATALOG.md)
- [Inventário de capacidades](skills-connectors/CAPABILITY_INVENTORY.md)
- [Guardrails de segurança](../SECURITY_GUARDRAILS.md)

## 7. Multiagente

O runtime usa uma fila compartilhada e workers supervisionados; não é um conjunto de papéis fixos. Rotinas publicam tarefas e workers elegíveis reivindicam trabalho conforme prioridade, dependências, lease e grants.

O runtime é opt-in. Antes de iniciar, verifique migrations, backend, autenticação, token individual, provider de inferência e grants. Workers text_reasoning-only não devem receber tarefas que exigem ferramentas externas.

Runbooks:
- [Fila multiagente](MULTI_AGENT_PRIORITY_QUEUE.md)
- [Uso e configuração](MULTI_AGENT_USAGE.md)
- [Runtime e supervisão](multiagent-runtime.md)

## 8. Testes e diagnóstico

```bash
python -m pytest -q
```

Execute primeiro os testes do subsistema alterado e depois os gates exigidos pelos workflows do PR. Para Android, use o Gradle wrapper do projeto. Para Linux, use verify-jarvis-os.sh. Para deploy ou serviços externos, valide o ambiente real separadamente.

## 9. Regra de estado

Em relatórios e diagnósticos, separe:
1. implementado no código;
2. conectado/disponível no host;
3. autorizado;
4. testado;
5. verificado ponta a ponta;
6. confirmado em produção.

Nunca afirme que o Jarvis está integralmente operacional apenas porque a API responde, o MCP lista ferramentas ou o dispositivo aparece na rede.
