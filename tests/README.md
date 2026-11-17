# Testes

A suíte usa pytest e está distribuída por subsistema. Não existe um único diretório de testes por camada: há testes de domínio, aplicação, adapters, runtime, segurança, contratos, scripts, integrações e regressões.

## Executar

```bash
python -m pytest -q
```

Execute primeiro o arquivo ou pacote relacionado à alteração. Depois rode os gates completos definidos pelos workflows ativos do GitHub Actions.

## Organização observada

- tests/application/: serviços e contratos da aplicação.
- tests/adapters/: adapters de API, edge e infraestrutura.
- tests/multiagent/: fila, workers, identidade e coordenação.
- tests/runtime/: runtime de ferramentas e toolchains.
- tests/security/: autenticação, autorização e isolamento.
- tests/scripts/: utilitários operacionais e scripts.
- tests/vision/: limites de dados e integrações de visão.
- arquivos tests/test_*.py: contratos e regressões transversais.

A árvore evolui continuamente; use o nome e o conteúdo dos testes presentes no branch, não esta lista como inventário exaustivo.

## Regras

- Testes de regressão são obrigatórios para correções de comportamento.
- Não desabilite testes válidos, não reduza cobertura e não altere expectativas apenas para fazer CI passar.
- Testes que exigem Docker, Android SDK, banco ou serviços externos devem declarar pré-requisitos.
- Resultado local não substitui os checks do PR; check verde não prova produção.
