# Portas de navegador

Macros JSON executadas no Chromium já aberto (CDP em `127.0.0.1:9222`), expostas como tools MCP.

## Duas vertentes

- **Visualização** (`portas_visualizacao.py`): `portas_listar`, `portas_descrever`, `portas_observar_aba`. Somente leitura, sempre liberada.
- **Utilização** (`portas_utilizacao.py`): `porta_<nome>`, uma por macro. Macros com `risco: "acao"` exigem `user_confirmed: true`.

## Regras

- Macro de `leitura` não pode conter `clicar` nem `digitar` (validado ao carregar).
- `goto` só para domínios em `dominios_permitidos`.
- Uma execução por vez e intervalo mínimo de 2 s por porta.
- Saídas retornam só o que a macro declara em `ler`. Cookies e tokens nunca são retornados.
- O servidor MCP continua em `stdio`, sem porta de rede. Nenhuma API HTTP é criada.

## Estado

- Implementado: núcleo, duas vertentes, macro de exemplo, testes unitários com fakes.
- Não verificado: execução real contra o Chromium; testes não executados neste commit.
- Pendente: a linha de registro `registrar_visualizacao_portas(...)` e `registrar_utilizacao_portas(...)` em `jarvis_desktop_mcp.py`, e a entrada em `CATALOG.md`.
