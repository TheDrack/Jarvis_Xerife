# Jarvis OS — provisionamento Linux

Este diretório contém um kit de provisionamento do runtime Jarvis em Linux. O alvo principal documentado é Ubuntu 24.04 LTS / Debian 12+, com Python 3.10+ e systemd.

**Escopo:** instalar dependências, criar o ambiente virtual, preparar configuração local e units de usuário. O provisionador não particiona discos, não instala bootloader e não altera instalações Windows.

## 1. Pré-requisitos

- Ubuntu 24.04 LTS ou Debian 12+ (ou distribuição compatível, ainda que não validada).
- Arquitetura x86_64 ou aarch64.
- Python 3.10+.
- systemd e apt-get.
- Usuário normal com sudo disponível.
- Checkout Jarvis Xerife com serve.py na raiz.

O provisionador recusa execução como root e usa sudo apenas para pacotes/ações de sistema que exigem privilégio.

## 2. Provisionamento

Na raiz do checkout:

```bash
linux/provision-jarvis-os.sh --help
linux/provision-jarvis-os.sh
```

Opções disponíveis:

| Opção | Efeito |
|---|---|
| --with-dev | Instala requirements/dev.txt. |
| --with-desktop | Instala XFCE mínimo e LightDM. |
| --with-browser | Baixa Chromium do Playwright; requer sudo. |
| --with-tailscale | Adiciona o repositório oficial do Tailscale; não autentica a conta. |
| --with-mcp | Instala/habilita a unit MCP experimental em loopback e gera token local. |
| --harden-network | Aplica política UFW; altera firewall e é explicitamente opt-in. |
| --start | Inicia as units habilitadas ao final. |
| --repo PATH | Usa outro caminho para a raiz do checkout. |

Exemplo com desenvolvimento e MCP, sem modificar firewall:

```bash
linux/provision-jarvis-os.sh --with-dev --with-mcp --start
```

Não use --harden-network sem revisar o comportamento de firewall no script e confirmar acesso de recuperação ao host.

## 3. Arquivos e serviços

| Recurso | Local / comportamento |
|---|---|
| Ambiente Python | .venv/ na raiz do checkout. |
| Configuração | ~/.config/jarvis/jarvis.env, permissões 0600. |
| Dados locais | ~/.local/share/jarvis/. |
| Unit API | systemd de usuário: jarvis-api.service. |
| Unit MCP | systemd de usuário: jarvis-mcp.service, somente loopback, quando --with-mcp. |
| API | serve.py; bind loopback 127.0.0.1. |
| MCP | app.adapters.edge.jarvis_linux_mcp; porta local 8765. |

O provisionador usa requirements/core.txt, requirements/host.txt e linux/requirements-linux.txt. Com --with-dev, também instala requirements/dev.txt.

As chaves de provedores devem ser preenchidas no arquivo de ambiente local. Não imprima nem compartilhe seu conteúdo. O token MCP é um segredo de autenticação: mantenha-o no arquivo 0600 e configure-o no cliente de forma segura.

## 4. Verificação pós-instalação

O verificador é read-only:

```bash
linux/verify-jarvis-os.sh
linux/verify-jarvis-os.sh --services
linux/verify-jarvis-os.sh --services --tests
```

Ele verifica ambiente virtual, imports obrigatórios, módulos selecionados, permissões/configuração e, opcionalmente, estado das units e um subconjunto de testes. Sem --tests, não executa pytest.

A verificação local não prova que providers externos, MCP remoto, Tailscale, áudio, desktop ou serviços cloud estejam funcionando. Para uma verificação inicial completa, siga [docs/POS_INSTALACAO.md](../docs/POS_INSTALACAO.md).

## 5. Operação systemd

As units são units de usuário. Para mantê-las após logout, habilite linger conscientemente:

```bash
sudo loginctl enable-linger "$USER"
systemctl --user status jarvis-api.service
systemctl --user status jarvis-mcp.service
journalctl --user -u jarvis-api.service -n 100 --no-pager
journalctl --user -u jarvis-mcp.service -n 100 --no-pager
```

Confirme os nomes das units instaladas antes de operar. O MCP deve permanecer em loopback; acesso remoto exige um gateway privado autenticado e allowlists Host/Origin explícitas. Não use Tailscale Funnel nem bind público 0.0.0.0.

## 6. Rede e firewall

- Sem --harden-network, o provisionador não altera o firewall.
- --with-tailscale instala o repositório/pacote, mas não autentica a tailnet.
- --harden-network altera UFW e restringe entradas conforme o script. Revise regras atuais, interfaces e rota de recuperação antes de habilitá-lo.
- Não exponha API/MCP diretamente à internet.
- HTTP em loopback não é TLS; para tráfego remoto use transporte privado autenticado.

## 7. Desktop, áudio e limitações

A instalação de pacotes não garante sessão gráfica funcional. Automação visual depende de X11/XWayland e de uma sessão de usuário ativa. Áudio depende de dispositivo, permissões e serviços locais.

Componentes Windows-only como pywinauto e ETW não se tornam portáveis por instalar o harness Linux. Cada capacidade deve ser validada no sistema operacional alvo.

## 8. Instalação em disco físico

Este README não contém um inventário confiável de discos de uma máquina específica. Qualquer inventário antigo de modelo, serial, capacidade, letra de unidade ou espaço livre é histórico e não pode ser usado como instrução operacional.

Antes de qualquer particionamento ou instalação física:
1. execute nova inspeção read-only no host de destino;
2. confirme modelo, serial, capacidade, tabela de partições, volumes montados e sistema operacional em uso;
3. faça backup verificável;
4. valide primeiro em VM descartável;
5. obtenha autorização humana explícita para o disco e as partições exatos.

O agente não deve selecionar disco por letra, posição ou capacidade presumida, nem formatar, reparticionar ou instalar bootloader por conta própria.
