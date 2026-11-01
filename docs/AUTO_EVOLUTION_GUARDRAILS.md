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
- `EvolutionGatekeeper._check_test_count()` ainda precisa tratar falha de coleta,
  timeout, ausência do pytest, saída não reconhecida e código de retorno diferente
  de zero como estados não validados.
- O caminho de `EvolutionOrchestrator` faz uma verificação preliminar antes de
  receber o código do LLM; o caminho que aplica patches da memória procedural via
  `CrystallizerEngine` precisa de uma verificação vinculada ao código candidato.

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
