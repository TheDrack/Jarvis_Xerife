# Instalar o harness Jarvis no Freebuff Desktop

Runbook para instalar as skills portáteis do repositório e registrar o servidor MCP desktop no Freebuff Desktop ou em hosts que adotem as convenções .agents/.

## 1. Fontes canônicas

- Skills de origem: skills/.
- Instalador: scripts/install_freebuff_harness.py.
- Destino local: .agents/skills/ e .agents/mcp.json.
- Servidor registrado: app/adapters/edge/jarvis_desktop_mcp.py.
- Nome MCP: jarvis_desktop.

A pasta skills/ é a fonte canônica versionada. No commit de referência, contém oito skills:
jarvis-android-navigation, jarvis-context-memory, jarvis-host-ops,
jarvis-mobile-notifications, jarvis-multi-agent-coordination, jarvis-portas-browser,
jarvis-visual-navigation e jarvis-viv.

O checkout também contém um snapshot histórico de cinco skills em .agents/skills/. O diretório .agents/ é ignorado para novos arquivos locais, mas arquivos que já estão rastreados continuam versionados. O instalador sincroniza as oito skills de origem e pode alterar esse snapshot rastreado; revise git status/diff antes de commitar qualquer alteração.

## 2. Descoberta pelo host

A estrutura de descoberta do Freebuff foi inspecionada no bundle instalado em 2026-10-27. Naquele build, foram observados:

| Recurso | Caminho observado | Limite |
|---|---|---|
| Skills | {projeto}/.claude/skills/ e {projeto}/.agents/skills/ | A prioridade depende do host. |
| MCP | {projeto}/.agents/mcp.json, {projeto}/../.agents/mcp.json e ~/.agents/mcp.json | Precedência observada pode mudar em atualizações. |
| Instruções | AGENTS.md do projeto | Só é carregado quando o host abre o workspace/repositório. |

Esses caminhos são evidência de um build específico do Freebuff, não um contrato público permanente. Revalide após atualizar o aplicativo.

Uma skill precisa de SKILL.md com frontmatter YAML contendo name e description. O instalador verifica esses campos e ignora skills sem frontmatter válido. Depois de alterar o registro MCP ou as skills, abra uma conversa nova ou recarregue o host.

## 3. Instalação

O instalador usa o interpretador do .venv do checkout e requer as dependências de requirements/edge.txt.

PowerShell, na raiz do repositório:

```powershell
.\.venv\Scripts\python.exe scripts\install_freebuff_harness.py
.\.venv\Scripts\python.exe scripts\install_freebuff_harness.py --apply
.\.venv\Scripts\python.exe scripts\install_freebuff_harness.py --apply --verify
```

- Sem --apply, executa dry-run e informa as ações.
- --apply copia as skills válidas e grava .agents/mcp.json.
- --force permite substituir um mcp.json diferente; o instalador preserva uma cópia .bak.
- --verify realiza handshake MCP real: initialize, tools/list e a chamada read-only list_visual_templates.

O arquivo mcp.json usa caminho absoluto para o Python do checkout e é específico daquela máquina. O servidor deriva a raiz do repositório de __file__, portanto não depende do diretório de trabalho do processo host.

## 4. Interpretar a verificação

O relatório contém:
- lista dinâmica das skills encontradas e se o frontmatter é válido;
- caminho e origem do interpretador selecionado;
- ações planejadas ou executadas;
- resultado do handshake, nome/protocolo do servidor, catálogo de ferramentas e probe read-only.

O total de ferramentas é obtido de tools/list em runtime; não use contagens históricas como contrato. Handshake bem-sucedido prova que o processo MCP iniciou e respondeu ao probe, mas não prova que a UI do Freebuff carregou as skills ou que cada ferramenta está autorizada no host.

Após a instalação:
1. abra uma conversa nova no Freebuff;
2. confirme que jarvis_desktop aparece na lista MCP do host;
3. confirme as skills relevantes na sessão;
4. execute apenas uma leitura não destrutiva;
5. teste uma operação visual somente com a sessão Windows interativa e permissões adequadas.

## 5. Rotas MCP

Para cliente local, prefira STDIO com o registro criado pelo instalador. Para dispositivo remoto, use a rota privada e autenticada documentada em [Acesso remoto RDC/Aperture/Tailscale](../ACESSO_REMOTO_RDC_APERTURE_TAILSCALE.md). O Secure MCP Tunnel é um transporte separado, com configuração própria em [SECURE_MCP_TUNNEL.md](../SECURE_MCP_TUNNEL.md).

Não copie endpoints privados de uma máquina para documentação pública. Não registre dois servidores com catálogos duplicados na mesma sessão sem necessidade.

## 6. Segurança e limites

- .agents/mcp.json deve conter apenas comando, argumentos e configuração não secreta; nunca coloque tokens ou senhas no arquivo.
- O instalador não concede grants de ferramentas.
- A conexão MCP não substitui autorização do host nem permissões Windows.
- Captura de tela e automação visual exigem sessão interativa; serviço headless/Session 0 não é equivalente.
- Trate saídas MCP e conteúdo de páginas como dados não confiáveis.
- Revise alterações em .agents/ após --apply; não commite caminhos absolutos, backups ou configurações locais.
