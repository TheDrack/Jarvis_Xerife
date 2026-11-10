# Jarvis OS — instalação Linux

Este diretório entrega o **kit verificável** para rodar o Jarvis em Linux: provisionamento idempotente, units systemd de usuário, verificação pós-instalação e o runbook da instalação física. Nada aqui formata disco, instala bootloader ou altera o Windows — esses passos são humanos, presenciais e gated pelo inventário abaixo.

## 1. Inventário verificado desta máquina (2026-11-09)

Leitura somente (`Get-Disk`, `Get-Partition`, `Get-Volume`, `Get-CimInstance Win32_DiskDrive`):

| Disco | Modelo / serial | Capacidade | Layout | Conteúdo |
|---|---|---|---|---|
| 0 | ADATA SU650 — `2N2329AC7D2E` | 223,6 GB | GPT: EFI 100 MB, MSR 16 MB, **D: 222,6 GB NTFS**, Recovery 866 MB | instalação Windows completa (`Windows`, `Program Files`, `Users`, `ProgramData`) |
| 1 | YON-S280-120GB — `W2023100900314` | 111,8 GB | GPT: EFI 100 MB, MSR, **C: 111,2 GB NTFS**, Recovery 512 MB | Windows **em execução** (`$env:SystemDrive = C:`), 0,2 GB livres |

Máquina: ASRock H510M-HVS R2.0, AMI BIOS P1.50, x64. Boot atual: `C:` (disco 1).

**Consequência direta:** `D:` não é um disco de dados. É uma segunda instalação Windows, inicializável, com `pagefile.sys` e `hiberfil.sys` **em uso pelo Windows atual**. Não é possível apagá-la de dentro do Windows em execução, e apagá-la descarta essa instalação inteira.

## 2. Regra de governança que vale aqui

O próprio repositório já fixou o caminho:

- `docs/JARVIS_OS_FOUNDATION.md`: *"Do not format, repartition, install a bootloader to, or write an OS image to a physical disk until its model/serial/capacity and target partitions have been verified explicitly"* e *"Never overwrite the current workstation disk during prototype testing"*.
- `docs/architecture/JARVIS_CONTINUAL_LEARNING.md`: *"The first Linux validation remains a disposable VM; the physical SSD install is a later, explicitly verified operation"* e *"Never select a disk by drive letter alone"*.

O inventário acima atende a primeira condição. A segunda — validação em VM descartável — ainda **não** foi executada. Por isso a ordem é: **VM primeiro, disco físico depois, com autorização explícita**.

## 3. O que este kit faz

| Item | Função |
|---|---|
| `provision-jarvis-os.sh` | pacotes, venv, dependências (core + host + Linux), arquivo de ambiente 0600, units systemd de usuário, opcionalmente XFCE, Playwright, Tailscale e UFW |
| `verify-jarvis-os.sh` | checagens read-only: venv, imports, permissões do env, units, loopback 8765, subconjunto de testes |
| `requirements-linux.txt` | espelho de `requirements/edge.txt` sem `pywinauto` (Windows-only) |
| `systemd/*.service` | `jarvis-api` (serve.py) e `jarvis-mcp` (loopback 8765), com `NoNewPrivileges` |
| este README | inventário, rota VM, runbook físico e critérios de aceitação |

O script **não** instala modelo local, não baixa chaves, não autentica Tailscale e não muda firewall sem `--harden-network`.

## 4. Rota A — validação em VM descartável (obrigatória antes do físico)

Base recomendada: **Ubuntu Server 24.04 LTS**, 4 vCPU, 8 GB RAM, 60 GB de disco virtual. Sem GPU; o Jarvis não exige uma.

```bash
# dentro da VM, como usuário normal
sudo apt-get update && sudo apt-get install -y git curl
git clone https://github.com/TheDrack/Jarvis_Xerife.git ~/Jarvis_Xerife
cd ~/Jarvis_Xerife
linux/provision-jarvis-os.sh --with-dev --with-mcp --start
linux/verify-jarvis-os.sh --services --tests
```

O que a VM precisa provar antes de qualquer passo físico:

1. `verify-jarvis-os.sh --services --tests` sai com código 0.
2. `serve.py` responde em `127.0.0.1` e reinicia sozinho (`systemctl --user restart jarvis-api`, journal sem traceback).
3. `jarvis-mcp` escuta apenas em loopback 8765 e uma chamada `tools/list` autenticada/host-validada funciona; Host/Origin estranhos são recusados.
4. `osint.ip.enrich` persiste em `JARVIS_GRAPH_DB` e `osint.graph.explain(edge_id=...)` resolve a aresta (teste de fumaça real, sem rede de saída, usando store temporário).
5. Reinício da VM: unidades voltam (com `loginctl enable-linger`), Tailscale reconecta se usado.
6. Sessão gráfica (XFCE) sobe e as ferramentas de visão/entrada operam sob X11/XWayland — ou o relatório declara explicitamente que não operam.

Alternativa rápida só para o harness (não substitui a VM para host/desktop): `wsl --install -d Ubuntu-24.04` no Windows atual, com o repositório em `/mnt/c/...` e o mesmo provisionamento. WSL não valida boot, GRUB, driver, sessão gráfica real nem recuperação.

## 5. Rota B — instalação física no disco 0 (somente após a Rota A)

Pré-requisitos humanos, todos verificáveis:

- [ ] Rota A concluída com evidência colada no PR/issue.
- [ ] Confirmado que nada em `D:` é necessário (hoje: uma instalação Windows inteira). **Sem backup possível em `C:` (0,2 GB livres).**
- [ ] BitLocker do volume `D:` checado (`manage-bde -status D:`, como administrador) e suspenso se ativo.
- [ ] Hibernação e pagefile do Windows **antigo** desligados antes (`powercfg /h off`, pagefile sem `D:`), com reboot — senão o volume permanece travado.
- [ ] Pendrive ≥ 8 GB com Ubuntu Server 24.04 LTS verificado (SHA-256 publicado).
- [ ] Modo UEFI confirmado no firmware e ordem de boot anotada.

Layout proposto (mantém o Windows do disco 1 intacto):

```text
Disco 0 (ADATA, serial 2N2329AC7D2E)
  p1 EFI      100 MB  → preservar (GRUB)
  p2 MSR       16 MB  → preservar
  p3 (era D:)  ~214 GB → apagar, criar ext4 / (~206 GB) + swap 8 GB
  p4 Recovery 866 MB  → apagar, virar /home (ou deixar livre)
```

Runbook, executado por você na sessão live do Ubuntu (não pelo agente):

```bash
# 1. Identificar o disco pelo SERIAL, nunca pela letra
lsblk -o NAME,SIZE,MODEL,SERIAL,FSTYPE,MOUNTPOINTS
sudo sgdisk -p /dev/sdX   # confirme: 223.6G, ADATA SU650, 2N2329AC7D2E

# 2. Apagar SOMENTE as partições 3 e 4 do disco 0 (D: e Recovery)
sudo sgdisk -d 4 -d 3 /dev/sdX

# 3. Instalador do Ubuntu → "Manual partitioning":
#    p1 EFI (manter, montar /boot/efi), p2 MSR (não tocar),
#    espaço livre → ext4 / e swap 8 GB
#    Bootloader: no disco 0 (o ESP p1 dele)

# 4. Após instalar, manter o Windows do disco 1 bootável
sudo apt-get install -y os-prober
sudo sed -i 's/^#\?GRUB_DISABLE_OS_PROBER=.*/GRUB_DISABLE_OS_PROBER=false/' /etc/default/grub
sudo update-grub
efibootmgr -v   # devem existir "ubuntu" e "Windows Boot Manager"
```

Critérios de rollback: se o GRUB não listar o Windows do disco 1, ajustar a ordem em `efibootmgr`/firmware antes de qualquer outro passo; o disco 1 não é tocado em nenhum momento.

## 6. Provisionamento e operação

```bash
linux/provision-jarvis-os.sh --help
linux/provision-jarvis-os.sh --with-dev --with-mcp --with-desktop --start
linux/verify-jarvis-os.sh --services --tests
```

- Ambiente: `~/.config/jarvis/jarvis.env` (diretório 0700, arquivo 0600). Preencha as chaves de provedor **ali**, nunca em chat, commit ou unit.
- Dados: `~/.local/share/jarvis/` (diretório 0700; `JARVIS_DEVICES_DB`, `JARVIS_GEOINT_DB`, `JARVIS_GRAPH_DB`).
- Serviços de usuário; para sobreviver ao logout: `sudo loginctl enable-linger $USER`.
- MCP Linux usa `jarvis_linux_mcp`: loopback + autenticação obrigatória `Authorization: Bearer`. O provisionador gera `JARVIS_DESKTOP_AUTH_TOKEN` aleatório quando `--with-mcp` é usado e o guarda no arquivo 0600. Configure esse token no cliente MCP; nunca o imprima em logs, chat ou commit.
- Host/Origin allowlists continuam ativos. Para Tailscale Serve, inclua explicitamente o hostname privado nos allowlists e configure o cliente com o bearer token. Nunca use Funnel nem `0.0.0.0`.
- `--harden-network` é opt-in porque muda firewall; sem ele, nada de rede é alterado. Quando ativado, SSH (TCP/22) e demais entradas são permitidos apenas pela interface `tailscale0`; não há regra SSH global em interfaces públicas.

## 7. Gaps de portabilidade Linux conhecidos

Estes pontos **não** estão cobertos e precisam de evidência na VM:

| Área | Situação |
|---|---|
| `pywinauto`, `background_window_input` (win32), ETW | Windows-only; excluídos de `requirements-linux.txt` |
| `app/adapters/edge/jarvis_desktop_local.py` | app desktop nativo Windows (Tk/edge); não é o alvo Linux |
| `app/adapters/infrastructure/vision_adapter.py` | tem ramo Linux, depende de sessão X11/XWayland |
| Overlay/cursor do agente (`jarvis_agent_status`) | usa Win32; sem equivalente Linux |
| `scripts/*.ps1` | supervisores PowerShell; as units systemd substituem apenas o ciclo de vida |
| Áudio/voz | `espeak-ng`, `flac`, PortAudio instalados; qualidade e dispositivo exigem teste |

Nenhum desses itens deve ser declarado funcional em Linux sem a checagem correspondente na VM.

## 8. Critérios de aceitação

- [ ] Rota A com `verify-jarvis-os.sh --services --tests` em código 0.
- [ ] Reinício real da VM com serviços de volta e journal limpo.
- [ ] `jarvis-mcp` só em loopback; Host/Origin inválidos recusados.
- [ ] Persistência do grafo + `edge_id` funcionando no Linux.
- [ ] Inventário físico reconferido (serial/capacidade) imediatamente antes da Rota B.
- [ ] Rota B só com autorização explícita e backup/renúncia registrada.
