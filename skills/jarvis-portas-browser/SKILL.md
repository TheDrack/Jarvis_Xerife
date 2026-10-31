---
name: jarvis-portas-browser
description: Use Jarvis browser portas to inspect and run declarative macros on the user's already-open Chromium through CDP. Use for listing portas, auditing a porta before running it, observing the current tab, or running a porta with its risk rules.
---

# Jarvis Portas de Navegador

Portas são macros JSON com vocabulário fechado de passos (`goto`, `esperar`, `clicar`, `digitar`, `ler`), executadas no Chromium já aberto via CDP em `127.0.0.1:9222`. Elas ficam em `data/portas/macros/` e são expostas como tools MCP do `jarvis_desktop_mcp.py`.

## Duas vertentes

1. **Visualização (somente leitura, sempre liberada):**
   - `portas_listar`: lista o catálogo com nome, descrição, risco, parâmetros e domínios.
   - `portas_descrever(nome)`: mostra domínios e tipos de passo, para auditoria antes de usar.
   - `portas_observar_aba`: captura a aba atual sem navegar. Devolve a imagem.
2. **Utilização (executa):**
   - `porta_<nome>(params, user_confirmed)`: uma tool por macro.
   - Macros com `risco: "acao"` exigem `user_confirmed: true`. Sem isso, a tool devolve `confirmation_required`, e você deve pedir autorização ao usuário antes de repetir.
   - Macros `leitura` rodam sem confirmação adicional.

## Fluxo recomendado

1. Chame `portas_listar` para ver o que existe.
2. Chame `portas_descrever` na porta escolhida e confirme que os domínios e tipos de passo são os esperados.
3. Se a aba atual importa, use `portas_observar_aba` antes de agir.
4. Execute `porta_<nome>`. Para ações, peça confirmação explícita ao usuário com o nome da porta e os parâmetros.
5. Verifique a saída. Se houver erro (`domínio fora da lista`, `limite de taxa`, parâmetro ausente), pare e explique. Não contorne a regra.

## Regras de segurança

- Não crie macro de leitura com `clicar` ou `digitar`. O núcleo rejeita isso ao carregar.
- `goto` só funciona para domínios em `dominios_permitidos`.
- Saídas retornam apenas o que a macro declara em `ler`. Nunca tente obter cookies ou tokens.
- A porta CDP 9222 deve ficar em localhost e, de preferência, em perfil dedicado de automação.
- Só automatize sites onde o usuário tem conta ou permissão, e respeite os termos de cada um.

## Como adicionar uma porta

Crie `data/portas/macros/<nome>.json` com os campos `nome`, `descricao`, `risco` (`leitura` ou `acao`), `parametros`, `dominios_permitidos` e `passos`. Macros sem `risco` ou com passos desconhecidos são rejeitadas ao carregar. Adicione testes em `tests/adapters/edge/`.

## Limitações

- Não verificada contra Chromium real neste repo até o momento. Antes de confiar em uma porta, rode-a em ambiente de teste.
- Requer Chromium com `--remote-debugging-port=9222` e sessão interativa.
