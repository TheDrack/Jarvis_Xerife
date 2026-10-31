# Portas de navegador

Macros JSON e observabilidade HTTP(S)/WebSocket no Chromium já aberto (CDP em `127.0.0.1:9222`), expostas como tools MCP.

## Duas vertentes

- **Visualização** (`portas_visualizacao.py`): `portas_listar`, `portas_descrever`, `portas_observar_aba`. Somente leitura, sempre liberada.
- **Utilização** (`portas_utilizacao.py`): `porta_<nome>`, uma por macro. Macros com `risco: "acao"` exigem `user_confirmed: true`.

## Observabilidade de tráfego

- `portas_trafego_iniciar` conecta ao Chromium por CDP e observa requisições/respostas/falhas HTTP(S) em todos os contextos e frames WebSocket nas abas anexadas.
- `portas_trafego_eventos` consulta o buffer incremental, com filtro por host e cursor `after_id`.
- `portas_trafego_status` informa estado e quantidade de abas; `portas_trafego_parar` desconecta sem fechar o Chromium.
- `portas_trafego_limpar` limpa o buffer em memória.
- Captura de payloads fica desligada por padrão. Quando habilitada explicitamente, previews são limitados e campos sensíveis conhecidos são redigidos. Cookies, headers de autenticação e corpos HTTP não são armazenados.

## Regras

- Macro de `leitura` não pode conter `clicar` nem `digitar` (validado ao carregar).
- `goto` só aceita `http`/`https`, sem credenciais embutidas, e apenas domínios em `dominios_permitidos`.
- Uma execução por vez e intervalo mínimo de 2 s por porta.
- Saídas retornam só o que a macro declara em `ler`. Cookies e tokens nunca são retornados.
- O servidor MCP continua em `stdio`, sem porta de rede. Nenhuma API HTTP é criada.
- Playwright é dependência de runtime declarada em `requirements/edge.txt`.

## Estado

- Implementado: núcleo, visualização, utilização, observador HTTP(S)/WebSocket, macros, skill e registro MCP.
- Testado: testes unitários de sanitização/redação e teste de integração de captura HTTP via Chromium/CDP no CI.
- Pendente: teste de frames WebSocket ponta a ponta via CDP no CI e validação no perfil Chromium real do usuário.
