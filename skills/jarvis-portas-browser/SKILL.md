---
name: jarvis-portas-browser
description: Use Jarvis browser portas to inspect and run declarative macros and observe HTTP(S)/WebSocket traffic and opt-in binary media capture in the user's already-open Chromium through CDP.
---

# Jarvis Portas de Navegador

Portas são macros JSON com vocabulário fechado de passos (\`goto\`, \`esperar\`, \`clicar\`, \`digitar\`, \`ler\`), executadas no Chromium já aberto via CDP em \`127.0.0.1:9222\`. Elas ficam em \`data/portas/macros/\` e são expostas como tools MCP do \`jarvis_desktop_mcp.py\`.

## Duas vertentes

1. **Visualização (somente leitura, sempre liberada):**
   - \`portas_listar\`: lista o catálogo com nome, descrição, risco, parâmetros e domínios.
   - \`portas_descrever(nome)\`: mostra domínios e tipos de passo, para auditoria antes de usar.
   - \`portas_observar_aba\`: captura a aba atual sem navegar. Devolve a imagem.
2. **Utilização (executa):**
   - \`porta_<nome>(params, user_confirmed)\`: uma tool por macro.
   - Macros com \`risco: "acao"\` exigem \`user_confirmed: true\`. Sem isso, a tool devolve \`confirmation_required\`, e você deve pedir autorização ao usuário antes de repetir.
   - Macros \`leitura\` rodam sem confirmação adicional.

## Conexão CDP dinâmica

- Se o Chromium/agent-browser não estiver no \`127.0.0.1:9222\`, use \`portas_cdp_descobrir_agent_browser(session="default")\` para obter o WebSocket CDP da sessão e configurar o núcleo.
- Para um endpoint obtido por outro meio, use \`portas_cdp_configurar(url)\`. O endpoint precisa ser loopback; destinos CDP remotos são recusados.
- O mesmo endpoint é compartilhado pelas macros e pelo observador.

## Observabilidade HTTP(S) e WebSocket

- \`portas_trafego_iniciar(capturar_payloads=False)\` começa a capturar requisições, respostas, falhas e frames WebSocket em todas as abas dos contextos CDP anexados.
- \`portas_trafego_eventos(limit, after_id, host_contains)\` lê eventos em buffer limitado e permite polling incremental por ID.
- \`portas_trafego_status\` e \`portas_trafego_parar\` consultam e encerram a sessão sem fechar o navegador.
- Payloads ficam desabilitados por padrão. Habilite previews apenas quando necessário; valores de campos conhecidos como tokens/senhas/cookies são redigidos, mas não se deve presumir que toda informação sensível arbitrária seja detectável.
- A observação é do tráfego do Chromium anexado, não de toda a rede/IP da máquina. Tráfego de outros processos requer instrumentação própria.

## Captura de mídia binária (opt-in)

1. Inicie a observação com \`portas_trafego_iniciar(capturar_midia=True)\`. Se o observador já estiver ativo sem mídia, pare e reinicie com essa opção.
2. Consulte \`portas_media_eventos(limit)\` para localizar fluxos e obter \`stream_id\`, MIME, protocolo, status e contadores.
3. Leia \`portas_media_chunks(stream_id, after_sequence, limit)\` incrementalmente. Os bytes são Base64 e cada chunk inclui sequência, offset e timestamp.
4. Use \`next_after_sequence\` como cursor. Se \`gap=true\`, chunks anteriores já foram removidos do buffer limitado; não presuma continuidade sem recuperar/reiniciar a origem.
5. \`portas_trafego_status\` informa sessões CDP e chunks no buffer.

O capturador usa \`Network.streamResourceContent\`/ \`Network.dataReceived\` e mantém no máximo 128 chunks de 256 KiB (~32 MiB). A captura é volátil e pull-based. O consumidor precisa acompanhar o fluxo e implementar backpressure. UMP é identificado pelo MIME, mas não é decodificado por esta camada; demux, timestamps de mídia, PCM, frames de vídeo e reprodução ficam para adaptadores posteriores. Bytes protegidos por DRM/EME não são descriptografados nem têm seus controles contornados.

## Fluxo recomendado

1. Chame \`portas_listar\` para ver o que existe.
2. Chame \`portas_descrever\` na porta escolhida e confirme que os domínios e tipos de passo são os esperados.
3. Se a aba atual importa, use \`portas_observar_aba\` antes de agir.
4. Execute \`porta_<nome>\`. Para ações, peça confirmação explícita ao usuário com o nome da porta e os parâmetros.
5. Verifique a saída. Se houver erro (\`domínio fora da lista\`, \`limite de taxa\`, parâmetro ausente), pare e explique. Não contorne a regra.

## Regras de segurança

- Não crie macro de leitura com \`clicar\` ou \`digitar\`. O núcleo rejeita isso ao carregar.
- \`goto\` só aceita HTTP/HTTPS, sem credenciais embutidas, e respeita \`dominios_permitidos\`.
- Saídas retornam apenas o que a macro declara em \`ler\`. Nunca tente obter cookies ou tokens.
- A porta CDP 9222 deve ficar em localhost e, de preferência, em perfil dedicado de automação.
- Só automatize sites onde o usuário tem conta ou permissão, e respeite os termos de cada um.

## Como adicionar uma porta

Crie \`data/portas/macros/<nome>.json\` com os campos \`nome\`, \`descricao\`, \`risco\` (\`leitura\` ou \`acao\`), \`parametros\`, \`dominios_permitidos\` e \`passos\`. Macros sem \`risco\` ou com passos desconhecidos são rejeitadas ao carregar. Adicione testes em \`tests/adapters/edge/\`.

## Limitações

- Ainda requer validação ponta a ponta em Chromium real para o tipo de resposta/protocolo específico.
- O capturador não interpreta o enquadramento UMP nem decodifica áudio/vídeo; é apenas a camada de aquisição de bytes.
- Requer Chromium com \`--remote-debugging-port=9222\` e sessão interativa.
