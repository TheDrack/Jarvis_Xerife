# Pacote app

O pacote app contém o núcleo Python do Jarvis Xerife. A árvore evoluiu além da estrutura original de assistente de voz; consulte docs/ARCHITECTURE.md para o mapa arquitetural completo.

## Estrutura

- core/: Nexus DI, configuração e composição.
- domain/: contratos e regras de domínio, incluindo tools, capabilities, intelligence, memory, context, graph, missions e orchestration.
- application/: casos de uso, serviços, portas, comunicação, segurança e privacidade.
- adapters/api/: adaptadores de entrada da API.
- adapters/edge/: integrações locais, desktop, host e dispositivos.
- adapters/infrastructure/: persistência, LLMs, provedores e serviços externos.
- runtime/: pipeline runner e runtime de ferramentas.
- multiagent/: contratos, scheduler, fila, transport e workers.
- communication/: componentes compartilhados de comunicação.
- static/: recursos web servidos pela aplicação.
- plugins/ e utils/: extensões e utilitários de suporte.

## Composição e entrypoints

O Nexus singleton em app.core.nexus é o mecanismo principal de resolução de componentes. app/container.py mantém wrappers de compatibilidade sobre o mesmo Nexus; não instancia um segundo container independente.

- main.py: inicialização principal combinada cloud/edge.
- serve.py: entrada headless/API.
- app/bootstrap_edge.py: inicialização local/edge com verificação de ambiente e setup wizard.

## Limites

A existência de um adapter ou service não garante credenciais, conexão, autorização ou saúde do serviço externo. Consulte o catálogo de capacidades e os testes do subsistema antes de declarar uma integração operacional.

- [Arquitetura](../docs/ARCHITECTURE.md)
- [Guia de agentes](../docs/AGENT_GUIDE.md)
- [Catálogo de capacidades](../docs/skills-connectors/CATALOG.md)
