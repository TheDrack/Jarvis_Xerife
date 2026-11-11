# Portas de navegador

Macros JSON e observabilidade HTTP(S)/WebSocket no Chromium já aberto via CDP local (por padrão \`127.0.0.1:9222\`, ou endpoint WS dinâmico do agent-browser), expostas como tools MCP.

## Duas vertentes

- **Visualização** (\`portas_visualizacao.py\`): \`portas_listar\`, \`portas_descrever\`, \`portas_observar_aba\`. Somente leitura, sempre liberada.
- **Utilização** (\`portas_utilizacao.py\`): \`porta_<nome>\`, uma por macro. Macros com \`risco: "acao"\` exigem \`user_confirmed: true\`.

## Conexão CDP

- Por padrão, o núcleo tenta \`http://127.0.0.1:9222\`.
- Para sessões agent-browser, chame \`portas_cdp_descobrir_agent_browser(session)\`; o endpoint \`ws://127.0.0.1:<porta>/devtools/browser/...\` é descoberto e configurado automaticamente.
- \`portas_cdp_configurar(url)\` aceita endpoint HTTP(S)/WS(S) somente em loopback. Endpoints CDP remotos são recusados.

## Observabilidade HTTP(S) e WebSocket

- \`portas_trafego_iniciar\` conecta ao Chromium por CDP e observa requisições/respostas/finalizações/falhas HTTP(S) em todos os contextos e frames WebSocket nas abas anexadas.
- \`portas_trafego_eventos\` consulta o buffer incremental, com filtro por host e cursor \`after_id\`.
- \`portas_trafego_status\` informa estado e quantidade de abas; \`portas_trafego_parar\` desconecta sem fechar o Chromium.
- \`portas_trafego_limpar\` limpa o buffer em memória.
- Captura de payloads fica desligada por padrão. Quando habilitada explicitamente, previews são limitados e campos sensíveis conhecidos são redigidos. Cookies, headers de autenticação e corpos HTTP não são armazenados.

## Captura binária de mídia

- Para capturar mídia, inicie explicitamente com \`portas_trafego_iniciar(capturar_midia=True)\`. A opção é independente de \`capturar_payloads\`.
- O observador anexa sessões CDP por aba, habilita \`Network.streamResourceContent\` e recebe os bytes entregues pelo Chromium em eventos \`Network.dataReceived\`. Isso captura respostas reconhecidas por MIME de áudio/vídeo, HLS, DASH e \`application/vnd.yt-ump\`, inclusive endpoints que declaram o MIME em um parâmetro de URL.
- \`portas_media_eventos\` lista os fluxos identificados e metadados sanitizados. \`portas_media_chunks(stream_id, after_sequence, limit)\` entrega os bytes em Base64, com sequência, offset e timestamp, para o player/consumidor autorizado.
- O buffer é volátil e limitado a 128 chunks de até 256 KiB (máximo aproximado de 32 MiB no total). Um consumidor que atrasar além da janela recebe \`gap=true\` e \`first_available_sequence\`; precisa reiniciar a leitura ou aceitar a perda indicada.
- \`protocol="ump"\` apenas identifica o tipo de transporte anunciado. O conteúdo UMP não é desmontado nem interpretado nesta camada. O adaptador preserva bytes; demux, sincronização, decodificação e renderização são camadas posteriores.
- A captura é pull-based pelo MCP, não uma transmissão push. O consumidor deve consultar os chunks incrementalmente e aplicar backpressure. O suporte real depende da versão do Chromium/CDP e do protocolo da origem; falhas de \`Network.streamResourceContent\` são reportadas no estado do fluxo.
- A captura não descriptografa conteúdo protegido, não contorna DRM/EME e não remove controles de acesso. Fluxos criptografados permanecem criptografados.
- O observador não persiste mídia em disco. Parar a captura desconecta CDP, mas mantém os chunks já capturados até limpar ou iniciar nova sessão.

## Regras

- Macro de \`leitura\` não pode conter \`clicar\` nem \`digitar\` (validado ao carregar).
- \`goto\` só aceita \`http\`/\`https\`, sem credenciais embutidas, e apenas domínios em \`dominios_permitidos\`.
- Uma execução por vez e intervalo mínimo de 2 s por porta.
- Saídas retornam só o que a macro declara em \`ler\`. Cookies e tokens nunca são retornados.
- O servidor MCP continua em \`stdio\`, sem porta de rede. Nenhuma API HTTP é criada.
- Playwright é dependência de runtime declarada em \`requirements/edge.txt\`.

## Estado

- Implementado: núcleo, visualização, utilização, observador HTTP(S)/WebSocket, captura binária opt-in via CDP, tools MCP de consulta incremental, macros, skill e registro MCP.
- Testes unitários: sanitização/redação, classificação de mídia, preservação de bytes, paginação e limites de buffer.
- Pendente: validação ponta a ponta em Chromium real para respostas HTTP/2/HTTP/3, captura de áudio/vídeo real, integração do consumidor com o player visual da aplicação e validação no perfil Chromium real do usuário.
