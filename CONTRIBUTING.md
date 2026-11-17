# Contribuir com Jarvis Xerife

Este repositório contém múltiplos runtimes e clientes. Antes de alterar um componente, identifique seu contrato, consumidores, permissões e testes.

## Ambiente

Use uma versão de Python compatível com os requisitos do projeto e crie um ambiente virtual:

```bash
git clone https://github.com/TheDrack/Jarvis_Xerife.git
cd Jarvis_Xerife
python -m venv .venv
```

Ative o ambiente e instale os grupos necessários ao trabalho:

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install -r requirements/dev.txt
```

Para desktop, edge ou produção, instale também o arquivo específico em requirements/. Não instale dependências de todos os alvos indiscriminadamente.

Use .env.example como referência. Configure apenas os serviços necessários e nunca adicione segredos reais ao repositório.

## Fluxo de desenvolvimento

1. Leia AGENTS.md e as instruções específicas do subsistema.
2. Consulte Graphify antes de grep: localize definições, callers, dependências, impacto e testes relacionados. Confirme a atualidade do índice em relação ao branch.
3. Leia contratos, adapters, configurações e testes existentes.
4. Escreva primeiro um teste que reproduza o comportamento esperado ou o bug.
5. Faça a menor alteração coerente com a arquitetura e preserve compatibilidade necessária.
6. Execute testes focados e depois os gates aplicáveis.
7. Atualize a documentação do subsistema e os índices quando contratos, configuração, entrypoints ou comportamento mudarem.
8. Revise diff, segredos, migrations e efeitos colaterais antes de abrir PR.

## Testes

```bash
python -m pytest -q
```

Para um ciclo rápido, execute o módulo/arquivo de teste relevante antes da suíte completa. Use os workflows GitHub Actions ativos como autoridade para os gates de CI; não presuma que um comando make exista sem verificar o Makefile.

Para alterações em Android, use o Gradle wrapper do projeto para os testes unitários e build debug. Para Docker, integração de banco ou provider externo, documente pré-requisitos e se o teste foi executado ou apenas inspecionado.

Não:
- remova ou marque testes válidos como skipped para obter CI verde;
- reduza metas de cobertura;
- simule resultado de provider como se fosse runtime real;
- declare migrations aplicadas sem consultar o banco de destino.

## Padrões de implementação

- Preserve separação entre domínio, aplicação e adaptadores quando o subsistema a adotar.
- Use contratos tipados e validação explícita nas fronteiras.
- Mantenha identidade/autorização fora do prompt e do modelo.
- Falhe fechadamente quando política, principal ou grant estiver ausente.
- Não misture credenciais com manifests ou telemetria.
- Adicione testes para sucesso, falha, autorização negada, entradas inválidas e concorrência quando aplicável.
- Não faça chamadas de rede ou efeitos de produção em testes unitários.

## Pull requests

A PR deve incluir:
- objetivo e contexto;
- resumo do comportamento alterado;
- arquivos/contratos impactados;
- testes executados e resultados reais;
- migrations/configuração necessárias;
- riscos, rollout e rollback;
- evidência de CI.

Mantenha a PR focada. Não misture refatoração ampla com mudança funcional sem justificativa. Não faça merge enquanto os checks exigidos estiverem pendentes ou falhando.

## Documentação

Atualize README quando mudar o uso geral ou a superfície pública; docs/ARCHITECTURE.md quando mudar camadas/fluxos; docs/AGENT_GUIDE.md quando mudar navegação/contratos de trabalho; e o runbook do subsistema quando mudar instalação/operação. Marque claramente estado implementado, testado, runtime-verificado e planejado.
