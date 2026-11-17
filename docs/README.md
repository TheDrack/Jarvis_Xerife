# Índice da documentação

Este índice aponta para os documentos mantidos no repositório. Documentos de arquitetura e contratos descrevem o código; runbooks descrevem procedimentos; auditorias e relatórios datados registram observações históricas. Nenhum documento isolado prova disponibilidade em produção.

## Comece por aqui

1. [README principal](../README.md) — propósito, instalação e superfícies.
2. [Arquitetura](ARCHITECTURE.md) — camadas, diretórios, limites e fluxos.
3. [Guia de agentes](AGENT_GUIDE.md) — bootstrap, navegação e regras de trabalho.
4. [Status](STATUS.md) — estados de implementação e evidência.
5. [Segurança](../SECURITY_GUARDRAILS.md) — invariantes de autorização e proteção.

## Contratos para agentes

- [Catálogo de skills e conectores](skills-connectors/CATALOG.md)
- [Inventário de capacidades](skills-connectors/CAPABILITY_INVENTORY.md)
- [Protocolo de contexto e memória](skills-connectors/CONTEXT_MEMORY_PROTOCOL.md)
- [Harness Freebuff](skills-connectors/FREEBUFF_HARNESS.md)
- [Host operations](skills-connectors/HOST_OPS.md)
- [Startup prompt](skills-connectors/STARTUP_PROMPT.md)

## Arquitetura e execução

- [Nexus](NEXUS.md)
- [Pipeline runner](PIPELINE_RUNNER.md)
- [Runtime multiagente](multiagent-runtime.md)
- [Fila dinâmica multiagente](MULTI_AGENT_PRIORITY_QUEUE.md)
- [Uso multiagente](MULTI_AGENT_USAGE.md)
- [Universal communication layer](communication/UNIVERSAL_COMMUNICATION_LAYER.md)
- [Universal toolbox](architecture/universal-toolbox.md)
- [Universal intelligence](architecture/jarvis-universal-intelligence.md)
- [Identidade de worker](architecture/agent-worker-identity.md)
- [Execution plans](architecture/declarative-execution-plans.md)

## Desktop, Android e rede

- [Desktop](../desktop/README.md)
- [Android nativo](../mobile/android/README.md)
- [Android network intelligence](ANDROID_NETWORK_INTELLIGENCE.md)
- [Navegação visual](NAVEGACAO_VISUAL.md)
- [Acesso remoto RDC / Aperture / Tailscale](ACESSO_REMOTO_RDC_APERTURE_TAILSCALE.md)
- [Secure MCP Tunnel](SECURE_MCP_TUNNEL.md)
- [Android access levels](ANDROID_ACCESS_LEVELS_AND_NETWORK_DISCOVERY.md)
- [Dynamic VPN telemetry](ANDROID_DYNAMIC_VPN_TELEMETRY.md)

## Instalação e operação

- [Instalação Windows](INSTALACAO_WINDOWS.md)
- [Pós-instalação e VIV](POS_INSTALACAO.md)
- [Jarvis OS foundation](JARVIS_OS_FOUNDATION.md)
- [Linux provisioning](../linux/README.md)
- [Host resource diagnostics](HOST_RESOURCE_DIAGNOSTICS.md)
- [Host storage diagnostics](HOST_STORAGE_DIAGNOSTICS.md)
- [Portas Browser](PORTAS_BROWSER.md)

## Segurança, governança e auditorias

- [Guardrails de segurança](../SECURITY_GUARDRAILS.md)
- [Sessões remotas efêmeras](security/EPHEMERAL_REMOTE_SESSIONS.md)
- [Auditoria de recuperação distribuída](AUDITORIA_RECUPERACAO_DISTRIBUIDA.md)
- [Auditoria do ledger de migrations](SUPABASE_MIGRATION_LEDGER_AUDIT.md)
- [Verificação de entregas](VERIFICACAO_ENTREGAS.md)

## Referência histórica e pesquisa

Documentos com termos como audit, status, roadmap, progress, proposal, draft, RFC, recovery ou data no título podem registrar um recorte histórico ou uma proposta. Leia a data, o commit e a seção de escopo antes de tratar seu conteúdo como estado atual. Mantenha conclusões históricas como histórico; corrija apenas quando uma revalidação substituir a evidência.
