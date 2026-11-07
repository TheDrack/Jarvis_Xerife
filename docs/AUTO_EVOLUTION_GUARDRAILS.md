# Guardrails da autoevolução

## Gatekeeper obrigatório

O fluxo de geração de código do `JarvisDevAgent` só pode avançar quando o
`EvolutionGatekeeper` estiver registrado no Nexus e aprovar a proposta.

A ausência do Gatekeeper é uma condição de bloqueio, não um modo de desenvolvimento
com aprovação automática. O agente deve preservar a proposta como rejeitada e não
criar uma PR a partir desse ciclo.

## Fronteira de validação de candidato — evidência na main

Na revisão da `main` em `82ca2ac`, o caminho usado pelo
`EvolutionOrchestrator` já não é um diretório temporário tratado como sandbox.
O `EvolutionSandbox.test_proposal()`:

1. exige código candidato e um `target_file` explícito;
2. valida o caminho dentro do checkout e exige um arquivo Python existente;
3. cria um snapshot em memória do repositório, substituindo o conteúdo do alvo pelo
   candidato antes de executar os testes;
4. envia o snapshot por stdin para um container Docker descartável, sem bind mount
   do checkout nem Docker socket;
5. executa `pytest tests/` dentro de `/workspace`, no snapshot que contém o
   candidato, e verifica o código de saída.

O container é iniciado com:

- `--network none`;
- root filesystem somente leitura;
- capabilities removidas e `no-new-privileges`;
- UID/GID não-root `65532:65532`;
- limites de CPU, memória, PIDs e tempo;
- tmpfs restrito para workspace e temporários;
- ambiente limpo: o processo Docker recebe somente `PATH` (e `SYSTEMROOT` no
  Windows); o container recebe apenas `HOME` e `TMPDIR` adicionais.

O snapshot exclui diretórios e arquivos locais conhecidos, incluindo `.git`,
`.venv`, `.env`, `.gh-token`, bancos locais e logs. Isso não substitui um
scanner geral de segredos: conteúdo sensível que tenha sido commitado em arquivos
com nomes comuns ainda pode entrar no snapshot e deve ser tratado como risco de
higiene do repositório.

### Testes que comprovam o contrato

- `tests/test_evolution_sandbox.py`: valida substituição do alvo no arquivo tar,
  exclusão de estado local, rejeição de caminhos inválidos e execução hardened.
- `tests/test_evolution_sandbox_docker_integration.py`: com a imagem CI real,
  verifica que o teste importa o candidato aplicado, que arquivo/segredos do host
  não estão acessíveis e que a conexão de rede externa falha.
- `.github/workflows/jarvis-pr-validation.yml`: constrói a imagem
  `Dockerfile.evolution-sandbox` e executa a suíte completa de pytest.

O adapter `DockerSandbox` em `app/adapters/infrastructure/docker_sandbox.py`
continua sem consumidor comprovado; ele não deve ser confundido com o caminho
efetivo, que é `EvolutionGatekeeper → EvolutionSandbox`.

## Publicação confiável

A evolução agendada separa os domínios de confiança:

- **Geração/validação:** recebe somente a credencial do provider. O candidato é
  validado no Docker e exportado como artefato fora do checkout.
- **Publicação:** job separado recebe o token GitHub, verifica schema, digest
  SHA-256, commit de origem, target e diff staged exato. Escreve somente o arquivo
  validado e abre uma PR. Não importa, executa nem testa o candidato.

O job de publicação não executa código gerado. A suíte de CI volta a executar na
PR. Falha de sandbox, artefato inválido, alvo stale/protegido ou diff adicional
bloqueiam a publicação.

## Limites ainda pendentes

1. **Seleção roadmap-driven:** na `main` em `82ca2ac`, o workflow agendado ainda
   usa o selector legado e não encontra `target_file` confiável. O resultado é
   bloqueio/no-op antes da chamada ao LLM. A PR #775 substitui a seleção pelo
   `RoadmapMissionSelector`; ela está aberta e seu manifesto permanece vazio,
   portanto ainda não habilita geração.
2. **Proteção do control plane:** a política da `main` protege prefixos críticos.
   A PR #775 acrescenta proteção explícita de arquivos do selector, orchestrator,
   gatekeeper, sandbox, candidate runner e publisher; isso ainda não está na
   `main` até merge/revisão.
3. **Cobertura de todos os escritores:** o sandbox valida o caminho
   `EvolutionOrchestrator → EvolutionGatekeeper`. Outros escritores, como
   `CrystallizerEngine` e ferramentas administrativas, precisam continuar
   sujeitos à mesma política de path e auditoria. Não inferir que toda mutação do
   repositório passa pelo sandbox apenas porque esse fluxo está isolado.
4. **Host Docker e conteúdo versionado:** o daemon Docker continua sendo parte da
   base confiável do runner. O snapshot não é submetido a um secret scanner geral;
   segredos commitados fora dos nomes excluídos são um risco residual.
5. **Branch protection:** a `main` ainda está sem proteção e sem required checks
   segundo a API observada. A correção administrativa está registrada na issue #682.

## Critérios de operação

- Não habilitar uma missão sem mapeamento revisado para um alvo Python existente,
  testes específicos, dependências, risco e resultado esperado.
- Não inferir caminho a partir da saída do LLM.
- Não conceder credenciais de publicação ao executor do candidato.
- Não desabilitar testes, enfraquecer gates, fazer commit direto em `main`, merge
  ou deploy automático.
- Manter a correção automática de PRs/Self Healing como mecanismo transversal,
  independente do roadmap cognitivo.

A fronteira Docker de candidato está implementada e testada em CI; a seleção
roadmap-driven, a proteção de branch e a comprovação de todos os escritores
permanecem pendentes. Uma PR aberta ou um teste isolado não conclui C0.
