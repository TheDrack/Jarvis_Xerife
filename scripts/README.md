# Scripts operacionais

Os scripts são ferramentas auxiliares de instalação, diagnóstico, manutenção, automação e execução. Não constituem um único daemon nem são todos iniciados automaticamente pelo processo principal.

## Inicialização e desktop

| Script | Finalidade |
|---|---|
| start_jarvis_desktop.ps1 | Iniciar a aplicação desktop local no Windows. |
| build_jarvis_desktop.ps1 | Construir o pacote Windows. |
| start-jarvis-boot.ps1 | Inicialização/boot no Windows; validar tarefas e ambiente antes de operar. |
| start-jarvis-mcp-interactive.ps1 | Iniciar o MCP interativo. |
| start_jarvis_tailscale.ps1 | Auxiliar a integração Tailscale. |
| setup_chatgpt_jarvis_tunnel.ps1 | Configurar/diagnosticar o Secure MCP Tunnel do usuário. |

## Multiagente e credenciais

| Script | Finalidade |
|---|---|
| run_multiagent_worker.py | Iniciar o worker multiagente opt-in. |
| check_multiagent_env.py | Validar presença de configuração e, opcionalmente, sondar a API. |
| manage_agent_worker_credentials.py | Provisionar/gerenciar credenciais individuais de worker. |

## Qualidade, arquitetura e manutenção

| Script | Finalidade |
|---|---|
| validate_architecture.py | Verificações de arquitetura. |
| autodoc.py | Gerar documentação/mapas derivados do código. |
| pr_manager.py | Operações auxiliares de gestão de PR. |
| repo_lifecycle_governance.py | Verificações de governança do ciclo de vida do repositório. |
| jarvis_healer.py | Fluxo de análise/recuperação de falhas de CI. |
| auto_fixer_logic.py | Lógica auxiliar de correção automática. |
| fix_applier.py | Aplicação/validação de correções. |
| capability_analyzer.py | Análise de capabilities. |
| capability_selector.py | Seleção de capabilities. |
| evolve_all_pending.py | Fluxo de evolução de itens pendentes. |
| publish_validated_evolution.py | Publicação de evolução validada. |

## Android e rede

- android/: ferramentas e scripts específicos de Android.
- network_inventory/: inventário de rede local e utilitários associados.
- send_mobile_notification.ps1: envio de notificação móvel.
- install_jarvis_return_activity.ps1: instalação do componente de retorno de atividade.

## Uso responsável

Antes de executar um script:
1. Leia o próprio código e os argumentos aceitos.
2. Confirme o diretório de trabalho, o ambiente e os efeitos colaterais.
3. Verifique se exige privilégios, credenciais, conexão ou dispositivo.
4. Use modo dry-run/diagnóstico quando disponível.
5. Não suponha que um script esteja ligado ao boot ou a um serviço apenas por existir.
6. Não exponha valores de segredos nos logs ou no terminal compartilhado.

A lista é um mapa dos scripts principais, não uma especificação completa de flags. A CLI do código é a fonte de verdade.
