# Guardrails da autoevolução

## Gatekeeper obrigatório

O fluxo de geração de código do `JarvisDevAgent` só pode avançar quando o
`EvolutionGatekeeper` estiver registrado no Nexus e aprovar a proposta.

A ausência do Gatekeeper é uma condição de bloqueio, não um modo de desenvolvimento
com aprovação automática. O agente deve preservar a proposta como rejeitada e não
criar uma PR a partir desse ciclo.

## Limites atuais — não confundir aprovação com isolamento

A proteção do Gatekeeper e o `EvolutionSandbox` ainda não constituem uma fronteira
de execução isolada:

- `EvolutionSandbox.test_proposal()` grava o texto recebido em `proposal.py`,
  mas não aplica a proposta ao arquivo-alvo copiado.
- A execução de pytest ocorre com o diretório de trabalho na raiz original do
  repositório, não dentro do diretório temporário.
- Portanto, `passed=true` demonstra apenas que a sintaxe foi aceita e que a suíte
  do checkout atual passou; não demonstra que o código proposto foi exercitado.
- `EvolutionGatekeeper._check_test_count()` agora exige código de saída zero
  e uma contagem positiva reconhecida; timeout, ausência do pytest, exceções, código
  diferente de zero e saída vazia/não reconhecida bloqueiam a proposta sem alterar
  o baseline anterior.
- O caminho de `EvolutionOrchestrator` faz uma verificação preliminar antes de
  receber o código do LLM; os patches da memória procedural ainda precisam de
  validação vinculada ao código candidato, mesmo com a proteção de caminho do
  `CrystallizerEngine`.

### Proteção de caminhos de escrita

`app/application/security/repository_path_policy.py` centraliza a política usada pelo
`EvolutionGatekeeper` e pelo `CrystallizerEngine`. Ela rejeita caminhos absolutos,
drives/UNC, `..`, aliases de nomes do Windows, escapes por symlink, diretórios
`.frozen` e prefixos protegidos (`app/core`, `capabilities`, capabilities de domínio,
adapters de infraestrutura e segurança). O `CrystallizerEngine` também rejeita
componentes symlink antes da escrita e revalida o destino após criar os diretórios.

Esse controle restringe o destino da escrita; não contém execução de código, não
remove credenciais do ambiente e não elimina a janela de corrida entre validação e
escrita. Portanto, não substitui container/VM efêmero nem os critérios de isolamento
listados abaixo.

Até esses pontos serem resolvidos, não declarar que a autoevolução de código possui
sandbox real ou validação completa da proposta. A criação de PR para revisão humana
não substitui a validação técnica.

## Critérios para habilitar aplicação autônoma de código

1. O código candidato precisa ser aplicado a uma cópia descartável do projeto.
2. A execução deve ocorrer em container/VM efêmero com filesystem, rede, processos e
   recursos limitados; o runner privilegiado não pode compartilhar credenciais.
3. Os testes devem executar sobre a cópia que contém a proposta aplicada.
4. Coleta de testes e execução precisam ter códigos de saída verificados; timeout,
   ausência de ferramenta e saída não reconhecida devem falhar de forma explícita.
5. Todos os caminhos de aplicação, inclusive Crystallizer e memória procedural,
   precisam passar pelo mesmo contrato de autorização.
6. A publicação permanece em branch/PR separada, com CI e revisão humana; nenhum
   Gatekeeper deve fazer merge ou deploy.

## Escopo desta alteração

Esta alteração fecha somente o fallback de aprovação automática quando o
`EvolutionGatekeeper` não está disponível no `JarvisDevAgent`. Ela não declara
resolvidos os limites listados acima e não altera capabilities, credenciais,
serviços externos ou dispositivos.
